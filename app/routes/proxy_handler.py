"""
app/routes/proxy_handler.py
-----------------------------
HTTP/HTTPS proxy request handler.

This module handles the actual forwarding of requests to upstream targets.
No authentication is required — authenticated users configure proxies via
proxy_manager.py; anyone can use a running proxy by its URL.

Delivery modes
--------------
Endpoint  — Flask routes at /proxy/<slug>  and /proxy/<slug>/<path:path>
Subdomain — Before-request hook: checks Host header for <slug>.localhost,
            then forwards if a matching running proxy exists.
            Modern OSes resolve *.localhost → 127.0.0.1 (RFC 6761).

Lifecycle states
----------------
status='running' → requests are forwarded to target_url
status='stopped' → 503 Service Unavailable is returned immediately
"""

import logging
import time

import requests as http
from flask import Blueprint, Response, abort, request, stream_with_context
from requests.exceptions import ConnectionError as ReqConnError, Timeout as ReqTimeout

from app import db
from app.models.proxy import ProxyConfig
from app.models.proxy_log import ProxyLog

logger = logging.getLogger(__name__)

proxy_handler_bp = Blueprint("proxy_handler", __name__)

# Headers that must not be forwarded (hop-by-hop per RFC 7230 §6.1)
_HOP_BY_HOP_REQUEST = frozenset({
    "host", "content-length", "transfer-encoding", "connection",
    "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "upgrade",
})

# Headers that must not be copied from the upstream response.
# NOTE: content-encoding is intentionally excluded here — it is handled
# explicitly in _forward because requests auto-decompresses the body, which
# means both the header and the content-length must be invalidated together.
_HOP_BY_HOP_RESPONSE = frozenset({
    "transfer-encoding", "connection", "keep-alive", "proxy-connection",
})


# ── Logging helper ────────────────────────────────────────────────────────────

