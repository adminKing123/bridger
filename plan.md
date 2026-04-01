# Bridger — Flask Web Application

## Project Overview

A Flask web application with full user authentication (registration, email OTP
verification, login, password reset) and a suite of developer tools — starting
with an **HTTP Proxy** service for forwarding requests and bypassing CORS.

> **Service documentation**
> - HTTP Proxy service → see [proxy-service.md](proxy-service.md)
> - Webex Integration service → see [webex-service.md](webex-service.md)

---

## Architecture

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Flask 3.x (Python) |
| ORM | Flask-SQLAlchemy 3.x |
| Database | SQLite 3 (`data.sqlite3`) |
| Auth sessions | Flask-Login |
| Password hashing | Flask-Bcrypt |
| Forms / CSRF | Flask-WTF + WTForms |
| Email delivery | Python `smtplib` over SMTP/TLS |
| HTTP proxying | `requests` library |
| Env management | python-dotenv |

---

## Project Structure

```
Bridger/
├── app/
│   ├── __init__.py            # App factory (extensions, blueprints)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py            # User + OTP SQLAlchemy models
│   │   ├── admin.py           # UserServicePermission model + SERVICES list
│   │   ├── proxy.py           # ProxyConfig model
│   │   ├── proxy_log.py       # ProxyLog model (per-request audit log)
│   │   ├── webex_config.py    # WebexConfig model
│   │   ├── webex_webhook.py   # WebexWebhook model
│   │   └── webex_webhook_log.py # WebexWebhookLog model
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── admin.py           # superadmin dashboard, user management, service permissions
│   │   ├── auth.py            # signup, login, logout, verify-email,
│   │   │                      #   forgot-password, reset-password
│   │   ├── profile.py         # protected /profile + landing index
│   │   ├── dashboard.py       # protected /dashboard
│   │   ├── proxy_manager.py   # CRUD + lifecycle for proxy configs
│   │   ├── proxy_handler.py   # Live request forwarding + subdomain hook
│   │   └── webex.py           # Webex config/webhook management + event receive
│   ├── services/
│   │   ├── __init__.py
│   │   ├── email_service.py   # SMTP email sender + template helpers
│   │   ├── otp_service.py     # OTP generation, storage, verification
│   │   └── webex_service.py   # Webex API calls (verify, webhooks, rooms, messages)
│   ├── forms/
│   │   ├── __init__.py
│   │   ├── auth_forms.py      # WTForms: Signup, Login, Verify,
│   │   │                      #   ForgotPassword, ResetPassword, UpdateProfile
│   │   ├── proxy_forms.py     # ProxyCreateForm, ProxyEditForm
│   │   ├── webex_forms.py     # WebexCreateForm, WebexEditForm
│   │   └── webex_webhook_forms.py # WebhookCreateForm
│   ├── templates/
│   │   ├── base.html          # Bootstrap 5 shell + navbar
│   │   ├── admin/
│   │   │   ├── dashboard.html # KPI cards + recent sign-ups
│   │   │   ├── users.html     # Paginated user list with search + status filter
│   │   │   └── user_detail.html # Profile, block/unblock, service permissions
│   │   ├── auth/
│   │   │   ├── login.html
│   │   │   ├── signup.html
│   │   │   ├── verify_email.html
│   │   │   ├── forgot_password.html
│   │   │   └── reset_password.html
│   │   ├── dashboard/
│   │   │   └── dashboard.html
│   │   ├── profile/
│   │   │   └── profile.html
│   │   ├── proxy/
│   │   │   ├── list.html      # Paginated proxy list
│   │   │   ├── create.html    # New proxy form
│   │   │   ├── detail.html    # View / inline-edit proxy
│   │   │   └── logs.html      # Paginated request log table
│   │   └── webex/
│   │       ├── list.html      # Configs list
│   │       ├── create.html    # New config form
│   │       ├── detail.html    # Config detail + webhooks panel
│   │       ├── webhook_create.html  # Webhook form + room picker modal
│   │       ├── webhook_logs.html    # Event log table with expand rows
│   │       ├── spaces.html    # AJAX-paginated rooms browser
│   │       └── room_messages.html   # Cursor-paginated message viewer
│   └── static/
│       ├── css/main.css
│       ├── css/admin.css
│       ├── css/webex.css
│       ├── js/main.js
│       └── js/webex.js
├── config.py                  # Config class (reads .env)
├── run.py                     # Entry point
├── .env                       # Secrets (not committed)
├── .gitignore
├── requirements.txt
├── proxy-service.md           # HTTP Proxy service documentation
├── webex-service.md           # Webex Integration service documentation
└── plan.md                    # ← This file
```

---

## Features

