"""
app/routes/webex.py
--------------------
Webex integration blueprint — CRUD for Webex access-token configurations
and webhook management.

Routes
------
GET         /webex/                                         list configs
GET/POST    /webex/new                                      create config
GET         /webex/<id>                                     config detail
POST        /webex/<id>/edit                                save config edits
POST        /webex/<id>/delete                              delete config
POST        /webex/<id>/verify                              re-verify token

GET/POST    /webex/<id>/webhooks/new                        add webhook
POST        /webex/<id>/webhooks/<wh_id>/delete             delete Bridger webhook
POST        /webex/<id>/webhooks/external/<webex_id>/delete  delete external webhook
GET         /webex/<id>/webhooks/<wh_id>/logs               view event logs
POST        /webex/<id>/webhooks/<wh_id>/logs/clear         clear event logs

POST        /webex/receive/<uuid>                           receive event (public)

GET         /webex/<id>/spaces                              browse all spaces (read-only)
GET         /webex/<id>/spaces/messages                    messages in a space (read-only)

GET         /webex/<id>/spaces/api                         rooms JSON (AJAX)
GET         /webex/<id>/spaces/messages/api               messages JSON (AJAX)
"""

import hashlib
import hmac
import json
import logging
import secrets
import uuid as _uuid
from datetime import datetime, timezone

from flask import (
    Blueprint, abort, flash, jsonify, redirect, render_template,
    request, url_for,
)
from flask_login import current_user, login_required

from app import csrf, db
from app.forms.webex_forms import WebexCreateForm, WebexEditForm
from app.forms.webex_webhook_forms import WebhookCreateForm
from app.models.webex_config import WebexConfig
from app.models.webex_webhook import WebexWebhook
from app.models.webex_webhook_log import WebexWebhookLog
from app.services.webex_service import (
    create_webhook as create_webhook_api,
    delete_webhook as delete_webhook_api,
    fetch_all_webhooks,
    fetch_messages,
    fetch_resource,
    fetch_room_detail,
    fetch_room_members,
    fetch_rooms,
    fetch_rooms_filtered,
    verify_token,
)

logger = logging.getLogger(__name__)

webex_bp = Blueprint("webex", __name__, url_prefix="/webex")


# ── Internal helpers ───────────────────────────────────────────────────────────

def _own_config_or_404(config_id: int) -> WebexConfig:
    """Return the WebexConfig owned by current_user, or abort 404."""
    cfg = WebexConfig.query.filter_by(id=config_id, user_id=current_user.id).first()
    if not cfg:
        abort(404)
    return cfg


def _own_webhook_or_404(config_id: int, wh_id: int) -> WebexWebhook:
    """Return the WebexWebhook belonging to config_id, ensuring ownership."""
    cfg = _own_config_or_404(config_id)
    wh = WebexWebhook.query.filter_by(id=wh_id, config_id=cfg.id).first()
    if not wh:
        abort(404)
    return wh


def _apply_verification(cfg: WebexConfig, profile: dict) -> None:
    """Cache API profile fields onto the config record and mark verified."""
    cfg.webex_person_id    = profile.get("id", "")
    cfg.webex_display_name = profile.get("displayName", "")
    cfg.webex_email        = (profile.get("emails") or [""])[0]
    cfg.webex_org_id       = profile.get("orgId", "")
    cfg.is_verified        = True
    cfg.last_verified_at   = datetime.now(timezone.utc)


# ══════════════════════════════════════════════════════════════════════════════
# Config CRUD
# ══════════════════════════════════════════════════════════════════════════════

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
    # Webhook counts keyed by config id — single query, no N+1
    config_ids = [c.id for c in configs.items]
    wh_counts: dict[int, int] = {}
    if config_ids:
        rows = (
            db.session.query(
                WebexWebhook.config_id,
                db.func.count(WebexWebhook.id).label("cnt"),
            )
            .filter(WebexWebhook.config_id.in_(config_ids))
            .group_by(WebexWebhook.config_id)
            .all()
        )
        wh_counts = {r.config_id: r.cnt for r in rows}
    return render_template("webex/list.html", configs=configs, wh_counts=wh_counts)


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


