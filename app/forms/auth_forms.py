"""
app/forms/auth_forms.py
------------------------
WTForms form classes for all authentication and profile flows.
Every form inherits from FlaskForm which automatically provides CSRF protection.

Forms:
    SignupForm          — new account registration
    LoginForm           — email + password sign-in
    VerifyEmailForm     — enter 6-digit email OTP
    ForgotPasswordForm  — enter email to request reset OTP
    ResetPasswordForm   — enter OTP + new password
    UpdateProfileForm   — update username from profile page
"""

from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    PasswordField,
    BooleanField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    EqualTo,
    Length,
    Optional,
    Regexp,
    ValidationError,
)

from app.models.user import User


class SignupForm(FlaskForm):
    """Form for new user registration."""

    username = StringField(
        "Username",
        validators=[
            DataRequired(message="Username is required."),
            Length(min=3, max=80, message="Username must be 3–80 characters."),
            Regexp(
                r"^[A-Za-z0-9_]+$",
                message="Username may only contain letters, numbers and underscores.",
            ),
        ],
        render_kw={"placeholder": "e.g. john_doe", "autocomplete": "username"},
    )
    email = StringField(
        "Email Address",
        validators=[
            DataRequired(message="Email is required."),
            Email(message="Please enter a valid email address."),
        ],
        render_kw={"placeholder": "you@example.com", "autocomplete": "email"},
    )
    first_name = StringField(
        "First Name",
        validators=[
            DataRequired(message="First name is required."),
            Length(max=80, message="First name must be under 80 characters."),
        ],
        render_kw={"placeholder": "John", "autocomplete": "given-name"},
    )
    last_name = StringField(
        "Last Name",
        validators=[
            Optional(),
            Length(max=80, message="Last name must be under 80 characters."),
        ],
        render_kw={"placeholder": "Doe", "autocomplete": "family-name"},
    )
    password = PasswordField(
        "Password",
        validators=[
            DataRequired(message="Password is required."),
            Length(min=8, message="Password must be at least 8 characters."),
        ],
        render_kw={"placeholder": "Minimum 8 characters", "autocomplete": "new-password"},
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(message="Please confirm your password."),
            EqualTo("password", message="Passwords must match."),
        ],
        render_kw={"placeholder": "Re-enter your password", "autocomplete": "new-password"},
    )
    submit = SubmitField("Create Account")

    def validate_username(self, username: StringField) -> None:
        """Ensure the username is not already taken."""
        user = User.query.filter_by(username=username.data).first()
        if user:
            raise ValidationError("That username is already taken.")

    def validate_email(self, email: StringField) -> None:
        """Ensure the email address is not already registered."""
        user = User.query.filter_by(email=email.data.lower()).first()
        if user:
            raise ValidationError("That email is already registered.")


class LoginForm(FlaskForm):
    """Form for signing in with email and password."""

    email = StringField(
        "Email Address",
        validators=[
            DataRequired(message="Email is required."),
            Email(message="Please enter a valid email address."),
        ],
        render_kw={"placeholder": "you@example.com", "autocomplete": "email"},
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(message="Password is required.")],
        render_kw={"placeholder": "Your password", "autocomplete": "current-password"},
    )
    remember_me = BooleanField("Remember me")
    submit = SubmitField("Sign In")


class VerifyEmailForm(FlaskForm):
    """Form for entering the 6-digit email verification OTP."""

    otp_code = StringField(
        "Verification Code",
        validators=[
            DataRequired(message="Please enter the verification code."),
            Length(min=6, max=6, message="The code must be exactly 6 digits."),
            Regexp(r"^\d{6}$", message="The code must contain exactly 6 digits."),
        ],
        render_kw={
            "placeholder": "000000",
            "maxlength": "6",
            "inputmode": "numeric",
            "autocomplete": "one-time-code",
        },
    )
    submit = SubmitField("Verify Email")


class ForgotPasswordForm(FlaskForm):
    """Form for requesting a password reset via email OTP."""

    email = StringField(
        "Email Address",
        validators=[
            DataRequired(message="Email is required."),
            Email(message="Please enter a valid email address."),
        ],
        render_kw={"placeholder": "you@example.com", "autocomplete": "email"},
    )
    submit = SubmitField("Send Reset Code")


class ResetPasswordForm(FlaskForm):
    """Form for submitting the password-reset OTP and choosing a new password."""

    otp_code = StringField(
        "Reset Code",
        validators=[
            DataRequired(message="Please enter the reset code."),
            Length(min=6, max=6, message="The code must be exactly 6 digits."),
            Regexp(r"^\d{6}$", message="The code must contain exactly 6 digits."),
        ],
        render_kw={
            "placeholder": "000000",
            "maxlength": "6",
            "inputmode": "numeric",
            "autocomplete": "one-time-code",
        },
    )
    password = PasswordField(
        "New Password",
        validators=[
            DataRequired(message="New password is required."),
            Length(min=8, message="Password must be at least 8 characters."),
        ],
        render_kw={"placeholder": "Minimum 8 characters", "autocomplete": "new-password"},
    )
    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[
            DataRequired(message="Please confirm your new password."),
            EqualTo("password", message="Passwords must match."),
        ],
        render_kw={"placeholder": "Re-enter new password", "autocomplete": "new-password"},
    )
    submit = SubmitField("Reset Password")


class UpdateProfileForm(FlaskForm):
    """Form for updating the currently logged-in user's username."""

    username = StringField(
        "Username",
        validators=[
            DataRequired(message="Username is required."),
            Length(min=3, max=80, message="Username must be 3–80 characters."),
            Regexp(
                r"^[A-Za-z0-9_]+$",
                message="Username may only contain letters, numbers and underscores.",
            ),
        ],
        render_kw={"autocomplete": "username"},
    )
    first_name = StringField(
        "First Name",
        validators=[
            DataRequired(message="First name is required."),
            Length(max=80, message="First name must be under 80 characters."),
        ],
        render_kw={"autocomplete": "given-name"},
    )
    last_name = StringField(
        "Last Name",
        validators=[
            Optional(),
            Length(max=80, message="Last name must be under 80 characters."),
        ],
        render_kw={"autocomplete": "family-name"},
    )
    submit = SubmitField("Save Changes")

    def __init__(self, original_username: str, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._original_username = original_username

    def validate_username(self, username: StringField) -> None:
        """Allow the existing username but reject any other duplicate."""
        if username.data != self._original_username:
            user = User.query.filter_by(username=username.data).first()
            if user:
                raise ValidationError("That username is already taken.")
