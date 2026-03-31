"""
app/models/user.py
------------------
SQLAlchemy ORM models:
  - User  : registered accounts
  - OTP   : one-time passwords for email verification and password reset
"""

from datetime import datetime, timezone
from flask_login import UserMixin
from app import db


class User(UserMixin, db.Model):
    """
    Represents a registered user account.

    Inherits UserMixin to satisfy Flask-Login's required interface:
        is_authenticated, is_active, is_anonymous, get_id()
    """

    __tablename__ = "users"

    id: int = db.Column(db.Integer, primary_key=True)
    username: str = db.Column(db.String(80), unique=True, nullable=False, index=True)
    email: str = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash: str = db.Column(db.String(255), nullable=False)
    is_verified: bool = db.Column(db.Boolean, default=False, nullable=False)
    first_name: str = db.Column(db.String(80), nullable=True)
    last_name: str = db.Column(db.String(80), nullable=True)
    created_at: datetime = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: datetime = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # One-to-many relationship with OTP records
    otps = db.relationship("OTP", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"


class OTP(db.Model):
    """
    Stores one-time passwords for email verification and password reset.

    Purpose constants:
        OTP_PURPOSE_EMAIL_VERIFY    = 'email_verify'
        OTP_PURPOSE_FORGOT_PASSWORD = 'forgot_password'
    """

    __tablename__ = "otps"

    # Purpose identifier constants
    OTP_PURPOSE_EMAIL_VERIFY: str = "email_verify"
    OTP_PURPOSE_FORGOT_PASSWORD: str = "forgot_password"

    id: int = db.Column(db.Integer, primary_key=True)
    user_id: int = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    otp_code: str = db.Column(db.String(6), nullable=False)
    purpose: str = db.Column(db.String(20), nullable=False)
    expires_at: datetime = db.Column(db.DateTime, nullable=False)
    is_used: bool = db.Column(db.Boolean, default=False, nullable=False)
    created_at: datetime = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    # Many-to-one back-reference to User
    user = db.relationship("User", back_populates="otps")

    # ── Helper methods ────────────────────────────────────────────────────────

    def is_expired(self) -> bool:
        """Return True if the OTP has passed its expiry time."""
        now = datetime.now(timezone.utc)
        # SQLite stores naive datetimes; ensure we compare in UTC
        expires = (
            self.expires_at
            if self.expires_at.tzinfo is not None
            else self.expires_at.replace(tzinfo=timezone.utc)
        )
        return now > expires

    def is_valid(self) -> bool:
        """Return True if the OTP has not been used and has not expired."""
        return not self.is_used and not self.is_expired()

    def __repr__(self) -> str:
        return f"<OTP id={self.id} purpose={self.purpose!r} user_id={self.user_id}>"
