"""OpsDesk: a deliberately local-only service desk learning application."""
from datetime import datetime, timezone
from pathlib import Path
import os
import sqlite3

from flask import Flask, jsonify, request, url_for

from . import db as database

CATEGORIES = {"access", "hardware", "software", "other"}
PRIORITIES = {"low", "normal", "high"}
STATUSES = {"open", "in_progress", "resolved"}
CREATE_FIELDS = {"title", "requester", "category", "priority", "description"}


def _now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _json_body():
    if not request.is_json:
        return None, (jsonify(error="Expected an application/json request body."), 415)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, (jsonify(error="Expected a JSON object."), 400)
    return payload, None


def _validate_ticket(payload):
    errors = {}
    result = {}
    unknown = set(payload) - CREATE_FIELDS
    if unknown:
        errors["fields"] = "Unexpected fields: " + ", ".join(sorted(unknown))

    for name, minimum, maximum in (
        ("title", 5, 120),
        ("requester", 2, 80),
        ("description", 10, 2000),
    ):
        value = payload.get(name)
        if not isinstance(value, str):
            errors[name] = "This field must be text."
        else:
            value = value.strip()
            if "\x00" in value:
                errors[name] = "This field cannot contain null characters."
            elif not minimum <= len(value) <= maximum:
                errors[name] = f"Use {minimum} to {maximum} characters."
            else:
                result[name] = value

    for name, allowed in (("category", CATEGORIES), ("priority", PRIORITIES)):
        value = payload.get(name)
        # Checking the type first prevents unhashable JSON values from becoming a 500 error.
        if not isinstance(value, str) or value not in allowed:
            errors[name] = "Choose a valid option."
        else:
            result[name] = value

    return result, errors


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True, static_folder=None)
    app.config.from_mapping(
        DATABASE=os.environ.get("OPSDESK_DATABASE", str(Path(app.instance_path) / "opsdesk.sqlite3")),
        MAX_CONTENT_LENGTH=32 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    app.teardown_appcontext(database.close_db)
    with app.app_context():
        database.init_db()

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self'; object-src 'none'; base-uri 'none'; "
            "frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.errorhandler(413)
    def body_too_large(_error):
        return jsonify(error="Request body is too large."), 413

    @app.errorhandler(404)
    def not_found(_error):
        if request.path.startswith("/api/"):
            return jsonify(error="Not found."), 404
        return "Not found.", 404

    @app.get("/api")
    def api_info():
        return jsonify(service="opsdesk-api", status="ok")

    @app.get("/health/live")
    def live():
        return jsonify(status="ok")

    @app.get("/health/ready")
    def ready():
        try:
            # This checks the application table, not merely a constant SELECT 1.
            database.get_db().execute("SELECT id FROM tickets LIMIT 1").fetchone()
        except sqlite3.Error:
            app.logger.warning("Readiness check failed: database unavailable")
            return jsonify(status="not_ready"), 503
        return jsonify(status="ready")

    @app.get("/api/summary")
    def summary():
        rows = database.get_db().execute(
            "SELECT status, COUNT(*) AS count FROM tickets GROUP BY status"
        ).fetchall()
        counts = {status: 0 for status in STATUSES}
        for row in rows:
            counts[row["status"]] = row["count"]
        return jsonify(total=sum(counts.values()), **counts)

    @app.get("/api/tickets")
    def list_tickets():
        status = request.args.get("status", "all")
        if status != "all" and status not in STATUSES:
            return jsonify(error="Invalid status filter."), 400
        db = database.get_db()
        if status == "all":
            rows = db.execute("SELECT * FROM tickets ORDER BY id DESC LIMIT 100").fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM tickets WHERE status = ? ORDER BY id DESC LIMIT 100", (status,)
            ).fetchall()
        return jsonify(tickets=[dict(row) for row in rows], limit=100)

    @app.get("/api/tickets/<int:ticket_id>")
    def get_ticket(ticket_id):
        row = database.get_db().execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        if row is None:
            return jsonify(error="Ticket not found."), 404
        return jsonify(ticket=dict(row))

    @app.post("/api/tickets")
    def create_ticket():
        payload, error = _json_body()
        if error:
            return error
        ticket, errors = _validate_ticket(payload)
        if errors:
            return jsonify(error="Validation failed.", details=errors), 400
        now = _now()
        db = database.get_db()
        with db:
            cursor = db.execute(
                """INSERT INTO tickets
                   (title, requester, category, priority, description, status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'open', ?, ?)""",
                (ticket["title"], ticket["requester"], ticket["category"], ticket["priority"],
                 ticket["description"], now, now),
            )
            ticket_id = cursor.lastrowid
        row = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        app.logger.info("Ticket created id=%s category=%s priority=%s", ticket_id, ticket["category"], ticket["priority"])
        response = jsonify(ticket=dict(row))
        response.status_code = 201
        response.headers["Location"] = url_for("get_ticket", ticket_id=ticket_id)
        return response

    @app.patch("/api/tickets/<int:ticket_id>")
    def update_ticket(ticket_id):
        payload, error = _json_body()
        if error:
            return error
        status = payload.get("status")
        if set(payload) != {"status"} or not isinstance(status, str) or status not in STATUSES:
            return jsonify(error="Provide only a valid status: open, in_progress, or resolved."), 400
        db = database.get_db()
        with db:
            cursor = db.execute(
                "UPDATE tickets SET status = ?, updated_at = ? WHERE id = ?", (status, _now(), ticket_id)
            )
        if cursor.rowcount == 0:
            return jsonify(error="Ticket not found."), 404
        row = db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        app.logger.info("Ticket status updated id=%s status=%s", ticket_id, status)
        return jsonify(ticket=dict(row))

    return app
