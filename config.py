"""
config.py
---------
Application configuration. Values are read from the environment / .env file.
"""

import os
from dotenv import load_dotenv

# Load .env before any other config access
load_dotenv()

# Absolute path to the project root directory
_BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    """Base configuration shared across all environments."""

    # ── Security ──────────────────────────────────────────────────────────────
    SECRET_KEY: str = os.environ.get(
        "SECRET_KEY",
        "dev-secret-key-replace-me-in-production",
    )

    # ── Database ──────────────────────────────────────────────────────────────
    SQLALCHEMY_DATABASE_URI: str = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{os.path.join(_BASE_DIR, 'data.sqlite3')}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS: bool = False

    # ── Email (SMTP) ──────────────────────────────────────────────────────────
    SMTP_HOST: str = os.environ.get("SMTP_HOST", "smtp.gmail.com")
    SMTP_PORT: int = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USER: str | None = os.environ.get("SMTP_USER")
    SMTP_APP_PASSWORD: str | None = os.environ.get("SMTP_APP_PASSWORD")

    # ── OTP ───────────────────────────────────────────────────────────────────
    OTP_EXPIRY_MINUTES: int = int(os.environ.get("OTP_EXPIRY_MINUTES", 10))

    # ── Session / Cookie security ─────────────────────────────────────────────
    SESSION_COOKIE_HTTPONLY: bool = True
    SESSION_COOKIE_SAMESITE: str = "Lax"


class DevelopmentConfig(Config):
    """Development-specific configuration."""

    DEBUG: bool = True


class ProductionConfig(Config):
    """Production-specific configuration — enforce strong secret key."""

    DEBUG: bool = False
    SESSION_COOKIE_SECURE: bool = True   # Only send cookies over HTTPS


# Mapping of environment name → config class
config_map: dict = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}
