"""
app/models/__init__.py
----------------------
Exposes all models for convenient importing:
    from app.models import User, OTP, ProxyConfig, WebexConfig
"""

from app.models.user import User, OTP
from app.models.proxy import ProxyConfig
from app.models.webex_config import WebexConfig

__all__ = ["User", "OTP", "ProxyConfig", "WebexConfig"]
