# Bridger — Complete Code Structure Guide

> Covers every layer of the application: directory layout, backend patterns,
> frontend architecture, CSS/JS reuse strategy, UI/UX conventions, and how all
> pieces connect.

---

## Table of Contents

1. [Directory Layout](#directory-layout)
2. [Entry Points](#entry-points)
3. [Configuration Layer](#configuration-layer)
4. [Backend Architecture](#backend-architecture)
   - [App Factory](#app-factory)
   - [Extensions](#extensions)
   - [Blueprints](#blueprints)
   - [Models](#models)
   - [Forms](#forms)
   - [Services](#services)
   - [Route Patterns](#route-patterns)
5. [Frontend Architecture](#frontend-architecture)
   - [Template Inheritance](#template-inheritance)
   - [CSS Split Strategy](#css-split-strategy)
   - [JavaScript Split Strategy](#javascript-split-strategy)
   - [CSS Design Tokens](#css-design-tokens)
   - [Shared Component Classes](#shared-component-classes)
6. [Page-by-Page Asset Map](#page-by-page-asset-map)
7. [UI/UX Patterns](#uiux-patterns)
8. [Security Patterns](#security-patterns)
9. [Request Lifecycle](#request-lifecycle)
10. [Data Flow Diagrams](#data-flow-diagrams)

---

## Directory Layout

```
Bridger/
├── run.py                        # Dev server entry point
├── config.py                     # Config classes (Dev / Prod)
├── requirements.txt              # Pinned Python dependencies
├── .env                          # Secrets — never committed
├── plan.md                       # Product plan
├── proxy-service.md              # HTTP Proxy service docs
├── webex-service.md              # Webex Integration service docs
├── code-structure.md             # ← this file
│
└── app/
    ├── __init__.py               # App factory + extension instances
    │
    ├── models/
    │   ├── user.py               # User, OTP models
    │   ├── proxy.py              # ProxyConfig model + slug generator
    │   ├── proxy_log.py          # ProxyLog model (per-request audit)
    │   ├── webex_config.py       # WebexConfig model
    │   ├── webex_webhook.py      # WebexWebhook model
    │   └── webex_webhook_log.py  # WebexWebhookLog model (enriched events)
    │
    ├── forms/
    │   ├── auth_forms.py         # SignupForm, LoginForm, VerifyEmailForm,
    │   │                         #   ForgotPasswordForm, ResetPasswordForm,
    │   │                         #   UpdateProfileForm
    │   ├── proxy_forms.py        # ProxyCreateForm, ProxyEditForm
    │   ├── webex_forms.py        # WebexCreateForm, WebexEditForm
    │   └── webex_webhook_forms.py # WebhookCreateForm
    │
    ├── routes/
    │   ├── auth.py               # /auth/* — all auth flows
    │   ├── profile.py            # /profile  +  / (landing redirect)
    │   ├── dashboard.py          # /dashboard
    │   ├── proxy_manager.py      # /proxies/* — CRUD + lifecycle
    │   ├── proxy_handler.py      # /proxy/<slug>/* + subdomain hook
    │   └── webex.py              # /webex/* — configs, webhooks, event receive
    │
    ├── services/
    │   ├── email_service.py      # SMTP sender + OTP email helpers
    │   ├── otp_service.py        # OTP creation + verification
    │   └── webex_service.py      # Webex API calls (token verify, webhooks, rooms, messages)
    │
    ├── templates/
    │   ├── base.html             # Shell: head, navbar, toasts, logout modal
    │   ├── auth/
    │   │   ├── login.html
    │   │   ├── signup.html
    │   │   ├── verify_email.html
    │   │   ├── forgot_password.html
    │   │   └── reset_password.html
    │   ├── dashboard/
    │   │   └── dashboard.html
    │   ├── profile/
    │   │   └── profile.html
    │   ├── proxy/
    │   │   ├── list.html
    │   │   ├── create.html
    │   │   ├── detail.html
    │   │   └── logs.html
    │   └── webex/
    │       ├── index.html            # Placeholder (unused)
    │       ├── list.html             # Configs list (paginated)
    │       ├── create.html           # New config form
    │       ├── detail.html           # Config detail + webhooks + Spaces button
    │       ├── webhook_create.html   # Webhook form + room picker modal
    │       ├── webhook_logs.html     # Event log table (expand rows, room-type badge)
    │       ├── spaces.html           # AJAX-paginated spaces browser
    │       └── room_messages.html    # Cursor-based message viewer
    │
    └── static/
        ├── css/
        │   ├── base.css          # Design tokens + every-page styles
        │   ├── auth.css          # Auth pages only
        │   ├── dashboard.css     # Dashboard page only
        │   ├── profile.css       # Profile page only
        │   ├── proxy.css         # All proxy pages + shared pagination classes
        │   ├── webex.css         # All Webex pages
        │   └── main.css          # Legacy source — NOT loaded by any template
        └── js/
            ├── base.js           # Every-page JS behaviours
            ├── auth.js           # Auth pages only
            ├── profile.js        # Profile page only
            ├── proxy.js          # All proxy pages
            ├── webex.js          # All Webex pages
            └── main.js           # Legacy source — NOT loaded by any template
```

---

## Entry Points

### `run.py`
Imports `create_app`, instantiates the app with `DevelopmentConfig` (or the
`FLASK_CONFIG` env var), and starts the dev server.

### `app/__init__.py`
The **application factory** (`create_app`). Nothing runs at import time — the
factory is called exactly once. This means:
- Multiple app instances can be safely created (testing, etc.).
- All extension globals (`db`, `login_manager`, `bcrypt`, `csrf`) are created
  at module level but bound to the app inside `create_app`.

---

## Configuration Layer

```
config.py
 └─ Config (base)
     ├─ DevelopmentConfig   DEBUG=True
     └─ ProductionConfig    DEBUG=False, SESSION_COOKIE_SECURE=True

config_map = { 'development' | 'production' | 'default' → class }
```

All values read from environment / `.env` via `python-dotenv`.
`DATABASE_URL` is required; the scheme is rewritten from `postgresql://` to
`postgresql+psycopg2://` automatically for SQLAlchemy 2.x compatibility.

| Key | Default | Notes |
|-----|---------|-------|
| `SECRET_KEY` | dev-only placeholder | Must be overridden in production |
| `DATABASE_URL` | — | No SQLite fallback — must be set |
| `SMTP_HOST/PORT/USER/APP_PASSWORD` | Gmail defaults | App password, not account password |
| `OTP_EXPIRY_MINUTES` | 10 | Applies to both OTP flows |
| `SQLALCHEMY_ENGINE_OPTIONS` | `sslmode=require` | Supabase / managed Postgres |

---

## Backend Architecture

### App Factory

`create_app()` in `app/__init__.py`:

```
create_app(config_class)
  │
  ├─ app = Flask(__name__)
  ├─ app.config.from_object(config_class)
  │
  ├─ db.init_app(app)
  ├─ login_manager.init_app(app)
  ├─ bcrypt.init_app(app)
  ├─ csrf.init_app(app)
  │
  ├─ login_manager.login_view = "auth.login"
  │
  ├─ register blueprints (auth, profile, dashboard,
  │                        proxy_manager, proxy_handler, webex)
  │
  ├─ app.before_request(handle_subdomain_proxy)   ← subdomain hook
  │
  └─ db.create_all()    ← idempotent schema creation
```

### Extensions

| Instance | Package | Purpose |
|----------|---------|---------|
| `db` | Flask-SQLAlchemy | ORM, session management, migrations |
| `login_manager` | Flask-Login | Session-based auth, `@login_required` |
| `bcrypt` | Flask-Bcrypt | Password hashing (salted bcrypt) |
| `csrf` | Flask-WTF CSRFProtect | CSRF token on every POST form |

All instances live in `app/__init__.py` and are imported by routes/models that
need them:

```python
from app import db, bcrypt
```

### Blueprints

| Blueprint | Prefix | Module | Auth required |
|-----------|--------|--------|---------------|
| `auth_bp` | `/auth` | `routes/auth.py` | No |
| `profile_bp` | — | `routes/profile.py` | Yes (profile/index routes) |
| `dashboard_bp` | `/dashboard` | `routes/dashboard.py` | Yes |
| `proxy_manager_bp` | `/proxies` | `routes/proxy_manager.py` | Yes |
| `proxy_handler_bp` | `/proxy` | `routes/proxy_handler.py` | No (public forwarding) |
| `webex_bp` | `/webex` | `routes/webex.py` | Yes (except `receive/<uuid>`) |

### Models

#### `User` (`users` table)
```
id · username · email · password_hash · is_verified
first_name · last_name · created_at · updated_at
 └─ otps → OTP[] (cascade delete)
```

#### `OTP` (`otps` table)
```
id · user_id(FK) · otp_code · purpose · expires_at · is_used · created_at
purpose ∈ { 'email_verify', 'forgot_password' }
```

#### `ProxyConfig` (`proxy_configs` table)
```
id · user_id(FK) · name · slug · target_url
proxy_type ∈ { 'endpoint', 'subdomain' }
status     ∈ { 'running', 'stopped' }
allowed_methods (comma-separated, e.g. "GET,POST,DELETE")
cors_bypass · skip_ngrok_warning
created_at · updated_at
 └─ logs → ProxyLog[] (cascade delete)
```
Slug generation: `adjective-noun-xxxx` (4 random hex chars) via `secrets`.
The slug is immutable after creation — changing it would break client integrations.

#### `ProxyLog` (`proxy_logs` table)
```
id · proxy_id(FK) · method · path · status_code
client_ip · duration_ms · created_at
```
One row per forwarded request. Log writes are non-fatal (wrapped in
try/except with rollback).

#### `WebexConfig` (`webex_configs` table)
```
id · user_id(FK) · name · access_token
webex_person_id · webex_display_name · webex_email · webex_org_id
is_verified · last_verified_at · created_at · updated_at
 └─ webhooks → WebexWebhook[] (cascade delete)
```
Properties: `initials` (2-letter avatar fallback), `masked_token` (`●●●●<last4>`), `display_email`.

#### `WebexWebhook` (`webex_webhooks` table)
```
id · config_id(FK) · uuid · name
resource · event · filter_str · target_url · uses_bridger_target
secret · webex_webhook_id · webex_status · partner_email
created_at · updated_at
 └─ logs → WebexWebhookLog[] (cascade delete)
```
The `uuid` is generated with `uuid.uuid4()` and forms the unique receive URL path.
`partner_email` is lazily populated on the first event received for a direct room.

#### `WebexWebhookLog` (`webex_webhook_logs` table)
```
id · webhook_id(FK) · received_at · client_ip
webex_event_id · resource · event_type · actor_id · org_id · app_id · owned_by
data_json · raw_payload
message_text · message_markdown · message_html · message_files
resource_json · sender_name · sender_email · receiver_name · receiver_email
room_type · signature_valid
```
One row per received Webex event, enriched with the resolved resource object
via a follow-up Webex API call immediately after event receipt.

### Forms

All forms inherit from `FlaskForm` (Flask-WTF), which auto-injects a CSRF token.

#### Auth forms (`forms/auth_forms.py`)

| Form | Fields | Custom validators |
|------|--------|-------------------|
| `SignupForm` | username, email, first_name, last_name, password, confirm_password | `validate_username` (unique), `validate_email` (unique) |
| `LoginForm` | email, password, remember_me | — |
| `VerifyEmailForm` | otp_code | — |
| `ForgotPasswordForm` | email | — |
| `ResetPasswordForm` | otp_code, password, confirm_password | — |
| `UpdateProfileForm` | username | `validate_username` (unique, skip if unchanged) |

#### Proxy forms (`forms/proxy_forms.py`)

| Form | Fields | Notes |
|------|--------|-------|
| `ProxyCreateForm` | name, slug, target_url, proxy_type, allowed_methods, cors_bypass, skip_ngrok_warning | `validate_slug` (regex + reserved names + uniqueness); `validate_allowed_methods` (min 1) |
| `ProxyEditForm` | name, target_url, allowed_methods, cors_bypass, skip_ngrok_warning | No slug / proxy_type — locked after creation |

`MultiCheckboxField` is a custom WTForms field that renders `SelectMultipleField`
as individual checkboxes with `ListWidget`.

#### Webex forms (`forms/webex_forms.py` + `forms/webex_webhook_forms.py`)

| Form | Fields | Notes |
|------|--------|-------|
| `WebexCreateForm` | name, access_token | Token verified against Webex on submit |
| `WebexEditForm` | name, access_token | Token optional — blank = keep existing |
| `WebhookCreateForm` | name, resource, event, filter_str, target_url | Room picker modal populates filter_str; multi-room creates one webhook per room |

### Services

#### `otp_service.py`
```
create_otp(user_id, purpose, expiry_minutes=10) → str
  ├─ invalidate existing unused OTPs for user+purpose
  ├─ generate 6-digit code via secrets.randbelow(900_000)+100_000
  └─ persist OTP row → return plaintext code

verify_otp(user_id, otp_code, purpose) → bool
  ├─ query by (user_id, otp_code, purpose, is_used=False)
  ├─ check expires_at > now()
  ├─ mark is_used=True
  └─ return True/False
```

#### `email_service.py`
```
send_email(to, subject, html_body, text_body=None) → bool
  ├─ reads SMTP_* from app.config
  ├─ builds MIMEMultipart('alternative')
  ├─ connects via smtplib.SMTP + STARTTLS
  └─ returns False on any exception (never raises)

send_verification_otp_email(email, username, otp_code) → bool
send_password_reset_otp_email(email, username, otp_code) → bool
  └─ both call send_email with pre-built HTML bodies
```

#### `webex_service.py`
All functions call the Webex REST API (`https://webexapis.com/v1`) with an
8-second timeout. None raises — all return `None`/`False`/`[]` on error.

```
verify_token(access_token)                                    → dict|None
create_webhook(token, name, target_url, resource,
               event, filter_str, secret)                     → dict|None
delete_webhook(token, webhook_id)                             → bool
fetch_rooms(token, max_results=200)                           → list[dict]
fetch_all_webhooks(token)                                     → list[dict]  (follows Link pagination)
fetch_room_members(token, room_id)                            → list[dict]
fetch_resource(token, resource, resource_id)                  → dict|None
_fetch_rooms_by_type(token, room_type, max_results)           → list[dict]  (internal)
fetch_rooms_filtered(token, room_type=None,
                     max_results=500)                         → list[dict]  (merges direct+group)
fetch_room_detail(token, room_id)                             → dict|None
fetch_messages(token, room_id, max_results=25,
               before_message=None)                           → list[dict]  (cursor-based)
```

`fetch_rooms_filtered` with `room_type=None` triggers two separate API calls
(`type=direct` and `type=group`) because the Webex API omits direct rooms when
no `type` parameter is supplied.

### Route Patterns

#### Standard authenticated route
```python
@blueprint.route("/path", methods=["GET", "POST"])
@login_required
def view():
    form = SomeForm()
    if form.validate_on_submit():
        # mutate DB
        flash("Success", "success")
        return redirect(url_for("..."))
    return render_template("page.html", form=form)
```

#### Ownership guard
```python
def _own_proxy_or_404(proxy_id: int) -> ProxyConfig:
    proxy = ProxyConfig.query.filter_by(
        id=proxy_id, user_id=current_user.id
    ).first()
    if not proxy:
        abort(404)
    return proxy
```
Used on every proxy management route. Prevents users from accessing each
other's resources without leaking existence via 403.

#### Safe redirect (open-redirect prevention)
```python
def _is_safe_redirect_url(target: str) -> bool:
    host_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (
        test_url.scheme in ("http", "https")
        and host_url.netloc == test_url.netloc
    )
```
Used in `auth.login` when a `next` query param is present.

#### Proxy forwarding (`proxy_handler.py`)
```
Incoming request
  ├─ stopped?        → 503
  ├─ OPTIONS?        → 200 preflight (CORS pre-flight passthrough)
  ├─ method blocked? → 405 + write log (duration_ms=None)
  ↓
forward via requests library (timeout=30s)
  ├─ strip hop-by-hop request headers
  ├─ add cors / ngrok headers if configured
  ├─ ConnectionError → 502
  ├─ Timeout         → 504
  ↓
build Flask Response
  ├─ copy upstream headers (minus hop-by-hop response headers)
  ├─ apply CORS headers if cors_bypass=True
  ├─ write ProxyLog (non-fatal)
  └─ return to client
```

---

## Frontend Architecture

### Template Inheritance

```
base.html  (shell)
  ├─ <head>: Bootstrap 5.3 CDN, Bootstrap Icons CDN, base.css
  ├─ {% block extra_head %}   ← page CSS injected here
  ├─ <nav>: app-navbar (conditional auth/guest links)
  ├─ Toast stack (flash messages, auto-rendered)
  ├─ Logout confirmation modal
  ├─ {% block content %}      ← page HTML
  ├─ Bootstrap JS bundle (CDN, deferred)
  ├─ base.js
  └─ {% block extra_scripts %} ← page JS injected here
```

Every page template:
1. `{% extends 'base.html' %}`
2. Overrides `{% block title %}` — tab title
3. Overrides `{% block extra_head %}` — loads its own CSS file
4. Overrides `{% block content %}` — page body
5. Overrides `{% block extra_scripts %}` — loads its own JS file (+ any inline JS)

### CSS Split Strategy

`main.css` is the original monolith — kept as source of truth but **not loaded
by any template**. Styles are split into purpose-scoped files:

```
base.css      → loaded by base.html (every page)
  • Design tokens (:root variables)
  • Body, typography reset
  • Navbar (.app-navbar, .btn-nav-cta)
  • Shared form controls (.form-control, .form-label, .input-group-icon)
  • Panel card (.panel)
  • Shared buttons (.btn-save, .btn-discard)
  • Page headings shared across pages (.dash-title, .dash-subtitle)
  • Empty-state panels (.dash-empty-panel/icon/title/body)
  • Shared detail components (.info-tile, .profile-view-field,
                               .danger-zone, .btn-danger-outline,
                               .btn-edit-profile, .profile-form-actions)
  • Toast system (.toast-stack, .toast-item, .toast-close)
  • Logout modal (.br-modal-backdrop, .br-modal, .br-modal-*)
  • Keyframe animations (@keyframes slideIn, fadeIn, pulse)

auth.css      → loaded only by auth/* templates
  • Auth wrapper + card (.auth-wrap, .auth-card)
  • Auth buttons (.btn-auth, .btn-ind, .btn-google)
  • Password toggle + strength meter + match indicator
  • OTP digit boxes (.otp-grid, .otp-box)
  • Multi-step form (.auth-step)
  • Auth separator + footer

dashboard.css → loaded only by dashboard/dashboard.html
  • KPI stat cards (.dash-kpi-grid, .dash-kpi-card, .dash-kpi-*)
  • Chart/activity panels (.dash-panel, .dash-panel-section)
  • Skeleton loaders (.skel, .skel-kpi-val, .skel-label, .skel-chart)
  • Inline link button (.btn-link-inline)

profile.css   → loaded only by profile/profile.html
  • Profile hero section (.profile-hero, .profile-avatar)
  • Profile-specific card panels

proxy.css     → loaded by all proxy/* templates + dashboard (top-proxies table)
  • Proxy hero bar (.proxy-hero, .proxy-hero-slug, .proxy-hero-meta)
  • Status badges (.proxy-status-badge, .proxy-status-dot)
  • Type badge (.proxy-type-badge)
  • Table (.proxy-table-wrap, .proxy-table, .proxy-table-*)
  • URL display box (.proxy-url-box, .proxy-url-code, .proxy-url-copy)
  • Mode grid (.proxy-mode-grid, .proxy-mode-card)
  • Toggle switches (.proxy-toggle-row)
  • Method checkboxes (.proxy-method-grid, .proxy-method-chip)
  • Log table (.proxy-log-table, .proxy-log-pill, .proxy-log-status,
               .proxy-log-pagination, .proxy-log-stats)
  • Also loaded by webex/spaces.html and webex/room_messages.html for
    shared pagination classes (.proxy-log-pagination, .proxy-log-page-btn, etc.)
  • Action buttons (.btn-proxy-action, .btn-proxy-danger)

  webex.css     → loaded by all webex/* templates
  • Config hero + avatar circle + profile field rows + token display
  • Verified/unverified badge (.webex-verified-badge)
  • Webhook table + resource/event type labels
  • Signature validity badge + space/room-type badge
  • Event log table with expand rows (.webex-log-*, .webex-detail-*)
  • JSON payload pre-block
  • Room picker modal overrides (search, list, checkbox items)
  • Webhooks tab bar (All/Bridger/External) + source badge
  • Type filter tabs (.webex-type-tabs, .webex-type-tab)
  • Search box (.webex-spaces-search-*)
  • Space row icon (.webex-space-icon)
  • Message items (.webex-messages-list, .webex-msg-*)
```

**Rule:** A class used on more than one page group moves to `base.css`.
This is how `dash-title`, `info-tile`, `danger-zone`, etc. ended up there
even though they were originally written for a single page.

### JavaScript Split Strategy

`main.js` is the original monolith — not loaded by any template. Split into
init-function files where each function is called on `DOMContentLoaded`:

```
base.js      → loaded by base.html (every page)
  • initFormLoading()    — spinner on submit buttons while form is submitting
  • initToastDismiss()   — dismiss toasts on ✕ click; auto-dismiss after 5 s
  • initLogoutModal()    — intercepts logout link, shows confirmation modal

auth.js      → loaded only by auth/* templates
  • initPasswordToggles()  — show/hide password eye icon on password inputs
  • initPasswordStrength() — live 4-tier strength meter on signup password
  • initPasswordMatch()    — live ✓/✗ match indicator on confirm_password
  • initOtpBoxes()         — auto-advance / backspace / paste handling for
                             6-box OTP input UI
  • initStepForm()         — multi-step forgot-password flow (step 1 = email,
                             step 2 = OTP + new password)

profile.js   → loaded only by profile/profile.html
  • initProfileEdit()    — toggle between read-only view and edit form;
                           cancel restores original values

proxy.js     → loaded by all proxy/* templates
  • initProxyCopy()      — copy-to-clipboard on [data-copy-target] buttons
                           with ✓ tick feedback
  • initClearLogs()      — delete confirmation modal before submitting the
                           clear-logs form

webex.js     → loaded by all webex/* templates
  • Webex-specific interactive behaviours (room picker, expand rows, etc.)
```

All init functions are self-contained — they query the DOM and no-op silently
if their target elements are not present. This means `base.js` can safely call
all base inits on auth pages without errors.

### CSS Design Tokens

All colours, shadows, radii, and typography are defined as CSS custom properties
in `:root` inside `base.css` and referenced everywhere else via `var(...)`.

```css
:root {
  --primary / --primary-dark / --primary-light / --primary-ring
  --bg / --surface / --border
  --text / --text-2 / --text-3
  --success / --success-bg
  --danger  / --danger-bg
  --warning / --warning-bg
  --info    / --info-bg
  --shadow-xs / --shadow-sm / --shadow-md / --shadow-lg / --shadow-card
  --radius-sm / --radius / --radius-lg / --radius-xl
  --font
  --transition
}
```

### Shared Component Classes

These live in `base.css` and are safe to use on any page:

| Class | Description |
|-------|-------------|
| `.panel` | White card with border, shadow, border-radius |
| `.panel.danger-zone` | Panel with red left-border accent |
| `.btn-save` | Indigo filled CTA button (submit, create, save) |
| `.btn-discard` | Ghost cancel button |
| `.btn-danger-outline` | Red outline delete/danger button |
| `.btn-edit-profile` | Ghost icon+text edit toggle button |
| `.btn-nav-cta` | Navbar "Sign Up" pill button |
| `.dash-title` | Page-level `<h1>` style |
| `.dash-subtitle` | Muted sub-line under a page title |
| `.dash-empty-panel` | Centred empty-state container |
| `.dash-empty-icon` | Big icon circle in empty state |
| `.dash-empty-title/body` | Empty state heading + text |
| `.info-tile` | Icon + label/value info block (used in detail + profile) |
| `.profile-view-field` | Label above a read-only value row |
| `.profile-form-actions` | Button row at bottom of edit form |
| `.form-control` (custom) | Custom-styled text input |
| `.toast-item` | Flash message with icon, body, close button |
| `.br-modal-*` | Logout confirmation modal system |

---

## Page-by-Page Asset Map

| Template | CSS | JS | Notes |
|----------|-----|----|-------|
| `base.html` | `base.css` | `base.js` | Loaded on every page |
| `auth/login.html` | `auth.css` | `auth.js` | Password toggle |
| `auth/signup.html` | `auth.css` | `auth.js` | Toggle + strength + match |
| `auth/verify_email.html` | `auth.css` | `auth.js` | OTP boxes |
| `auth/forgot_password.html` | `auth.css` | `auth.js` | Step form + OTP boxes |
| `auth/reset_password.html` | `auth.css` | `auth.js` | OTP boxes + strength + match |
| `dashboard/dashboard.html` | `dashboard.css` + `proxy.css` | Inline JS | `proxy.css` for top-proxies table rendered by JS |
| `profile/profile.html` | `profile.css` | `profile.js` | Edit toggle |
| `proxy/list.html` | `proxy.css` | `proxy.js` | Copy + lifecycle |
| `proxy/create.html` | `proxy.css` | `proxy.js` | Inline slug/target JS + proxy.js |
| `proxy/detail.html` | `proxy.css` | Inline JS + `proxy.js` | Inline edit form toggle |
| `proxy/logs.html` | `proxy.css` | Inline JS + `proxy.js` | Clear-logs modal |
| `webex/list.html` | `webex.css` | `webex.js` | Configs table |
| `webex/create.html` | `webex.css` | `webex.js` | New config form |
| `webex/detail.html` | `webex.css` | `webex.js` | Webhooks tab bar, Spaces button |
| `webex/webhook_create.html` | `webex.css` | `webex.js` | Room picker modal + inline fetch JS |
| `webex/webhook_logs.html` | `proxy.css` + `webex.css` | `webex.js` | Expand rows, room-type badge |
| `webex/spaces.html` | `proxy.css` + `webex.css` | Inline JS | AJAX prev/next replaces `<tbody>` |
| `webex/room_messages.html` | `proxy.css` + `webex.css` | Inline JS | AJAX load-more appends items |

---

## UI/UX Patterns

### Flash Messages (Toasts)
Routes call `flash("message", "category")` where category ∈
`{success, danger, warning, info}`. `base.html` renders all flashed messages
as `.toast-item` elements in a fixed `.toast-stack`. `base.js:initToastDismiss`
handles dismiss-on-click and 5-second auto-dismiss.

### Destructive Action Confirmation
Any destructive action (logout, delete proxy, clear logs) goes through a
modal before submitting. This prevents accidental data loss. Implemented via
the `.br-modal-backdrop` system in `base.html` + `base.js:initLogoutModal`,
and inline JS for page-specific modals.

### Inline Edit Pattern (proxy detail + profile)
Pages default to a read-only view. Clicking an **Edit** button (`btn-edit-profile`)
uses JS to:
1. Hide the read-only `.profile-view-*` block
2. Show the edit form
3. Cancel restores original field values and switches back to read-only

This avoids a full page navigation for common edits.

### Paginated Tables
All list views (`/proxies/`, `/proxies/<id>/logs`) use Flask-SQLAlchemy's
`.paginate(per_page=30)`. Templates receive a `Pagination` object and render
`Prev / Page X of Y / Next` controls using `.proxy-log-pagination` styles.

### Form Submission Feedback
`base.js:initFormLoading` attaches to every `<form>` submit event:
- Disables the submit button
- Replaces its text with a spinner + "Please wait…"
- Re-enables on page focus (handles browser back-button)

This prevents double-submission and gives immediate visual feedback.

### Empty States
When a list is empty, templates render a `.dash-empty-panel` (centred card
with icon, heading, body copy, and a CTA button) instead of an empty table.

### OTP Input
Verification pages use a 6-box OTP grid (`.otp-grid`, `.otp-box`) where
`auth.js:initOtpBoxes`:
- Auto-advances focus on digit entry
- Handles backspace to move back
- Handles paste of a 6-digit string (distributes digits)
- Concatenates all box values into a hidden `<input name="otp_code">` on submit

### Password Strength Meter
Sign-up and reset pages show a live 4-tier strength bar (`.pw-strength-bar`)
driven by `auth.js:initPasswordStrength`. Criteria: length ≥ 8, uppercase,
number, symbol.

---

## Security Patterns

| Pattern | Implementation |
|---------|---------------|
| Password hashing | `flask_bcrypt.generate_password_hash` (salted bcrypt) |
| CSRF protection | `Flask-WTF CSRFProtect` — token on every `<form>` via `{{ csrf_token() }}` |
| OTP entropy | `secrets.randbelow(900_000) + 100_000` — cryptographically random, no modular bias |
| OTP single-use + expiry | `is_used=True` on consume; `expires_at` checked on verify |
| OTP invalidation | Previous unused tokens for same user+purpose invalidated on new request |
| Login-only pages | `@login_required` on every management route |
| Resource ownership | `_own_proxy_or_404(proxy_id)` — 404 (not 403) to avoid leaking resource existence |
| Open-redirect | `_is_safe_redirect_url()` validates `next` param against `request.host_url` |
| Email enumeration | Forgot-password shows a generic flash regardless of whether the email exists |
| Session cookies | `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE='Lax'`; `SESSION_COOKIE_SECURE=True` in production |
| Proxy log safety | DB errors in `_write_log()` are caught + rolled back — never propagate to the client |
| CORS bypass scope | `Access-Control-Allow-Origin: *` is opt-in per proxy, not global |

---

## Request Lifecycle

### Authenticated page request (e.g. `/proxies/`)

```
Browser GET /proxies/
  │
  ├─ Flask routing → proxy_manager_bp.list_proxies
  ├─ @login_required → checks session; if missing → redirect /auth/login?next=%2Fproxies%2F
  ├─ ProxyConfig.query.filter_by(user_id=current_user.id).paginate(...)
  └─ render_template("proxy/list.html", proxies=pagination)
       ├─ extends base.html
       ├─ injects proxy.css via {% block extra_head %}
       ├─ renders table rows with Jinja2 for loop
       └─ injects proxy.js via {% block extra_scripts %}
```

### Auth form submission (e.g. POST `/auth/signup`)

```
Browser POST /auth/signup
  │
  ├─ Flask-WTF validates CSRF token (abort 400 if missing/invalid)
  ├─ SignupForm.validate_on_submit()
  │   ├─ WTForms field validators run
  │   └─ validate_username() + validate_email() custom validators run
  ├─ bcrypt.generate_password_hash(password)
  ├─ db.session.add(user) + db.session.commit()
  ├─ create_otp(user.id, 'email_verify') → OTP row created
  ├─ send_verification_otp_email(...)    → SMTP send (non-fatal on failure)
  ├─ session['verify_email'] = user.email
  └─ redirect → /auth/verify-email
```

### Proxy forwarding request (e.g. GET `/proxy/swift-ray-a3f9/api/users`)

```
Browser GET /proxy/swift-ray-a3f9/api/users
  │
  ├─ Flask routing → proxy_handler_bp.proxy_endpoint(slug, path)
  ├─ ProxyConfig.query.filter_by(slug='swift-ray-a3f9').first_or_404()
  ├─ status == 'stopped' → return 503
  ├─ method not in allowed_methods → write log(405) → return 405
  ├─ strip hop-by-hop headers from request
  ├─ requests.request(method, target_url + path, ..., timeout=30)
  │   ├─ ConnectionError → return 502
  │   └─ Timeout         → return 504
  ├─ build Flask Response (upstream body + status)
  ├─ strip hop-by-hop response headers
  ├─ add CORS headers (if cors_bypass)
  ├─ _write_log(proxy, status_code, duration_ms)  ← non-fatal
  └─ return response to browser
```

---

## Data Flow Diagrams

### Email Verification Flow
```
[Signup Form]
  → create User (is_verified=False)
  → create_otp('email_verify')
  → send_verification_otp_email
  → session['verify_email']
  → redirect /auth/verify-email

[Verify Email Form]
  → verify_otp(user.id, code, 'email_verify')
     ├─ invalid/expired → flash error, retry
     └─ valid → user.is_verified=True → flash success → redirect /auth/login
```

### Password Reset Flow
```
[Forgot Password Form]
  → user = User.query.filter_by(email=...).first()
  → if user: create_otp('forgot_password') + send_password_reset_otp_email
  → always: generic flash (anti-enumeration)
  → session['reset_email'] = email
  → redirect /auth/reset-password

[Reset Password Form]
  → verify_otp(user.id, code, 'forgot_password')
     ├─ invalid → flash error, retry
     └─ valid → user.password_hash = bcrypt.hash(new_pw)
              → session.pop('reset_email')
              → redirect /auth/login
```

### Proxy Lifecycle
```
Create (status='stopped')
  └─[Start] → status='running' → forwards requests + writes ProxyLog rows
      └─[Stop]   → status='stopped' → returns 503
          └─[Delete] → CASCADE deletes all ProxyLog rows
```
