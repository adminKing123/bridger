"""
app/models/syncore_access.py
-----------------------------
Models for SynCore employee access control:

  - SynCoreEmployeeRequest : a user's request to access a SynCore employee
  - UserEmployeeAccess     : approved junction record (user ↔ employee + permission)

Access lifecycle:
    User submits request (pending)
      ↓
    Admin approves  → UserEmployeeAccess row created  (viewer | editor)
    Admin rejects   → status = rejected, user can re-request
    Admin revokes   → UserEmployeeAccess.is_active = False
"""

from datetime import datetime, timezone

from app import db


class SynCoreEmployeeRequest(db.Model):
    """
    Tracks a user's request to be granted access to a SynCore employee profile.

    Statuses:
        pending  — awaiting admin review
        approved — admin approved; a UserEmployeeAccess row exists
        rejected — admin rejected; user may re-request by submitting again
    """

    __tablename__ = "syncore_employee_requests"

    # ── Status constants ──────────────────────────────────────────────────────
    STATUS_PENDING  = "pending"
    STATUS_APPROVED = "approved"
    STATUS_REJECTED = "rejected"

    # ── Permission constants ──────────────────────────────────────────────────
    PERMISSION_VIEWER = "viewer"
    PERMISSION_EDITOR = "editor"

    # ── Columns ───────────────────────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("syncore_employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Email the user searched for (preserved for audit purposes)
    employee_email = db.Column(db.String(200), nullable=False)

    # Permission level requested by the user
    requested_permission = db.Column(
        db.String(20), nullable=False, default=PERMISSION_VIEWER
    )

    # Current status of the request
    status = db.Column(
        db.String(20), nullable=False, default=STATUS_PENDING, index=True
    )

    # Optional note from admin on rejection
    rejection_reason = db.Column(db.String(500), nullable=True)

    # ── Timestamps & review metadata ──────────────────────────────────────────
    requested_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    reviewed_at    = db.Column(db.DateTime, nullable=True)
    reviewed_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user        = db.relationship("User", foreign_keys=[user_id])
    employee    = db.relationship("SynCoreEmployee", foreign_keys=[employee_id])
    reviewed_by = db.relationship("User", foreign_keys=[reviewed_by_id])

    def __repr__(self) -> str:
        return (
            f"<SynCoreEmployeeRequest id={self.id} "
            f"user_id={self.user_id} employee_id={self.employee_id} "
            f"status={self.status!r}>"
        )

    @property
    def is_pending(self) -> bool:
        return self.status == self.STATUS_PENDING

    @property
    def is_approved(self) -> bool:
        return self.status == self.STATUS_APPROVED

    @property
    def is_rejected(self) -> bool:
        return self.status == self.STATUS_REJECTED


class UserEmployeeAccess(db.Model):
    """
    Approved access granting a user the right to view or interact with a
    SynCore employee profile.

    Permissions:
        viewer — read-only (details, attendance, projects, work logs)
        editor — all of viewer + login / logout actions

    Created when an admin approves a SynCoreEmployeeRequest.
    Revoked by setting is_active = False.
    """

    __tablename__ = "user_employee_access"

    # ── Permission constants ──────────────────────────────────────────────────
    PERMISSION_VIEWER = "viewer"
    PERMISSION_EDITOR = "editor"

    # ── Columns ───────────────────────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    employee_id = db.Column(
        db.Integer,
        db.ForeignKey("syncore_employees.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # viewer | editor
    permission = db.Column(db.String(20), nullable=False, default=PERMISSION_VIEWER)

    # False when admin revokes access
    is_active = db.Column(db.Boolean, default=True, nullable=False, index=True)

    # Reference back to the originating request (nullable — admin could grant directly)
    request_id = db.Column(
        db.Integer,
        db.ForeignKey("syncore_employee_requests.id", ondelete="SET NULL"),
        nullable=True,
    )

    granted_at     = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    granted_by_id  = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationships ─────────────────────────────────────────────────────────
    user       = db.relationship("User", foreign_keys=[user_id])
    employee   = db.relationship("SynCoreEmployee", foreign_keys=[employee_id])
    granted_by = db.relationship("User", foreign_keys=[granted_by_id])
    request    = db.relationship("SynCoreEmployeeRequest", foreign_keys=[request_id])

    __table_args__ = (
        db.UniqueConstraint("user_id", "employee_id", name="uq_user_employee_access"),
    )

    def __repr__(self) -> str:
        return (
            f"<UserEmployeeAccess id={self.id} "
            f"user_id={self.user_id} employee_id={self.employee_id} "
            f"permission={self.permission!r} active={self.is_active}>"
        )

    @property
    def can_edit(self) -> bool:
        """True when permission level includes action capabilities."""
        return self.permission == self.PERMISSION_EDITOR and self.is_active
