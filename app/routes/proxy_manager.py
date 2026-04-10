"""
app/routes/proxy_manager.py
-----------------------------
Proxy management blueprint — CRUD + lifecycle operations for HTTP/HTTPS
proxy configurations. All routes require authentication.

Routes
------
GET            /proxies/             — list user's proxies
GET/POST       /proxies/new          — create a proxy
GET            /proxies/<id>         — view proxy detail (with inline edit)
POST           /proxies/<id>/edit    — save proxy edits
POST           /proxies/<id>/delete  — permanently delete a proxy
POST           /proxies/<id>/start   — set status=running
POST           /proxies/<id>/stop    — set status=stopped
GET            /proxies/<id>/logs    — paginated request log for a proxy
"""

import logging

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from app import db
from app.forms.proxy_forms import ProxyCreateForm, ProxyEditForm
from app.models.proxy import ProxyConfig
from app.models.proxy_log import ProxyLog

logger = logging.getLogger(__name__)

proxy_manager_bp = Blueprint("proxy_manager", __name__, url_prefix="/proxies")


# ── Blueprint-level service guard ─────────────────────────────────────────────

@proxy_manager_bp.before_request
def _require_proxy_service():
    """
    Block access to proxy management for users whose proxy service has been
    revoked by an administrator.  Unauthenticated requests are handled by
    @login_required on each view.
    """
    if not current_user.is_authenticated:
        return None
    if current_user.is_superadmin:
        return None
    from app.models.admin import UserServicePermission
    perm = UserServicePermission.query.filter_by(
        user_id=current_user.id, service="proxy", is_enabled=True
    ).first()
    if not perm:
        flash(
            "The HTTP Proxy service has not been enabled for your account. "
            "Contact the administrator to request access.",
            "warning",
        )
        return redirect(url_for("dashboard.dashboard"))
    return None

def _own_proxy_or_404(proxy_id: int) -> ProxyConfig:
    """Return the ProxyConfig owned by current_user, or abort with 404."""
    proxy = ProxyConfig.query.filter_by(id=proxy_id, user_id=current_user.id).first()
    if not proxy:
        abort(404)
    return proxy


# ── List ───────────────────────────────────────────────────────────────────────

@proxy_manager_bp.route("/")
@login_required
def list_proxies():
    """Display all proxy configurations belonging to the current user (paginated)."""
    page = request.args.get("page", 1, type=int)
    proxies = (
        ProxyConfig.query
        .filter_by(user_id=current_user.id)
        .order_by(ProxyConfig.created_at.desc())
        .paginate(page=page, per_page=30, error_out=False)
    )
    return render_template("proxy/list.html", proxies=proxies)


# ── Create ─────────────────────────────────────────────────────────────────────

@proxy_manager_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_proxy():
    """Render the create form and persist a new proxy configuration."""
    form = ProxyCreateForm()

    if request.method == "GET":
        # Pre-fill slug with a unique generated value
        form.slug.data = ProxyConfig.generate_unique_slug()

    if form.validate_on_submit():
        proxy = ProxyConfig(
            user_id=current_user.id,
            name=form.name.data.strip(),
            slug=form.slug.data,          # already normalised by validate_slug
            target_url=form.target_url.data,
            proxy_type=form.proxy_type.data,
            allowed_methods=",".join(form.allowed_methods.data),
            cors_bypass=form.cors_bypass.data,
            cors_origins=form.cors_origins.data,
            skip_ngrok_warning=form.skip_ngrok_warning.data,
            status=ProxyConfig.STATUS_STOPPED,
        )
        db.session.add(proxy)
        db.session.commit()
        logger.info("Proxy created: slug=%s user_id=%s", proxy.slug, current_user.id)
        flash(f"Proxy '{proxy.name}' created successfully.", "success")
        return redirect(url_for("proxy_manager.detail_proxy", proxy_id=proxy.id))

    return render_template("proxy/create.html", form=form)


# ── Detail ─────────────────────────────────────────────────────────────────────

@proxy_manager_bp.route("/<int:proxy_id>")
@login_required
def detail_proxy(proxy_id: int):
    """Show full proxy details with an inline edit form."""
    proxy = _own_proxy_or_404(proxy_id)
    edit_form = ProxyEditForm(obj=proxy)
    # Pre-populate MultiCheckboxField from the comma-separated DB value
    if not edit_form.is_submitted():
        edit_form.allowed_methods.data = proxy.allowed_methods_list()
        edit_form.cors_origins.data = proxy.cors_origins.replace(",", "\n")
    return render_template("proxy/detail.html", proxy=proxy, edit_form=edit_form)


