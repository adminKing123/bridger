"""
app/routes/admin.py
-------------------
Super-admin blueprint.  All routes require is_superadmin=True on the
current user — enforced via the @superadmin_required decorator.

Routes:
    GET   /admin/                        — redirect to user management
    GET   /admin/users/management        — user management dashboard
    GET   /admin/users                   — paginated user list with search + filter
    GET   /admin/users/<id>              — user detail (info, block status, services)
    POST  /admin/users/<id>/block        — toggle block / unblock
    POST  /admin/users/<id>/services     — update service permissions
    GET   /admin/syncore/management      — syncore management dashboard
    GET   /admin/syncore/employees       — paginated employee list
    GET   /admin/syncore/employees/<id>  — employee detail view
    POST  /admin/syncore/sync            — trigger employee sync
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
    jsonify,
)
from flask_login import current_user, login_required

from app import db
from app.models.user import User
from app.models.admin import UserServicePermission, SERVICES
from app.models.syncore_employee import SynCoreEmployee

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
    """Admin dashboard - redirect to user management."""
    return redirect(url_for("admin.users_management"))


@admin_bp.route("/users/management")
@superadmin_required
def users_management():
    """User management dashboard with stats and recent signups."""
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
    syncore_users = (
        db.session.query(UserServicePermission)
        .join(User, User.id == UserServicePermission.user_id)
        .filter(
            UserServicePermission.service == "syncore",
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
        "admin/users_management.html",
        total_users=total_users,
        blocked_users=blocked_users,
        verified_users=verified_users,
        proxy_users=proxy_users,
        webex_users=webex_users,
        syncore_users=syncore_users,
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


# ── SynCore Employee Management ───────────────────────────────────────────────

@admin_bp.route("/syncore/management")
@superadmin_required
def syncore_management():
    """SynCore management dashboard."""
    # Get employee statistics
    total_employees = SynCoreEmployee.query.count()
    active_employees = SynCoreEmployee.query.filter_by(status="Active").count()
    
    # Get last sync time
    last_synced = (
        db.session.query(db.func.max(SynCoreEmployee.last_synced_at))
        .scalar()
    )
    
    return render_template(
        "admin/syncore_management.html",
        total_employees=total_employees,
        active_employees=active_employees,
        last_synced=last_synced,
    )


@admin_bp.route("/syncore/employees")
@superadmin_required
def syncore_employees():
    """Paginated, searchable SynCore employee list."""
    q             = request.args.get("q", "").strip()
    status_filter = request.args.get("status", "all")
    page          = request.args.get("page", 1, type=int)

    query = SynCoreEmployee.query

    if q:
        like  = f"%{q}%"
        query = query.filter(
            db.or_(
                SynCoreEmployee.name.ilike(like),
                SynCoreEmployee.email.ilike(like),
                SynCoreEmployee.employee_id.ilike(like),
                SynCoreEmployee.designation.ilike(like)
            )
        )

    if status_filter == "active":
        query = query.filter_by(status="Active")
    elif status_filter == "inactive":
        query = query.filter(
            db.or_(
                SynCoreEmployee.status == "In-Active",
                SynCoreEmployee.status == "Inactive"
            )
        )

    # Get total counts for stats
    total_employees = SynCoreEmployee.query.count()
    active_employees = SynCoreEmployee.query.filter_by(status="Active").count()
    
    # Get last sync time
    last_synced = (
        db.session.query(db.func.max(SynCoreEmployee.last_synced_at))
        .scalar()
    )

    pagination = query.order_by(SynCoreEmployee.name.asc()).paginate(
        page=page, per_page=25, error_out=False
    )

    return render_template(
        "admin/syncore_employees.html",
        pagination=pagination,
        q=q,
        status_filter=status_filter,
        total_employees=total_employees,
        active_employees=active_employees,
        last_synced=last_synced,
    )


@admin_bp.route("/syncore/employees/<int:employee_id>")
@superadmin_required
def syncore_employee_detail(employee_id: int):
    """View detailed information for a specific SynCore employee."""
    employee = SynCoreEmployee.query.get_or_404(employee_id)
    return render_template(
        "admin/syncore_employee_detail.html",
        employee=employee,
    )


@admin_bp.route("/syncore/employees/<int:employee_id>/logs")
@superadmin_required
def syncore_employee_logs(employee_id: int):
    """Fetch today's attendance logs for a specific employee."""
    employee = SynCoreEmployee.query.get_or_404(employee_id)
    
    try:
        from app.services.util_syncore import get_today_log_status
        
        logs = get_today_log_status(
            user_id=employee.user_id,
            signed_array=employee.signed_array
        )
        
        return jsonify({
            "success": True,
            "logs": logs,
            "employee_name": employee.name
        })
        
    except Exception as e:
        logger.error(
            "Error fetching logs for employee %s: %s",
            employee_id,
            str(e),
            exc_info=True
        )
        return jsonify({
            "success": False,
            "error": f"Failed to fetch logs: {str(e)}"
        }), 500


