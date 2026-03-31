# Bridger — Flask Web Application

## Project Overview

A Flask web application with full user authentication (registration, email OTP
verification, login, password reset) and a suite of developer tools — starting
with an **HTTP Proxy** service for forwarding requests and bypassing CORS.

> **Service documentation**
> - HTTP Proxy service → see [proxy-service.md](proxy-service.md)

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
│   │   ├── proxy.py           # ProxyConfig model
│   │   └── proxy_log.py       # ProxyLog model (per-request audit log)
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py            # signup, login, logout, verify-email,
│   │   │                      #   forgot-password, reset-password
│   │   ├── profile.py         # protected /profile + landing index
│   │   ├── dashboard.py       # protected /dashboard
│   │   ├── proxy_manager.py   # CRUD + lifecycle for proxy configs
│   │   └── proxy_handler.py   # Live request forwarding + subdomain hook
│   ├── services/
│   │   ├── __init__.py
│   │   ├── email_service.py   # SMTP email sender + template helpers
│   │   └── otp_service.py     # OTP generation, storage, verification
│   ├── forms/
│   │   ├── __init__.py
│   │   ├── auth_forms.py      # WTForms: Signup, Login, Verify,
│   │   │                      #   ForgotPassword, ResetPassword, UpdateProfile
│   │   └── proxy_forms.py     # ProxyCreateForm, ProxyEditForm
│   ├── templates/
│   │   ├── base.html          # Bootstrap 5 shell + navbar
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
│   │   └── proxy/
│   │       ├── list.html      # Paginated proxy list
│   │       ├── create.html    # New proxy form
│   │       ├── detail.html    # View / inline-edit proxy
│   │       └── logs.html      # Paginated request log table
│   └── static/
│       ├── css/main.css
│       └── js/main.js
├── config.py                  # Config class (reads .env)
├── run.py                     # Entry point
├── .env                       # Secrets (not committed)
├── .gitignore
├── requirements.txt
├── proxy-service.md           # HTTP Proxy service documentation
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
- [x] Proxy logs UI (paginated table + stats strip)
- [ ] Unit tests
- [ ] Deployment config (Gunicorn / Docker)
