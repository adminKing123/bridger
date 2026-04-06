"""
app/routes/admin.py
-------------------
Super-admin blueprint.  All routes require is_superadmin=True on the
current user — enforced via the @superadmin_required decorator.

Routes:
    GET   /admin/                                           — redirect to user management
    GET   /admin/users/management                           — user management dashboard
    GET   /admin/users                                      — paginated user list with search + filter
    GET   /admin/users/<id>                                 — user detail (info, block status, services)
    POST  /admin/users/<id>/block                           — toggle block / unblock
    POST  /admin/users/<id>/services                        — update service permissions
    GET   /admin/syncore/management                         — syncore management dashboard
    GET   /admin/syncore/employees                          — paginated employee list
    GET   /admin/syncore/employees/<id>                     — employee detail view
    GET   /admin/syncore/employees/<id>/attendance          — employee attendance with date filter
    GET   /admin/syncore/employees/<id>/projects            — employee projects
    POST  /admin/syncore/employees/<id>/login               — mark employee login
    POST  /admin/syncore/employees/<id>/logout              — mark employee logout
    POST  /admin/syncore/sync                               — trigger employee sync
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

    from app.models.syncore_access import SynCoreEmployeeRequest
    pending_requests = SynCoreEmployeeRequest.query.filter_by(status="pending").count()

    return render_template(
        "admin/syncore_management.html",
        total_employees=total_employees,
        active_employees=active_employees,
        last_synced=last_synced,
        pending_requests=pending_requests,
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


@admin_bp.route("/syncore/employees/<int:employee_id>/attendance")
@superadmin_required
def syncore_employee_attendance(employee_id: int):
    """View attendance records for a specific employee with date filtering and pagination."""
    employee = SynCoreEmployee.query.get_or_404(employee_id)

    try:
        from app.services.util_syncore import get_attendance

        # Default date range: first to last day of current month
        today = datetime.now()
        default_start = today.replace(day=1).strftime("%m/%d/%Y")
        # Last day of month: first day of next month minus one day
        if today.month == 12:
            default_end = today.replace(year=today.year + 1, month=1, day=1)
        else:
            default_end = today.replace(month=today.month + 1, day=1)
        default_end = (default_end - __import__("datetime").timedelta(days=1)).strftime("%m/%d/%Y")

        start_date = request.args.get("start_date", default_start).strip()
        end_date = request.args.get("end_date", default_end).strip()
        page = request.args.get("page", 1, type=int)
        per_page = 50

        # Fetch all attendance records for the date range
        all_records = get_attendance(
            start_date=start_date,
            end_date=end_date,
            user_id=employee.user_id,
            signed_array=employee.signed_array
        )

        # Sort by log_date descending (most recent first)
        try:
            all_records.sort(
                key=lambda r: datetime.strptime(r.get("log_date", "01/01/1970"), "%m/%d/%Y"),
                reverse=True
            )
        except (ValueError, TypeError):
            pass

        # Pagination
        total = len(all_records)
        total_pages = max((total + per_page - 1) // per_page, 1)
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page
        records = all_records[start_idx:start_idx + per_page]

        # Summary stats
        late_count = sum(1 for r in all_records if r.get("is_came_late", "-") not in ("-", None, ""))
        total_logged = 0.0
        for r in all_records:
            lh = r.get("logged_hours", "") or ""
            parts = lh.split(":")
            try:
                total_logged += int(parts[0]) + int(parts[1]) / 60 if len(parts) == 2 else 0
            except (ValueError, IndexError):
                pass
        total_hours_int = int(total_logged)
        total_minutes_int = round((total_logged - total_hours_int) * 60)

        pagination = {
            "items": records,
            "page": page,
            "per_page": per_page,
            "total": total,
            "pages": total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_num": page - 1 if page > 1 else None,
            "next_num": page + 1 if page < total_pages else None,
        }

        return render_template(
            "admin/syncore_employee_attendance.html",
            employee=employee,
            pagination=pagination,
            start_date=start_date,
            end_date=end_date,
            late_count=late_count,
            total_hours=total_hours_int,
            total_minutes=total_minutes_int,
            total_days=total,
        )

    except Exception as e:
        logger.error(
            "Error fetching attendance for employee %s: %s",
            employee_id,
            str(e),
            exc_info=True
        )
        flash(f"Failed to fetch attendance: {str(e)}", "danger")
        return redirect(url_for("admin.syncore_employee_detail", employee_id=employee_id))


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

        # Filter by search query (project name)
        search_query = request.args.get("q", "").strip()

        # Apply status filter
        if status_filter == "active":
            filtered_projects = [p for p in all_projects if p.get("project_status") == "Active"]
        elif status_filter == "inactive":
            filtered_projects = [p for p in all_projects if p.get("project_status") == "In-Active"]
        else:
            filtered_projects = all_projects

        # Apply search filter
        if search_query:
            filtered_projects = [
                p for p in filtered_projects
                if search_query.lower() in (p.get("project_name") or "").lower()
            ]

        # Calculate pagination
        total = len(filtered_projects)
        total_pages = max((total + per_page - 1) // per_page, 1)
        page = max(1, min(page, total_pages))
        start_idx = (page - 1) * per_page

        # Get projects for current page
        projects = filtered_projects[start_idx:start_idx + per_page]

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

        # Count active and inactive projects (unfiltered)
        active_count = sum(1 for p in all_projects if p.get("project_status") == "Active")
        inactive_count = len(all_projects) - active_count

        return render_template(
            "admin/syncore_employee_projects.html",
            employee=employee,
            pagination=pagination,
            status_filter=status_filter,
            search_query=search_query,
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


@admin_bp.route("/syncore/employees/<int:employee_id>/projects/<project_id>")
@superadmin_required
def syncore_project_detail(employee_id: int, project_id: str):
    """View modules and activities for a specific project."""
    employee = SynCoreEmployee.query.get_or_404(employee_id)

    try:
        from app.services.util_syncore import get_project_modules, get_project_activities

        modules, activities = (
            get_project_modules(
                user_id=employee.user_id,
                signed_array=employee.signed_array,
                project_id=project_id
            ),
            get_project_activities(
                user_id=employee.user_id,
                signed_array=employee.signed_array,
                project_id=project_id
            )
        )

        # Derive project name from modules/activities if available
        project_name = None
        if modules:
            project_name = modules[0].get("project_name")
        if not project_name and activities:
            project_name = activities[0].get("project_name")
        if not project_name:
            project_name = f"Project #{project_id}"

        return render_template(
            "admin/syncore_project_detail.html",
            employee=employee,
            project_id=project_id,
            project_name=project_name,
            modules=modules,
            activities=activities,
        )

    except Exception as e:
        logger.error(
            "Error fetching project detail for employee %s project %s: %s",
            employee_id, project_id, str(e), exc_info=True
        )
        flash(f"Failed to fetch project details: {str(e)}", "danger")
        return redirect(url_for("admin.syncore_employee_projects", employee_id=employee_id))


@admin_bp.route("/syncore/employees/<int:employee_id>/project-logs")
@superadmin_required
def syncore_employee_project_logs(employee_id: int):
    """View work logs for an employee, filterable by project/module/activity and date."""
    employee = SynCoreEmployee.query.get_or_404(employee_id)

    try:
        from app.services.util_syncore import (
            get_emp_projects, get_project_modules, get_project_activities, get_emp_project_log
        )
        import datetime as _dt

        # ── Date defaults: current month ──────────────────────────────────────
        today = datetime.now()
        default_start = today.replace(day=1).strftime("%m/%d/%Y")
        if today.month == 12:
            last_day = today.replace(year=today.year + 1, month=1, day=1) - _dt.timedelta(days=1)
        else:
            last_day = today.replace(month=today.month + 1, day=1) - _dt.timedelta(days=1)
        default_end = last_day.strftime("%m/%d/%Y")

        start_date  = request.args.get("start_date", default_start).strip()
        end_date    = request.args.get("end_date",   default_end).strip()
        project_id  = request.args.get("project_id",  "").strip()
        module_id   = request.args.get("module_id",   "").strip()
        activity_id = request.args.get("activity_id", "").strip()
        page        = request.args.get("page", 1, type=int)
        per_page    = 20

        # ── Fetch all projects for the dropdown ───────────────────────────────
        all_projects = get_emp_projects(
            user_id=employee.user_id,
            signed_array=employee.signed_array
        )

        # ── If a project is selected, fetch its modules & activities ──────────
        project_modules    = []
        project_activities = []
        if project_id:
            project_modules = get_project_modules(
                user_id=employee.user_id,
                signed_array=employee.signed_array,
                project_id=project_id
            )
            project_activities = get_project_activities(
                user_id=employee.user_id,
                signed_array=employee.signed_array,
                project_id=project_id
            )

        # ── Fetch logs ────────────────────────────────────────────────────────
        logs = get_emp_project_log(
            start_date=start_date,
            end_date=end_date,
            user_id=employee.user_id,
            signed_array=employee.signed_array,
            project_id=int(project_id)  if project_id  else 0,
            module_id=int(module_id)    if module_id    else 0,
            activity_id=int(activity_id) if activity_id else 0,
        )

        # Sort newest first
        try:
            logs.sort(
                key=lambda r: datetime.strptime(r.get("log_date", "01/01/1970"), "%m/%d/%Y"),
                reverse=True
            )
        except (ValueError, TypeError):
            pass

        # ── Summary stats ─────────────────────────────────────────────────────
        total_hours = sum(
            float(r.get("hour_clocked", 0) or 0) for r in logs
        )

        # ── Pagination ────────────────────────────────────────────────────────
        total      = len(logs)
        total_pages = max((total + per_page - 1) // per_page, 1)
        page       = max(1, min(page, total_pages))
        records    = logs[(page - 1) * per_page : page * per_page]

        pagination = {
            "items":    records,
            "page":     page,
            "per_page": per_page,
            "total":    total,
            "pages":    total_pages,
            "has_prev": page > 1,
            "has_next": page < total_pages,
            "prev_num": page - 1 if page > 1 else None,
            "next_num": page + 1 if page < total_pages else None,
        }

        return render_template(
            "admin/syncore_employee_project_logs.html",
            employee=employee,
            pagination=pagination,
            start_date=start_date,
            end_date=end_date,
            project_id=project_id,
            module_id=module_id,
            activity_id=activity_id,
            all_projects=all_projects,
            project_modules=project_modules,
            project_activities=project_activities,
            total_hours=total_hours,
            total_logs=total,
        )

    except Exception as e:
        logger.error(
            "Error fetching project logs for employee %s: %s",
            employee_id, str(e), exc_info=True
        )
        flash(f"Failed to fetch project logs: {str(e)}", "danger")
        return redirect(url_for("admin.syncore_employee_projects", employee_id=employee_id))


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


@admin_bp.route("/syncore/employees/<int:employee_id>/login", methods=["POST"])
@superadmin_required
def syncore_employee_login(employee_id: int):
    """Mark employee login/attendance entry."""
    employee = SynCoreEmployee.query.get_or_404(employee_id)
    
    try:
        from app.services.util_syncore import login
        
        data = request.get_json() or {}
        override_comment = data.get("override_comment", "")
        
        result = login(
            user_id=employee.user_id,
            signed_array=employee.signed_array,
            override_comment=override_comment
        )
        
        # Check if there's an error in the result
        if "error" in result:
            return jsonify({
                "success": False,
                "error": result.get("error", "Failed to mark login")
            }), 400
        
        # Success - log and return the API message
        logger.info(
            "Admin %s marked login for employee %s (%s)",
            current_user.username,
            employee.name,
            employee.employee_id
        )
        return jsonify({
            "success": True,
            "message": result.get("message", "Login marked successfully"),
            "employee_name": employee.name
        })
        
    except Exception as e:
        logger.error(
            "Error marking login for employee %s: %s",
            employee_id,
            str(e),
            exc_info=True
        )
        return jsonify({
            "success": False,
            "error": f"Failed to mark login: {str(e)}"
        }), 500


@admin_bp.route("/syncore/employees/<int:employee_id>/logout", methods=["POST"])
@superadmin_required
def syncore_employee_logout(employee_id: int):
    """Mark employee logout/attendance exit."""
    employee = SynCoreEmployee.query.get_or_404(employee_id)
    
    try:
        from app.services.util_syncore import logout
        
        data = request.get_json() or {}
        override_comment = data.get("override_comment", "")
        
        result = logout(
            user_id=employee.user_id,
            signed_array=employee.signed_array,
            override_comment=override_comment
        )
        
        # Check if there's an error in the result
        if "error" in result:
            return jsonify({
                "success": False,
                "error": result.get("error", "Failed to mark logout")
            }), 400
        
        # Success - log and return the API message
        logger.info(
            "Admin %s marked logout for employee %s (%s)",
            current_user.username,
            employee.name,
            employee.employee_id
        )
        return jsonify({
            "success": True,
            "message": result.get("message", "Logout marked successfully"),
            "employee_name": employee.name
        })
        
    except Exception as e:
        logger.error(
            "Error marking logout for employee %s: %s",
            employee_id,
            str(e),
            exc_info=True
        )
        return jsonify({
            "success": False,
            "error": f"Failed to mark logout: {str(e)}"
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


# ── SynCore Employee Access Requests ──────────────────────────────────────────

@admin_bp.route("/syncore/employee-requests")
@superadmin_required
def syncore_employee_requests():
    """
    Paginated list of all SynCore employee access requests, filterable by status.
    """
    from app.models.syncore_access import SynCoreEmployeeRequest

    status_filter = request.args.get("status", "pending")
    page          = request.args.get("page", 1, type=int)

    query = SynCoreEmployeeRequest.query
    if status_filter in ("pending", "approved", "rejected"):
        query = query.filter_by(status=status_filter)

    pagination = query.order_by(
        SynCoreEmployeeRequest.requested_at.desc()
    ).paginate(page=page, per_page=20, error_out=False)

    counts = {
        "all":      SynCoreEmployeeRequest.query.count(),
        "pending":  SynCoreEmployeeRequest.query.filter_by(status="pending").count(),
        "approved": SynCoreEmployeeRequest.query.filter_by(status="approved").count(),
        "rejected": SynCoreEmployeeRequest.query.filter_by(status="rejected").count(),
    }

    # Build a dict of request_id -> UserEmployeeAccess so the template can
    # flag approved-but-revoked rows (is_active == False) differently.
    from app.models.syncore_access import UserEmployeeAccess
    approved_ids = [r.id for r in pagination.items if r.is_approved]
    access_by_request: dict = {}
    if approved_ids:
        accesses = UserEmployeeAccess.query.filter(
            UserEmployeeAccess.request_id.in_(approved_ids)
        ).all()
        access_by_request = {a.request_id: a for a in accesses}

    return render_template(
        "admin/syncore_employee_requests.html",
        pagination=pagination,
        status_filter=status_filter,
        counts=counts,
        access_by_request=access_by_request,
    )


@admin_bp.route("/syncore/employee-requests/<int:request_id>")
@superadmin_required
def syncore_employee_request_detail(request_id: int):
    """View a single employee access request with approve / reject actions."""
    from app.models.syncore_access import SynCoreEmployeeRequest, UserEmployeeAccess

    emp_request     = SynCoreEmployeeRequest.query.get_or_404(request_id)
    existing_access = UserEmployeeAccess.query.filter_by(
        user_id=emp_request.user_id,
        employee_id=emp_request.employee_id,
    ).first()

    return render_template(
        "admin/syncore_employee_request_detail.html",
        emp_request=emp_request,
        existing_access=existing_access,
    )


@admin_bp.route("/syncore/employee-requests/<int:request_id>/approve", methods=["POST"])
@superadmin_required
def syncore_approve_request(request_id: int):
    """Approve an employee access request and create/update a UserEmployeeAccess record."""
    from app.models.syncore_access import SynCoreEmployeeRequest, UserEmployeeAccess
    from app.services.email_service import send_request_approved_email

    emp_request = SynCoreEmployeeRequest.query.get_or_404(request_id)

    if not emp_request.is_pending:
        flash("This request has already been reviewed.", "warning")
        return redirect(url_for("admin.syncore_employee_request_detail", request_id=request_id))

    permission = request.form.get("permission", "viewer")
    if permission not in ("viewer", "editor"):
        permission = "viewer"

    # Upsert the access record for this user+employee pair
    existing = UserEmployeeAccess.query.filter_by(
        user_id=emp_request.user_id,
        employee_id=emp_request.employee_id,
    ).first()

    if existing:
        existing.permission    = permission
        existing.is_active     = True
        existing.granted_at    = datetime.now(timezone.utc)
        existing.granted_by_id = current_user.id
        existing.request_id    = emp_request.id
    else:
        db.session.add(UserEmployeeAccess(
            user_id=emp_request.user_id,
            employee_id=emp_request.employee_id,
            permission=permission,
            is_active=True,
            request_id=emp_request.id,
            granted_at=datetime.now(timezone.utc),
            granted_by_id=current_user.id,
        ))

    emp_request.status        = SynCoreEmployeeRequest.STATUS_APPROVED
    emp_request.reviewed_at   = datetime.now(timezone.utc)
    emp_request.reviewed_by_id = current_user.id
    db.session.commit()

    try:
        send_request_approved_email(
            to_email=emp_request.user.email,
            username=emp_request.user.username,
            employee_name=emp_request.employee.name,
            permission=permission,
        )
    except Exception as e:
        logger.warning("Could not send approval email: %s", e)

    flash(
        f"Access approved — {emp_request.user.username} → "
        f"{emp_request.employee.name} ({permission}).",
        "success",
    )
    logger.info(
        "Admin %s approved request #%s: user %s → employee %s (%s)",
        current_user.username, request_id,
        emp_request.user.username, emp_request.employee.name, permission,
    )
    return redirect(url_for("admin.syncore_employee_requests"))


@admin_bp.route("/syncore/employee-requests/<int:request_id>/reject", methods=["POST"])
@superadmin_required
def syncore_reject_request(request_id: int):
    """Reject an employee access request with an optional reason."""
    from app.models.syncore_access import SynCoreEmployeeRequest
    from app.services.email_service import send_request_rejected_email

    emp_request = SynCoreEmployeeRequest.query.get_or_404(request_id)

    if not emp_request.is_pending:
        flash("This request has already been reviewed.", "warning")
        return redirect(url_for("admin.syncore_employee_request_detail", request_id=request_id))

    reason                      = request.form.get("rejection_reason", "").strip()
    emp_request.status          = SynCoreEmployeeRequest.STATUS_REJECTED
    emp_request.rejection_reason = reason or None
    emp_request.reviewed_at     = datetime.now(timezone.utc)
    emp_request.reviewed_by_id  = current_user.id
    db.session.commit()

    try:
        send_request_rejected_email(
            to_email=emp_request.user.email,
            username=emp_request.user.username,
            employee_name=emp_request.employee.name,
            reason=reason,
        )
    except Exception as e:
        logger.warning("Could not send rejection email: %s", e)

    flash(
        f"Request from {emp_request.user.username} for "
        f"{emp_request.employee.name} has been rejected.",
        "success",
    )
    logger.info(
        "Admin %s rejected request #%s from user %s for employee %s",
        current_user.username, request_id,
        emp_request.user.username, emp_request.employee.name,
    )
    return redirect(url_for("admin.syncore_employee_requests"))


@admin_bp.route("/syncore/user-employee-access/<int:access_id>/revoke", methods=["POST"])
@superadmin_required
def syncore_revoke_access(access_id: int):
    """Revoke (deactivate) a user's approved access to a SynCore employee."""
    from app.models.syncore_access import UserEmployeeAccess

    access            = UserEmployeeAccess.query.get_or_404(access_id)
    access.is_active  = False
    db.session.commit()

    flash(
        f"Access revoked for {access.user.username} to {access.employee.name}.",
        "success",
    )
    logger.info(
        "Admin %s revoked access #%s: user %s → employee %s",
        current_user.username, access_id,
        access.user.username, access.employee.name,
    )
    next_url = request.form.get("next") or url_for("admin.syncore_employee_requests")
    return redirect(next_url)
