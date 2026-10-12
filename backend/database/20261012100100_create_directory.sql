-- ---------------------------------------------------------------------------
-- S1 Directory sync: read-only mirror of the identity provider snapshot (D8).
-- Written only by the directory sync job; no API endpoint writes these tables.
-- ---------------------------------------------------------------------------

-- Teams as defined in the directory, with the identifiers each platform uses for them.
CREATE TABLE groups (
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
CREATE TABLE users (
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
CREATE TABLE user_groups (
    user_id    TEXT NOT NULL REFERENCES users (user_id),
    group_id   TEXT NOT NULL REFERENCES groups (group_id),
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by TEXT NOT NULL,
    PRIMARY KEY (user_id, group_id)
);
