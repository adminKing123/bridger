"""
app/models/admin.py
-------------------
Admin-related models:
  - UserServicePermission : which services each user is allowed to access
"""

from datetime import datetime, timezone
from app import db

# Canonical list of service identifiers in the platform
SERVICES = ("proxy", "webex", "syncore")


class UserServicePermission(db.Model):
    """
    Controls which Bridger services a user can access.
    One row per (user, service) pair.

    The unique constraint on (user_id, service) ensures there is never more
    than one permission record for a given user + service combination.
    """

    __tablename__ = "user_service_permissions"

    id: int = db.Column(db.Integer, primary_key=True)
    user_id: int = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    service: str = db.Column(db.String(50), nullable=False)
    is_enabled: bool = db.Column(db.Boolean, default=True, nullable=False)
    granted_at: datetime = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    # The admin user who last changed this permission (nullable for system grants)
    granted_by_id: int | None = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    user = db.relationship(
        "User",
        foreign_keys=[user_id],
        back_populates="service_permissions",
    )
    granted_by = db.relationship("User", foreign_keys=[granted_by_id])

    __table_args__ = (
        db.UniqueConstraint("user_id", "service", name="uq_user_service"),
    )

    def __repr__(self) -> str:
        return (
            f"<UserServicePermission user_id={self.user_id} "
            f"service={self.service!r} enabled={self.is_enabled}>"
        )
