"""
app/routes/dashboard.py
------------------------
Dashboard blueprint — all routes require login.

The page itself renders instantly with no heavy DB work.
Per-service stats are fetched lazily via a JSON API called from the frontend
after page load. Each service has its own API endpoint:

    GET /dashboard/api/stats/proxy  — HTTP Proxy service statistics

Adding a new service = add one more `_<service>_stats()` helper and one
corresponding `/api/stats/<service>` route. The HTML/JS pattern stays the same.

Routes:
    GET  /dashboard                    — Main shell (fast, no DB queries)
    GET  /dashboard/api/stats/proxy    — HTTP Proxy stats JSON
    GET  /dashboard/api/stats/webex    — Webex stats JSON
    GET  /dashboard/api/stats/syncore  — SynCore stub JSON (coming soon)
"""

import logging
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, render_template
from flask_login import current_user, login_required
from sqlalchemy import func

from app import db
from app.models.proxy import ProxyConfig
from app.models.proxy_log import ProxyLog
from app.models.syncore_access import SynCoreEmployeeRequest, UserEmployeeAccess
from app.models.syncore_employee import SynCoreEmployee
from app.models.webex_config import WebexConfig
from app.models.webex_webhook import WebexWebhook
from app.models.webex_webhook_log import WebexWebhookLog

logger = logging.getLogger(__name__)

dashboard_bp = Blueprint("dashboard", __name__)


# ── Page route (no DB work) ────────────────────────────────────────────────────

@dashboard_bp.route("/dashboard")
@login_required
def dashboard():
    """Render the dashboard shell. Stats are fetched client-side via the API."""
    return render_template("dashboard/dashboard.html")


# ── JSON API — one endpoint per service ───────────────────────────────────────

@dashboard_bp.route("/dashboard/api/stats/proxy")
@login_required
def api_proxy_stats():
    """
    Return HTTP Proxy service statistics as JSON.

    Called by the frontend after page load. Scoped strictly to the current
    user — no user data can leak across accounts.
    """
    user_id   = current_user.id
    proxies   = ProxyConfig.query.filter_by(user_id=user_id).all()
    proxy_ids = [p.id for p in proxies]
    total     = len(proxies)
    running   = sum(1 for p in proxies if p.is_running)

    if not proxy_ids:
        return jsonify({
            "total": 0, "running": 0, "stopped": 0,
            "total_requests": 0, "requests_24h": 0,
            "success_rate": None,
            "daily_labels": [], "daily_counts": [],
            "method_labels": [], "method_counts": [],
            "top_proxies": [],
        })

    now       = datetime.utcnow()
    since_24h = now - timedelta(hours=24)
    since_7d  = now - timedelta(days=7)

    total_requests = ProxyLog.query.filter(
        ProxyLog.proxy_id.in_(proxy_ids)
    ).count()

    requests_24h = ProxyLog.query.filter(
        ProxyLog.proxy_id.in_(proxy_ids),
        ProxyLog.created_at >= since_24h,
    ).count()

    ok_24h = ProxyLog.query.filter(
        ProxyLog.proxy_id.in_(proxy_ids),
        ProxyLog.created_at >= since_24h,
        ProxyLog.status_code < 400,
    ).count()

    success_rate = round(ok_24h / requests_24h * 100) if requests_24h else None

    # Requests per day — last 7 days (fill gaps with 0)
    # func.date() works on SQLite, PostgreSQL, and MySQL
    daily_rows = (
        db.session.query(
            func.date(ProxyLog.created_at).label("day"),
            func.count(ProxyLog.id).label("cnt"),
        )
        .filter(ProxyLog.proxy_id.in_(proxy_ids), ProxyLog.created_at >= since_7d)
        .group_by(func.date(ProxyLog.created_at))
        .order_by(func.date(ProxyLog.created_at))
        .all()
    )
    # str() normalises both date objects (Postgres/MySQL) and strings (SQLite)
    day_map = {str(row.day): row.cnt for row in daily_rows}
    daily_labels, daily_counts = [], []
    for offset in range(6, -1, -1):
        dt = now - timedelta(days=offset)
        daily_labels.append(dt.strftime("%d %b"))
        daily_counts.append(day_map.get(dt.strftime("%Y-%m-%d"), 0))

    # HTTP method breakdown
    method_rows = (
        db.session.query(ProxyLog.method, func.count(ProxyLog.id).label("cnt"))
        .filter(ProxyLog.proxy_id.in_(proxy_ids))
        .group_by(ProxyLog.method)
        .all()
    )

    # Top 5 proxies by total request count
    top_rows = (
        db.session.query(
            ProxyConfig.id,
            ProxyConfig.name,
            ProxyConfig.status,
            func.count(ProxyLog.id).label("req_count"),
        )
        .outerjoin(ProxyLog, ProxyLog.proxy_id == ProxyConfig.id)
        .filter(ProxyConfig.user_id == user_id)
        .group_by(ProxyConfig.id)
        .order_by(func.count(ProxyLog.id).desc())
        .limit(5)
        .all()
    )

    return jsonify({
        "total":          total,
        "running":        running,
        "stopped":        total - running,
        "total_requests": total_requests,
        "requests_24h":   requests_24h,
        "success_rate":   success_rate,
        "daily_labels":   daily_labels,
        "daily_counts":   daily_counts,
        "method_labels":  [r.method for r in method_rows],
        "method_counts":  [r.cnt    for r in method_rows],
        "top_proxies":    [
            {"id": r.id, "name": r.name, "status": r.status, "count": r.req_count}
            for r in top_rows
        ],
    })


