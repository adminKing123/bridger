"""
app/forms/webex_forms.py
-------------------------
WTForms classes for Webex integration management.

Forms
-----
WebexCreateForm  — create a new Webex configuration (token required)
WebexEditForm    — edit an existing configuration (token optional; blank = keep current)
"""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import DataRequired, Length, Optional


class WebexCreateForm(FlaskForm):
    """Form to create a new Webex configuration. Access token is required."""

    name = StringField(
        "Configuration Name",
        validators=[DataRequired(), Length(2, 120)],
        description="A recognisable label for this Webex configuration.",
    )
    access_token = PasswordField(
        "Access Token",
        validators=[DataRequired(), Length(10, 500)],
        description="Your Webex personal or bot access token.",
    )
    submit = SubmitField("Save Configuration")


class WebexEditForm(FlaskForm):
    """
    Form to edit an existing Webex configuration.

    Leaving access_token blank keeps the currently stored token.
    If a new token is provided it must be at least 10 characters.
    """

    name = StringField(
        "Configuration Name",
        validators=[DataRequired(), Length(2, 120)],
    )
    access_token = PasswordField(
        "Access Token",
        validators=[Optional(), Length(0, 500)],
        description="Leave blank to keep the current token.",
    )
    submit = SubmitField("Save Changes")
