"""
run.py
------
Application entry point for development use.
For production, run with Gunicorn:
    gunicorn "run:app" --bind 0.0.0.0:8000

CLI commands
------------
    flask create-superadmin   — Create the one-time superadmin account
"""

import os
import click
from app import create_app

app = create_app()


# ── CLI: create superadmin ────────────────────────────────────────────────────

@app.cli.command("create-superadmin")
@click.option("--username",   prompt="Username",   help="Superadmin username")
@click.option("--email",      prompt="Email",      help="Superadmin email")
@click.option("--first-name", prompt="First name", default="Admin", show_default=True,
              help="First name (display only)")
@click.option("--password",   prompt="Password",   hide_input=True,
              confirmation_prompt="Confirm password", help="Login password")
def create_superadmin(username: str, email: str, first_name: str, password: str) -> None:
    """Create the one-time superadmin account (CLI only)."""
    from datetime import datetime, timezone
    from app.models.user import User
    from app.models.admin import UserServicePermission, SERVICES
    from app import db, bcrypt

    # Guard: only one superadmin may ever exist
    existing = User.query.filter_by(is_superadmin=True).first()
    if existing:
        click.echo(click.style(
            f"[ERROR] A superadmin already exists: "
            f"{existing.username} ({existing.email})",
            fg="red",
        ))
        return

    if User.query.filter_by(username=username.strip()).first():
        click.echo(click.style(f"[ERROR] Username '{username}' is already taken.", fg="red"))
        return

    if User.query.filter_by(email=email.strip().lower()).first():
        click.echo(click.style(f"[ERROR] Email '{email}' is already registered.", fg="red"))
        return

    hashed = bcrypt.generate_password_hash(password).decode("utf-8")
    user = User(
        username=username.strip(),
        email=email.strip().lower(),
        password_hash=hashed,
        first_name=first_name.strip(),
        is_verified=True,
        is_superadmin=True,
    )
    db.session.add(user)
    db.session.flush()  # populate user.id

    now = datetime.now(timezone.utc)
    for svc in SERVICES:
        db.session.add(UserServicePermission(
            user_id=user.id,
            service=svc,
            is_enabled=True,
            granted_at=now,
            granted_by_id=None,
        ))

    db.session.commit()
    click.echo(click.style(
        f"[OK] Superadmin '{user.username}' ({user.email}) created successfully.",
        fg="green",
    ))


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True,
    )
