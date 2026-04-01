# Bridger — Webex Integration Service

> Part of the Bridger platform. See [plan.md](plan.md) for the full project overview.

The Webex Integration service lets authenticated users connect one or more Webex
accounts (or bot tokens), register incoming webhooks from those accounts, receive
and store enriched event payloads, and browse rooms and messages through a
live Webex API viewer.

---

## Table of Contents

1. [Concepts](#concepts)
2. [Data Model](#data-model)
3. [Route Map](#route-map)
4. [Webhook Event Flow](#webhook-event-flow)
5. [Receiver Resolution](#receiver-resolution)
6. [Spaces Browser](#spaces-browser)
7. [Messages Viewer](#messages-viewer)
8. [Forms](#forms)
9. [Service Functions](#service-functions)
10. [Security Notes](#security-notes)

---

## Concepts

| Term | Meaning |
|------|---------|
| **Config** | A saved Webex account/bot token owned by a user. Stores the access token, verified identity info, and acts as the parent for webhooks. |
| **Webhook** | A Webex webhook registered (via Webex API) to send events to a Bridger receive URL. May be Bridger-managed or external. |
| **Receive URL** | `POST /webex/receive/<uuid>` — a unique public URL per webhook that Webex POSTs events to. |
| **WebhookLog** | One DB row written for every received Webex event, enriched with the full resource object (message text, sender, receiver, room type, etc.). |
| **Spaces Browser** | An AJAX-paginated UI to browse all rooms accessible to the config's token, with type filtering and search. |
| **Messages Viewer** | A cursor-based message viewer for a specific room — loads 25 messages on open, then appends older ones on demand. |
| **partner_email** | The email of the other participant in a direct (1:1) room — lazily fetched and cached on the webhook record. |

---

## Data Model

### `webex_configs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `user_id` | INTEGER FK | → `users.id` CASCADE DELETE |
| `name` | VARCHAR(100) | User-chosen display name |
| `access_token` | TEXT | Webex API token (stored as-is) |
| `webex_person_id` | VARCHAR(100) | Person ID from `GET /people/me` |
| `webex_display_name` | VARCHAR(200) | Display name from Webex |
| `webex_email` | VARCHAR(200) | Primary email from Webex |
| `webex_org_id` | VARCHAR(100) | Org ID from Webex |
| `is_verified` | BOOLEAN | True after successful `verify_token()` call |
| `last_verified_at` | DATETIME | UTC timestamp of last successful verify |
| `created_at` | DATETIME | UTC |
| `updated_at` | DATETIME | UTC, auto-updated |

**Properties:** `initials` (2-letter avatar fallback), `masked_token` (shows `••••<last4>`), `display_email`.

### `webex_webhooks`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `config_id` | INTEGER FK | → `webex_configs.id` CASCADE DELETE |
| `uuid` | VARCHAR(36) | UUID used in the receive URL — unique per webhook |
| `name` | VARCHAR(200) | Friendly name |
| `resource` | VARCHAR(50) | Webex resource type (messages, rooms, …) |
| `event` | VARCHAR(50) | Webex event type (created, updated, …) |
| `filter_str` | VARCHAR(500) | Filter expression (e.g. `roomId=Y2lzY29…`) |
| `target_url` | VARCHAR(500) | Forwarding URL (empty if Bridger-target) |
| `uses_bridger_target` | BOOLEAN | True when Bridger's own receive URL is the target |
| `secret` | VARCHAR(100) | HMAC secret registered with Webex for signature verification |
| `webex_webhook_id` | VARCHAR(100) | Webhook ID returned by Webex API |
| `webex_status` | VARCHAR(50) | Last known Webex status (`active`, `inactive`, etc.) |
| `partner_email` | VARCHAR(200) | Lazily-cached email of the other participant in a direct room |
| `created_at` | DATETIME | UTC |
| `updated_at` | DATETIME | UTC, auto-updated |

### `webex_webhook_logs`

| Column | Type | Notes |
|--------|------|-------|
| `id` | INTEGER PK | |
| `webhook_id` | INTEGER FK | → `webex_webhooks.id` CASCADE DELETE |
| `received_at` | DATETIME | UTC timestamp when event arrived |
| `client_ip` | VARCHAR(45) | Forwarded/remote IP of Webex server |
| `webex_event_id` | VARCHAR(100) | Webex event `id` field (de-duplication key) |
| `resource` | VARCHAR(50) | Resource type from payload |
| `event_type` | VARCHAR(50) | Event type from payload |
| `actor_id` | VARCHAR(100) | Person ID of the actor who triggered the event |
| `org_id` | VARCHAR(100) | Org ID from payload |
| `app_id` | VARCHAR(100) | App ID from payload |
| `owned_by` | VARCHAR(50) | `creator` or `org` ownership from payload |
| `data_json` | TEXT | Raw `data` object from the webhook payload (JSON) |
| `raw_payload` | TEXT | Full raw request body (JSON) |
| `message_text` | TEXT | Resolved message plain text (from follow-up API call) |
| `message_markdown` | TEXT | Resolved message Markdown |
| `message_html` | TEXT | Resolved message HTML |
| `message_files` | TEXT | JSON-encoded list of file attachment URLs |
| `resource_json` | TEXT | Full resolved resource object (JSON) |
| `sender_name` | VARCHAR(200) | Display name of the message sender |
| `sender_email` | VARCHAR(200) | Email of the message sender |
| `receiver_name` | VARCHAR(200) | Display name of the intended receiver (direct rooms) |
| `receiver_email` | VARCHAR(200) | Email of the intended receiver (direct rooms) |
| `room_type` | VARCHAR(20) | `direct` or `group` |
| `signature_valid` | BOOLEAN | HMAC-SHA1 signature check result |

---

## Route Map

All management routes require `@login_required`. The receive endpoint is public
and `@csrf.exempt`.

| Method | Endpoint | Auth | Description |
|--------|----------|------|-------------|
| GET | `/webex/` | ✓ | List all configs (paginated, 10/page) |
| GET/POST | `/webex/new` | ✓ | Create config — verifies token before saving |
| GET | `/webex/<id>` | ✓ | Config detail: profile, edit panel, danger zone, webhooks |
| POST | `/webex/<id>/edit` | ✓ | Save name/token edits; re-verifies if token changed |
| POST | `/webex/<id>/delete` | ✓ | Delete config + cascade delete webhooks/logs |
| POST | `/webex/<id>/verify` | ✓ | Re-verify token and refresh Webex identity fields |
| GET/POST | `/webex/<id>/webhooks/new` | ✓ | Create webhook(s) — multi-room creates one per room |
| POST | `/webex/<id>/webhooks/<wh_id>/delete` | ✓ | Delete webhook (DB + Webex API deregister) |
| POST | `/webex/<id>/webhooks/external/<webex_id>/delete` | ✓ | Delete external Webex webhook (API only) |
| GET | `/webex/<id>/webhooks/<wh_id>/logs` | ✓ | Paginated event log (25/page) with expand rows |
| POST | `/webex/<id>/webhooks/<wh_id>/logs/clear` | ✓ | Delete all log rows for a webhook |
| POST | `/webex/receive/<uuid>` | Public | Receive Webex event → enrich → store |
| GET | `/webex/<id>/rooms` | ✓ | JSON: room list for webhook-create room picker modal |
| GET | `/webex/<id>/spaces` | ✓ | Spaces browser page (SSR + AJAX pagination) |
| GET | `/webex/<id>/spaces/messages` | ✓ | Room messages page (initial 25 SSR) |
| GET | `/webex/<id>/spaces/api` | ✓ | JSON: paginated room list (AJAX prev/next) |
| GET | `/webex/<id>/spaces/messages/api` | ✓ | JSON: older messages cursor (AJAX load-more) |

---

## Webhook Event Flow

```
POST /webex/receive/<uuid>
  │
  ├─ Validate UUID format (regex) → 400 if invalid
  ├─ Look up WebexWebhook by uuid → 404 if not found
  │
  ├─ HMAC-SHA1 verification (if uses_bridger_target and secret set)
  │   ├─ Read X-Spark-Signature header
  │   ├─ Compute HMAC-SHA1(secret, raw_body)
  │   ├─ signature_valid = hmac.compare_digest(expected, actual)
  │   └─ (non-fatal: log is written even if invalid, flagged in DB)
  │
  ├─ Parse JSON payload
  │   ├─ Extract: id, resource, event, actorId, orgId, appId, ownedBy
  │   └─ Extract data object: id, roomId, roomType, personId, personEmail
  │
  ├─ Fetch full resource object (follow-up API call)
  │   └─ fetch_resource(access_token, resource, data_obj['id'])
  │       → resource_json, message_text/markdown/html/files
  │
  ├─ Resolve sender
  │   ├─ sender from resource_json: displayName + emails[0]
  │   └─ fallback: personEmail from data_obj
  │
  ├─ Resolve receiver  [see Receiver Resolution section]
  │
  ├─ Resolve room_type
  │   ├─ data_obj.get('roomType')
  │   └─ fallback: resource_obj.get('roomType')
  │
  ├─ Persist WebexWebhookLog row
  └─ HTTP 200 OK (always — Webex retries on non-200)
```

---

## Receiver Resolution

Receiver population differs by room type:

### Direct (1:1) rooms

The goal is to identify *who the message was sent to* — i.e. the person who
is **not** the sender.

**Lazy `partner_email` caching:**
When a webhook with a `roomId=` filter processes its first event:
1. If the webhook has no `partner_email` stored yet, `fetch_room_members` is
   called to list all members of that room.
2. The partner is identified as the member whose `personId` ≠ the config owner's
   `webex_person_id`.
3. The partner's email is stored on `wh.partner_email` (persisted to DB).
4. On all subsequent events for the same webhook, the cached value is used
   without any extra API call.

**Receiver assignment:**
- If `sender_email == config.webex_email` (the owner sent the message) →
  `receiver_email = wh.partner_email`, `receiver_name` resolved from resource.
- If `sender_email == wh.partner_email` (the partner sent the message) →
  `receiver_email = config.webex_email`, `receiver_name = config.webex_display_name`.
- Secondary fallback: `resource_obj.get('toPersonEmail')` if `partner_email`
  is still not cached.

### Group rooms

Group messages have no single intended receiver; the receiver fields are left
empty.

---

## Spaces Browser

Accessible at `GET /webex/<id>/spaces`.

### Type filter + search
- Three tabs: **All / Direct / Group** (full-page GET navigation with `?type=` param).
- Search box filters by room title client-side via `?q=` param (passed to API).

### AJAX pagination
- The initial page renders via SSR. Prev/Next buttons fire a `fetch()` to
  `/webex/<id>/spaces/api?type=...&q=...&page=N` which returns JSON:
  ```json
  { "rooms": [...], "page": 2, "per_page": 20, "total": 143,
    "has_prev": true, "has_next": true }
  ```
- JavaScript replaces only the `<tbody>` of the spaces table; the rest of the
  page (filter tabs, search box, pagination controls) stays on screen.

### "All" rooms — merged fetch
Webex's `GET /rooms` API returns **only group rooms** when no `type` parameter
is sent. To populate the **All** tab:
- `_fetch_rooms_by_type(token, 'direct', max)` and
  `_fetch_rooms_by_type(token, 'group', max)` are called separately.
- Results are merged and sorted by `lastActivity` descending.

---

## Messages Viewer

Accessible at `GET /webex/<id>/spaces/messages?room_id=<roomId>`.

### Initial load (SSR)
The route fetches the first 25 messages from the Webex API and renders them
server-side. The oldest message's `id` is stored in `data-before` on the
"Older messages" button.

### Load older (AJAX cursor)
When the user clicks **Older messages**:
1. JavaScript reads `data-before` from the button.
2. `fetch()` calls `/webex/<id>/spaces/messages/api?room_id=...&before_message=<id>`
   which returns:
   ```json
   { "messages": [...], "has_more": true }
   ```
3. The new message items are **prepended** to (top of) the message list.
4. `data-before` is updated to the oldest message in the new batch.
5. When `has_more` is false, the button is replaced with a "No older messages"
   label.

Messages are displayed newest-at-bottom within each batch. Avatar initials
are used as a fallback when no profile image is available.

---

## Forms

### `WebexCreateForm` (`forms/webex_forms.py`)

| Field | Type | Notes |
|-------|------|-------|
| `name` | StringField | Required, max 100 chars |
| `access_token` | StringField | Required — verified against Webex on submit |

### `WebexEditForm` (`forms/webex_forms.py`)

| Field | Type | Notes |
|-------|------|-------|
| `name` | StringField | Required |
| `access_token` | StringField | Optional — blank = keep existing token |

### `WebhookCreateForm` (`forms/webex_webhook_forms.py`)

| Field | Type | Notes |
|-------|------|-------|
| `name` | StringField | Required |
| `resource` | SelectField | messages, rooms, memberships, meetings, attachmentActions, telephony_calls, all |
| `event` | SelectField | created, updated, deleted, started, ended, all |
| `filter_str` | StringField | Optional filter expression (e.g. `roomId=Y2…`) |
| `target_url` | StringField | Optional — blank = use Bridger's own receive URL |

The webhook create page includes a **Room Picker** modal: a searchable
multi-select list of rooms fetched from `GET /webex/<id>/rooms`. Selecting
rooms automatically populates `filter_str` input(s) and creates one webhook
record per selected room.

---

## Service Functions

All functions live in `app/services/webex_service.py`. Webex API base URL:
`https://webexapis.com/v1`. All requests use an 8-second timeout.

| Function | Signature | Returns | Notes |
|----------|-----------|---------|-------|
| `verify_token` | `(access_token)` | `dict \| None` | `GET /people/me` |
| `create_webhook` | `(access_token, name, target_url, resource, event, filter_str, secret)` | `dict \| None` | `POST /webhooks` |
| `delete_webhook` | `(access_token, webhook_id)` | `bool` | `DELETE /webhooks/{id}` |
| `fetch_rooms` | `(access_token, max_results=200)` | `list[dict]` | Used by room picker AJAX |
| `fetch_all_webhooks` | `(access_token)` | `list[dict]` | Follows `Link` header pagination |
| `fetch_room_members` | `(access_token, room_id)` | `list[dict]` | Used at partner_email caching |
| `fetch_resource` | `(access_token, resource, resource_id)` | `dict \| None` | Follow-up resource enrichment after event |
| `_fetch_rooms_by_type` | `(access_token, room_type, max_results)` | `list[dict]` | Internal — single-type room fetch |
| `fetch_rooms_filtered` | `(access_token, room_type=None, max_results=500)` | `list[dict]` | Merges direct+group via two calls when `room_type=None` |
| `fetch_room_detail` | `(access_token, room_id)` | `dict \| None` | `GET /rooms/{id}` |
| `fetch_messages` | `(access_token, room_id, max_results=25, before_message=None)` | `list[dict]` | Cursor-based: passes `beforeMessage` param to Webex |

---

## Security Notes

| Concern | Implementation |
|---------|---------------|
| **HMAC signature** | Every event at `receive/<uuid>` is verified with HMAC-SHA1 against the stored `secret`. Invalid signatures are flagged (`signature_valid=False`) but not rejected — ensures all events are logged even if secret changes. |
| **CSRF exemption** | The receive endpoint is `@csrf.exempt` because Webex cannot include a CSRF token. All other Webex routes are protected by Flask-WTF's `CSRFProtect`. |
| **Ownership guard** | Every management route calls `_own_config_or_404(config_id)` which queries `filter_by(id=..., user_id=current_user.id)` — 404 (not 403) to avoid leaking resource existence. |
| **Token storage** | Access tokens are stored in plaintext in the DB. The UI only displays a masked version (`••••<last4>`) via the `masked_token` property. |
| **UUID receive URL** | The webhook receive URL uses a UUID generated via `uuid.uuid4()`. This is not guessable; Webex events from unknown UUIDs are rejected with 404. |
| **Public endpoint hardening** | The receive endpoint validates UUID format before DB lookup (prevents format-based injection). `client_ip` is taken from `X-Forwarded-For` with a fallback to `request.remote_addr`. |
| **External webhook deletion** | The "delete external webhook" route deregisters webhooks on the Webex API side using the config owner's token — verifying ownership before making the API call. |
