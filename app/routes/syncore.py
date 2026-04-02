"""
app/routes/syncore.py
---------------------
SynCore — Organisational Synapses HRMS Data Panel.

All management routes require authentication plus the 'syncore' service
permission (enforced via the before_request hook, same pattern as proxy and
webex services).

Routes
------
GET    /syncore/           — landing / dashboard page
GET    /syncore/api/stats  — stats stub (returns {"status": "coming_soon"})
"""

import logging

from flask import Blueprint, flash, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)

syncore_bp = Blueprint("syncore", __name__, url_prefix="/syncore")


# ── Blueprint-level service guard ─────────────────────────────────────────────

@syncore_bp.before_request
def _require_syncore_service():
    """
    Block access for users whose syncore service has not been granted.
    Unauthenticated requests are handled by @login_required on each view.
    """
    if not current_user.is_authenticated:
        return None
    if current_user.is_superadmin:
        return None
    from app.models.admin import UserServicePermission
    perm = UserServicePermission.query.filter_by(
        user_id=current_user.id, service="syncore", is_enabled=True
    ).first()
    if not perm:
        flash(
            "SynCore has not been enabled for your account. "
            "Contact the administrator to request access.",
            "warning",
        )
        return redirect(url_for("dashboard.dashboard"))
    return None


# ── Routes ────────────────────────────────────────────────────────────────────

@syncore_bp.route("/")
@login_required
def index():
    """SynCore landing page."""
    return render_template("syncore/index.html")


@syncore_bp.route("/api/stats")
@login_required
def api_stats():
    """
    SynCore statistics stub.

    Returns a 'coming_soon' status — the real implementation will replace this
    once SynCore features are built out.
    """
    return jsonify({"status": "coming_soon"})
