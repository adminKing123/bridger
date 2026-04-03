"""
app/models/syncore_employee.py
-------------------------------
SynCore HRMS Employee data model.

Stores employee information synced from the SynCore HRMS API.
"""

from datetime import datetime, timezone, date
from app import db


class SynCoreEmployee(db.Model):
    """
    Represents an employee synced from the SynCore HRMS system.
    
    This table mirrors the employee data from the external HRMS API,
    allowing local queries and reporting without repeatedly hitting
    the external service.
    """

    __tablename__ = "syncore_employees"

    id: int = db.Column(db.Integer, primary_key=True)
    
    # ── Core identifiers ──────────────────────────────────────────────────────
    user_id: str = db.Column(db.String(50), nullable=False, index=True)
    employee_id: str = db.Column(db.String(50), unique=True, nullable=False, index=True)
    signed_array: str = db.Column(db.String(255), nullable=True)
    
    # ── Personal information ──────────────────────────────────────────────────
    name: str = db.Column(db.String(200), nullable=False, index=True)
    email: str = db.Column(db.String(200), nullable=True, index=True)
    gender: str = db.Column(db.String(20), nullable=True)
    
    # ── Organization details ──────────────────────────────────────────────────
    firm_id: str = db.Column(db.String(50), nullable=True, index=True)
    firm_name: str = db.Column(db.String(200), nullable=True)
    org_team_id: str = db.Column(db.String(50), nullable=True)
    org_name: str = db.Column(db.String(200), nullable=True)
    is_org_manager: bool = db.Column(db.Boolean, default=False, nullable=False)
    
    # ── Job details ───────────────────────────────────────────────────────────
    designation: str = db.Column(db.String(200), nullable=True)
    user_type: str = db.Column(db.String(50), nullable=True)  # Employee, Intern, etc.
    status: str = db.Column(db.String(50), nullable=True, index=True)  # Active, In-Active
    
    # ── Team & reporting ──────────────────────────────────────────────────────
    team_lead_id: str = db.Column(db.String(50), nullable=True)
    team_lead_name: str = db.Column(db.String(200), nullable=True)
    
    # ── Work timing ───────────────────────────────────────────────────────────
    reporting_time: str = db.Column(db.String(20), nullable=True)
    working_hours: str = db.Column(db.String(20), nullable=True)
    monthly_worklog_hours: str = db.Column(db.String(20), nullable=True)
    
    # ── Dates ─────────────────────────────────────────────────────────────────
    joining_date: date = db.Column(db.Date, nullable=True, index=True)
    leaving_date: date = db.Column(db.Date, nullable=True)
    training_completion_date: date = db.Column(db.Date, nullable=True)
    
    # ── Leave balances ────────────────────────────────────────────────────────
    comp_off: str = db.Column(db.String(20), nullable=True)
    emergency_leave: str = db.Column(db.String(20), nullable=True)
    casual_leave: str = db.Column(db.String(20), nullable=True)
    extended_leave: str = db.Column(db.String(20), nullable=True)
    
    # ── Other attributes ──────────────────────────────────────────────────────
    syn_coin: str = db.Column(db.String(20), nullable=True)
    overrides: str = db.Column(db.String(20), nullable=True)
    
    # ── Audit fields ──────────────────────────────────────────────────────────
    created_by: str = db.Column(db.String(200), nullable=True)
    modified_by: str = db.Column(db.String(200), nullable=True)
    
    # ── Sync tracking ─────────────────────────────────────────────────────────
    last_synced_at: datetime = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    created_at: datetime = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def __repr__(self) -> str:
        return (
            f"<SynCoreEmployee id={self.id} "
            f"employee_id={self.employee_id!r} "
            f"name={self.name!r}>"
        )
    
    @property
    def is_active(self) -> bool:
        """Check if the employee is currently active."""
        return self.status and self.status.lower() == "active"
    
    @property
    def formatted_joining_date(self) -> str:
        """Return formatted joining date or empty string."""
        if self.joining_date:
            return self.joining_date.strftime("%b %d, %Y")
        return "—"
    
    @property
    def formatted_leaving_date(self) -> str:
        """Return formatted leaving date or empty string."""
        if self.leaving_date:
            return self.leaving_date.strftime("%b %d, %Y")
        return "—"
