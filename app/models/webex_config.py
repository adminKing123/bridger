"""
app/models/webex_config.py
--------------------------
WebexConfig ORM model — stores Webex integration configurations
managed by authenticated users.

Each record holds a user-provided access token and caches the
profile data returned by the Webex API (people/me) at last
verification.
"""

from datetime import datetime, timezone

from app import db


class WebexConfig(db.Model):
    """Represents a single user-managed Webex integration configuration."""

    __tablename__ = "webex_configs"

    # ── Primary key & ownership ────────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── User-provided fields ───────────────────────────────────────────────────
    name         = db.Column(db.String(120), nullable=False)   # human label
    access_token = db.Column(db.String(500), nullable=False)   # Webex bearer token

    # ── Cached from Webex API (people/me) ─────────────────────────────────────
    webex_person_id   = db.Column(db.String(200), nullable=True)
    webex_display_name = db.Column(db.String(200), nullable=True)
    webex_email       = db.Column(db.String(200), nullable=True)
    webex_org_id      = db.Column(db.String(200), nullable=True)

    # ── Verification state ─────────────────────────────────────────────────────
    is_verified     = db.Column(db.Boolean, default=False, nullable=False)
    last_verified_at = db.Column(db.DateTime, nullable=True)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationship ───────────────────────────────────────────────────────────
    owner = db.relationship(
        "User",
        backref=db.backref("webex_configs", cascade="all, delete-orphan"),
    )

    # ── Helpers ────────────────────────────────────────────────────────────────
    @property
    def display_email(self) -> str:
        """Return first cached email or an em-dash if not yet verified."""
        return self.webex_email or "—"

    @property
    def initials(self) -> str:
        """Return up to two initials from webex_display_name for the avatar."""
        if not self.webex_display_name:
            return "?"
        parts = self.webex_display_name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.webex_display_name[:2].upper()

    @property
    def masked_token(self) -> str:
        """Return the token with only the last 4 chars visible."""
        if len(self.access_token) <= 8:
            return "••••••••"
        return "•" * (len(self.access_token) - 4) + self.access_token[-4:]

    def __repr__(self) -> str:
        return f"<WebexConfig id={self.id} name={self.name!r} verified={self.is_verified}>"
