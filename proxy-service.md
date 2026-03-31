# Bridger — HTTP Proxy Service

> Part of the Bridger platform. See [plan.md](plan.md) for the full project overview.

The HTTP Proxy service lets authenticated users create named proxy configurations that
forward incoming HTTP/HTTPS requests to an upstream target URL — handling CORS bypass,
method filtering, and per-request audit logging automatically.

---

## Table of Contents

1. [Concepts](#concepts)
2. [Delivery Modes](#delivery-modes)
3. [Data Model](#data-model)
4. [Route Map](#route-map)
5. [Request Forwarding](#request-forwarding)
6. [Proxy Logging](#proxy-logging)
7. [Configuration Options](#configuration-options)
8. [Lifecycle](#lifecycle)
9. [Security Notes](#security-notes)

---

## Concepts

| Term | Meaning |
|------|---------|
| **Proxy config** | A saved configuration record owned by a user (name, slug, target, mode, etc.) |
| **Slug** | A short URL-safe identifier generated for each proxy (e.g. `swift-ray-a3f9`) |
| **Target URL** | The upstream server all requests are forwarded to |
| **Delivery mode** | How clients reach the proxy — via a path prefix or a subdomain |
| **Proxy log** | One DB row written for every forwarded request (method, path, status, IP, duration) |

---

## Delivery Modes

### Endpoint mode
Requests are received at a path prefix on the main app host:

```
http://localhost:5000/proxy/<slug>/[path]
```

Example:
```
http://localhost:5000/proxy/swift-ray-a3f9/api/users
    → forwards to → https://api.example.com/api/users
```

### Subdomain mode
Requests are received on a dedicated subdomain of `localhost`:

```
http://<slug>.localhost:[port]/[path]
```

Example:
```
http://swift-ray-a3f9.localhost:5000/api/users
    → forwards to → https://api.example.com/api/users
```

Modern operating systems resolve `*.localhost` to `127.0.0.1` automatically
(RFC 6761 §6.3) — no hosts-file changes required on Windows 11, macOS 13+,
or Linux with systemd-resolved.

---

## Data Model

### `proxy_configs`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER FK | → `users.id` CASCADE DELETE |
| name | VARCHAR(120) | Human-readable label |
| slug | VARCHAR(80) | Unique URL-safe identifier, immutable after creation |
| target_url | VARCHAR(500) | Upstream base URL |
| proxy_type | VARCHAR(20) | `endpoint` or `subdomain` |
| allowed_methods | VARCHAR(100) | Comma-separated list e.g. `GET,POST,DELETE` |
| cors_bypass | BOOLEAN | Adds `Access-Control-Allow-Origin: *` headers |
| skip_ngrok_warning | BOOLEAN | Adds `ngrok-skip-browser-warning: true` header |
| status | VARCHAR(20) | `running` or `stopped` |
| created_at | DATETIME | UTC |
| updated_at | DATETIME | UTC, auto-updated |

### `proxy_logs`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| proxy_id | INTEGER FK | → `proxy_configs.id` CASCADE DELETE, indexed |
| method | VARCHAR(10) | HTTP method of the incoming request |
| path | VARCHAR(2000) | Full path (without query string) |
| status_code | INTEGER | Upstream response status (or `405` for blocked methods) |
| client_ip | VARCHAR(45) | Originating client IP; respects `X-Forwarded-For` |
| duration_ms | INTEGER | Wall-clock time for the upstream round-trip (ms); `NULL` for 405s |
| created_at | DATETIME | UTC, indexed |

---

## Route Map

All management routes require authentication (`@login_required`).
Forwarding routes are public — any client can hit a running proxy.

### Management (`/proxies/…`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/proxies/` | List all proxies for the current user (30 per page) |
| GET/POST | `/proxies/new` | Show create form / persist new proxy |
| GET | `/proxies/<id>` | Proxy detail page with inline edit form |
| POST | `/proxies/<id>/edit` | Save edits (name, target, methods, flags) |
| POST | `/proxies/<id>/delete` | Permanently delete proxy and all its logs |
| POST | `/proxies/<id>/start` | Set `status = running` |
| POST | `/proxies/<id>/stop` | Set `status = stopped` |
| GET | `/proxies/<id>/logs` | Paginated request log (30 per page, newest first) |

### Forwarding

| Method | Path | Description |
|--------|------|-------------|
| ANY | `/proxy/<slug>/[path]` | Endpoint-mode: forward to target |
| ANY | `<slug>.localhost/[path]` | Subdomain-mode: intercepted by `before_request` hook |

---

## Request Forwarding

Handled in `app/routes/proxy_handler.py`.

### Flow

```
Incoming request
    │
    ├─ proxy stopped?  → 503 Service Unavailable
    │
    ├─ OPTIONS?        → immediate 200 preflight response
    │
    ├─ method blocked? → 405 Method Not Allowed  ──┐
    │                                               │ write log
    ▼                                               │
  Forward upstream (requests library)              │
    │                                              ◄┘
    ├─ connection error → 502 Bad Gateway
    ├─ timeout          → 504 Gateway Timeout
    │
    ▼
  Build Flask response ← upstream response
    │
    ├─ strip hop-by-hop headers
    ├─ apply CORS headers (if cors_bypass=True)
    ├─ write ProxyLog row
    │
    ▼
  Return response to client
```

### Hop-by-hop headers stripped

**Request** (not forwarded upstream):
`host`, `content-length`, `transfer-encoding`, `connection`, `keep-alive`,
`proxy-authenticate`, `proxy-authorization`, `te`, `trailers`, `upgrade`

**Response** (not copied to client):
`content-encoding`, `transfer-encoding`, `connection`, `keep-alive`, `proxy-connection`

### Client IP detection

```python
X-Forwarded-For: <ip1>, <ip2>   → uses ip1 (leftmost / originating client)
No X-Forwarded-For               → uses request.remote_addr
```

---

## Proxy Logging

Every forwarded request (including blocked 405s) writes one `ProxyLog` row.
Log writes are **non-fatal** — any DB error is caught, rolled back, and logged
to the application logger without interrupting the proxy response.

### Logs UI (`/proxies/<id>/logs`)

- Paginated table: 30 rows per page, newest first
- Stats strip at the top: total requests · 2xx–3xx count · 4xx–5xx count · average duration
- Method pills colour-coded (GET=green, POST=blue, PUT=amber, PATCH=purple, DELETE=red)
- Status badges colour-coded by range (2xx=green, 3xx=blue, 4xx=amber, 5xx=red)

---

## Configuration Options

| Option | Form field | Effect |
|--------|-----------|--------|
| **Name** | `name` | Display label only |
| **Target URL** | `target_url` | Upstream base URL; all requests are appended to this |
| **Access Mode** | `proxy_type` | `endpoint` or `subdomain` — set at creation, immutable |
| **Allowed Methods** | `allowed_methods` | Multi-select; requests with other methods return 405 |
| **CORS Bypass** | `cors_bypass` | Adds `Access-Control-Allow-*` headers to every response |
| **Skip Ngrok Warning** | `skip_ngrok_warning` | Adds `ngrok-skip-browser-warning: true` to upstream request |

---

## Lifecycle

```
Created (status=stopped)
    │
    ▼
[Start]  →  status=running  →  forwards requests + writes logs
    │
[Stop]   →  status=stopped  →  returns 503 to all clients
    │
[Delete] →  proxy_configs row deleted  →  all proxy_logs cascade-deleted
```

Slug and access mode (`proxy_type`) are **locked after creation** — changing
either would break existing client integrations.

---

## Security Notes

- Proxy configs are **user-scoped** — users can only view, edit, or delete their own proxies.
- The `_own_proxy_or_404` helper enforces ownership on every management route.
- **CSRF tokens** are required on all state-changing management forms (Flask-WTF).
- Forwarding routes are intentionally **unauthenticated** so third-party clients can use them.
- `RESERVED_SLUGS` (e.g. `proxy`, `admin`, `api`) cannot be used to prevent route conflicts.
- Upstream requests time out after **30 seconds** to avoid hanging worker threads.
- Log writes use a try/except with rollback — a DB failure never leaks an exception to the client.
