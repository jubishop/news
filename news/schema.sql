CREATE TABLE reporters (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    prompt TEXT NOT NULL,
    schedule_json TEXT NOT NULL CHECK(json_valid(schedule_json)),
    schedule_effective_date TEXT NOT NULL,
    materialized_through TEXT NOT NULL,
    paused INTEGER NOT NULL DEFAULT 0 CHECK(paused IN (0,1)),
    config_version INTEGER NOT NULL DEFAULT 1,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    deleted_at REAL,
    completed_at REAL
);
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    reporter_id TEXT NOT NULL REFERENCES reporters(id) ON DELETE RESTRICT,
    expected_date TEXT NOT NULL,
    kind TEXT NOT NULL CHECK(kind IN ('scheduled','catch_up')),
    state TEXT NOT NULL CHECK(state IN ('pending','running','retry_wait','published',
        'nothing_to_publish','skipped_paused','failed','superseded','cancelled')),
    created_at REAL NOT NULL,
    finished_at REAL,
    retry_not_before REAL,
    retry_generation INTEGER NOT NULL DEFAULT 1,
    superseded_by_run_id TEXT REFERENCES runs(id) ON DELETE RESTRICT,
    closed_reason TEXT,
    UNIQUE(reporter_id, expected_date)
);
CREATE TABLE run_attempts (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id) ON DELETE RESTRICT,
    attempt_number INTEGER NOT NULL,
    retry_generation INTEGER NOT NULL,
    worker_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    acknowledgment_only INTEGER NOT NULL CHECK(acknowledgment_only IN (0,1)),
    config_snapshot_json TEXT NOT NULL CHECK(json_valid(config_snapshot_json)),
    started_at REAL NOT NULL,
    finished_at REAL,
    claim_token_hash TEXT NOT NULL,
    claim_expires_at REAL NOT NULL,
    outcome TEXT CHECK(outcome IN ('published','nothing_to_publish','skipped_paused','failed')),
    reason TEXT,
    error_code TEXT,
    error_message TEXT,
    retryable INTEGER CHECK(retryable IN (0,1)),
    submission_id TEXT,
    payload_hash TEXT,
    receipt_json TEXT CHECK(receipt_json IS NULL OR json_valid(receipt_json)),
    UNIQUE(run_id, attempt_number),
    UNIQUE(worker_id, request_id),
    UNIQUE(worker_id, submission_id)
);
CREATE UNIQUE INDEX one_open_attempt ON run_attempts(run_id) WHERE outcome IS NULL;
CREATE UNIQUE INDEX one_success ON run_attempts(run_id)
    WHERE outcome IN ('published','nothing_to_publish');
CREATE TABLE articles (
    id TEXT PRIMARY KEY,
    reporter_id TEXT NOT NULL REFERENCES reporters(id) ON DELETE RESTRICT,
    attempt_id TEXT NOT NULL REFERENCES run_attempts(id) ON DELETE RESTRICT,
    reporter_name TEXT NOT NULL,
    title TEXT NOT NULL,
    summary TEXT NOT NULL,
    body_markdown TEXT NOT NULL,
    sources_json TEXT NOT NULL CHECK(json_valid(sources_json)),
    article_date TEXT NOT NULL,
    coverage_start TEXT NOT NULL,
    coverage_end TEXT NOT NULL CHECK(coverage_end >= coverage_start),
    published_at REAL NOT NULL,
    deleted_at REAL
);
CREATE INDEX article_feed ON articles(published_at DESC,id DESC) WHERE deleted_at IS NULL;
CREATE INDEX article_reporter ON articles(reporter_id,published_at DESC,id DESC);
CREATE INDEX article_trash ON articles(deleted_at) WHERE deleted_at IS NOT NULL;
CREATE INDEX run_state ON runs(state,expected_date);
CREATE TABLE worker_checkins (
    id TEXT PRIMARY KEY,
    worker_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    received_at REAL NOT NULL,
    reporting_date TEXT NOT NULL,
    UNIQUE(worker_id,request_id)
);
CREATE INDEX worker_contact ON worker_checkins(worker_id,received_at DESC);
CREATE TABLE incidents (
    id TEXT PRIMARY KEY,
    incident_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    reporter_id TEXT REFERENCES reporters(id) ON DELETE RESTRICT,
    run_id TEXT REFERENCES runs(id) ON DELETE RESTRICT,
    worker_id TEXT,
    message TEXT NOT NULL,
    first_seen_at REAL NOT NULL,
    last_seen_at REAL NOT NULL,
    resolved_at REAL,
    notification_sent_at REAL,
    notification_attempts INTEGER NOT NULL DEFAULT 0,
    notification_retry_at REAL,
    notification_error TEXT,
    notification_started_at REAL,
    notification_payload_json TEXT,
    notification_receipt_id TEXT
);
CREATE UNIQUE INDEX one_active_incident ON incidents(incident_key) WHERE resolved_at IS NULL;
CREATE INDEX incident_delivery ON incidents(notification_retry_at)
    WHERE notification_sent_at IS NULL AND resolved_at IS NULL;
PRAGMA user_version = 1;
