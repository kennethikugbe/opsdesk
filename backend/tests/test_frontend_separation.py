"""Check that the static UI exists separately and uses relative API routes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_frontend_is_separate_static_source():
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    js = (ROOT / "frontend" / "static" / "app.js").read_text(encoding="utf-8")
    css = (ROOT / "frontend" / "static" / "style.css").read_text(encoding="utf-8")
    assert "Support, sorted." in html
    assert "/static/style.css" in html and "/static/app.js" in html
    assert "{{" not in html  # HTML can be served by a static web server.
    assert 'api("/api/summary")' in js  # Browser accesses its same origin.
    assert "localhost:" not in js and "127.0.0.1:" not in js
    assert ".ticket-list" in css
