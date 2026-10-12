-- ---------------------------------------------------------------------------
-- S0 Foundations
-- ---------------------------------------------------------------------------

-- Key/value facts about this database file. Holds the environment marker that
-- stops a server started as one environment from opening another's database (D9).
CREATE TABLE meta (
    key        TEXT PRIMARY KEY,                    -- e.g. 'environment'
    value      TEXT NOT NULL,                       -- e.g. 'prod'
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_by TEXT NOT NULL
);
