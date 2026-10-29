CREATE TABLE newsletters (
    newsletter_date TEXT PRIMARY KEY,
    article_ids_json TEXT NOT NULL CHECK(json_valid(article_ids_json)),
    payload_json TEXT CHECK(payload_json IS NULL OR json_valid(payload_json)),
    created_at REAL NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    started_at REAL,
    retry_at REAL,
    error TEXT,
    sent_at REAL,
    receipt_id TEXT
);
CREATE INDEX newsletter_delivery ON newsletters(retry_at)
    WHERE payload_json IS NOT NULL AND sent_at IS NULL;
CREATE TABLE newsletter_state (
    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
    covered_through REAL NOT NULL
);
INSERT INTO newsletter_state VALUES(1,coalesce((SELECT max(published_at) FROM articles),0));
PRAGMA user_version = 4;
