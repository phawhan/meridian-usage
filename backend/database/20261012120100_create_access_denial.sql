-- ---------------------------------------------------------------------------
-- S3 Access denials: every refused request, for security review and for showing that the
-- permission model holds (Part B's denied cross-group read and denied write land here too).
-- ---------------------------------------------------------------------------

-- Append-only. One row per refused request: unidentified callers (401) and policy
-- denials (403). Allowed requests are not logged here.
CREATE TABLE access_denial (
    id             INTEGER PRIMARY KEY,
    channel        TEXT NOT NULL CHECK (channel IN ('api', 'connector')),  -- admin API or MCP connector (Part B)
    caller         TEXT,                          -- user_id as presented; NULL when no identity was sent
    action         TEXT NOT NULL,                 -- e.g. read_usage, write_capability, identify
    target_group   TEXT,                          -- group asked about, as presented (may not exist)
    required_scope TEXT,                          -- scope the caller lacked, when that was the reason
    reason         TEXT NOT NULL,                 -- the same reason text returned to the caller
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by     TEXT NOT NULL                  -- system:api or system:connector
);

CREATE INDEX ix_access_denial_caller ON access_denial (caller, id);