@dashboard_bp.route("/dashboard/api/stats/webex")
@login_required
def api_webex_stats():
    """
    Return Webex Integration service statistics as JSON.
    Scoped strictly to the current user.
    """
    user_id  = current_user.id
    configs  = WebexConfig.query.filter_by(user_id=user_id).all()
    cfg_ids  = [c.id for c in configs]
    total    = len(configs)
    verified = sum(1 for c in configs if c.is_verified)

    if not cfg_ids:
        return jsonify({
            "total": 0, "verified": 0,
            "total_webhooks": 0, "bridger_webhooks": 0,
            "total_events": 0, "events_24h": 0,
            "daily_labels": [], "daily_counts": [],
            "resource_labels": [], "resource_counts": [],
            "top_configs": [],
        })

    now       = datetime.utcnow()
    since_24h = now - timedelta(hours=24)
    since_7d  = now - timedelta(days=7)

    # Webhook counts
    wh_ids = [
        r.id for r in WebexWebhook.query
        .filter(WebexWebhook.config_id.in_(cfg_ids))
        .with_entities(WebexWebhook.id)
        .all()
    ]
    total_webhooks   = len(wh_ids)
    bridger_webhooks = WebexWebhook.query.filter(
        WebexWebhook.config_id.in_(cfg_ids),
        WebexWebhook.uses_bridger_target == True,
    ).count()

    total_events = WebexWebhookLog.query.filter(
        WebexWebhookLog.webhook_id.in_(wh_ids)
    ).count() if wh_ids else 0

    events_24h = WebexWebhookLog.query.filter(
        WebexWebhookLog.webhook_id.in_(wh_ids),
        WebexWebhookLog.received_at >= since_24h,
    ).count() if wh_ids else 0

    # Events per day — last 7 days
    # func.date() works on SQLite, PostgreSQL, and MySQL
    daily_rows = (
        db.session.query(
            func.date(WebexWebhookLog.received_at).label("day"),
            func.count(WebexWebhookLog.id).label("cnt"),
        )
        .filter(
            WebexWebhookLog.webhook_id.in_(wh_ids),
            WebexWebhookLog.received_at >= since_7d,
        )
        .group_by(func.date(WebexWebhookLog.received_at))
        .order_by(func.date(WebexWebhookLog.received_at))
        .all()
    ) if wh_ids else []
    # str() normalises both date objects (Postgres/MySQL) and strings (SQLite)
    day_map = {str(row.day): row.cnt for row in daily_rows}
    daily_labels, daily_counts = [], []
    for offset in range(6, -1, -1):
        dt = now - timedelta(days=offset)
        daily_labels.append(dt.strftime("%d %b"))
        daily_counts.append(day_map.get(dt.strftime("%Y-%m-%d"), 0))

    # Resource type breakdown
    resource_rows = (
        db.session.query(
            WebexWebhookLog.resource,
            func.count(WebexWebhookLog.id).label("cnt"),
        )
        .filter(WebexWebhookLog.webhook_id.in_(wh_ids))
        .group_by(WebexWebhookLog.resource)
        .all()
    ) if wh_ids else []

    # Top 5 configs by event count
    top_rows = (
        db.session.query(
            WebexConfig.id,
            WebexConfig.name,
            WebexConfig.is_verified,
            func.count(WebexWebhookLog.id).label("evt_count"),
        )
        .outerjoin(WebexWebhook, WebexWebhook.config_id == WebexConfig.id)
        .outerjoin(WebexWebhookLog, WebexWebhookLog.webhook_id == WebexWebhook.id)
        .filter(WebexConfig.user_id == user_id)
        .group_by(WebexConfig.id)
        .order_by(func.count(WebexWebhookLog.id).desc())
        .limit(5)
        .all()
    )

    return jsonify({
        "total":            total,
        "verified":         verified,
        "total_webhooks":   total_webhooks,
        "bridger_webhooks": bridger_webhooks,
        "total_events":     total_events,
        "events_24h":       events_24h,
        "daily_labels":     daily_labels,
        "daily_counts":     daily_counts,
        "resource_labels":  [r.resource or "unknown" for r in resource_rows],
        "resource_counts":  [r.cnt for r in resource_rows],
        "top_configs":      [
            {"id": r.id, "name": r.name, "verified": r.is_verified, "count": r.evt_count}
            for r in top_rows
        ],
    })


