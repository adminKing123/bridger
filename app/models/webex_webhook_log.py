"""
app/models/webex_webhook_log.py
--------------------------------
WebexWebhookLog ORM model — one row per event received at our
/webex/receive/<uuid> endpoint. Stores the complete Webex event
envelope plus signature-verification result.
"""

from datetime import datetime, timezone

from app import db


class WebexWebhookLog(db.Model):
    """One received Webex webhook event."""

    __tablename__ = "webex_webhook_logs"

    # ── Primary key & ownership ────────────────────────────────────────────────
    id         = db.Column(db.Integer, primary_key=True)
    webhook_id = db.Column(
        db.Integer,
        db.ForeignKey("webex_webhooks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Request metadata ───────────────────────────────────────────────────────
    received_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )
    client_ip = db.Column(db.String(50), nullable=True)

    # ── Webex event envelope fields ────────────────────────────────────────────
    # Webex-assigned unique event ID
    webex_event_id = db.Column(db.String(200), nullable=True)

    # Resource that triggered the event (messages, rooms, memberships, …)
    resource       = db.Column(db.String(100), nullable=True)

    # Event type that was fired (created, updated, deleted, …)
    event_type     = db.Column(db.String(50),  nullable=True)

    # Person ID of the actor who triggered the event
    actor_id       = db.Column(db.String(200), nullable=True)

    # Organisation ID from the event envelope
    org_id         = db.Column(db.String(200), nullable=True)

    # App ID (the app that owns the webhook)
    app_id         = db.Column(db.String(200), nullable=True)

    # Ownership scope returned by Webex (creator / org)
    owned_by       = db.Column(db.String(50),  nullable=True)

    # ── Payload storage ────────────────────────────────────────────────────────
    # The "data" sub-object from the event (serialised JSON)
    data_json   = db.Column(db.Text, nullable=True)

    # The full raw request body as received (serialised JSON)
    raw_payload = db.Column(db.Text, nullable=True)

    # ── Enriched resource data (fetched from Webex API after delivery) ─────────
    # For messages.created: plain text body of the message
    message_text     = db.Column(db.Text,          nullable=True)
    # For messages.created: markdown body of the message (if present)
    message_markdown = db.Column(db.Text,          nullable=True)
    # For messages.created: rendered HTML from Webex (if present)
    message_html     = db.Column(db.Text,          nullable=True)
    # For messages.created: JSON array of file attachment URLs
    message_files    = db.Column(db.Text,          nullable=True)
    # Full enriched resource object fetched from the API (serialised JSON)
    resource_json    = db.Column(db.Text,          nullable=True)

    # ── Sender / receiver (resolved from Webex People API) ────────────────────
    sender_name      = db.Column(db.String(200),   nullable=True)
    sender_email     = db.Column(db.String(200),   nullable=True)
    receiver_name    = db.Column(db.String(200),   nullable=True)
    receiver_email   = db.Column(db.String(200),   nullable=True)

    # ── Space / room type ─────────────────────────────────────────────────────
    # "direct" → 1:1 conversation, "group" → space with 3+ members, None → unknown
    room_type        = db.Column(db.String(20),    nullable=True)

    # ── Signature verification ─────────────────────────────────────────────────
    # True  → HMAC-SHA1 signature matched our stored secret
    # False → signature mismatch (possible tampered request)
    # None  → verification was skipped (no secret or custom target)
    signature_valid = db.Column(db.Boolean, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<WebexWebhookLog id={self.id} "
            f"resource={self.resource} event={self.event_type}>"
        )
