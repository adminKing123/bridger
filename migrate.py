"""
migrate.py
----------
Database migration script for Bridger.

Usage:
    python migrate.py

Behaviour:
  - Fresh install : creates all tables from scratch via SQLAlchemy.
  - Existing DB   : applies any missing structural changes (ALTER TABLE, new tables)
                    without touching existing rows.

Run this script once when deploying to a new environment, and again whenever
the schema has changed.
"""

import sys

# ── Bootstrap Flask app ───────────────────────────────────────────────────────

from run import app          # noqa: E402  (imports create_app result)
from app import db           # noqa: E402


def _col_exists(conn, table: str, column: str) -> bool:
    """Return True if *column* exists in *table* (SQLite-safe check)."""
    result = conn.execute(
        db.text("SELECT COUNT(*) FROM pragma_table_info(:tbl) WHERE name = :col"),
        {"tbl": table, "col": column},
    )
    return result.scalar() > 0


def _table_exists(conn, table: str) -> bool:
    """Return True if *table* exists in the database."""
    result = conn.execute(
        db.text(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=:tbl"
        ),
        {"tbl": table},
    )
    return result.scalar() > 0


def run_migrations() -> None:
    with app.app_context():
        engine = db.engine

        # ── Step 1 : create all tables that do not yet exist ──────────────────
        # create_all() is a no-op for tables that already exist.
        db.create_all()
        print("[OK] db.create_all() — all declared tables now exist.")

        # ── Step 2 : incremental column additions (upgrade path) ──────────────
        # Guards against running on a DB created before a column was added.
        with engine.connect() as conn:

            # ── users : is_superadmin ─────────────────────────────────────────
            if not _col_exists(conn, "users", "is_superadmin"):
                conn.execute(
                    db.text(
                        "ALTER TABLE users "
                        "ADD COLUMN is_superadmin BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
                conn.commit()
                print("[OK] users.is_superadmin column added.")
            else:
                print("[--] users.is_superadmin already present.")

            # ── users : is_blocked ────────────────────────────────────────────
            if not _col_exists(conn, "users", "is_blocked"):
                conn.execute(
                    db.text(
                        "ALTER TABLE users "
                        "ADD COLUMN is_blocked BOOLEAN NOT NULL DEFAULT 0"
                    )
                )
                conn.commit()
                print("[OK] users.is_blocked column added.")
            else:
                print("[--] users.is_blocked already present.")

            # ── user_service_permissions table ────────────────────────────────
            # create_all() already handles this, but we log its presence.
            if _table_exists(conn, "user_service_permissions"):
                print("[--] user_service_permissions table already present.")
            else:
                # create_all() above should have created it; warn if not.
                print("[WARN] user_service_permissions was NOT created — check model imports.")

        print("\nMigration complete.")


if __name__ == "__main__":
    try:
        run_migrations()
    except Exception as exc:
        print(f"\n[ERROR] Migration failed: {exc}", file=sys.stderr)
        sys.exit(1)