@webex_bp.route("/<int:config_id>")
@login_required
def detail_config(config_id: int):
    """Display details of a single Webex configuration, including webhooks."""
    cfg = _own_config_or_404(config_id)
    form = WebexEditForm(obj=cfg)
    form.access_token.data = ""

    tab = request.args.get("tab", "all")  # "all" | "bridger"

    # ── Bridger-managed webhooks (DB) ──────────────────────────────────────
    page = request.args.get("wh_page", 1, type=int)
    bridger_webhooks = (
        WebexWebhook.query
        .filter_by(config_id=cfg.id)
        .order_by(WebexWebhook.created_at.desc())
        .paginate(page=page, per_page=10, error_out=False)
    )

    # ── All webhooks from Webex API — merged with DB ───────────────────────
    # Map our DB records by their Webex-assigned ID for fast lookup
    bridger_ids: set[str] = {
        wh.webex_webhook_id
        for wh in WebexWebhook.query.filter_by(config_id=cfg.id).all()
        if wh.webex_webhook_id
    }

    api_webhooks = fetch_all_webhooks(cfg.access_token) if cfg.is_verified else []
    # Webhooks that exist on Webex but were NOT created via Bridger
    external_webhooks = [
        wh for wh in api_webhooks
        if wh.get("id") not in bridger_ids
    ]

    return render_template(
        "webex/detail.html",
        cfg=cfg,
        form=form,
        webhooks=bridger_webhooks,
        external_webhooks=external_webhooks,
        tab=tab,
    )


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


@webex_bp.route("/<int:config_id>/delete", methods=["POST"])
@login_required
def delete_config(config_id: int):
    """Permanently delete a Webex configuration."""
    cfg = _own_config_or_404(config_id)
    db.session.delete(cfg)
    db.session.commit()
    flash(f'Webex configuration "{cfg.name}" deleted.', "info")
    return redirect(url_for("webex.index"))


# ══════════════════════════════════════════════════════════════════════════════
# Webhook management
# ══════════════════════════════════════════════════════════════════════════════

