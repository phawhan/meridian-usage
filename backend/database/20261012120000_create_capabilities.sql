-- ---------------------------------------------------------------------------
-- S3 Capability controls: per-group on/off switches for assistant capabilities.
-- The only tables a person changes through the API. Who may change them is decided by
-- the environment policy (environments/<env>.yaml scopes), never by these tables (D5).
-- ---------------------------------------------------------------------------

-- Live switch state, one row per group x capability. Rows missing for a group are seeded
-- from the environment's capability_defaults (the baseline) on startup; existing rows are
-- never overwritten by the baseline, so a switch a person flipped survives restarts (D5).
CREATE TABLE capability_state (
    group_id   TEXT NOT NULL REFERENCES groups (group_id),
    capability TEXT NOT NULL CHECK (capability IN ('usage-connector', 'web-search', 'code-execution')),
    enabled    INTEGER NOT NULL CHECK (enabled IN (0, 1)),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by TEXT NOT NULL,                     -- system:startup when seeded from the baseline
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_by TEXT NOT NULL,                     -- user_id of whoever last changed it
    PRIMARY KEY (group_id, capability)
);

-- Append-only history of every switch change, including the initial seed. Answers "who
-- changed what, when, and under which policy": policy_file_id is the environment config
-- version (source_file row) in force at the time.
CREATE TABLE capability_audit (
    id             INTEGER PRIMARY KEY,
    group_id       TEXT NOT NULL REFERENCES groups (group_id),
    capability     TEXT NOT NULL,
    action         TEXT NOT NULL CHECK (action IN ('seed', 'set', 'reset')),  -- reset = back to baseline
    old_enabled    INTEGER CHECK (old_enabled IN (0, 1)),  -- NULL for a seed
    new_enabled    INTEGER NOT NULL CHECK (new_enabled IN (0, 1)),
    policy_file_id INTEGER NOT NULL REFERENCES source_file (id),
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by     TEXT NOT NULL                  -- user_id, or system:startup for a seed
);

CREATE INDEX ix_capability_audit_group ON capability_audit (group_id, capability, id);
