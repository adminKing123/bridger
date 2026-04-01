"""
app/services/webex_service.py
------------------------------
Webex REST API helpers.

Functions
---------
verify_token(access_token) → dict | None
    Calls GET /people/me with the given bearer token.
    Returns the parsed JSON body on success, or None on any failure
    (invalid token, network error, non-200 response).

create_webhook(access_token, name, target_url, resource, event,
               filter_str, secret) → dict | None
    Registers a new webhook via POST /webhooks.
    Returns the parsed JSON response on success, or None on failure.

delete_webhook(access_token, webhook_id) → bool
    Deletes a webhook via DELETE /webhooks/{id}.
    Returns True on success (204), False otherwise.
"""

import logging

import requests

logger = logging.getLogger(__name__)

_WEBEX_API_BASE = "https://webexapis.com/v1"
_REQUEST_TIMEOUT = 8  # seconds


def verify_token(access_token: str) -> dict | None:
    """
    Verify a Webex access token by calling the people/me endpoint.

    Args:
        access_token: The Webex bearer token to verify.

    Returns:
        Parsed JSON dict from the API on success, or None on failure.
    """
    try:
        response = requests.get(
            f"{_WEBEX_API_BASE}/people/me",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=_REQUEST_TIMEOUT,
        )
        if response.status_code == 200:
            return response.json()
        logger.warning(
            "Webex token verification failed — status %s", response.status_code
        )
        return None
    except requests.RequestException as exc:
        logger.warning("Webex API request error: %s", exc)
        return None


def create_webhook(
    access_token: str,
    name: str,
    target_url: str,
    resource: str,
    event: str,
    filter_str: str | None = None,
    secret: str | None = None,
) -> dict | None:
    """
    Register a new Webex webhook via POST /webhooks.

    Args:
        access_token: Webex bearer token for the config.
        name:         Human-readable webhook name.
        target_url:   URL Webex will POST events to.
        resource:     Webex resource type (messages, rooms, …).
        event:        Event type (created, updated, deleted, all, …).
        filter_str:   Optional Webex filter expression.
        secret:       Optional HMAC-SHA1 signing secret.

    Returns:
        Parsed JSON dict from Webex API on success, or None on failure.
    """
    payload: dict = {
        "name":      name,
        "targetUrl": target_url,
        "resource":  resource,
        "event":     event,
    }
    if filter_str:
        payload["filter"] = filter_str
    if secret:
        payload["secret"] = secret

    try:
        response = requests.post(
            f"{_WEBEX_API_BASE}/webhooks",
            json=payload,
            headers={
                "Authorization":  f"Bearer {access_token}",
                "Content-Type":   "application/json",
            },
            timeout=_REQUEST_TIMEOUT,
        )
        if response.status_code == 200:
            return response.json()
        logger.warning(
            "Webex create_webhook failed — status %s: %s",
            response.status_code,
            response.text[:200],
        )
        return None
    except requests.RequestException as exc:
        logger.warning("Webex create_webhook request error: %s", exc)
        return None


def delete_webhook(access_token: str, webhook_id: str) -> bool:
    """
    Delete a Webex webhook via DELETE /webhooks/{id}.

    Args:
        access_token: Webex bearer token for the config.
        webhook_id:   The Webex-assigned webhook ID to delete.

    Returns:
        True if deletion was successful (HTTP 204), False otherwise.
    """
    try:
        response = requests.delete(
            f"{_WEBEX_API_BASE}/webhooks/{webhook_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_REQUEST_TIMEOUT,
        )
        if response.status_code == 204:
            return True
        logger.warning(
            "Webex delete_webhook failed — status %s", response.status_code
        )
        return False
    except requests.RequestException as exc:
        logger.warning("Webex delete_webhook request error: %s", exc)
        return False


def fetch_rooms(access_token: str, max_results: int = 200) -> list[dict]:
    """
    Fetch the list of Webex rooms/spaces the token has access to.

    Args:
        access_token: Webex bearer token.
        max_results:  Maximum number of rooms to return (Webex cap: 1000).

    Returns:
        List of room dicts (id, title, type, isLocked, lastActivity, created).
        Returns an empty list on any error.
    """
    try:
        response = requests.get(
            f"{_WEBEX_API_BASE}/rooms",
            params={"max": max_results, "sortBy": "lastactivity"},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            timeout=_REQUEST_TIMEOUT,
        )
        if response.status_code == 200:
            return response.json().get("items", [])
        logger.warning(
            "Webex fetch_rooms failed — status %s", response.status_code
        )
        return []
    except requests.RequestException as exc:
        logger.warning("Webex fetch_rooms request error: %s", exc)
        return []


def fetch_all_webhooks(access_token: str) -> list[dict]:
    """
    Fetch every webhook registered under this Webex access token.

    Follows Webex pagination (max 100 per page) until all pages are consumed.

    Returns:
        List of webhook dicts from the Webex API, or an empty list on error.
        Each dict contains at minimum: id, name, targetUrl, resource, event,
        filter, status, created, orgId, appId, ownedBy, actorId.
    """
    results: list[dict] = []
    params: dict = {"max": 100}

    try:
        while True:
            response = requests.get(
                f"{_WEBEX_API_BASE}/webhooks",
                params=params,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Content-Type": "application/json",
                },
                timeout=_REQUEST_TIMEOUT,
            )
            if response.status_code != 200:
                logger.warning(
                    "Webex fetch_all_webhooks failed — status %s", response.status_code
                )
                break

            data = response.json()
            items = data.get("items", [])
            results.extend(items)

            # Webex uses Link header for pagination
            link_header = response.headers.get("Link", "")
            if 'rel="next"' in link_header:
                # Extract the next cursor from the Link header
                import re
                match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
                if match:
                    from urllib.parse import urlparse, parse_qs
                    next_url = match.group(1)
                    qs = parse_qs(urlparse(next_url).query)
                    params = {k: v[0] for k, v in qs.items()}
                    continue
            break

    except requests.RequestException as exc:
        logger.warning("Webex fetch_all_webhooks request error: %s", exc)

    return results
