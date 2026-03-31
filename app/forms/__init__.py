"""
app/forms/__init__.py
----------------------
Forms package — exposes all WTForms form classes.
"""

from app.forms.auth_forms import (
    SignupForm,
    LoginForm,
    VerifyEmailForm,
    ForgotPasswordForm,
    ResetPasswordForm,
    UpdateProfileForm,
)

__all__ = [
    "SignupForm",
    "LoginForm",
    "VerifyEmailForm",
    "ForgotPasswordForm",
    "ResetPasswordForm",
    "UpdateProfileForm",
]
