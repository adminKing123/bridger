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


# ── SynCore employee access request emails ────────────────────────────────────

def send_employee_access_request_email(
    admin_email: str,
    requester_username: str,
    requester_email: str,
    employee_name: str,
    employee_email: str,
    requested_permission: str,
    review_url: str,
) -> bool:
    """
    Notify the admin about a new SynCore employee access request.

    Args:
        admin_email:           Admin's email address (from SMTP_USER / ADMIN_EMAIL env).
        requester_username:    The user who submitted the request.
        requester_email:       The requester's account email.
        employee_name:         Name of the employee being requested.
        employee_email:        Email of the requested employee.
        requested_permission:  'viewer' or 'editor'.
        review_url:            Absolute URL to the admin review page.

    Returns:
        True if the email was sent successfully.
    """
    subject = f"[Bridger] New SynCore Access Request from {requester_username}"
    permission_label = requested_permission.capitalize()
    html_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; background:#f8f9fa; padding:30px;">
      <div style="max-width:560px;margin:0 auto;background:#fff;border-radius:8px;
                  padding:32px;box-shadow:0 2px 8px rgba(0,0,0,.08);">
        <h2 style="color:#4361ee;margin-top:0;">New Employee Access Request</h2>
        <p>A user has requested access to a SynCore employee profile.</p>
        <table style="width:100%;border-collapse:collapse;margin:20px 0;">
          <tr>
            <td style="padding:8px 12px;background:#f8f9fa;font-weight:600;border-radius:4px 0 0 4px;width:40%;">Requested By</td>
            <td style="padding:8px 12px;background:#f0f4ff;border-radius:0 4px 4px 0;">{requester_username} &lt;{requester_email}&gt;</td>
          </tr>
          <tr><td colspan="2" style="height:4px;"></td></tr>
          <tr>
            <td style="padding:8px 12px;background:#f8f9fa;font-weight:600;border-radius:4px 0 0 4px;">Employee</td>
            <td style="padding:8px 12px;background:#f0f4ff;border-radius:0 4px 4px 0;">{employee_name} &lt;{employee_email}&gt;</td>
          </tr>
          <tr><td colspan="2" style="height:4px;"></td></tr>
          <tr>
            <td style="padding:8px 12px;background:#f8f9fa;font-weight:600;border-radius:4px 0 0 4px;">Permission</td>
            <td style="padding:8px 12px;background:#f0f4ff;border-radius:0 4px 4px 0;">{permission_label}</td>
          </tr>
        </table>
        <div style="text-align:center;margin:28px 0;">
          <a href="{review_url}"
             style="display:inline-block;background:#4361ee;color:#fff;padding:12px 28px;
                    border-radius:6px;font-weight:600;text-decoration:none;">
            Review Request
          </a>
        </div>
        <hr style="border:none;border-top:1px solid #e9ecef;margin:24px 0;">
        <p style="color:#adb5bd;font-size:12px;text-align:center;">
          &copy; 2026 Bridger &mdash; This is an automated message, please do not reply.
        </p>
      </div>
    </body>
    </html>
    """
    text_body = (
        f"New SynCore access request from {requester_username} ({requester_email}).\n\n"
        f"Employee: {employee_name} ({employee_email})\n"
        f"Permission: {permission_label}\n\n"
        f"Review: {review_url}"
    )
    return send_email(admin_email, subject, html_body, text_body)


def send_request_approved_email(
    to_email: str,
    username: str,
    employee_name: str,
    permission: str,
) -> bool:
    """
    Notify a user that their SynCore employee access request was approved.

    Args:
        to_email:     Recipient address.
        username:     User's display name.
        employee_name: Name of the employee access was granted for.
        permission:   'viewer' or 'editor'.

    Returns:
        True if the email was sent successfully.
    """
    subject = f"[Bridger] SynCore Access Approved — {employee_name}"
    permission_label = permission.capitalize()
    html_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; background:#f8f9fa; padding:30px;">
      <div style="max-width:500px;margin:0 auto;background:#fff;border-radius:8px;
                  padding:32px;box-shadow:0 2px 8px rgba(0,0,0,.08);">
        <h2 style="color:#198754;margin-top:0;">&#10003; Access Approved</h2>
        <p>Hi <strong>{username}</strong>,</p>
        <p>
          Your request to access the SynCore profile for
          <strong>{employee_name}</strong> has been approved with
          <strong>{permission_label}</strong> permission.
        </p>
        <p>You can now view this employee's details, attendance, and project logs
           from the SynCore section of your Bridger account.</p>
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
        f"Your request to access {employee_name} has been approved ({permission_label}).\n"
        f"Log in to Bridger to view their profile."
    )
    return send_email(to_email, subject, html_body, text_body)


def send_request_rejected_email(
    to_email: str,
    username: str,
    employee_name: str,
    reason: str = "",
) -> bool:
    """
    Notify a user that their SynCore employee access request was rejected.

    Args:
        to_email:     Recipient address.
        username:     User's display name.
        employee_name: Name of the requested employee.
        reason:       Optional rejection reason from admin.

    Returns:
        True if the email was sent successfully.
    """
    subject = f"[Bridger] SynCore Access Request — {employee_name}"
    reason_html = (
        f"<p><strong>Reason:</strong> {reason}</p>" if reason else ""
    )
    reason_text = f"\nReason: {reason}" if reason else ""
    html_body = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head><meta charset="UTF-8"></head>
    <body style="font-family: Arial, sans-serif; background:#f8f9fa; padding:30px;">
      <div style="max-width:500px;margin:0 auto;background:#fff;border-radius:8px;
                  padding:32px;box-shadow:0 2px 8px rgba(0,0,0,.08);">
        <h2 style="color:#dc3545;margin-top:0;">Access Request Not Approved</h2>
        <p>Hi <strong>{username}</strong>,</p>
        <p>
          Your request to access the SynCore profile for
          <strong>{employee_name}</strong> was not approved at this time.
        </p>
        {reason_html}
        <p style="color:#6c757d;font-size:14px;">
          You may contact your administrator for further information or submit a new request.
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
        f"Your request to access {employee_name} was not approved.{reason_text}\n"
        f"Contact your administrator for more information."
    )
    return send_email(to_email, subject, html_body, text_body)
