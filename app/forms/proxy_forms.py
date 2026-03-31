"""
app/forms/proxy_forms.py
-------------------------
WTForms classes for HTTP proxy management.

Forms
-----
ProxyCreateForm — create a new proxy (slug is user-editable, auto-suggested)
ProxyEditForm   — update an existing proxy (slug and type are locked)
"""

import re

from flask_wtf import FlaskForm
from wtforms import StringField, RadioField, BooleanField, SubmitField, SelectMultipleField
from wtforms.validators import DataRequired, Length, ValidationError
from wtforms.widgets import ListWidget, CheckboxInput


class MultiCheckboxField(SelectMultipleField):
    """A SelectMultipleField rendered as a list of checkboxes."""
    widget = ListWidget(prefix_label=False)
    option_widget = CheckboxInput()


HTTP_METHODS = [(m, m) for m in ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"]]

# Slug rules: 3–80 chars, lowercase alphanumeric + hyphens,
# must start and end with alphanumeric (not a hyphen).
_SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")


class ProxyCreateForm(FlaskForm):
    """
    Form to create a new HTTP/HTTPS proxy configuration.

    The slug is pre-populated with a generated value and can be edited.
    Uniqueness and reserved-name validation are enforced server-side.
    """

    name = StringField(
        "Display Name",
        validators=[DataRequired(), Length(2, 100)],
        description="A recognisable label for this proxy.",
    )
    slug = StringField(
        "Proxy Name",
        validators=[DataRequired(), Length(3, 80)],
        description="Unique identifier used in your proxy URL. Lowercase letters, numbers, and hyphens only.",
    )
    target_url = StringField(
        "Target URL",
        validators=[DataRequired(), Length(7, 500)],
        description="The upstream URL this proxy will forward all requests to.",
    )
    proxy_type = RadioField(
        "Access Mode",
        choices=[
            ("endpoint",  "Endpoint  —  /proxy/{name}/"),
            ("subdomain", "Subdomain  —  {name}.localhost/"),
        ],
        default="endpoint",
    )
    allowed_methods = MultiCheckboxField(
        "Allowed Methods",
        choices=HTTP_METHODS,
        default=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    )
    cors_bypass = BooleanField(
        "Bypass CORS  (adds Access-Control-Allow-Origin: *)",
        default=True,
    )
    skip_ngrok_warning = BooleanField(
        "Skip Ngrok browser warning header",
        default=True,
    )
    submit = SubmitField("Create Proxy")

    def validate_allowed_methods(self, field: MultiCheckboxField) -> None:
        if not field.data:
            raise ValidationError("At least one HTTP method must be selected.")

    # ── Custom validators ──────────────────────────────────────────────────────

    def validate_slug(self, field: StringField) -> None:
        """Enforce slug format, reserved names, and uniqueness."""
        from app.models.proxy import ProxyConfig

        slug = field.data.strip().lower()
        field.data = slug  # normalise in place

        if len(slug) < 3:
            raise ValidationError("Proxy name must be at least 3 characters.")

        if not _SLUG_RE.match(slug):
            raise ValidationError(
                "Proxy name must be 3–80 characters, lowercase letters / numbers / hyphens only, "
                "and cannot start or end with a hyphen."
            )

        if slug in ProxyConfig.RESERVED_SLUGS:
            raise ValidationError(
                f"'{slug}' is a reserved name. Please choose something different."
            )

        if ProxyConfig.query.filter_by(slug=slug).first():
            raise ValidationError(
                "That proxy name is already taken. Please choose another."
            )

    def validate_target_url(self, field: StringField) -> None:
        """Ensure the target URL uses http or https."""
        url = field.data.strip() if field.data else ""
        if not url.startswith(("http://", "https://")):
            raise ValidationError("Target URL must begin with http:// or https://")
        field.data = url.rstrip("/")  # strip trailing slash for clean concatenation


class ProxyEditForm(FlaskForm):
    """
    Form to edit an existing proxy configuration.

    The slug and proxy_type are intentionally locked after creation —
    changing either would invalidate existing integrations that depend on
    the generated URL.
    """

    name = StringField(
        "Display Name",
        validators=[DataRequired(), Length(2, 100)],
    )
    target_url = StringField(
        "Target URL",
        validators=[DataRequired(), Length(7, 500)],
    )
    allowed_methods = MultiCheckboxField(
        "Allowed Methods",
        choices=HTTP_METHODS,
    )
    cors_bypass        = BooleanField("Bypass CORS  (adds Access-Control-Allow-Origin: *)")
    skip_ngrok_warning = BooleanField("Skip Ngrok browser warning header")
    submit             = SubmitField("Save Changes")

    def validate_allowed_methods(self, field: MultiCheckboxField) -> None:
        if not field.data:
            raise ValidationError("At least one HTTP method must be selected.")

    def validate_target_url(self, field: StringField) -> None:
        url = field.data.strip() if field.data else ""
        if not url.startswith(("http://", "https://")):
            raise ValidationError("Target URL must begin with http:// or https://")
        field.data = url.rstrip("/")