@dashboard_bp.route("/dashboard/api/stats/syncore")
@login_required
def api_syncore_stats():
    """
    Return SynCore statistics for the current user.
    Counts active accesses, permissions, and pending requests.
    """
    user_id = current_user.id

    # Active employee accesses
    accesses = (
        UserEmployeeAccess.query
        .filter_by(user_id=user_id, is_active=True)
        .all()
    )
    total_accesses = len(accesses)
    editor_count   = sum(1 for a in accesses if a.permission == UserEmployeeAccess.PERMISSION_EDITOR)
    viewer_count   = total_accesses - editor_count

    # Request counts
    all_requests = SynCoreEmployeeRequest.query.filter_by(user_id=user_id).all()
    pending_count  = sum(1 for r in all_requests if r.status == SynCoreEmployeeRequest.STATUS_PENDING)
    approved_count = sum(1 for r in all_requests if r.status == SynCoreEmployeeRequest.STATUS_APPROVED)
    rejected_count = sum(1 for r in all_requests if r.status == SynCoreEmployeeRequest.STATUS_REJECTED)

    # Recent 5 employees (most recently granted)
    recent_accesses = (
        UserEmployeeAccess.query
        .filter_by(user_id=user_id, is_active=True)
        .order_by(UserEmployeeAccess.granted_at.desc())
        .limit(5)
        .all()
    )
    recent_employees = [
        {
            "access_id":   a.id,
            "employee_id": a.employee_id,
            "name":        a.employee.name,
            "designation": a.employee.designation or "",
            "firm":        a.employee.firm_name or "",
            "permission":  a.permission,
            "is_active":   a.employee.is_active,
            "granted_at":  a.granted_at.strftime("%b %d, %Y"),
        }
        for a in recent_accesses
    ]

    return jsonify({
        "total_accesses":  total_accesses,
        "editor_count":    editor_count,
        "viewer_count":    viewer_count,
        "pending_count":   pending_count,
        "approved_count":  approved_count,
        "rejected_count":  rejected_count,
        "total_requests":  len(all_requests),
        "recent_employees": recent_employees,
    })
