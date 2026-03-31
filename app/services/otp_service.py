"""
app/services/otp_service.py
----------------------------
Stateless helpers for creating and verifying OTP records in the database.

Public API:
    create_otp(user_id, purpose, expiry_minutes) -> str
    verify_otp(user_id, otp_code, purpose)       -> bool
"""

import secrets
import logging
from datetime import datetime, timezone, timedelta

from app import db
from app.models.user import OTP

logger = logging.getLogger(__name__)


def _generate_otp_code() -> str:
    """
    Generate a cryptographically secure 6-digit OTP.

    Uses `secrets.randbelow` to ensure uniform distribution without
    the modular bias that a simple `% 10^6` would introduce.
    """
    return str(secrets.randbelow(900_000) + 100_000)


def create_otp(user_id: int, purpose: str, expiry_minutes: int = 10) -> str:
    """
    Generate a new OTP for a user purpose, invalidate previous ones, and
    persist it to the database.

    Args:
        user_id:        ID of the target user.
        purpose:        Either OTP.OTP_PURPOSE_EMAIL_VERIFY or
                        OTP.OTP_PURPOSE_FORGOT_PASSWORD.
        expiry_minutes: Minutes until the OTP expires (default 10).

    Returns:
        The plaintext 6-digit OTP string to include in the email.
    """
    # Invalidate any existing, unused OTPs for this user + purpose
    OTP.query.filter_by(
        user_id=user_id,
        purpose=purpose,
        is_used=False,
    ).update({"is_used": True})

    otp_code = _generate_otp_code()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)

    new_otp = OTP(
        user_id=user_id,
        otp_code=otp_code,
        purpose=purpose,
        expires_at=expires_at,
    )
    db.session.add(new_otp)
    db.session.commit()

    logger.debug(
        "OTP created — user_id=%s purpose=%s expires_at=%s",
        user_id,
        purpose,
        expires_at,
    )
    return otp_code


def verify_otp(user_id: int, otp_code: str, purpose: str) -> bool:
    """
    Verify an OTP submitted by the user.

    Looks up the most recent matching OTP that is unused, then checks
    whether it has expired. On success, marks the OTP as used.

    Args:
        user_id:  ID of the user attempting verification.
        otp_code: 6-digit code submitted by the user.
        purpose:  Expected purpose of the OTP.

    Returns:
        True if the OTP is valid (correct, unused, not expired).
        False otherwise — no information about why is returned to the caller
        to prevent enumeration.
    """
    otp: OTP | None = (
        OTP.query.filter_by(
            user_id=user_id,
            otp_code=otp_code,
            purpose=purpose,
            is_used=False,
        )
        .order_by(OTP.created_at.desc())
        .first()
    )

    if otp is None:
        logger.debug("OTP not found — user_id=%s purpose=%s", user_id, purpose)
        return False

    if not otp.is_valid():
        logger.debug(
            "OTP expired or already used — id=%s user_id=%s", otp.id, user_id
        )
        return False

    # Consume the OTP
    otp.is_used = True
    db.session.commit()

    logger.debug("OTP verified — id=%s user_id=%s purpose=%s", otp.id, user_id, purpose)
    return True
