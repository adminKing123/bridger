"""
app/routes/dashboard.py
------------------------
Dashboard blueprint — all routes require login.

Routes:
    GET  /dashboard  — Main dashboard (protected)
"""

import logging

from flask import Blueprint, render_template
from flask_login import login_required, current_user

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    """Render the main application dashboard."""
    return render_template("dashboard/dashboard.html")