| # | Feature | Description |
|---|---------|-------------|
| 1 | User Registration | Username · Email · Password (bcrypt-hashed) |
| 2 | Email OTP Verification | 6-digit code emailed on signup; expires in 10 min |
| 3 | Login | Email + password; blocks unverified accounts |
| 4 | Forgot Password | Email entered → OTP sent; enter OTP + new password |
| 5 | Protected Profile | View info + update username; redirects to login if not authed |
| 6 | Dashboard | Authenticated landing page with account stat cards |
| 7 | HTTP Proxy Service | Per-user proxy configs; endpoint & subdomain delivery modes; CORS bypass; per-request logging with client IP — see [proxy-service.md](proxy-service.md) |
| 8 | Webex Integration Service | Per-user Webex account/bot configs; Bridger-hosted webhook registration with HMAC verification; enriched event log (sender, receiver, room type, message text); AJAX spaces browser with type filter/search; cursor-based message viewer — see [webex-service.md](webex-service.md) |
| 9 | Super Admin System | CLI-created superadmin account; admin dashboard with KPIs; paginated user list with search/filter; per-user block/unblock (force-logout on block); per-user service permissions (proxy granted on signup; webex requires admin approval); service guards on all protected blueprints |

---

## OTP Flows

### Email Verification
```
POST /auth/signup
  → user created (is_verified=False)
  → OTP created in DB (purpose='email_verify', expires in 10 min)
  → OTP emailed to user
  → session['verify_email'] = user.email
  → redirect → /auth/verify-email

POST /auth/verify-email
  → OTP row looked up by (user_id, otp_code, purpose, is_used=False)
  → if valid: is_verified=True; OTP marked used; redirect → /auth/login
  → if invalid/expired: error flash, retry

POST /auth/resend-otp
  → existing unused OTPs invalidated; new OTP created + emailed
```

### Password Reset
```
POST /auth/forgot-password  (email entered)
  → user looked up by email
  → OTP created (purpose='forgot_password') + emailed
  → session['reset_email'] = user.email
  → redirect → /auth/reset-password

POST /auth/reset-password  (OTP + new password entered)
  → OTP verified
  → if valid: password updated; session cleared; redirect → /auth/login
```

---

## Database Models

### `users`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| username | VARCHAR(80) | unique, indexed |
| email | VARCHAR(120) | unique, indexed, stored lowercase |
| password_hash | VARCHAR(255) | bcrypt |
| is_verified | BOOLEAN | default False |
| first_name | VARCHAR(80) | nullable |
| last_name | VARCHAR(80) | nullable |
| is_superadmin | BOOLEAN | default False; set via `flask create-superadmin` only |
| is_blocked | BOOLEAN | default False; blocked users are force-logged-out |
| created_at | DATETIME | UTC |
| updated_at | DATETIME | UTC, auto-updated |

### `otps`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER FK | → users.id CASCADE DELETE |
| otp_code | VARCHAR(6) | 6-digit numeric |
| purpose | VARCHAR(20) | `email_verify` or `forgot_password` |
| expires_at | DATETIME | UTC, 10 min from creation |
| is_used | BOOLEAN | default False |
| created_at | DATETIME | UTC |

