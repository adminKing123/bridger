"""
app/routes/syncore.py
---------------------
SynCore — user-facing HRMS Data Panel routes.

Access to this blueprint requires the 'syncore' service permission (enforced
via before_request). Employee data is further gated by UserEmployeeAccess
records (viewer | editor permissions).

Routes
------
GET    /syncore/                             — dashboard (approved employees + quick stats)
GET    /syncore/employees                    — full list of user's approved employees
GET    /syncore/employees/request            — enter employee email + preview + confirm
POST   /syncore/employees/request            — submit access request
GET    /syncore/requests                     — user's request history
GET    /syncore/employees/<id>/              — employee detail          [viewer+]
GET    /syncore/employees/<id>/attendance    — attendance with filters  [viewer+]
GET    /syncore/employees/<id>/projects      — project list             [viewer+]
GET    /syncore/employees/<id>/projects/<p>  — project modules/acts     [viewer+]
GET    /syncore/employees/<id>/project-logs  — work log viewer          [viewer+]
POST   /syncore/employees/<id>/login         — mark login               [editor only]
POST   /syncore/employees/<id>/logout        — mark logout              [editor only]
"""

import logging
from datetime import datetime, timezone

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from app import db
from app.models.syncore_access import SynCoreEmployeeRequest, UserEmployeeAccess
from app.models.syncore_employee import SynCoreEmployee

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


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _get_access(access_id: int, require_editor: bool = False) -> UserEmployeeAccess:
    """
    Return the active UserEmployeeAccess record owned by the current user.
    Aborts 404 if not found / inactive, 403 if permission is insufficient.
    """
    access = UserEmployeeAccess.query.filter_by(
        id=access_id,
        user_id=current_user.id,
        is_active=True,
    ).first_or_404()

    if require_editor and access.permission != UserEmployeeAccess.PERMISSION_EDITOR:
        abort(403)

    return access


def _build_date_defaults() -> tuple:
    """Return (start_date, end_date) for the current month in MM/DD/YYYY format."""
    import datetime as _dt
    today = datetime.now()
    start = today.replace(day=1).strftime("%m/%d/%Y")
    if today.month == 12:
        last = today.replace(year=today.year + 1, month=1, day=1) - _dt.timedelta(days=1)
    else:
        last = today.replace(month=today.month + 1, day=1) - _dt.timedelta(days=1)
    return start, last.strftime("%m/%d/%Y")