@webex_bp.route("/<int:config_id>/webhooks/new", methods=["GET", "POST"])
@login_required
def create_webhook(config_id: int):
    """Register a new Webex webhook against a configuration."""
    cfg = _own_config_or_404(config_id)
    form = WebhookCreateForm()

    # Pre-generate a UUID so we can show the target URL before submit
    webhook_uuid = request.form.get("webhook_uuid", "")
    try:
        webhook_uuid = str(_uuid.UUID(webhook_uuid))   # validate format
    except ValueError:
        webhook_uuid = str(_uuid.uuid4())

    default_target = url_for(
        "webex.receive_event", wh_uuid=webhook_uuid, _external=True
    )

    if request.method == "GET":
        form.target_url.data = default_target

    if form.validate_on_submit():
        target      = form.target_url.data.strip()
        uses_bridger = target == default_target

        # Multi-room selection: create one webhook per picked room
        room_filters = request.form.getlist("room_filter[]")

        if room_filters:
            created, failed = 0, 0
            for room_filter in room_filters:
                per_uuid   = str(_uuid.uuid4())
                per_target = url_for(
                    "webex.receive_event", wh_uuid=per_uuid, _external=True
                )
                per_secret = secrets.token_hex(32)
                api_result = create_webhook_api(
                    access_token=cfg.access_token,
                    name=f"{form.name.data.strip()} ({room_filter})",
                    target_url=per_target,
                    resource=form.resource.data,
                    event=form.event.data,
                    filter_str=room_filter,
                    secret=per_secret,
                )
                # Cache partner email for direct-room message webhooks
                per_partner_email = None
                if form.resource.data == "messages" and room_filter.startswith("roomId="):
                    room_id = room_filter.split("=", 1)[1]
                    members = fetch_room_members(cfg.access_token, room_id)
                    owner_email = (cfg.webex_email or "").lower()
                    for m in members:
                        if m.get("personEmail", "").lower() != owner_email:
                            per_partner_email = m.get("personEmail")
                            break

                wh = WebexWebhook(
                    config_id=cfg.id,
                    uuid=per_uuid,
                    name=f"{form.name.data.strip()} ({room_filter})",
                    resource=form.resource.data,
                    event=form.event.data,
                    filter_str=room_filter,
                    target_url=per_target,
                    uses_bridger_target=True,
                    secret=per_secret,
                    webex_webhook_id=api_result.get("id") if api_result else None,
                    webex_status=api_result.get("status", "unknown") if api_result else "unknown",
                    partner_email=per_partner_email,
                )
                db.session.add(wh)
                if api_result:
                    created += 1
                else:
                    failed += 1
            db.session.commit()
            if failed == 0:
                flash(f"{created} webhook(s) registered successfully with Webex.", "success")
            elif created == 0:
                flash("Webhooks saved locally, but none could be registered via the Webex API.", "warning")
            else:
                flash(f"{created} webhook(s) registered; {failed} could not be registered via the Webex API.", "warning")
            return redirect(url_for("webex.detail_config", config_id=cfg.id))

        # Single webhook (manual filter or no filter)
        wh_secret  = secrets.token_hex(32)

        # Register the webhook with Webex
        api_result = create_webhook_api(
            access_token=cfg.access_token,
            name=form.name.data.strip(),
            target_url=target,
            resource=form.resource.data,
            event=form.event.data,
            filter_str=form.filter_str.data.strip() or None,
            secret=wh_secret,
        )

        # Cache partner email for direct-room message webhooks
        single_partner_email = None
        raw_filter = form.filter_str.data.strip() if form.filter_str.data else ""
        if form.resource.data == "messages" and "roomId=" in raw_filter:
            room_id = raw_filter.split("roomId=", 1)[1].split("&")[0]
            members = fetch_room_members(cfg.access_token, room_id)
            owner_email = (cfg.webex_email or "").lower()
            for m in members:
                if m.get("personEmail", "").lower() != owner_email:
                    single_partner_email = m.get("personEmail")
                    break

        wh = WebexWebhook(
            config_id=cfg.id,
            uuid=webhook_uuid,
            name=form.name.data.strip(),
            resource=form.resource.data,
            event=form.event.data,
            filter_str=form.filter_str.data.strip() or None,
            target_url=target,
            uses_bridger_target=uses_bridger,
            secret=wh_secret,
            webex_webhook_id=api_result.get("id") if api_result else None,
            webex_status=api_result.get("status", "unknown") if api_result else "unknown",
            partner_email=single_partner_email,
        )

        db.session.add(wh)
        db.session.commit()

        if api_result:
            flash("Webhook registered successfully with Webex.", "success")
        else:
            flash(
                "Webhook saved locally, but could not be registered via the Webex API. "
                "The access token may lack the spark:webhooks_write scope.",
                "warning",
            )

        return redirect(url_for("webex.detail_config", config_id=cfg.id))

    return render_template(
        "webex/webhook_create.html",
        cfg=cfg,
        form=form,
        webhook_uuid=webhook_uuid,
        default_target=default_target,
    )


@webex_bp.route("/<int:config_id>/webhooks/<int:wh_id>/delete", methods=["POST"])
@login_required
def delete_webhook(config_id: int, wh_id: int):
    """Delete a webhook locally and deregister it from Webex."""
    wh = _own_webhook_or_404(config_id, wh_id)
    cfg = wh.config

    if wh.webex_webhook_id:
        deleted = delete_webhook_api(cfg.access_token, wh.webex_webhook_id)
        if not deleted:
            logger.warning(
                "Could not delete Webex webhook %s from API — removing locally anyway.",
                wh.webex_webhook_id,
            )

    db.session.delete(wh)
    db.session.commit()
    flash(f'Webhook "{wh.name}" removed.', "info")
    return redirect(url_for("webex.detail_config", config_id=cfg.id, tab="bridger"))


@webex_bp.route("/<int:config_id>/webhooks/external/<string:webex_wh_id>/delete", methods=["POST"])
@login_required
def delete_external_webhook(config_id: int, webex_wh_id: str):
    """Delete a webhook that exists on Webex but was not created via Bridger."""
    cfg = _own_config_or_404(config_id)
    deleted = delete_webhook_api(cfg.access_token, webex_wh_id)
    if deleted:
        flash("External webhook removed from Webex.", "info")
    else:
        flash("Could not remove the webhook from Webex — it may already be gone.", "warning")
    return redirect(url_for("webex.detail_config", config_id=cfg.id, tab="all"))


