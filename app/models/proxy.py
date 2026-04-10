"""
app/models/proxy.py
--------------------
ProxyConfig ORM model — stores HTTP/HTTPS proxy service configurations
managed by authenticated users.

Each proxy can be delivered via two modes:
  - endpoint  : /proxy/<slug>/<path>   (served by the Bridger app itself)
  - subdomain : <slug>.localhost:<port> (via Host-header routing middleware)
"""

import secrets
import string
from datetime import datetime

from app import db


# ── Slug generation helpers ────────────────────────────────────────────────────

_ADJECTIVES = [
    "swift", "bright", "calm", "dark", "fast", "green", "hot",
    "icy", "jade", "keen", "lean", "mist", "nova", "open", "pink",
    "quiet", "red", "sky", "teal", "blue", "gray", "gold", "silver",
    "bold", "crisp", "deep", "flat", "kind", "low", "prime", "warm",
]

_NOUNS = [
    "fox", "ray", "hub", "net", "arc", "dot", "key",
    "link", "node", "path", "port", "gate", "beam", "wave",
    "core", "edge", "mesh", "wire", "pipe", "pulse", "sync",
]


def _generate_slug() -> str:
    """
    Generate a human-readable random slug in the form 'adjective-noun-xxxx'.
    e.g., 'swift-ray-a3f9'
    """
    charset = string.digits + "abcdef"
    suffix = "".join(secrets.choice(charset) for _ in range(4))
    adj  = secrets.choice(_ADJECTIVES)
    noun = secrets.choice(_NOUNS)
    return f"{adj}-{noun}-{suffix}"


# ── Model ──────────────────────────────────────────────────────────────────────

class ProxyConfig(db.Model):
    """
    Represents a single user-managed HTTP/HTTPS proxy configuration.

    Delivery modes
    --------------
    endpoint  — Requests forwarded at /proxy/<slug>/[path] by the Bridger app.
    subdomain — Requests forwarded when the Host header is <slug>.localhost.
                Requires the client to resolve <slug>.localhost (modern OSes
                resolve *.localhost to 127.0.0.1 automatically per RFC 6761).

    Lifecycle
    ---------
    status='stopped'  → proxy route returns 503; no forwarding occurs.
    status='running'  → proxy route forwards requests to target_url.
    """

    __tablename__ = "proxy_configs"

    # ── Primary key & ownership ────────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Identity ───────────────────────────────────────────────────────────────
    name       = db.Column(db.String(100), nullable=False)         # human label
    slug       = db.Column(db.String(80),  unique=True, nullable=False)  # URL key
    target_url = db.Column(db.String(500), nullable=False)          # upstream URL

    # ── Configuration ──────────────────────────────────────────────────────────
    proxy_type         = db.Column(db.String(20),  nullable=False, default="endpoint")
    status             = db.Column(db.String(20),  nullable=False, default="stopped")
    cors_bypass        = db.Column(db.Boolean,     nullable=False, default=True)
    skip_ngrok_warning = db.Column(db.Boolean,     nullable=False, default=True)
    # Comma-separated list of HTTP methods this proxy will forward, e.g. "GET,POST,DELETE".
    # Defaults to all supported methods.
    allowed_methods    = db.Column(
        db.String(60),
        nullable=False,
        default="GET,POST,PUT,DELETE,PATCH,OPTIONS",
    )
    cors_origins = db.Column(
        db.String(2000),
        nullable=False,
        default="*",
    )

    # ── Timestamps ─────────────────────────────────────────────────────────────
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # ── Relationship ───────────────────────────────────────────────────────────
    user = db.relationship(
        "User",
        backref=db.backref("proxies", lazy="dynamic", cascade="all, delete-orphan"),
    )

    # ── Constants ──────────────────────────────────────────────────────────────
    STATUS_RUNNING   = "running"
    STATUS_STOPPED   = "stopped"
    TYPE_ENDPOINT    = "endpoint"
    TYPE_SUBDOMAIN   = "subdomain"
    ALL_HTTP_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]

    def allowed_methods_list(self) -> list[str]:
        """Return allowed_methods as a Python list."""
        return [m.strip().upper() for m in self.allowed_methods.split(",") if m.strip()]

    def cors_origins_list(self) -> list[str]:
        """Return cors_origins as a Python list."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    # Slugs that cannot be used — they conflict with existing app routes or
    # common DNS names that would cause confusion.
    RESERVED_SLUGS = frozenset({
        "proxy", "proxies", "auth", "dashboard", "profile",
        "static", "api", "admin", "login", "logout", "signup",
        "register", "www", "mail", "ftp", "localhost", "new",
    })

    # ── Properties ─────────────────────────────────────────────────────────────
    @property
    def is_running(self) -> bool:
        """True when this proxy is actively forwarding requests."""
        return self.status == self.STATUS_RUNNING

    @property
    def access_url(self) -> str:
        """
        Return the full access URL for this proxy based on the current request host.
        Should only be called within a Flask request context.
        """
        from flask import request as _req

        host = _req.host  # e.g. 'localhost:5000'

        if self.proxy_type == self.TYPE_SUBDOMAIN:
            # e.g. swift-ray-a3f9.localhost:5000
            hostname = host.split(":")[0]
            port_part = (":" + host.split(":")[1]) if ":" in host else ""
            return f"http://{self.slug}.{hostname}{port_part}/"

        # Endpoint mode: http://localhost:5000/proxy/<slug>/
        return f"http://{host}/proxy/{self.slug}/"

    @property
    def type_label(self) -> str:
        """Human-friendly delivery mode label."""
        return "Endpoint" if self.proxy_type == self.TYPE_ENDPOINT else "Subdomain"

    # ── Class methods ──────────────────────────────────────────────────────────
    @classmethod
    def generate_unique_slug(cls) -> str:
        """
        Generate a random slug that is not already taken in the database.
        Falls back to a hex token if all attempts collide (extremely unlikely).
        """
        for _ in range(30):
            candidate = _generate_slug()
            if candidate not in cls.RESERVED_SLUGS and not cls.query.filter_by(slug=candidate).first():
                return candidate
        return secrets.token_hex(6)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ProxyConfig slug={self.slug!r} type={self.proxy_type!r} status={self.status!r}>"
