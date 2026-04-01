"""
app/routes/admin.py
-------------------
Super-admin blueprint.  All routes require is_superadmin=True on the
current user — enforced via the @superadmin_required decorator.

Routes:
    GET   /admin/                        — overview dashboard (stats + recent signups)
    GET   /admin/users                   — paginated user list with search + filter
    GET   /admin/users/<id>              — user detail (info, block status, services)
    POST  /admin/users/<id>/block        — toggle block / unblock
    POST  /admin/users/<id>/services     — update service permissions
"""

import logging
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app import db
from app.models.user import User
from app.models.admin import UserServicePermission, SERVICES

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


# ── Access guard ───────────────────────────────────────────────────────────────

def superadmin_required(f):
    """Decorator: abort 403 unless the logged-in user is the superadmin."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_superadmin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ── Dashboard ──────────────────────────────────────────────────────────────────

@admin_bp.route("/")
@superadmin_required
def dashboard():
    """Stats overview + recent signups."""
    regular = User.query.filter_by(is_superadmin=False)
    total_users   = regular.count()
    blocked_users = regular.filter_by(is_blocked=True).count()
    verified_users = User.query.filter_by(is_superadmin=False, is_verified=True).count()

    proxy_users = (
        db.session.query(UserServicePermission)
        .join(User, User.id == UserServicePermission.user_id)
        .filter(
            UserServicePermission.service == "proxy",
            UserServicePermission.is_enabled == True,
            User.is_superadmin == False,
        )
        .count()
    )
    webex_users = (
        db.session.query(UserServicePermission)
        .join(User, User.id == UserServicePermission.user_id)
        .filter(
            UserServicePermission.service == "webex",
            UserServicePermission.is_enabled == True,
            User.is_superadmin == False,
        )
        .count()
    )

    recent_users = (
        User.query
        .filter_by(is_superadmin=False)
        .order_by(User.created_at.desc())
        .limit(8)
        .all()
    )

    return render_template(
        "admin/dashboard.html",
        total_users=total_users,
        blocked_users=blocked_users,
        verified_users=verified_users,
        proxy_users=proxy_users,
        webex_users=webex_users,
        recent_users=recent_users,
        services=SERVICES,
    )


# ── Users list ─────────────────────────────────────────────────────────────────

@admin_bp.route("/users")
@superadmin_required
def users():
    """Paginated, searchable user list with block-status filter."""
    q             = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "all")
    page          = request.args.get("page", 1, type=int)

    query = User.query.filter_by(is_superadmin=False)

    if q:
        like  = f"%{q}%"
        query = query.filter(
            db.or_(User.username.ilike(like), User.email.ilike(like))
        )

    if status_filter == "blocked":
        query = query.filter_by(is_blocked=True)
    elif status_filter == "active":
        query = query.filter_by(is_blocked=False)

    pagination = query.order_by(User.created_at.desc()).paginate(
        page=page, per_page=20, error_out=False
    )

    # Pre-fetch service permissions for every user on this page in one query
    user_ids = [u.id for u in pagination.items]
    perms    = UserServicePermission.query.filter(
        UserServicePermission.user_id.in_(user_ids)
    ).all()
    perm_map: dict[int, dict[str, bool]] = {}
    for p in perms:
        perm_map.setdefault(p.user_id, {})[p.service] = p.is_enabled

    return render_template(
        "admin/users.html",
        pagination=pagination,
        q=q,
        status_filter=status_filter,
        perm_map=perm_map,
        services=SERVICES,
    )


# ── User detail ────────────────────────────────────────────────────────────────

@admin_bp.route("/users/<int:user_id>")
@superadmin_required
def user_detail(user_id: int):
    """View a user's profile, block status, and service permissions."""
    user  = User.query.filter_by(id=user_id, is_superadmin=False).first_or_404()
    perms = {p.service: p for p in user.service_permissions}
    return render_template(
        "admin/user_detail.html",
        user=user,
        perms=perms,
        services=SERVICES,
    )


# ── Block / Unblock ────────────────────────────────────────────────────────────

@admin_bp.route("/users/<int:user_id>/block", methods=["POST"])
@superadmin_required
def toggle_block(user_id: int):
    """Toggle is_blocked on a regular user."""
    user         = User.query.filter_by(id=user_id, is_superadmin=False).first_or_404()
    user.is_blocked = not user.is_blocked
    db.session.commit()

    action = "blocked" if user.is_blocked else "unblocked"
    flash(f"User {user.username!r} has been {action}.", "success")
    logger.info("Admin %s %s user %s", current_user.username, action, user.username)

    next_url = request.form.get("next") or url_for("admin.users")
    return redirect(next_url)


# ── Service permissions ────────────────────────────────────────────────────────

@admin_bp.route("/users/<int:user_id>/services", methods=["POST"])
@superadmin_required
def update_services(user_id: int):
    """Upsert service permission rows from the detail-page checkbox form."""
    user = User.query.filter_by(id=user_id, is_superadmin=False).first_or_404()

    for service in SERVICES:
        enabled = service in request.form   # checkbox is present only when ticked
        perm    = UserServicePermission.query.filter_by(
            user_id=user.id, service=service
        ).first()

        if perm:
            perm.is_enabled   = enabled
            perm.granted_at   = datetime.now(timezone.utc)
            perm.granted_by_id = current_user.id
        else:
            perm = UserServicePermission(
                user_id=user.id,
                service=service,
                is_enabled=enabled,
                granted_at=datetime.now(timezone.utc),
                granted_by_id=current_user.id,
            )
            db.session.add(perm)

    db.session.commit()
    flash(f"Service permissions updated for {user.username!r}.", "success")
    logger.info(
        "Admin %s updated services for user %s", current_user.username, user.username
    )
    return redirect(url_for("admin.user_detail", user_id=user.id))
