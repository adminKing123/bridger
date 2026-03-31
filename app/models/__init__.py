"""
app/models/__init__.py
----------------------
Exposes all models for convenient importing:
    from app.models import User, OTP, ProxyConfig
"""

from app.models.user import User, OTP
from app.models.proxy import ProxyConfig

__all__ = ["User", "OTP", "ProxyConfig"]
