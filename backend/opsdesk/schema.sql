CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL CHECK(length(title) BETWEEN 5 AND 120),
    requester TEXT NOT NULL CHECK(length(requester) BETWEEN 2 AND 80),
    category TEXT NOT NULL CHECK(category IN ('access', 'hardware', 'software', 'other')),
    priority TEXT NOT NULL CHECK(priority IN ('low', 'normal', 'high')),
    description TEXT NOT NULL CHECK(length(description) BETWEEN 10 AND 2000),
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'in_progress', 'resolved')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickets_status_id ON tickets (status, id DESC);