@webex_bp.route("/<int:config_id>/webhooks/<int:wh_id>/logs")
@login_required
def webhook_logs(config_id: int, wh_id: int):
    """Display paginated event logs for a single webhook."""
    wh = _own_webhook_or_404(config_id, wh_id)
    page = request.args.get("page", 1, type=int)
    logs = (
        WebexWebhookLog.query
        .filter_by(webhook_id=wh.id)
        .order_by(WebexWebhookLog.received_at.desc())
        .paginate(page=page, per_page=25, error_out=False)
    )
    return render_template("webex/webhook_logs.html", wh=wh, cfg=wh.config, logs=logs)


@webex_bp.route("/<int:config_id>/webhooks/<int:wh_id>/logs/clear", methods=["POST"])
@login_required
def clear_webhook_logs(config_id: int, wh_id: int):
    """Permanently delete all event logs for a webhook."""
    wh = _own_webhook_or_404(config_id, wh_id)
    WebexWebhookLog.query.filter_by(webhook_id=wh.id).delete()
    db.session.commit()
    flash(f'All logs for webhook "{wh.name}" cleared.', "info")
    return redirect(url_for("webex.webhook_logs", config_id=config_id, wh_id=wh_id))


# ══════════════════════════════════════════════════════════════════════════════
# Public receive endpoint — called by Webex when an event fires
# ══════════════════════════════════════════════════════════════════════════════

@webex_bp.route("/receive/<string:wh_uuid>", methods=["POST"])
@csrf.exempt
def receive_event(wh_uuid: str):
    """
    Receive a Webex webhook event and store it as a WebexWebhookLog.

    This endpoint is public (no login required, CSRF exempt) and must
    always return 200 OK so Webex does not retry delivery.
    """
    # Validate UUID format to prevent DB lookup on garbage input
    try:
        str(_uuid.UUID(wh_uuid))
    except ValueError:
        return ("Bad Request", 400)

    wh = WebexWebhook.query.filter_by(uuid=wh_uuid).first()
    if not wh:
        # Return 200 to prevent Webex retry loops; just silently discard
        return ("", 200)

    raw_body = request.get_data()

    # ── Signature verification ─────────────────────────────────────────────
    sig_valid: bool | None = None
    if wh.secret and wh.uses_bridger_target:
        provided = request.headers.get("X-Spark-Signature", "")
        expected = hmac.new(
            wh.secret.encode(), raw_body, hashlib.sha1
        ).hexdigest()
        sig_valid = hmac.compare_digest(expected, provided)

    # ── Parse payload ──────────────────────────────────────────────────────
    try:
        payload: dict = json.loads(raw_body)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    data_obj = payload.get("data", {})

    # ── Determine client IP ────────────────────────────────────────────────
    client_ip = (
        request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        or request.remote_addr
    )

    # ── Fetch full resource from Webex API (e.g. message text) ──────────────
    resource_type = payload.get("resource")   # "messages", "rooms", …
    resource_id   = data_obj.get("id")        # data.id from the envelope
    actor_id      = payload.get("actorId")
    resource_obj: dict | None = None

    if resource_id and resource_type:
        resource_obj = fetch_resource(
            wh.config.access_token, resource_type, resource_id
        )

    # Sender — email is in the webhook envelope directly
    sender_name  = None
    sender_email = data_obj.get("personEmail")

    # Room type — prefer data_obj (always present for messages events);
    # fall back to the fetched resource object for other resource types.
    room_type = (
        data_obj.get("roomType")
        or (resource_obj.get("roomType") if resource_obj else None)
    )

    # Receiver — determined from sender + owner identity.
    #   • direct rooms:  one of {owner, partner} sent the message
    #   • group rooms:   no single receiver; leave blank
    receiver_name  = None
    receiver_email = None
    owner_email    = wh.config.webex_email

    if room_type == "direct":
        if sender_email and sender_email.lower() == (owner_email or "").lower():
            # Owner sent the message — receiver is the partner.
            # 1) Try the partner_email cached at webhook creation.
            # 2) Fall back to toPersonEmail in the fetched message object
            #    (present when the message was created via the API with toPersonEmail).
            receiver_email = (
                wh.partner_email
                or (resource_obj.get("toPersonEmail") if resource_obj else None)
            )
        else:
            # Someone else sent to the owner — owner is the receiver.
            receiver_email = owner_email
            receiver_name  = wh.config.webex_display_name

            # Lazily cache the partner email so future owner→partner messages
            # can resolve the receiver without an extra API call.
            if not wh.partner_email and sender_email:
                wh.partner_email = sender_email
                # commit happens below with the log entry
    # group / None — receiver_email stays None (multiple recipients)

    # ── Persist log entry ──────────────────────────────────────────────────
    entry = WebexWebhookLog(
        webhook_id=wh.id,
        client_ip=client_ip,
        webex_event_id=payload.get("id"),
        resource=resource_type,
        event_type=payload.get("event"),
        actor_id=actor_id,
        org_id=payload.get("orgId"),
        app_id=payload.get("appId"),
        owned_by=payload.get("ownedBy"),
        data_json=json.dumps(data_obj) if data_obj else None,
        raw_payload=json.dumps(payload) if payload else raw_body.decode("utf-8", errors="replace"),
        signature_valid=sig_valid,
        # Enriched fields from follow-up API call
        message_text     = resource_obj.get("text")                          if resource_obj else None,
        message_markdown = resource_obj.get("markdown")                      if resource_obj else None,
        message_html     = resource_obj.get("html")                          if resource_obj else None,
        message_files    = json.dumps(resource_obj.get("files", []))         if resource_obj and resource_obj.get("files") else None,
        resource_json    = json.dumps(resource_obj)                           if resource_obj else None,
        # Sender / receiver
        sender_name    = sender_name,
        sender_email   = sender_email,
        receiver_name  = receiver_name,
        receiver_email = receiver_email,
        room_type      = room_type,
    )
    db.session.add(entry)
    db.session.commit()

    return ("", 200)


