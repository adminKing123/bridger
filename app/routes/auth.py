"""
app/routes/auth.py
-------------------
Authentication blueprint.

Routes:
    GET/POST  /auth/signup          — Register a new account
    GET/POST  /auth/verify-email    — Submit email verification OTP
    POST      /auth/resend-otp      — Resend email verification OTP
    GET/POST  /auth/login           — Sign in
    GET       /auth/logout          — Sign out
    GET/POST  /auth/forgot-password — Request a password-reset OTP
    GET/POST  /auth/reset-password  — Submit OTP + new password
"""

import logging
from urllib.parse import urlparse, urljoin

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    session,
    request,
)
from flask_login import login_user, logout_user, login_required, current_user

from app import db, bcrypt
from app.models.user import User, OTP
from app.forms.auth_forms import (
    SignupForm,
    LoginForm,
    VerifyEmailForm,
    ForgotPasswordForm,
    ResetPasswordForm,
)
from app.services.otp_service import create_otp, verify_otp
from app.services.email_service import (
    send_verification_otp_email,
    send_password_reset_otp_email,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# ── Internal helper ────────────────────────────────────────────────────────────

def _is_safe_redirect_url(target: str) -> bool:
    """
    Validate that a redirect target stays on the same host.
    Prevents open-redirect attacks via the `next` query parameter.
    """
    host_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return (
        test_url.scheme in ("http", "https")
        and host_url.netloc == test_url.netloc
    )


# ── Signup ─────────────────────────────────────────────────────────────────────

@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    """Register a new user account and send an email verification OTP."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))

    form = SignupForm()

    if form.validate_on_submit():
        hashed_pw = bcrypt.generate_password_hash(form.password.data).decode("utf-8")
        user = User(
            username=form.username.data.strip(),
            email=form.email.data.strip().lower(),
            password_hash=hashed_pw,
            first_name=form.first_name.data.strip(),
            last_name=form.last_name.data.strip() if form.last_name.data else None,
        )
        db.session.add(user)
        db.session.commit()
        logger.info("New user registered: %s", user.email)

        # Send verification OTP
        otp_code = create_otp(user.id, OTP.OTP_PURPOSE_EMAIL_VERIFY)
        email_sent = send_verification_otp_email(user.email, user.username, otp_code)

        if email_sent:
            flash(
                "Account created! Please check your email for a 6-digit verification code.",
                "success",
            )
        else:
            flash(
                "Account created, but we could not send the verification email. "
                "Use 'Resend Code' on the next page.",
                "warning",
            )

        session["verify_email"] = user.email
        return redirect(url_for("auth.verify_email"))

    return render_template("auth/signup.html", form=form)


# ── Email verification ─────────────────────────────────────────────────────────

@auth_bp.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    """Accept the 6-digit email verification OTP and activate the account."""
    email: str | None = session.get("verify_email")

    if not email:
        flash("No pending verification. Please sign up first.", "warning")
        return redirect(url_for("auth.signup"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("Account not found. Please sign up again.", "danger")
        session.pop("verify_email", None)
        return redirect(url_for("auth.signup"))

    if user.is_verified:
        session.pop("verify_email", None)
        flash("Your email is already verified. Please sign in.", "info")
        return redirect(url_for("auth.login"))

    form = VerifyEmailForm()

    if form.validate_on_submit():
        if verify_otp(user.id, form.otp_code.data, OTP.OTP_PURPOSE_EMAIL_VERIFY):
            user.is_verified = True
            db.session.commit()
            session.pop("verify_email", None)
            logger.info("Email verified for user: %s", user.email)
            flash("Email verified! You can now sign in.", "success")
            return redirect(url_for("auth.login"))
        else:
            flash("Invalid or expired code. Please try again or request a new one.", "danger")

    return render_template("auth/verify_email.html", form=form, email=email)


@auth_bp.route("/resend-otp", methods=["POST"])
def resend_otp():
    """Invalidate the existing verification OTP and send a fresh one."""
    email: str | None = session.get("verify_email")

    if not email:
        flash("Session expired. Please sign up again.", "warning")
        return redirect(url_for("auth.signup"))

    user = User.query.filter_by(email=email).first()
    if not user or user.is_verified:
        return redirect(url_for("auth.login"))

    otp_code = create_otp(user.id, OTP.OTP_PURPOSE_EMAIL_VERIFY)
    if send_verification_otp_email(user.email, user.username, otp_code):
        flash("A new verification code has been sent to your email.", "success")
    else:
        flash("Failed to send email. Please try again in a moment.", "danger")

    return redirect(url_for("auth.verify_email"))


# ── Login / Logout ─────────────────────────────────────────────────────────────

@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Authenticate an existing, verified user and start a session."""
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))

    form = LoginForm()

    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.strip().lower()).first()

        if user and bcrypt.check_password_hash(user.password_hash, form.password.data):
            if not user.is_verified:
                session["verify_email"] = user.email
                flash(
                    "Please verify your email before signing in. "
                    "Check your inbox for the code.",
                    "warning",
                )
                return redirect(url_for("auth.verify_email"))

            login_user(user, remember=form.remember_me.data)
            logger.info("User logged in: %s", user.email)

            next_page = request.args.get("next")
            if next_page and _is_safe_redirect_url(next_page):
                return redirect(next_page)
            return redirect(url_for("dashboard.dashboard"))

        flash("Incorrect email or password.", "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.route("/logout")
@login_required
def logout():
    """End the current user's session."""
    logger.info("User logged out: %s", current_user.email)
    logout_user()
    flash("You have been signed out.", "info")
    return redirect(url_for("auth.login"))


# ── Forgot / Reset password ────────────────────────────────────────────────────

@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """
    Accept an email address and send a password-reset OTP.

    A generic flash message is always shown to prevent email enumeration.
    """
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.dashboard"))

    form = ForgotPasswordForm()

    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        user = User.query.filter_by(email=email).first()

        # Only act if the user exists AND is verified; show the same message
        # regardless to prevent email enumeration.
        if user and user.is_verified:
            otp_code = create_otp(user.id, OTP.OTP_PURPOSE_FORGOT_PASSWORD)
            send_password_reset_otp_email(user.email, user.username, otp_code)
            session["reset_email"] = user.email
            logger.info("Password reset OTP sent for: %s", user.email)
            flash(
                "If that email is registered and verified, a reset code has been sent.",
                "info",
            )
            return redirect(url_for("auth.reset_password"))

        # Generic message — do NOT tell the user the email doesn't exist
        flash(
            "If that email is registered and verified, a reset code has been sent.",
            "info",
        )

    return render_template("auth/forgot_password.html", form=form)


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    """Accept OTP + new password to complete the password-reset flow."""
    email: str | None = session.get("reset_email")

    if not email:
        flash("No active reset session. Please request a new reset code.", "warning")
        return redirect(url_for("auth.forgot_password"))

    user = User.query.filter_by(email=email).first()
    if not user:
        flash("Invalid session. Please try again.", "danger")
        session.pop("reset_email", None)
        return redirect(url_for("auth.forgot_password"))

    form = ResetPasswordForm()

    if form.validate_on_submit():
        if verify_otp(user.id, form.otp_code.data, OTP.OTP_PURPOSE_FORGOT_PASSWORD):
            user.password_hash = bcrypt.generate_password_hash(
                form.password.data
            ).decode("utf-8")
            db.session.commit()
            session.pop("reset_email", None)
            logger.info("Password reset completed for: %s", user.email)
            flash("Password reset successfully! Please sign in with your new password.", "success")
            return redirect(url_for("auth.login"))
        else:
            flash("Invalid or expired reset code. Please try again.", "danger")

    return render_template("auth/reset_password.html", form=form, email=email)
