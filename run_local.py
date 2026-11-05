"""Local development convenience: serve the split UI and API on loopback.

This is only a way to test the app before building the separate deployment.
The planned independent frontend will be served by a reverse proxy, not this file.
"""
from pathlib import Path
import logging
import sys

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from flask import send_from_directory  # noqa: E402
from opsdesk import create_app  # noqa: E402


def create_local_app(test_config=None):
    app = create_app(test_config)
    frontend = ROOT / "frontend"

    @app.get("/")
    def frontend_home():
        return send_from_directory(frontend, "index.html")

    @app.get("/static/<path:filename>")
    def frontend_static(filename):
        return send_from_directory(frontend / "static", filename)

    return app


if __name__ == "__main__":
    app = create_local_app()
    app.logger.setLevel(logging.INFO)
    app.run(host="127.0.0.1", port=5000, debug=False)
