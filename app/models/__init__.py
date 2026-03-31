"""
app/models/__init__.py
----------------------
Exposes all models for convenient importing:
    from app.models import User, OTP
"""

from app.models.user import User, OTP

__all__ = ["User", "OTP"]
