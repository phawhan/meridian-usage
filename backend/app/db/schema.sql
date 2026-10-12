-- Meridian usage service schema (SQLite).
-- Applied on every start, so every statement must be idempotent (D11).
-- Tables are added by the story that owns them (see docs/PART_A_PLAN.md, section 3).
--
-- Conventions
--   * Timestamps are ISO 8601 UTC text, e.g. 2026-10-12T09:30:00.000Z.
--   * Audit columns on every table:
--       created_at / created_by  set once on insert
--       updated_at / updated_by  set by the application on every update
--     "by" is a directory user_id for human actions, or "system:<process>" for jobs
--     (system:startup, system:directory-sync, system:ingest).
--   * Append-only log tables carry only created_at / created_by.
--   * Nothing is hard-deleted from mirror tables; see deactivated_at (D14).
--   * Every mirrored or ingested row points at the source_file version that wrote it,
--     so any number traces back: fact -> raw row -> file -> sync run (D15).


-- ---------------------------------------------------------------------------
-- S0 Foundations
-- ---------------------------------------------------------------------------

-- Key/value facts about this database file. Holds the environment marker that
-- stops a server started as one environment from opening another's database (D9).
CREATE TABLE IF NOT EXISTS meta (
    key        TEXT PRIMARY KEY,                    -- e.g. 'environment'
    value      TEXT NOT NULL,                       -- e.g. 'prod'
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_by TEXT NOT NULL
);


-- ---------------------------------------------------------------------------
-- Sync bookkeeping: every file the service takes in, whatever its kind (D15).
-- ---------------------------------------------------------------------------

-- One row per sync pass (server start or CLI). Groups the files handled together,
-- e.g. users.json and groups.json, which must be applied as a pair.
CREATE TABLE IF NOT EXISTS sync_run (
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
CREATE TABLE IF NOT EXISTS source_file (
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

CREATE INDEX IF NOT EXISTS ix_source_file_path ON source_file (path, id);


-- ---------------------------------------------------------------------------
-- S1 Directory sync: read-only mirror of the identity provider snapshot (D8).
-- Written only by the directory sync job; no API endpoint writes these tables.
-- ---------------------------------------------------------------------------

-- Teams as defined in the directory, with the identifiers each platform uses for them.
CREATE TABLE IF NOT EXISTS groups (
    group_id             TEXT PRIMARY KEY,          -- e.g. 'clinical-operations'
    name                 TEXT NOT NULL,             -- display name, e.g. 'Clinical Operations'
    team_lead_user_id    TEXT NOT NULL,             -- validated in code; an FK would be circular
    claude_rbac_group_id TEXT NOT NULL UNIQUE,      -- joins Claude rows (rbac_group_id)
    gcp_project_id       TEXT NOT NULL UNIQUE,      -- joins Gemini billing rows (project.id)
    gcp_project_number   TEXT NOT NULL,             -- numeric form of the GCP project
    cost_centre          TEXT NOT NULL,             -- finance cost centre, e.g. 'CC-33DE'
    deactivated_at       TEXT,                      -- NULL = active; set when missing from a snapshot
    source_file_id       INTEGER NOT NULL REFERENCES source_file (id),  -- groups.json version that last wrote it
    created_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by           TEXT NOT NULL,
    updated_at           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_by           TEXT NOT NULL
);

-- Seat holders. Their role decides what they may see and change (scopes come from env YAML).
CREATE TABLE IF NOT EXISTS users (
    user_id        TEXT PRIMARY KEY,                -- joins Claude actor.user_id
    email          TEXT NOT NULL UNIQUE,            -- lowercased; joins Gemini 'owner' label
    name           TEXT NOT NULL,
    role           TEXT NOT NULL CHECK (role IN ('member', 'team_lead', 'platform_admin')),
    claude_seat    INTEGER NOT NULL CHECK (claude_seat IN (0, 1)),
    gcp_principal  TEXT,                            -- e.g. 'user:priya.nair@meridianls.example'
    deactivated_at TEXT,                            -- NULL = active; inactive users cannot be callers
    source_file_id INTEGER NOT NULL REFERENCES source_file (id),  -- users.json version that last wrote it
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by     TEXT NOT NULL,
    updated_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_by     TEXT NOT NULL
);

-- Current group membership. Only changed memberships are touched on sync, so created_at
-- means "member since this service first saw it". Removed memberships are deleted:
-- historical usage keeps its own group on the fact row (D6), not here.
CREATE TABLE IF NOT EXISTS user_groups (
    user_id    TEXT NOT NULL REFERENCES users (user_id),
    group_id   TEXT NOT NULL REFERENCES groups (group_id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by TEXT NOT NULL,
    PRIMARY KEY (user_id, group_id)
);
