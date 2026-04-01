"""
app/models/__init__.py
----------------------
Exposes all models for convenient importing:
    from app.models import User, OTP, ProxyConfig, WebexConfig,
                           WebexWebhook, WebexWebhookLog,
                           UserServicePermission
"""

from app.models.user import User, OTP
from app.models.proxy import ProxyConfig
from app.models.webex_config import WebexConfig
from app.models.webex_webhook import WebexWebhook
from app.models.webex_webhook_log import WebexWebhookLog
from app.models.admin import UserServicePermission

__all__ = [
    "User", "OTP",
    "ProxyConfig",
    "WebexConfig",
    "WebexWebhook",
    "WebexWebhookLog",
    "UserServicePermission",
]
