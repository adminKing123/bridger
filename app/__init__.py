"""
app/__init__.py
---------------
Application factory. Creates and configures the Flask app, initialises all
extensions, and registers blueprints.
"""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf import CSRFProtect

from config import DevelopmentConfig

# ── Extension instances (initialised against the app inside create_app) ───────
db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()
csrf = CSRFProtect()


@login_manager.user_loader
def load_user(user_id: str):
    """Flask-Login callback — loads a User from the session's user_id."""
    from app.models.user import User  # local import avoids circular dependency
    return db.session.get(User, int(user_id))


def create_app(config_class=DevelopmentConfig) -> Flask:
    """
    Create and configure the Flask application.

    Args:
        config_class: A Config class (default: DevelopmentConfig).

    Returns:
        Configured Flask application instance.
    """
    app = Flask(__name__)
    app.config.from_object(config_class)

    # ── Initialise extensions ─────────────────────────────────────────────────
    db.init_app(app)
    login_manager.init_app(app)
    bcrypt.init_app(app)

    # Subdomain-proxy requests are plain cross-origin API calls — they never
    # carry a CSRF token.  Register the handler BEFORE csrf.init_app so it
    # runs first and returns a response before Flask-WTF's protect() hook
    # fires.  When handle_subdomain_proxy returns None (non-proxy request)
    # all subsequent before_request hooks (including CSRF) run normally.
    from app.routes.proxy_handler import handle_subdomain_proxy
    app.before_request(handle_subdomain_proxy)

    csrf.init_app(app)

    # ── Login manager settings ────────────────────────────────────────────────
    login_manager.login_view = "auth.login"           # type: ignore[assignment]
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    # ── Register blueprints ───────────────────────────────────────────────────
    from app.routes.auth import auth_bp
    from app.routes.profile import profile_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.proxy_manager import proxy_manager_bp
    from app.routes.proxy_handler import proxy_handler_bp
    from app.routes.webex import webex_bp
    from app.routes.syncore import syncore_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(proxy_manager_bp)
    app.register_blueprint(proxy_handler_bp)

    # Proxy routes are called cross-origin by external clients — they must
    # never require a CSRF token.  Exempt the entire blueprint so Flask-WTF
    # does not reject OPTIONS preflights or POST/PUT/DELETE requests.
    csrf.exempt(proxy_handler_bp)

    app.register_blueprint(webex_bp)
    app.register_blueprint(syncore_bp)
    app.register_blueprint(admin_bp)

    # ── CORS for proxy paths (app-level, covers both endpoint + subdomain) ────
    # This after_request runs for EVERY response, including ones returned by
    # before_request hooks (which blueprint-level after_request misses).
    # We only inject headers for actual proxy traffic so the rest of the app
    # is unaffected.
    @app.after_request
    def _proxy_cors_headers(response):
        from flask import request as _req
        host     = _req.host
        hostname = host.split(":")[0]
        parts    = hostname.rsplit(".", 1)
        is_subdomain_proxy = (
            len(parts) == 2
            and parts[1] == "localhost"
            and parts[0] not in ("www", "localhost")
        )
        is_endpoint_proxy = _req.path.startswith("/proxy/")
        if not (is_endpoint_proxy or is_subdomain_proxy):
            return response
        # Always allow the browser to reach proxy endpoints.
        # The per-proxy cors_bypass / cors_origins settings control finer-grained
        # origin filtering inside _forward(); here we just unblock the pre-flight.
        if "Access-Control-Allow-Origin" not in response.headers:
            response.headers["Access-Control-Allow-Origin"] = "*"
        if _req.method == "OPTIONS":
            response.headers.setdefault("Access-Control-Allow-Headers", "*")
            response.headers.setdefault("Access-Control-Allow-Methods",
                                        "GET, POST, PUT, DELETE, PATCH, OPTIONS")
            response.headers.setdefault("Access-Control-Max-Age", "86400")
        return response

    # ── Custom Jinja2 filters ─────────────────────────────────────────────────
    @app.template_filter('to_date_input')
    def to_date_input(value: str) -> str:
        """Convert MM/DD/YYYY date string to YYYY-MM-DD for HTML date inputs."""
        try:
            from datetime import datetime
            return datetime.strptime(value, "%m/%d/%Y").strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            return value or ""

    # ── Force-logout blocked users on every request ───────────────────────────
    @app.before_request
    def _check_blocked_user():
        from flask import flash, redirect, url_for
        from flask_login import current_user, logout_user
        if (
            current_user.is_authenticated
            and not current_user.is_superadmin
            and current_user.is_blocked
        ):
            logout_user()
            flash(
                "Your account has been blocked. Please contact the administrator.",
                "danger",
            )
            return redirect(url_for("auth.login"))

    # ── Create database tables ────────────────────────────────────────────────
    with app.app_context():
        db.create_all()

    return app