### `proxy_configs`
See [proxy-service.md → Data Model](proxy-service.md#data-model).

### `proxy_logs`
See [proxy-service.md → Data Model](proxy-service.md#data-model).

### `webex_configs`
See [webex-service.md → Data Model](webex-service.md#data-model).

### `webex_webhooks`
See [webex-service.md → Data Model](webex-service.md#data-model).

### `webex_webhook_logs`
See [webex-service.md → Data Model](webex-service.md#data-model).

### `user_service_permissions`
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| user_id | INTEGER FK | → users.id CASCADE DELETE, indexed |
| service | VARCHAR(50) | `proxy` or `webex` |
| is_enabled | BOOLEAN | default True |
| granted_at | DATETIME | UTC |
| granted_by_id | INTEGER FK | → users.id SET NULL (nullable — NULL for system grants) |

Unique constraint on `(user_id, service)`. Superadmin bypasses this table entirely — `has_service()` always returns True for superadmins.

---

## Route Map

| Method | Endpoint | Auth Required | Description |
|--------|----------|---------------|-------------|
| GET/POST | `/auth/signup` | No | Register new account |
| GET/POST | `/auth/verify-email` | No | Enter email OTP |
| POST | `/auth/resend-otp` | No | Resend verification OTP |
| GET/POST | `/auth/login` | No | Login |
| GET | `/auth/logout` | Yes | Logout |
| GET/POST | `/auth/forgot-password` | No | Request password reset |
| GET/POST | `/auth/reset-password` | No | Submit OTP + new password |
| GET | `/dashboard` | **Yes** | Dashboard home |
| GET/POST | `/profile` | **Yes** | View/edit profile |
| GET | `/proxies/` | **Yes** | List proxies (paginated) |
| GET/POST | `/proxies/new` | **Yes** | Create proxy |
| GET | `/proxies/<id>` | **Yes** | Proxy detail / inline edit |
| POST | `/proxies/<id>/edit` | **Yes** | Save proxy edits |
| POST | `/proxies/<id>/delete` | **Yes** | Delete proxy |
| POST | `/proxies/<id>/start` | **Yes** | Start proxy |
| POST | `/proxies/<id>/stop` | **Yes** | Stop proxy |
| GET | `/proxies/<id>/logs` | **Yes** | Paginated request log |
| ANY | `/proxy/<slug>/[path]` | No | Endpoint-mode forwarding |
| ANY | `<slug>.localhost/[path]` | No | Subdomain-mode forwarding |
| GET | `/webex/` | **Yes** | List Webex configs (paginated) |
| GET/POST | `/webex/new` | **Yes** | Create Webex config |
| GET | `/webex/<id>` | **Yes** | Config detail + webhooks panel |
| POST | `/webex/<id>/edit` | **Yes** | Edit config name/token |
| POST | `/webex/<id>/delete` | **Yes** | Delete config + cascade |
| POST | `/webex/<id>/verify` | **Yes** | Re-verify token |
| GET/POST | `/webex/<id>/webhooks/new` | **Yes** | Create webhook(s) |
| POST | `/webex/<id>/webhooks/<wh_id>/delete` | **Yes** | Delete Bridger webhook |
| GET | `/webex/<id>/webhooks/<wh_id>/logs` | **Yes** | Event log (paginated) |
| POST | `/webex/<id>/webhooks/<wh_id>/logs/clear` | **Yes** | Clear event logs |
| POST | `/webex/receive/<uuid>` | No | Receive Webex event (CSRF exempt) |
| GET | `/webex/<id>/spaces` | **Yes** | Spaces browser |
| GET | `/webex/<id>/spaces/messages` | **Yes** | Room messages viewer |
| GET | `/webex/<id>/spaces/api` | **Yes** | JSON: rooms (AJAX) |
| GET | `/webex/<id>/spaces/messages/api` | **Yes** | JSON: messages cursor (AJAX) |
| GET | `/admin/` | **Superadmin** | Admin dashboard (KPI stats + recent sign-ups) |
| GET | `/admin/users` | **Superadmin** | Paginated user list with search + status filter |
| GET | `/admin/users/<id>` | **Superadmin** | User detail (profile, block panel, service permissions) |
| POST | `/admin/users/<id>/block` | **Superadmin** | Toggle block/unblock |
| POST | `/admin/users/<id>/services` | **Superadmin** | Update service permissions |

---

## Security Measures

- Passwords hashed with **bcrypt** (salted)
- **CSRF protection** on every form (Flask-WTF)
- OTPs are **cryptographically random** (`secrets` module)
- OTPs **expire in 10 minutes** and are **single-use**
- Previous OTPs for same user+purpose **invalidated** on refresh
- Email enumeration prevented in forgot-password flow (generic flash)
- Login sessions protected via Flask-Login + `SESSION_COOKIE_HTTPONLY`
- Open-redirect prevented: `next` parameter validated against host URL
- Credentials stored only in `.env` (excluded from version control)
- Superadmin created **only** via `flask create-superadmin` CLI — no web endpoint
- Blocked users are force-logged-out on their next request (`before_request` hook)
- Service access enforced by `before_request` guards on each blueprint; superadmin always bypasses
- Proxy service granted automatically on signup; Webex requires explicit admin approval

---

## Development Setup

```bash
# 1. Create virtual environment
python -m venv venv
venv\Scripts\activate      # Windows
source venv/bin/activate   # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env       # then fill in secrets

# 4. Run development server
python run.py
```

App runs at: http://localhost:5000

---

## Delivery Status

- [x] Project plan & structure
- [x] `requirements.txt`
- [x] `.env` configuration
- [x] `config.py`
- [x] Database models (User, OTP)
- [x] Email service
- [x] OTP service
- [x] WTForms (auth + profile)
- [x] Auth routes (all flows)
- [x] Profile route (protected)
- [x] Bootstrap 5 templates (all pages)
- [x] Custom CSS + JS
- [x] Dashboard
- [x] HTTP Proxy service (endpoint + subdomain modes)
- [x] Proxy request logging (DB-persisted, client IP, timing)
- [x] Webex Integration service (config CRUD, token verification)
- [x] Webex webhook management (create, delete Bridger + external)
- [x] Webex event receive + HMAC-SHA1 verification
- [x] Webex event log (enriched: sender, receiver, room type, message text)
- [x] Webex spaces browser (AJAX pagination, type filter, search)
- [x] Webex room messages viewer (cursor-based AJAX load-more)
- [x] Proxy logs UI (paginated table + stats strip)
- [x] Super admin system (CLI creation, user list, block/unblock, service permissions)
- [x] Service permission guards on proxy and webex blueprints
- [x] Dashboard + navbar conditional service rendering
- [ ] Unit tests
- [ ] Deployment config (Gunicorn / Docker)
