"""
app/routes/webex.py
--------------------
Webex integration blueprint — placeholder for Webex configuration,
webhook management, and event logging.

Routes
------
GET  /webex/  — Webex service landing page
"""

from flask import render_template
from flask_login import login_required
from flask import Blueprint

webex_bp = Blueprint("webex", __name__, url_prefix="/webex")


@webex_bp.route("/")
@login_required
def index():
    return render_template("webex/index.html")
