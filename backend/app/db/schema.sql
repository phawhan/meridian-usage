-- Applied on every start; every statement must be idempotent.
-- Tables are added by the story that owns them (see docs/PART_A_PLAN.md, section 3).

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
