"""
app/models/webex_webhook.py
---------------------------
WebexWebhook ORM model — represents a single Webex webhook registered
against a WebexConfig. Each webhook has a unique UUID that appears in
the Bridger receive endpoint URL so incoming events can be routed back
to the right record.
"""

import uuid as _uuid
from datetime import datetime, timezone

from app import db


class WebexWebhook(db.Model):
    """A Webex webhook owned by a WebexConfig."""

    __tablename__ = "webex_webhooks"

    # ── Primary key & ownership ────────────────────────────────────────────────
    id        = db.Column(db.Integer, primary_key=True)
    config_id = db.Column(
        db.Integer,
        db.ForeignKey("webex_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Routing UUID — appears in our receive endpoint URL ────────────────────
    uuid = db.Column(
        db.String(36),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: str(_uuid.uuid4()),
    )

    # ── User-provided fields ───────────────────────────────────────────────────
    name       = db.Column(db.String(200), nullable=False)
    resource   = db.Column(db.String(100), nullable=False)   # messages, rooms, …
    event      = db.Column(db.String(50),  nullable=False)   # created, updated, deleted, all
    filter_str = db.Column(db.String(500), nullable=True)    # optional Webex filter expression

    # ── Target URL ─────────────────────────────────────────────────────────────
    target_url          = db.Column(db.String(500), nullable=False)
    # True  → target is our /webex/receive/<uuid> endpoint → we receive & log events
    # False → target is a custom URL → events go elsewhere → we can't log
    uses_bridger_target = db.Column(db.Boolean, default=True, nullable=False)

    # ── HMAC signing secret (auto-generated; used for signature verification) ─
    secret = db.Column(db.String(100), nullable=True)

    # ── Cached from Webex API response ────────────────────────────────────────
    webex_webhook_id = db.Column(db.String(200), nullable=True)
    webex_status     = db.Column(db.String(50),  nullable=True)   # active / inactive / unknown

    # ── Cached partner email for direct-room webhooks ────────────────────────
    # Populated once at webhook creation for messages resource + roomId filter.
    # Used in receive_event to identify the receiver without extra API calls.
    partner_email = db.Column(db.String(200), nullable=True)

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

    # ── Relationships ──────────────────────────────────────────────────────────
    config = db.relationship(
        "WebexConfig",
        backref=db.backref("webhooks", cascade="all, delete-orphan", lazy="dynamic"),
    )
    logs = db.relationship(
        "WebexWebhookLog",
        backref="webhook",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    # ── Helpers ────────────────────────────────────────────────────────────────
    @property
    def log_count(self) -> int:
        """Total number of received event logs for this webhook."""
        return self.logs.count()

    @property
    def resource_label(self) -> str:
        """Human-readable resource name."""
        _labels = {
            "messages": "Messages",
            "rooms": "Rooms",
            "memberships": "Memberships",
            "meetings": "Meetings",
            "attachmentActions": "Attachment Actions",
            "telephony_calls": "Telephony Calls",
            "all": "All Resources",
        }
        return _labels.get(self.resource, self.resource)

    def __repr__(self) -> str:
        return f"<WebexWebhook id={self.id} name={self.name!r} resource={self.resource}>"
