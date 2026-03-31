"""
app/routes/profile.py
----------------------
Profile blueprint — all routes require login.

Routes:
    GET       /      — redirects to /profile
    GET/POST  /profile — view and update the authenticated user's profile
"""

import logging

from flask import Blueprint, render_template, redirect, url_for, flash
from flask_login import login_required, current_user

from app import db
from app.forms.auth_forms import UpdateProfileForm

logger = logging.getLogger(__name__)

profile_bp = Blueprint("profile", __name__)


@profile_bp.route("/")
def index():
    """Root URL — redirect authenticated users to the dashboard, others to login."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))
    return redirect(url_for("auth.login"))


@profile_bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    """
    Display and update the current user's profile.

    GET  — pre-fills form with current username.
    POST — validates and saves an updated username.
    """
    form = UpdateProfileForm(
        original_username=current_user.username,
        obj=current_user,
    )

    if form.validate_on_submit():
        current_user.username = form.username.data.strip()
        current_user.first_name = form.first_name.data.strip()
        current_user.last_name = form.last_name.data.strip() if form.last_name.data else None
        db.session.commit()
        logger.info("Profile updated for user: %s", current_user.email)
        flash("Profile updated successfully!", "success")
        return redirect(url_for("profile.profile"))

    return render_template("profile/profile.html", form=form)
