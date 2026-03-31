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
    csrf.init_app(app)

    # ── Login manager settings ────────────────────────────────────────────────
    login_manager.login_view = "auth.login"           # type: ignore[assignment]
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "warning"

    # ── Register blueprints ───────────────────────────────────────────────────
    from app.routes.auth import auth_bp
    from app.routes.profile import profile_bp
    from app.routes.dashboard import dashboard_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(dashboard_bp)

    # ── Create database tables ────────────────────────────────────────────────
    with app.app_context():
        db.create_all()

    return app