# ══════════════════════════════════════════════════════════════════════════════
# Room picker — AJAX endpoint
# ══════════════════════════════════════════════════════════════════════════════

@webex_bp.route("/<int:config_id>/rooms", methods=["GET"])
@login_required
def list_rooms(config_id: int):
    """
    Return JSON list of Webex rooms for the room picker.
    Called from the webhook create form via fetch().
    """
    cfg = _own_config_or_404(config_id)
    if not cfg.access_token:
        return jsonify({"error": "No access token configured."}), 400

    rooms = fetch_rooms(cfg.access_token)
    return jsonify({
        "me": {
            "personId":    cfg.webex_person_id or "",
            "displayName": cfg.webex_display_name or "Me",
            "email":       cfg.webex_email or "",
        },
        "rooms": [
            {
                "id":           r.get("id", ""),
                "title":        r.get("title", "Untitled"),
                "type":         r.get("type", "group"),
                "isLocked":     r.get("isLocked", False),
                "lastActivity": r.get("lastActivity", ""),
            }
            for r in rooms
        ]
    })


# ══════════════════════════════════════════════════════════════════════════════
# Spaces browser — read-only views into Webex rooms and messages
# ══════════════════════════════════════════════════════════════════════════════

@webex_bp.route("/<int:config_id>/spaces")
@login_required
def spaces(config_id: int):
    """
    List all Webex spaces the token has access to.
    Supports filtering by type (direct / group) and title search.
    Pagination is client-side (all rooms fetched once from Webex API).
    """
    cfg = _own_config_or_404(config_id)
    if not cfg.is_verified:
        flash("Verify the Webex token before browsing spaces.", "warning")
        return redirect(url_for("webex.detail_config", config_id=cfg.id))

    room_type = request.args.get("type", "").strip()   # "" | "direct" | "group"
    q         = request.args.get("q",    "").strip().lower()
    page      = request.args.get("page",  1, type=int)

    all_rooms = fetch_rooms_filtered(cfg.access_token, room_type=room_type or None)

    # Title search (local — Webex API has no keyword search for rooms)
    if q:
        all_rooms = [r for r in all_rooms if q in (r.get("title") or "").lower()]

    per_page    = 20
    total       = len(all_rooms)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page        = max(1, min(page, total_pages))
    rooms_page  = all_rooms[(page - 1) * per_page : page * per_page]

    return render_template(
        "webex/spaces.html",
        cfg=cfg,
        rooms=rooms_page,
        total=total,
        page=page,
        per_page=per_page,
        total_pages=total_pages,
        room_type=room_type,
        q=q,
    )


