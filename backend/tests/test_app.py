import sqlite3

import pytest

from opsdesk import create_app
from opsdesk.db import get_db


@pytest.fixture()
def app(tmp_path):
    return create_app({"TESTING": True, "DATABASE": str(tmp_path / "tickets.sqlite3")})


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def ticket():
    return {
        "title": "Cannot access the dashboard",
        "requester": "A Fictional User",
        "category": "access",
        "priority": "normal",
        "description": "The dashboard shows an access denied message.",
    }


def test_api_info_and_security_headers(client):
    response = client.get("/api")
    assert response.status_code == 200
    assert response.get_json() == {"service": "opsdesk-api", "status": "ok"}
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_liveness_and_readiness(client):
    assert client.get("/health/live").get_json() == {"status": "ok"}
    assert client.get("/health/ready").get_json() == {"status": "ready"}


def test_readiness_fails_when_table_is_unavailable(app, client):
    with app.app_context():
        db = get_db()
        db.execute("DROP TABLE tickets")
        db.commit()
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.get_json() == {"status": "not_ready"}
    assert client.get("/health/live").status_code == 200


def test_create_retrieve_and_summary(client, ticket):
    ticket["title"] = "  Cannot access the dashboard  "
    response = client.post("/api/tickets", json=ticket)
    assert response.status_code == 201
    created = response.get_json()["ticket"]
    assert created["title"] == "Cannot access the dashboard"
    assert created["status"] == "open"
    assert created["created_at"].endswith("Z")
    assert response.headers["Location"] == f"/api/tickets/{created['id']}"
    assert client.get(response.headers["Location"]).get_json()["ticket"] == created
    assert client.get("/api/summary").get_json() == {
        "total": 1, "open": 1, "in_progress": 0, "resolved": 0,
    }


def test_change_status_and_filter(client, ticket):
    first = client.post("/api/tickets", json=ticket).get_json()["ticket"]
    second = client.post("/api/tickets", json=ticket).get_json()["ticket"]
    response = client.patch(f"/api/tickets/{first['id']}", json={"status": "in_progress"})
    assert response.status_code == 200
    assert response.get_json()["ticket"]["status"] == "in_progress"
    open_tickets = client.get("/api/tickets?status=open").get_json()["tickets"]
    assert [t["id"] for t in open_tickets] == [second["id"]]
    assert client.get("/api/summary").get_json()["in_progress"] == 1
    assert client.get("/api/tickets?status=bogus").status_code == 400
    assert client.get("/api/tickets?status=open%27%20OR%201%3D1--").status_code == 400


def test_list_is_newest_first_and_limited(client, ticket):
    for _ in range(101):
        assert client.post("/api/tickets", json=ticket).status_code == 201
    result = client.get("/api/tickets").get_json()
    assert result["limit"] == 100
    assert len(result["tickets"]) == 100
    assert result["tickets"][0]["id"] == 101
    assert client.get("/api/summary").get_json()["total"] == 101


@pytest.mark.parametrize("patch", [
    {"title": "tiny"},
    {"requester": "x"},
    {"description": "too short"},
    {"description": "x" * 2001},
    {"title": "hello\u0000world"},
    {"priority": "urgent"},
    {"priority": []},
    {"category": {"unexpected": "object"}},
    {"unknown": "field"},
])
def test_invalid_ticket_rejected(client, ticket, patch):
    ticket.update(patch)
    response = client.post("/api/tickets", json=ticket)
    assert response.status_code == 400
    assert response.get_json()["error"] == "Validation failed."
    assert client.get("/api/summary").get_json()["total"] == 0


def test_bad_bodies_and_size_limit(client):
    assert client.post("/api/tickets", data="no").status_code == 415
    assert client.post("/api/tickets", data="{", content_type="application/json").status_code == 400
    assert client.post("/api/tickets", json=[]).status_code == 400
    assert client.post("/api/tickets", data='{"x":"' + "x" * 33000 + '"}',
                       content_type="application/json").status_code == 413


def test_missing_and_invalid_status_updates(client, ticket):
    assert client.get("/api/tickets/999").status_code == 404
    assert client.patch("/api/tickets/999", json={"status": "open"}).status_code == 404
    created = client.post("/api/tickets", json=ticket).get_json()["ticket"]
    url = f"/api/tickets/{created['id']}"
    for payload in ({}, {"status": []}, {"status": "done"}, {"status": "open", "role": "admin"}):
        assert client.patch(url, json=payload).status_code == 400
    assert client.get(url).get_json()["ticket"]["status"] == "open"


def test_sql_like_and_html_text_is_stored_as_text(client, ticket):
    ticket["title"] = "<script>alert('x')</script>"
    ticket["description"] = "Robert'); DROP TABLE tickets;--"
    response = client.post("/api/tickets", json=ticket)
    assert response.status_code == 201
    result = client.get("/api/tickets").get_json()["tickets"][0]
    assert result["title"] == ticket["title"]
    assert result["description"] == ticket["description"]
    assert client.get("/health/ready").status_code == 200


def test_database_persists_across_app_restarts(tmp_path, ticket):
    path = str(tmp_path / "persistent.sqlite3")
    first_app = create_app({"TESTING": True, "DATABASE": path})
    assert first_app.test_client().post("/api/tickets", json=ticket).status_code == 201
    second_app = create_app({"TESTING": True, "DATABASE": path})
    assert second_app.test_client().get("/api/summary").get_json()["total"] == 1
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 1
