"""
app/models/proxy_log.py
------------------------
ProxyLog ORM model — stores one record for every request forwarded through
a proxy, including the client IP and basic response metadata.
"""

from datetime import datetime

from app import db


class ProxyLog(db.Model):
    """
    Audit log entry for a single proxied HTTP request.

    Each row is written by proxy_handler after (or during) forwarding.
    Rows are linked to ProxyConfig via proxy_id; deleting the proxy
    cascades deletion to its logs.
    """

    __tablename__ = "proxy_logs"

    id         = db.Column(db.Integer,  primary_key=True)
    proxy_id   = db.Column(
        db.Integer,
        db.ForeignKey("proxy_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Request metadata ───────────────────────────────────────────────────────
    method      = db.Column(db.String(10),  nullable=False)          # GET, POST, …
    path        = db.Column(db.String(500), nullable=False)          # forwarded path
    status_code = db.Column(db.Integer,     nullable=True)           # upstream status
    client_ip   = db.Column(db.String(45),  nullable=False)          # IPv4 or IPv6
    duration_ms = db.Column(db.Integer,     nullable=True)           # round-trip ms

    # ── Timestamp ──────────────────────────────────────────────────────────────
    created_at  = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    # ── Relationship ───────────────────────────────────────────────────────────
    proxy = db.relationship(
        "ProxyConfig",
        backref=db.backref("logs", lazy="dynamic", cascade="all, delete-orphan"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ProxyLog proxy={self.proxy_id} {self.method} {self.status_code}>"