# ── Edit ───────────────────────────────────────────────────────────────────────

@proxy_manager_bp.route("/<int:proxy_id>/edit", methods=["POST"])
@login_required
def edit_proxy(proxy_id: int):
    """
    Accept a POST from the inline edit form.
    On validation error: re-render the detail page with the form open.
    """
    proxy = _own_proxy_or_404(proxy_id)
    form = ProxyEditForm()

    if form.validate_on_submit():
        proxy.name              = form.name.data.strip()
        proxy.target_url        = form.target_url.data
        proxy.allowed_methods   = ",".join(form.allowed_methods.data)
        proxy.cors_bypass       = form.cors_bypass.data
        proxy.cors_origins      = form.cors_origins.data
        proxy.skip_ngrok_warning = form.skip_ngrok_warning.data
        db.session.commit()
        logger.info("Proxy updated: slug=%s", proxy.slug)
        flash(f"Proxy '{proxy.name}' updated successfully.", "success")
        return redirect(url_for("proxy_manager.detail_proxy", proxy_id=proxy.id))

    # Return with form errors so the JS can auto-open the edit panel
    return render_template(
        "proxy/detail.html",
        proxy=proxy,
        edit_form=form,
        edit_open=True,
    )


# ── Delete ─────────────────────────────────────────────────────────────────────

@proxy_manager_bp.route("/<int:proxy_id>/delete", methods=["POST"])
@login_required
def delete_proxy(proxy_id: int):
    """Permanently delete a proxy configuration."""
    proxy = _own_proxy_or_404(proxy_id)
    name = proxy.name
    db.session.delete(proxy)
    db.session.commit()
    logger.info("Proxy deleted: slug=%s user_id=%s", proxy.slug, current_user.id)
    flash(f"Proxy '{name}' has been deleted.", "info")
    return redirect(url_for("proxy_manager.list_proxies"))


# ── Start / Stop ───────────────────────────────────────────────────────────────

@proxy_manager_bp.route("/<int:proxy_id>/start", methods=["POST"])
@login_required
def start_proxy(proxy_id: int):
    """Set proxy status to running, enabling request forwarding."""
    proxy = _own_proxy_or_404(proxy_id)
    if proxy.is_running:
        flash("Proxy is already running.", "info")
    else:
        proxy.status = ProxyConfig.STATUS_RUNNING
        db.session.commit()
        logger.info("Proxy started: slug=%s", proxy.slug)
        flash(f"Proxy '{proxy.name}' is now running.", "success")
    return redirect(url_for("proxy_manager.detail_proxy", proxy_id=proxy.id))


@proxy_manager_bp.route("/<int:proxy_id>/stop", methods=["POST"])
@login_required
def stop_proxy(proxy_id: int):
    """Set proxy status to stopped, halting request forwarding (returns 503)."""
    proxy = _own_proxy_or_404(proxy_id)
    if not proxy.is_running:
        flash("Proxy is already stopped.", "info")
    else:
        proxy.status = ProxyConfig.STATUS_STOPPED
        db.session.commit()
        logger.info("Proxy stopped: slug=%s", proxy.slug)
        flash(f"Proxy '{proxy.name}' has been stopped.", "info")
    return redirect(url_for("proxy_manager.detail_proxy", proxy_id=proxy.id))


@proxy_manager_bp.route("/<int:proxy_id>/logs")
@login_required
def logs_proxy(proxy_id: int):
    """Show paginated request logs for a proxy owned by the current user."""
    proxy = _own_proxy_or_404(proxy_id)
    page = request.args.get("page", 1, type=int)
    logs = (
        ProxyLog.query
        .filter_by(proxy_id=proxy.id)
        .order_by(ProxyLog.created_at.desc())
        .paginate(page=page, per_page=30, error_out=False)
    )
    return render_template("proxy/logs.html", proxy=proxy, logs=logs)


@proxy_manager_bp.route("/<int:proxy_id>/logs/clear", methods=["POST"])
@login_required
def clear_logs(proxy_id: int):
    """Delete all log entries for a proxy owned by the current user."""
    proxy = _own_proxy_or_404(proxy_id)
    deleted = ProxyLog.query.filter_by(proxy_id=proxy.id).delete()
    db.session.commit()
    logger.info("Cleared %d log entries for proxy slug=%s", deleted, proxy.slug)
    flash(f"All logs cleared for '{proxy.name}'.", "success")
    return redirect(url_for("proxy_manager.logs_proxy", proxy_id=proxy.id))
