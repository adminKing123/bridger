"""
app/routes/webex.py
--------------------
Webex integration blueprint — CRUD for Webex access-token configurations.
The token is verified against the Webex people/me API on create, edit,
and explicit re-verify. Profile data is cached on the record.

Routes
------
GET         /webex/             — list user's Webex configs (paginated)
GET/POST    /webex/new          — create a new config
GET         /webex/<id>         — view config detail
POST        /webex/<id>/edit    — save name / token edits
POST        /webex/<id>/delete  — permanently delete a config
POST        /webex/<id>/verify  — re-verify the stored token
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.forms.webex_forms import WebexCreateForm, WebexEditForm
from app.models.webex_config import WebexConfig
from app.services.webex_service import verify_token

logger = logging.getLogger(__name__)

webex_bp = Blueprint("webex", __name__, url_prefix="/webex")


# ── Internal helper ────────────────────────────────────────────────────────────

def _own_config_or_404(config_id: int) -> WebexConfig:
    """Return the WebexConfig owned by current_user, or abort with 404."""
    cfg = WebexConfig.query.filter_by(id=config_id, user_id=current_user.id).first()
    if not cfg:
        abort(404)
    return cfg


def _apply_verification(cfg: WebexConfig, profile: dict) -> None:
    """Cache API profile fields onto the config record and mark verified."""
    cfg.webex_person_id    = profile.get("id", "")
    cfg.webex_display_name = profile.get("displayName", "")
    cfg.webex_email        = (profile.get("emails") or [""])[0]
    cfg.webex_org_id       = profile.get("orgId", "")
    cfg.is_verified        = True
    cfg.last_verified_at   = datetime.now(timezone.utc)


# ── List ───────────────────────────────────────────────────────────────────────

@webex_bp.route("/")
@login_required
def index():
    """Display all Webex configurations belonging to the current user."""
    page = request.args.get("page", 1, type=int)
    configs = (
        WebexConfig.query
        .filter_by(user_id=current_user.id)
        .order_by(WebexConfig.created_at.desc())
        .paginate(page=page, per_page=20, error_out=False)
    )
    return render_template("webex/list.html", configs=configs)


# ── Create ─────────────────────────────────────────────────────────────────────

@webex_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_config():
    """Create a new Webex configuration. Verifies the token on save."""
    form = WebexCreateForm()

    if form.validate_on_submit():
        profile = verify_token(form.access_token.data)

        cfg = WebexConfig(
            user_id=current_user.id,
            name=form.name.data.strip(),
            access_token=form.access_token.data,
        )

        if profile:
            _apply_verification(cfg, profile)
            flash("Webex configuration saved and verified successfully.", "success")
        else:
            cfg.is_verified = False
            flash(
                "Configuration saved, but the token could not be verified. "
                "Check the token and use Verify to retry.",
                "warning",
            )

        db.session.add(cfg)
        db.session.commit()
        return redirect(url_for("webex.detail_config", config_id=cfg.id))

    return render_template("webex/create.html", form=form)


# ── Detail ─────────────────────────────────────────────────────────────────────

@webex_bp.route("/<int:config_id>")
@login_required
def detail_config(config_id: int):
    """Display details of a single Webex configuration."""
    cfg = _own_config_or_404(config_id)
    form = WebexEditForm(obj=cfg)
    # Don't pre-fill the token field
    form.access_token.data = ""
    return render_template("webex/detail.html", cfg=cfg, form=form)


# ── Edit ───────────────────────────────────────────────────────────────────────

@webex_bp.route("/<int:config_id>/edit", methods=["POST"])
@login_required
def edit_config(config_id: int):
    """Save edits to name and/or access token; re-verifies token if changed."""
    cfg = _own_config_or_404(config_id)
    form = WebexEditForm()

    if form.validate_on_submit():
        cfg.name = form.name.data.strip()
        new_token = form.access_token.data

        if new_token:
            cfg.access_token = new_token
            # Reset verification state; re-verify immediately
            cfg.is_verified = False
            cfg.webex_person_id = None
            cfg.webex_display_name = None
            cfg.webex_email = None
            cfg.webex_org_id = None
            cfg.last_verified_at = None

            profile = verify_token(new_token)
            if profile:
                _apply_verification(cfg, profile)
                flash("Configuration updated and token verified.", "success")
            else:
                flash(
                    "Configuration saved, but the new token could not be verified.",
                    "warning",
                )
        else:
            flash("Configuration name updated.", "success")

        db.session.commit()
    else:
        for field_errors in form.errors.values():
            for error in field_errors:
                flash(error, "danger")

    return redirect(url_for("webex.detail_config", config_id=cfg.id))


# ── Verify ─────────────────────────────────────────────────────────────────────

@webex_bp.route("/<int:config_id>/verify", methods=["POST"])
@login_required
def verify_config(config_id: int):
    """Re-verify the stored access token against the Webex API."""
    cfg = _own_config_or_404(config_id)

    profile = verify_token(cfg.access_token)
    if profile:
        _apply_verification(cfg, profile)
        db.session.commit()
        flash("Token verified successfully. Profile updated.", "success")
    else:
        cfg.is_verified = False
        db.session.commit()
        flash("Token verification failed. The token may be expired or invalid.", "danger")

    return redirect(url_for("webex.detail_config", config_id=cfg.id))


# ── Delete ─────────────────────────────────────────────────────────────────────

@webex_bp.route("/<int:config_id>/delete", methods=["POST"])
@login_required
def delete_config(config_id: int):
    """Permanently delete a Webex configuration."""
    cfg = _own_config_or_404(config_id)
    db.session.delete(cfg)
    db.session.commit()
    flash(f"Webex configuration \"{cfg.name}\" deleted.", "info")
    return redirect(url_for("webex.index"))

