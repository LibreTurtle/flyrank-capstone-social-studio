ALTER TABLE slots ADD COLUMN updated_at TEXT NOT NULL DEFAULT '';
UPDATE slots SET updated_at = created_at WHERE updated_at = '';

CREATE TABLE publish_attempts (
    id INTEGER PRIMARY KEY,
    slot_id INTEGER NOT NULL REFERENCES slots(id) ON DELETE CASCADE,
    attempt_number INTEGER NOT NULL,
    adapter TEXT NOT NULL,
    result TEXT NOT NULL CHECK (result IN ('in_progress', 'succeeded', 'failed', 'unknown')),
    remote_reference TEXT,
    preview TEXT,
    error TEXT,
    started_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    finished_at TEXT,
    UNIQUE(slot_id, attempt_number)
);

CREATE UNIQUE INDEX one_successful_publish_per_slot
    ON publish_attempts(slot_id)
    WHERE result = 'succeeded';

CREATE TABLE mock_posts (
    id INTEGER PRIMARY KEY,
    slot_id INTEGER NOT NULL REFERENCES slots(id) ON DELETE CASCADE,
    adapter TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    preview TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(slot_id)
);
