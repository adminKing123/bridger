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
