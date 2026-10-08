ALTER TABLE variants ADD COLUMN updated_at TEXT NOT NULL DEFAULT '';
UPDATE variants SET updated_at = created_at WHERE updated_at = '';

CREATE TABLE slots (
    id INTEGER PRIMARY KEY,
    variant_id INTEGER NOT NULL REFERENCES variants(id) ON DELETE CASCADE,
    scheduled_at TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    state TEXT NOT NULL DEFAULT 'pending'
        CHECK (state IN ('pending', 'processing', 'published', 'failed')),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    UNIQUE(variant_id, scheduled_at)
);
