"""
app/services/email_service.py
------------------------------
SMTP email delivery using Python's built-in smtplib over STARTTLS (port 587).

Public helpers:
    send_email(...)                    — low-level sender
    send_verification_otp_email(...)   — signup OTP email
    send_password_reset_otp_email(...) — password-reset OTP email
"""

import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app

logger = logging.getLogger(__name__)


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
) -> bool:
    """
    Send an email via SMTP with STARTTLS.

    Args:
        to_email:  Recipient email address.
        subject:   Email subject line.
        html_body: HTML version of the body.
        text_body: Plain-text fallback (optional).

    Returns:
        True on success, False on any SMTP / connection failure.
    """
    smtp_host: str = current_app.config["SMTP_HOST"]
    smtp_port: int = current_app.config["SMTP_PORT"]
    smtp_user: str = current_app.config["SMTP_USER"]
    smtp_password: str = current_app.config["SMTP_APP_PASSWORD"]

    if not smtp_user or not smtp_password:
        logger.error("SMTP credentials are not configured.")
        return False

    # Build multipart/alternative message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Bridger <{smtp_user}>"
    msg["To"] = to_email

    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
        logger.info("Email sent to %s — subject: %s", to_email, subject)
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed. Check SMTP_USER and SMTP_APP_PASSWORD.")
    except smtplib.SMTPException as exc:
        logger.error("SMTP error sending to %s: %s", to_email, exc)
    except OSError as exc:
        logger.error("Network error sending email to %s: %s", to_email, exc)

    return False


# ── Specialised email helpers ─────────────────────────────────────────────────

def send_verification_otp_email(to_email: str, username: str, otp_code: str) -> bool:
    """
    Send an email-verification OTP to a newly registered user.

    Args:
        to_email:  Recipient address.
        username:  Display name used in greeting.
        otp_code:  6-digit OTP string.

    Returns:
        True if the email was sent successfully.
    """
    subject = "Verify your Bridger account"
    html_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; background:#f8f9fa; padding:30px;">
      <div style="max-width:500px;margin:0 auto;background:#fff;border-radius:8px;
                  padding:32px;box-shadow:0 2px 8px rgba(0,0,0,.08);">
        <h2 style="color:#4361ee;margin-top:0;">Verify Your Email</h2>
        <p>Hi <strong>{username}</strong>,</p>
        <p>Thanks for signing up! Please use the code below to verify your email address:</p>
        <div style="text-align:center;margin:28px 0;">
          <span style="display:inline-block;font-size:36px;font-weight:700;letter-spacing:10px;
                       color:#4361ee;background:#eef0fd;padding:16px 32px;border-radius:8px;">
            {otp_code}
          </span>
        </div>
        <p style="color:#6c757d;font-size:14px;">
          This code expires in <strong>10 minutes</strong>.
          If you did not create an account, you can safely ignore this email.
        </p>
        <hr style="border:none;border-top:1px solid #e9ecef;margin:24px 0;">
        <p style="color:#adb5bd;font-size:12px;text-align:center;">
          &copy; 2026 Bridger &mdash; This is an automated message, please do not reply.
        </p>
      </div>
    </body>
    </html>
    """
    text_body = (
        f"Hi {username},\n\n"
        f"Your Bridger email verification code is: {otp_code}\n\n"
        f"This code expires in 10 minutes.\n"
        f"If you did not sign up, please ignore this email."
    )
    return send_email(to_email, subject, html_body, text_body)


def send_password_reset_otp_email(to_email: str, username: str, otp_code: str) -> bool:
    """
    Send a password-reset OTP to a verified user.

    Args:
        to_email:  Recipient address.
        username:  Display name used in greeting.
        otp_code:  6-digit OTP string.

    Returns:
        True if the email was sent successfully.
    """
    subject = "Bridger password reset code"
    html_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; background:#f8f9fa; padding:30px;">
      <div style="max-width:500px;margin:0 auto;background:#fff;border-radius:8px;
                  padding:32px;box-shadow:0 2px 8px rgba(0,0,0,.08);">
        <h2 style="color:#e63946;margin-top:0;">Password Reset</h2>
        <p>Hi <strong>{username}</strong>,</p>
        <p>We received a request to reset your Bridger password. Use the code below:</p>
        <div style="text-align:center;margin:28px 0;">
          <span style="display:inline-block;font-size:36px;font-weight:700;letter-spacing:10px;
                       color:#e63946;background:#fdf0f1;padding:16px 32px;border-radius:8px;">
            {otp_code}
          </span>
        </div>
        <p style="color:#6c757d;font-size:14px;">
          This code expires in <strong>10 minutes</strong>.
          If you did not request a password reset, you can safely ignore this email.
        </p>
        <hr style="border:none;border-top:1px solid #e9ecef;margin:24px 0;">
        <p style="color:#adb5bd;font-size:12px;text-align:center;">
          &copy; 2026 Bridger &mdash; This is an automated message, please do not reply.
        </p>
      </div>
    </body>
    </html>
    """
    text_body = (
        f"Hi {username},\n\n"
        f"Your Bridger password reset code is: {otp_code}\n\n"
        f"This code expires in 10 minutes.\n"
        f"If you did not request a reset, please ignore this email."
    )
    return send_email(to_email, subject, html_body, text_body)