@admin_bp.route("/syncore/employees/<int:employee_id>/projects")
@superadmin_required
def syncore_employee_projects(employee_id: int):
    """View all projects assigned to a specific employee with pagination."""
    employee = SynCoreEmployee.query.get_or_404(employee_id)
    
    try:
        from app.services.util_syncore import get_emp_projects
        
        # Fetch all projects from API
        all_projects = get_emp_projects(
            user_id=employee.user_id,
            signed_array=employee.signed_array
        )
        
        # Pagination parameters
        page = request.args.get("page", 1, type=int)
        per_page = 20
        
        # Filter by status if provided
        status_filter = request.args.get("status", "all")
        
        # Apply status filter
        if status_filter == "active":
            filtered_projects = [p for p in all_projects if p.get("project_status") == "Active"]
        elif status_filter == "inactive":
            filtered_projects = [p for p in all_projects if p.get("project_status") == "In-Active"]
        else:
            filtered_projects = all_projects
        
        # Calculate pagination
        total = len(filtered_projects)
        total_pages = (total + per_page - 1) // per_page if total > 0 else 1
        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        
        # Get projects for current page
        projects = filtered_projects[start_idx:end_idx]
        
        # Build pagination object
        pagination = {
            "items": projects,
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_num": page - 1 if page > 1 else None,
            "next_num": page + 1 if page < total_pages else None,
        }
        
        # Count active and inactive projects
        active_count = sum(1 for p in all_projects if p.get("project_status") == "Active")
        inactive_count = len(all_projects) - active_count
        
        return render_template(
            "admin/syncore_employee_projects.html",
            employee=employee,
            pagination=pagination,
            status_filter=status_filter,
            active_count=active_count,
            inactive_count=inactive_count,
            total_count=len(all_projects)
        )
        
    except Exception as e:
        logger.error(
            "Error fetching projects for employee %s: %s",
            employee_id,
            str(e),
            exc_info=True
        )
        flash(f"Failed to fetch projects: {str(e)}", "danger")
        return redirect(url_for("admin.syncore_employee_detail", employee_id=employee_id))


@admin_bp.route("/syncore/employees/<int:employee_id>/email-settings")
@superadmin_required
def syncore_employee_email_settings(employee_id: int):
    """Fetch email notification settings for a specific employee."""
    employee = SynCoreEmployee.query.get_or_404(employee_id)
    
    try:
        from app.services.util_syncore import get_user_mail_setting
        
        settings = get_user_mail_setting(
            user_id=employee.user_id,
            signed_array=employee.signed_array
        )
        
        return jsonify({
            "success": True,
            "settings": settings,
            "employee_name": employee.name
        })
        
    except Exception as e:
        logger.error(
            "Error fetching email settings for employee %s: %s",
            employee_id,
            str(e),
            exc_info=True
        )
        return jsonify({
            "success": False,
            "error": f"Failed to fetch email settings: {str(e)}"
        }), 500


@admin_bp.route("/syncore/sync", methods=["POST"])
@superadmin_required
def syncore_sync():
    """Trigger sync of employee data from SynCore HRMS API."""
    try:
        from app.services.util_syncore import sync_employees_to_db
        
        logger.info(
            "Admin %s initiated SynCore employee sync",
            current_user.username
        )
        
        stats = sync_employees_to_db()
        
        if stats.get("errors", 0) > 0:
            error_msg = f"Sync completed with {stats['errors']} errors."
            if stats.get("error_details"):
                error_msg += f" First error: {stats['error_details'][0]}"
            flash(error_msg, "warning")
        
        success_msg = (
            f"Sync complete! "
            f"{stats.get('added', 0)} added, "
            f"{stats.get('updated', 0)} updated out of "
            f"{stats.get('total', 0)} total employees."
        )
        flash(success_msg, "success")
        
        logger.info(
            "SynCore sync by %s: %s",
            current_user.username,
            success_msg
        )
        
        return jsonify({
            "success": True,
            "stats": stats,
            "message": success_msg
        })
        
    except Exception as e:
        error_msg = f"Sync failed: {str(e)}"
        logger.error("SynCore sync error: %s", error_msg, exc_info=True)
        flash(error_msg, "danger")
        return jsonify({
            "success": False,
            "error": error_msg
        }), 500