def _paginate_list(items: list, page: int, per_page: int) -> dict:
    """Slice a Python list into a pagination dict matching the admin route pattern."""
    total       = len(items)
    total_pages = max((total + per_page - 1) // per_page, 1)
    page        = max(1, min(page, total_pages))
    records     = items[(page - 1) * per_page: page * per_page]
    return {
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


# ── Dashboard ─────────────────────────────────────────────────────────────────

@syncore_bp.route("/")
@login_required
def index():
    """SynCore landing page — shows approved employees or prompts to request."""
    page = request.args.get("page", 1, type=int)
    all_accesses = (
        UserEmployeeAccess.query
        .filter_by(user_id=current_user.id, is_active=True)
        .order_by(UserEmployeeAccess.granted_at.desc())
        .all()
    )
    pending_count = SynCoreEmployeeRequest.query.filter_by(
        user_id=current_user.id, status="pending"
    ).count()

    return render_template(
        "syncore/index.html",
        pagination=_paginate_list(all_accesses, page, 10),
        total=len(all_accesses),
        pending_count=pending_count,
    )


# ── Employee list ──────────────────────────────────────────────────────────────

@syncore_bp.route("/employees")
@login_required
def employees():
    """Full list of employees the current user has been approved to access."""
    q = request.args.get("q", "").strip()

    query = (
        UserEmployeeAccess.query
        .filter_by(user_id=current_user.id, is_active=True)
        .join(SynCoreEmployee, UserEmployeeAccess.employee_id == SynCoreEmployee.id)
    )
    if q:
        like  = f"%{q}%"
        query = query.filter(
            db.or_(
                SynCoreEmployee.name.ilike(like),
                SynCoreEmployee.email.ilike(like),
                SynCoreEmployee.designation.ilike(like),
            )
        )

    page = request.args.get("page", 1, type=int)
    all_accesses = query.order_by(SynCoreEmployee.name.asc()).all()
    return render_template(
        "syncore/employees.html",
        pagination=_paginate_list(all_accesses, page, 20),
        total=len(all_accesses),
        q=q,
    )


# ── Request employee access ────────────────────────────────────────────────────

@syncore_bp.route("/employees/request", methods=["GET", "POST"])
@login_required
def request_employee():
    """
    Two-step access request:
      GET  ?email=…  — look up employee, show preview + confirm form
      POST           — submit the access request
    """
    if request.method == "POST":
        email      = request.form.get("employee_email", "").strip().lower()
        permission = request.form.get("permission", "viewer")
        if permission not in ("viewer", "editor"):
            permission = "viewer"

        employee = SynCoreEmployee.query.filter(
            db.func.lower(SynCoreEmployee.email) == email
        ).first()
        if not employee:
            flash("No employee found with that email address.", "danger")
            return redirect(url_for("syncore.request_employee", email=email))

        # Guard: active access already exists
        existing_access = UserEmployeeAccess.query.filter_by(
            user_id=current_user.id,
            employee_id=employee.id,
            is_active=True,
        ).first()
        if existing_access and existing_access.permission == permission:
            # Same permission — nothing to change
            flash(
                f"You already have {permission} access to {employee.name}.",
                "info",
            )
            return redirect(url_for("syncore.employee_detail", access_id=existing_access.id))
        # If existing access has a DIFFERENT permission, fall through to
        # create a permission-change request (admin handles the upsert on approval).

        # Guard: pending request already exists for this employee
        pending_req = SynCoreEmployeeRequest.query.filter_by(
            user_id=current_user.id,
            employee_id=employee.id,
            status="pending",
        ).first()
        if pending_req:
            flash(
                f"You already have a pending request for {employee.name}. "
                "Please wait for admin review.",
                "warning",
            )
            return redirect(url_for("syncore.requests"))

        # Create request record
        emp_request = SynCoreEmployeeRequest(
            user_id=current_user.id,
            employee_id=employee.id,
            employee_email=email,
            requested_permission=permission,
            status="pending",
            requested_at=datetime.now(timezone.utc),
        )
        db.session.add(emp_request)
        db.session.commit()

        # Email admin
        try:
            from app.services.email_service import send_employee_access_request_email
            admin_email = current_app.config.get("SMTP_USER", "")
            if admin_email:
                send_employee_access_request_email(
                    admin_email=admin_email,
                    requester_username=current_user.username,
                    requester_email=current_user.email,
                    employee_name=employee.name,
                    employee_email=email,
                    requested_permission=permission,
                    review_url=url_for(
                        "admin.syncore_employee_request_detail",
                        request_id=emp_request.id,
                        _external=True,
                    ),
                )
        except Exception as e:
            logger.warning("Could not send admin notification email: %s", e)

        logger.info(
            "User %s requested %s access to employee %s",
            current_user.username, permission, employee.name,
        )
        flash(
            f"Request submitted for {employee.name}. "
            "You will be notified once the admin reviews it.",
            "success",
        )
        return redirect(url_for("syncore.requests"))

    # GET — optional email preview
    email           = request.args.get("email", "").strip().lower()
    employee        = None
    preview_state   = None  # None | found | not_found | already_access | pending | pending_change
    existing_access = None

    if email:
        employee = SynCoreEmployee.query.filter(
            db.func.lower(SynCoreEmployee.email) == email
        ).first()
        if not employee:
            preview_state = "not_found"
        else:
            existing_access = UserEmployeeAccess.query.filter_by(
                user_id=current_user.id, employee_id=employee.id, is_active=True
            ).first()
            pending_req = SynCoreEmployeeRequest.query.filter_by(
                user_id=current_user.id, employee_id=employee.id, status="pending"
            ).first()

            if existing_access:
                # User has active access — check if a change request is already pending
                preview_state = "pending_change" if pending_req else "already_access"
            elif pending_req:
                preview_state = "pending"
            else:
                preview_state = "found"

    return render_template(
        "syncore/request_employee.html",
        email=email,
        employee=employee,
        preview_state=preview_state,
        existing_access=existing_access,
    )


# ── Request history ────────────────────────────────────────────────────────────

@syncore_bp.route("/requests")
@login_required
def requests():
    """The current user's access request history."""
    page = request.args.get("page", 1, type=int)
    all_requests = (
        SynCoreEmployeeRequest.query
        .filter_by(user_id=current_user.id)
        .order_by(SynCoreEmployeeRequest.requested_at.desc())
        .all()
    )
    # Map employee_id -> active access so the template can link approved rows
    # to the employee detail page directly.
    active_accesses = UserEmployeeAccess.query.filter_by(
        user_id=current_user.id, is_active=True
    ).all()
    access_by_employee = {a.employee_id: a for a in active_accesses}
    return render_template(
        "syncore/requests.html",
        pagination=_paginate_list(all_requests, page, 20),
        total=len(all_requests),
        access_by_employee=access_by_employee,
    )


# ── Employee detail ────────────────────────────────────────────────────────────

@syncore_bp.route("/employees/<int:access_id>/")
@login_required
def employee_detail(access_id: int):
    """Employee detail (viewer+)."""
    access   = _get_access(access_id)
    employee = access.employee
    return render_template(
        "syncore/employee_detail.html",
        access=access,
        employee=employee,
    )


# ── Attendance ─────────────────────────────────────────────────────────────────

@syncore_bp.route("/employees/<int:access_id>/attendance")
@login_required
def employee_attendance(access_id: int):
    """Attendance records with date filter and pagination (viewer+)."""
    access   = _get_access(access_id)
    employee = access.employee

    try:
        from app.services.util_syncore import get_attendance

        default_start, default_end = _build_date_defaults()
        start_date = request.args.get("start_date", default_start).strip()
        end_date   = request.args.get("end_date",   default_end).strip()
        page       = request.args.get("page", 1, type=int)

        all_records = get_attendance(
            start_date=start_date,
            end_date=end_date,
            user_id=employee.user_id,
            signed_array=employee.signed_array,
        )

        try:
            all_records.sort(
                key=lambda r: datetime.strptime(r.get("log_date", "01/01/1970"), "%m/%d/%Y"),
                reverse=True,
            )
        except (ValueError, TypeError):
            pass

        total      = len(all_records)
        late_count = sum(
            1 for r in all_records
            if r.get("is_came_late", "-") not in ("-", None, "")
        )

        total_logged = 0.0
        for r in all_records:
            lh = r.get("logged_hours", "") or ""
            parts = lh.split(":")
            try:
                total_logged += (
                    int(parts[0]) + int(parts[1]) / 60
                    if len(parts) == 2 else 0
                )
            except (ValueError, IndexError):
                pass
        total_hours_int   = int(total_logged)
        total_minutes_int = round((total_logged - total_hours_int) * 60)

        return render_template(
            "syncore/employee_attendance.html",
            access=access,
            employee=employee,
            pagination=_paginate_list(all_records, page, 50),
            start_date=start_date,
            end_date=end_date,
            late_count=late_count,
            total_hours=total_hours_int,
            total_minutes=total_minutes_int,
            total_days=total,
        )

    except Exception as e:
        logger.error("Attendance error access %s: %s", access_id, e, exc_info=True)
        flash(f"Failed to fetch attendance: {e}", "danger")
        return redirect(url_for("syncore.employee_detail", access_id=access_id))


# ── Projects ───────────────────────────────────────────────────────────────────

@syncore_bp.route("/employees/<int:access_id>/projects")
@login_required
def employee_projects(access_id: int):
    """Project list with search and pagination (viewer+)."""
    access   = _get_access(access_id)
    employee = access.employee

    try:
        from app.services.util_syncore import get_emp_projects

        all_projects  = get_emp_projects(
            user_id=employee.user_id, signed_array=employee.signed_array
        )
        status_filter = request.args.get("status", "all")
        q             = request.args.get("q", "").strip()
        page          = request.args.get("page", 1, type=int)

        filtered = all_projects
        if status_filter == "active":
            filtered = [p for p in filtered if p.get("project_status") == "Active"]
        elif status_filter == "inactive":
            filtered = [p for p in filtered if p.get("project_status") != "Active"]
        if q:
            filtered = [
                p for p in filtered
                if q.lower() in (p.get("project_name") or "").lower()
            ]

        active_count   = sum(1 for p in all_projects if p.get("project_status") == "Active")
        inactive_count = len(all_projects) - active_count

        return render_template(
            "syncore/employee_projects.html",
            access=access,
            employee=employee,
            pagination=_paginate_list(filtered, page, 20),
            status_filter=status_filter,
            search_query=q,
            active_count=active_count,
            inactive_count=inactive_count,
            total_count=len(all_projects),
        )

    except Exception as e:
        logger.error("Projects error access %s: %s", access_id, e, exc_info=True)
        flash(f"Failed to fetch projects: {e}", "danger")
        return redirect(url_for("syncore.employee_detail", access_id=access_id))


# ── Project detail ─────────────────────────────────────────────────────────────

@syncore_bp.route("/employees/<int:access_id>/projects/<project_id>")
@login_required
def employee_project_detail(access_id: int, project_id: str):
    """Modules and activities for a project (viewer+)."""
    access   = _get_access(access_id)
    employee = access.employee

    try:
        from app.services.util_syncore import get_project_modules, get_project_activities

        modules, activities = (
            get_project_modules(
                user_id=employee.user_id,
                signed_array=employee.signed_array,
                project_id=project_id,
            ),
            get_project_activities(
                user_id=employee.user_id,
                signed_array=employee.signed_array,
                project_id=project_id,
            ),
        )

        project_name = (
            (modules[0].get("project_name") if modules else None)
            or (activities[0].get("project_name") if activities else None)
            or f"Project #{project_id}"
        )

        return render_template(
            "syncore/employee_project_detail.html",
            access=access,
            employee=employee,
            project_id=project_id,
            project_name=project_name,
            modules=modules,
            activities=activities,
        )

    except Exception as e:
        logger.error("Project detail error access %s / %s: %s", access_id, project_id, e)
        flash(f"Failed to fetch project details: {e}", "danger")
        return redirect(url_for("syncore.employee_projects", access_id=access_id))


# ── Project work logs ──────────────────────────────────────────────────────────

@syncore_bp.route("/employees/<int:access_id>/project-logs")
@login_required
def employee_project_logs(access_id: int):
    """Work log viewer with date + cascading project/module/activity filters (viewer+)."""
    access   = _get_access(access_id)
    employee = access.employee

    try:
        from app.services.util_syncore import (
            get_emp_projects, get_project_modules,
            get_project_activities, get_emp_project_log,
        )

        default_start, default_end = _build_date_defaults()
        start_date  = request.args.get("start_date", default_start).strip()
        end_date    = request.args.get("end_date",   default_end).strip()
        project_id  = request.args.get("project_id",  "").strip()
        module_id   = request.args.get("module_id",   "").strip()
        activity_id = request.args.get("activity_id", "").strip()
        page        = request.args.get("page", 1, type=int)

        all_projects       = get_emp_projects(
            user_id=employee.user_id, signed_array=employee.signed_array
        )
        project_modules    = []
        project_activities = []
        if project_id:
            project_modules = get_project_modules(
                user_id=employee.user_id, signed_array=employee.signed_array,
                project_id=project_id,
            )
            project_activities = get_project_activities(
                user_id=employee.user_id, signed_array=employee.signed_array,
                project_id=project_id,
            )

        logs = get_emp_project_log(
            start_date=start_date,
            end_date=end_date,
            user_id=employee.user_id,
            signed_array=employee.signed_array,
            project_id=int(project_id)   if project_id   else 0,
            module_id=int(module_id)     if module_id     else 0,
            activity_id=int(activity_id) if activity_id  else 0,
        )

        try:
            logs.sort(
                key=lambda r: datetime.strptime(r.get("log_date", "01/01/1970"), "%m/%d/%Y"),
                reverse=True,
            )
        except (ValueError, TypeError):
            pass

        total_hours = sum(float(r.get("hour_clocked", 0) or 0) for r in logs)

        return render_template(
            "syncore/employee_project_logs.html",
            access=access,
            employee=employee,
            pagination=_paginate_list(logs, page, 20),
            start_date=start_date,
            end_date=end_date,
            project_id=project_id,
            module_id=module_id,
            activity_id=activity_id,
            all_projects=all_projects,
            project_modules=project_modules,
            project_activities=project_activities,
            total_hours=total_hours,
            total_logs=len(logs),
        )

    except Exception as e:
        logger.error("Project logs error access %s: %s", access_id, e, exc_info=True)
        flash(f"Failed to fetch work logs: {e}", "danger")
        return redirect(url_for("syncore.employee_projects", access_id=access_id))


# ── Login / Logout (Editor only) ───────────────────────────────────────────────

@syncore_bp.route("/employees/<int:access_id>/login", methods=["POST"])
@login_required
def employee_login(access_id: int):
    """Mark employee login via SynCore API — editor permission required."""
    access   = _get_access(access_id, require_editor=True)
    employee = access.employee
    try:
        from app.services.util_syncore import login as syncore_login
        result = syncore_login(
            user_id=employee.user_id,
            signed_array=employee.signed_array,
            override_comment=request.form.get("override_comment", ""),
        )
        if result.get("success"):
            flash("Login marked successfully.", "success")
        else:
            flash(result.get("message", "Login failed."), "warning")
    except Exception as e:
        logger.error("Login error access %s: %s", access_id, e)
        flash(f"Login failed: {e}", "danger")
    return redirect(url_for("syncore.employee_detail", access_id=access_id))


@syncore_bp.route("/employees/<int:access_id>/logout", methods=["POST"])
@login_required
def employee_logout(access_id: int):
    """Mark employee logout via SynCore API — editor permission required."""
    access   = _get_access(access_id, require_editor=True)
    employee = access.employee
    try:
        from app.services.util_syncore import logout as syncore_logout
        result = syncore_logout(
            user_id=employee.user_id,
            signed_array=employee.signed_array,
            override_comment=request.form.get("override_comment", ""),
        )
        if result.get("success"):
            flash("Logout marked successfully.", "success")
        else:
            flash(result.get("message", "Logout failed."), "warning")
    except Exception as e:
        logger.error("Logout error access %s: %s", access_id, e)
        flash(f"Logout failed: {e}", "danger")
    return redirect(url_for("syncore.employee_detail", access_id=access_id))


# ── Work Log — Fill Log (User side: editor permission only) ───────────────────

@syncore_bp.route("/employees/<int:employee_id>/worklog/projects")
@login_required
def user_worklog_projects(employee_id: int):
    """AJAX: return the project list for the work-log modal (editor only)."""
    access = UserEmployeeAccess.query.filter_by(
        user_id=current_user.id,
        employee_id=employee_id,
        is_active=True,
        permission=UserEmployeeAccess.PERMISSION_EDITOR,
    ).first_or_404()
    employee = access.employee
    try:
        from app.services.util_syncore import get_emp_projects
        projects = get_emp_projects(
            user_id=employee.user_id,
            signed_array=employee.signed_array,
        )
        return jsonify({"success": True, "projects": projects})
    except Exception as e:
        logger.error("user_worklog_projects error employee %s: %s", employee_id, e)
        return jsonify({"success": False, "error": str(e)}), 500


@syncore_bp.route("/employees/<int:employee_id>/worklog/project-details")
@login_required
def user_worklog_project_details(employee_id: int):
    """AJAX: return modules + activities for a project (editor only, modal cascade)."""
    access = UserEmployeeAccess.query.filter_by(
        user_id=current_user.id,
        employee_id=employee_id,
        is_active=True,
        permission=UserEmployeeAccess.PERMISSION_EDITOR,
    ).first_or_404()
    employee   = access.employee
    project_id = request.args.get("project_id", "").strip()
    if not project_id:
        return jsonify({"success": False, "error": "project_id is required"}), 400
    try:
        from app.services.util_syncore import get_project_modules, get_project_activities
        modules    = get_project_modules(
            user_id=employee.user_id, signed_array=employee.signed_array,
            project_id=project_id,
        )
        activities = get_project_activities(
            user_id=employee.user_id, signed_array=employee.signed_array,
            project_id=project_id,
        )
        return jsonify({"success": True, "modules": modules, "activities": activities})
    except Exception as e:
        logger.error("user_worklog_project_details error employee %s: %s", employee_id, e)
        return jsonify({"success": False, "error": str(e)}), 500


@syncore_bp.route("/employees/<int:employee_id>/worklog/fill", methods=["POST"])
@login_required
def user_fill_work_log(employee_id: int):
    """Submit a daily work log entry (editor permission required)."""
    access = UserEmployeeAccess.query.filter_by(
        user_id=current_user.id,
        employee_id=employee_id,
        is_active=True,
        permission=UserEmployeeAccess.PERMISSION_EDITOR,
    ).first_or_404()
    employee = access.employee
    try:
        from app.services.util_syncore import fill_work_log

        project_id   = request.form.get("project_id",   "").strip()
        module_id    = request.form.get("module_id",    "").strip()
        activity_id  = request.form.get("activity_id",  "").strip()
        work_desc    = request.form.get("work_desc",    "").strip()
        hour_clocked = request.form.get("hour_clocked", "").strip()

        if not all([project_id, module_id, activity_id, work_desc, hour_clocked]):
            flash("All fields are required to submit a work log.", "danger")
            return redirect(url_for("syncore.employee_detail", access_id=access.id))

        result = fill_work_log(
            project_id=project_id,
            module_id=module_id,
            activity_id=activity_id,
            work_desc=work_desc,
            hour_clocked=hour_clocked,
            user_id=employee.user_id,
            signed_array=employee.signed_array,
        )

        if "error" in result:
            flash(f"Work log submission failed: {result['error']}", "danger")
        else:
            flash(result.get("message", "Work log submitted successfully."), "success")
            logger.info(
                "User %s filled work log for employee %s (project=%s)",
                current_user.username, employee.name, project_id,
            )

    except Exception as e:
        logger.error("user_fill_work_log error employee %s: %s", employee_id, e, exc_info=True)
        flash(f"Work log submission failed: {e}", "danger")

    return redirect(url_for("syncore.employee_detail", access_id=access.id))