def _client_ip() -> str:
    """Return the real client IP, respecting X-Forwarded-For if present."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first address (the originating client)
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _write_log(proxy: ProxyConfig, status_code: int | None, duration_ms: int | None) -> None:
    """Persist a ProxyLog row. Silently swallows DB errors to never break the proxy."""
    try:
        entry = ProxyLog(
            proxy_id    = proxy.id,
            method      = request.method,
            path        = request.full_path.rstrip("?"),
            status_code = status_code,
            client_ip   = _client_ip(),
            duration_ms = duration_ms,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:  # noqa: BLE001
        db.session.rollback()
        logger.exception("Failed to write proxy log for proxy %s", proxy.slug)


# ── Core forwarding logic ──────────────────────────────────────────────────────

def _stopped_response() -> Response:
    return Response(
        "<h1 style='font-family:sans-serif'>503 — Proxy Stopped</h1>"
        "<p style='font-family:sans-serif'>This proxy is currently stopped by its owner.</p>",
        status=503,
        content_type="text/html",
    )


def _resolve_cors_origin(proxy: ProxyConfig) -> str:
    """
    Return the value for Access-Control-Allow-Origin.

    If the proxy's allowed origins list contains *, returns * unconditionally.
    Otherwise, reflects the incoming Origin header if it appears in the list,
    or returns 'null' (which causes browsers to block the request) if not.
    """
    origins = proxy.cors_origins_list()
    if not origins or "*" in origins:
        return "*"
    incoming = request.headers.get("Origin", "")
    if incoming and incoming in origins:
        return incoming
    return "null"  # no match — browser CORS policy will reject the response


def _options_preflight(proxy: ProxyConfig) -> Response:
    """Return an immediate 200 for CORS preflight OPTIONS requests."""
    resp = Response(status=200)
    if proxy.cors_bypass:
        origin_val = _resolve_cors_origin(proxy)
        resp.headers["Access-Control-Allow-Origin"]  = origin_val
        resp.headers["Access-Control-Allow-Headers"] = "*"
        resp.headers["Access-Control-Allow-Methods"] = proxy.allowed_methods
        if origin_val != "*":
            resp.headers["Vary"] = "Origin"
    return resp


def _build_target_url(proxy: ProxyConfig, path: str) -> str:
    """Join proxy.target_url with the forwarded path and query string.

    Strips any trailing slash from the base so that a path like 'api/v1'
    never produces a double-slash URL regardless of how target_url was saved.
    """
    base = proxy.target_url.rstrip("/")
    target = f"{base}/{path}" if path else base
    if request.query_string:
        target += "?" + request.query_string.decode("utf-8", errors="replace")
    return target


def _forward(proxy: ProxyConfig, path: str) -> Response:
    """Forward the current Flask request to the upstream target and stream
    the response back.  Supports any content type, binary payloads, and
    large file downloads without buffering the entire body in memory.

    Args:
        proxy: The active ProxyConfig record.
        path:  Relative path to append to the target URL (may be empty).

    Returns:
        Streaming Flask Response mirroring the upstream reply.
    """
    if not proxy.is_running:
        return _stopped_response()

    target = _build_target_url(proxy, path)

    # Build forwarded headers — strip hop-by-hop, optionally inject extras
    headers = {
        k: v
        for k, v in request.headers
        if k.lower() not in _HOP_BY_HOP_REQUEST
    }
    if proxy.skip_ngrok_warning:
        headers["ngrok-skip-browser-warning"] = "true"

    # Send to the upstream server — stream=True means the response body is
    # not downloaded until we iterate over it, keeping memory usage flat.
    t_start = time.monotonic()
    try:
        upstream = http.request(
            method=request.method,
            url=target,
            headers=headers,
            data=request.get_data(),
            cookies=request.cookies,
            allow_redirects=False,
            timeout=30,
            stream=True,
        )
    except ReqConnError:
        logger.warning("Proxy %s: connection refused to %s", proxy.slug, target)
        _write_log(proxy, 502, None)
        return Response(
            "<h1 style='font-family:sans-serif'>502 — Bad Gateway</h1>"
            "<p style='font-family:sans-serif'>Could not connect to the target server.</p>",
            status=502,
            content_type="text/html",
        )
    except ReqTimeout:
        logger.warning("Proxy %s: timeout reaching %s", proxy.slug, target)
        _write_log(proxy, 504, None)
        return Response(
            "<h1 style='font-family:sans-serif'>504 — Gateway Timeout</h1>"
            "<p style='font-family:sans-serif'>The target server did not respond in time.</p>",
            status=504,
            content_type="text/html",
        )

    # Time-to-first-byte — headers are available now; body is still streaming
    duration = int((time.monotonic() - t_start) * 1000)
    _write_log(proxy, upstream.status_code, duration)

    # Build response headers.
    # content-encoding is handled explicitly: the requests library automatically
    # decompresses gzip/deflate/br content when iterating, so the header is now
    # stale.  We drop it and also drop content-length (which reflected the
    # *compressed* size).  Werkzeug will use chunked transfer for the decoded
    # stream instead.
    resp_headers = {}
    had_content_encoding = False
    for name, value in upstream.headers.items():
        lower = name.lower()
        if lower == "content-encoding":
            had_content_encoding = True
            continue  # decoded by requests — header is no longer valid
        if lower in _HOP_BY_HOP_RESPONSE:
            continue
        resp_headers[name] = value

    if had_content_encoding:
        # Remove stale compressed length; chunked encoding takes over
        resp_headers.pop("Content-Length", None)
        resp_headers.pop("content-length", None)

    # Apply CORS bypass
    if proxy.cors_bypass:
        origin_val = _resolve_cors_origin(proxy)
        resp_headers["Access-Control-Allow-Origin"]  = origin_val
        resp_headers["Access-Control-Allow-Headers"] = "*"
        resp_headers["Access-Control-Allow-Methods"] = proxy.allowed_methods
        if origin_val != "*":
            resp_headers["Vary"] = "Origin"

    def _stream_body():
        for chunk in upstream.iter_content(chunk_size=16 * 1024):
            yield chunk

    return Response(
        stream_with_context(_stream_body()),
        status=upstream.status_code,
        headers=resp_headers,
    )


# ── Endpoint mode routes ───────────────────────────────────────────────────────

_PROXY_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]


@proxy_handler_bp.route(
    "/proxy/<slug>",
    defaults={"path": ""},
    methods=_PROXY_METHODS,
    strict_slashes=False,
)
@proxy_handler_bp.route(
    "/proxy/<slug>/<path:path>",
    methods=_PROXY_METHODS,
    strict_slashes=False,
)
def endpoint_proxy(slug: str, path: str) -> Response:
    """Handle endpoint-mode proxy requests at /proxy/<slug>/[path]."""
    proxy = ProxyConfig.query.filter_by(
        slug=slug,
        proxy_type=ProxyConfig.TYPE_ENDPOINT,
    ).first()

    if not proxy:
        abort(404)

    if request.method == "OPTIONS":
        return _options_preflight(proxy)

    # Block methods not enabled for this proxy
    if request.method not in proxy.allowed_methods_list():
        _write_log(proxy, 405, None)
        return Response(
            f"<h1 style='font-family:sans-serif'>405 \u2014 Method Not Allowed</h1>"
            f"<p style='font-family:sans-serif'>This proxy does not allow {request.method} requests.</p>",
            status=405,
            content_type="text/html",
        )

    return _forward(proxy, path)


# ── Subdomain mode — before_request hook ──────────────────────────────────────

def handle_subdomain_proxy():
    """
    Before-request hook that intercepts subdomain-mode proxy requests.

    When the Host header is '<slug>.localhost[:<port>]', this function looks
    up a running subdomain proxy with that slug and forwards the request.
    Returning None allows normal Flask routing to proceed.

    Registration: app.before_request(handle_subdomain_proxy) in the factory.

    Subdomain resolution note
    -------------------------
    Modern operating systems resolve *.localhost to 127.0.0.1 automatically
    (RFC 6761 §6.3), so no hosts-file changes are required on macOS 13+,
    Windows 11, and most Linux distributions with systemd-resolved.
    """
    host     = request.host             # e.g. 'swift-ray-a3f9.localhost:5000'
    hostname = host.split(":")[0]       # strip port → 'swift-ray-a3f9.localhost'
    parts    = hostname.rsplit(".", 1)  # ['swift-ray-a3f9', 'localhost']

    # Only intercept <something>.localhost patterns
    if len(parts) != 2 or parts[1] != "localhost":
        return None

    slug = parts[0]

    # Skip reserved slugs — prevents interfering with the app's own paths
    if slug in ProxyConfig.RESERVED_SLUGS:
        return None

    proxy = ProxyConfig.query.filter_by(
        slug=slug,
        proxy_type=ProxyConfig.TYPE_SUBDOMAIN,
    ).first()

    if not proxy:
        return None  # not a registered proxy; fall through to normal routing

    path = request.path.lstrip("/")

    if request.method == "OPTIONS":
        return _options_preflight(proxy)

    if request.method not in proxy.allowed_methods_list():
        _write_log(proxy, 405, None)
        return Response(
            f"<h1 style='font-family:sans-serif'>405 \u2014 Method Not Allowed</h1>"
            f"<p style='font-family:sans-serif'>This proxy does not allow {request.method} requests.</p>",
            status=405,
            content_type="text/html",
        )

    return _forward(proxy, path)
