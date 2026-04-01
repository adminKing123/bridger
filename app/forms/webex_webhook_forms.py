"""
app/forms/webex_webhook_forms.py
---------------------------------
WTForms form for creating a new Webex webhook on a configuration.
"""

from flask_wtf import FlaskForm
from wtforms import SelectField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, URL

# ── Choices ────────────────────────────────────────────────────────────────────

RESOURCE_CHOICES = [
    ("messages",          "Messages"),
    ("rooms",             "Rooms (Spaces)"),
    ("memberships",       "Memberships"),
    ("meetings",          "Meetings"),
    ("attachmentActions", "Attachment Actions"),
    ("telephony_calls",   "Telephony Calls"),
    ("all",               "All Resources"),
]

EVENT_CHOICES = [
    ("created", "Created"),
    ("updated", "Updated"),
    ("deleted", "Deleted"),
    ("started", "Started"),
    ("ended",   "Ended"),
    ("all",     "All Events"),
]


# ── Form ───────────────────────────────────────────────────────────────────────

class WebhookCreateForm(FlaskForm):
    """Form for registering a new Webex webhook against a configuration."""

    name = StringField(
        "Webhook Name",
        validators=[DataRequired(), Length(max=200)],
        render_kw={"placeholder": "e.g. New Message Alerts"},
    )

    resource = SelectField(
        "Resource",
        choices=RESOURCE_CHOICES,
        validators=[DataRequired()],
    )

    event = SelectField(
        "Event",
        choices=EVENT_CHOICES,
        validators=[DataRequired()],
    )

    filter_str = StringField(
        "Filter",
        validators=[Optional(), Length(max=500)],
        render_kw={"placeholder": "e.g. roomId=Y2lzY29zcGFyazov…  (optional)"},
    )

    target_url = StringField(
        "Target URL",
        validators=[DataRequired(), URL(require_tld=False), Length(max=500)],
    )

    submit = SubmitField("Register Webhook")
