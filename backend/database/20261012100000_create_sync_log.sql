-- ---------------------------------------------------------------------------
-- Sync bookkeeping: every file the service takes in, whatever its kind (D15).
-- ---------------------------------------------------------------------------

-- One row per sync pass (server start or CLI). Groups the files handled together,
-- e.g. users.json and groups.json, which must be applied as a pair.
CREATE TABLE sync_run (
    id          INTEGER PRIMARY KEY,
    trigger     TEXT NOT NULL CHECK (trigger IN ('startup', 'cli')),
    status      TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed')),
    finished_at TEXT,                                -- NULL while running
    error       TEXT,                                -- why the run failed, if it did
    created_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by  TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_by  TEXT NOT NULL
);

-- One row per file version taken in. A file is skipped (no new row) when the latest
-- version recorded at the same path has the same sha256, so the same bytes always get
-- the same verdict once. Comparing against the latest, not "ever seen", lets a
-- re-delivered older snapshot roll the mirror back.
CREATE TABLE source_file (
    id               INTEGER PRIMARY KEY,
    sync_run_id      INTEGER NOT NULL REFERENCES sync_run (id),
    source_kind      TEXT NOT NULL CHECK (source_kind IN (
                         'directory_users', 'directory_groups',
                         'claude_usage', 'claude_cost', 'gemini_billing',
                         'environment_config')),
    path             TEXT NOT NULL,                  -- relative to repo root, e.g. data/directory/users.json
    sha256           TEXT NOT NULL,                  -- content hash; identifies the version
    exported_at      TEXT,                           -- the source's own timestamp (exported_at, data_refreshed_at, max export_time)
    status           TEXT NOT NULL CHECK (status IN ('applied', 'rejected')),
    error            TEXT,                           -- validation errors when rejected
    rows_read        INTEGER,                        -- records found in the file
    rows_inserted    INTEGER,                        -- new rows written
    rows_updated     INTEGER,                        -- existing rows changed
    rows_deactivated INTEGER,                        -- directory only: rows missing from this snapshot
    rows_quarantined INTEGER,                        -- usage exports only: rows that could not be attributed
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by       TEXT NOT NULL,
    updated_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_by       TEXT NOT NULL
);

CREATE INDEX ix_source_file_path ON source_file (path, id);