@webex_bp.route("/<int:config_id>/spaces/messages")
@login_required
def room_messages(config_id: int):
    """
    Show messages in a specific Webex space.
    Cursor-based pagination via the ``before`` query param (a message ID).
    This endpoint is strictly read-only — no writes to Webex.
    """
    cfg = _own_config_or_404(config_id)
    if not cfg.is_verified:
        flash("Verify the Webex token before viewing messages.", "warning")
        return redirect(url_for("webex.detail_config", config_id=cfg.id))

    room_id = request.args.get("room_id", "").strip()
    if not room_id:
        return redirect(url_for("webex.spaces", config_id=cfg.id))

    before_message = request.args.get("before", "").strip() or None

    room = fetch_room_detail(cfg.access_token, room_id)
    if room is None:
        flash("Space not found or access denied.", "warning")
        return redirect(url_for("webex.spaces", config_id=cfg.id))

    per_page = 25
    messages = fetch_messages(
        cfg.access_token,
        room_id=room_id,
        max_results=per_page,
        before_message=before_message,
    )

    # If exactly per_page returned there are likely older messages
    has_older = len(messages) == per_page
    oldest_id = messages[-1]["id"] if messages else None

    return render_template(
        "webex/room_messages.html",
        cfg=cfg,
        room=room,
        messages=messages,
        room_id=room_id,
        before_message=before_message,
        has_older=has_older,
        oldest_id=oldest_id,
    )


# ══════════════════════════════════════════════════════════════════════════════
# JSON API endpoints — consumed by JS in spaces.html / room_messages.html
# ══════════════════════════════════════════════════════════════════════════════

@webex_bp.route("/<int:config_id>/spaces/api")
@login_required
def spaces_api(config_id: int):
    """Return a page of Webex rooms as JSON for AJAX pagination."""
    cfg = _own_config_or_404(config_id)
    if not cfg.is_verified:
        return jsonify({"error": "Token not verified"}), 400

    room_type = request.args.get("type", "").strip()
    q         = request.args.get("q",    "").strip().lower()
    page      = request.args.get("page",  1, type=int)

    all_rooms = fetch_rooms_filtered(cfg.access_token, room_type=room_type or None)

    if q:
        all_rooms = [r for r in all_rooms if q in (r.get("title") or "").lower()]

    per_page    = 20
    total       = len(all_rooms)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page        = max(1, min(page, total_pages))
    rooms_page  = all_rooms[(page - 1) * per_page : page * per_page]

    return jsonify({
        "rooms":       rooms_page,
        "total":       total,
        "page":        page,
        "per_page":    per_page,
        "total_pages": total_pages,
    })


@webex_bp.route("/<int:config_id>/spaces/messages/api")
@login_required
def room_messages_api(config_id: int):
    """Return older messages as JSON for AJAX load-more."""
    cfg = _own_config_or_404(config_id)
    if not cfg.is_verified:
        return jsonify({"error": "Token not verified"}), 400

    room_id        = request.args.get("room_id", "").strip()
    before_message = request.args.get("before",  "").strip() or None

    if not room_id:
        return jsonify({"error": "room_id required"}), 400

    per_page = 25
    messages = fetch_messages(
        cfg.access_token,
        room_id=room_id,
        max_results=per_page,
        before_message=before_message,
    )

    has_older = len(messages) == per_page
    oldest_id = messages[-1]["id"] if messages else None

    return jsonify({
        "messages":  messages,
        "has_older": has_older,
        "oldest_id": oldest_id,
    })
