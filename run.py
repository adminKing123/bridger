"""
run.py
------
Application entry point for development use.
For production, run with Gunicorn:
    gunicorn "run:app" --bind 0.0.0.0:8000
"""

import os
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=True,
    )
