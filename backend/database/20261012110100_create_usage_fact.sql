-- S2 Usage ingestion: the unified model and ingestion issues (derived data).

-- The unified model: one row per platform x day x user x group x model x product,
-- in common units. Derived: rebuilt per (platform, usage_date) whenever raw rows for that
-- day change (partition overwrite), so re-running ingestion is always safe. Rows are
-- replaced, never updated, so only created_* audit columns apply.
CREATE TABLE usage_fact (
    id            INTEGER PRIMARY KEY,
    platform      TEXT NOT NULL CHECK (platform IN ('claude', 'gemini')),
    usage_date    TEXT NOT NULL,                      -- UTC day, YYYY-MM-DD
    iso_week      TEXT NOT NULL,                      -- e.g. 2026-W36, from usage_date
    month         TEXT NOT NULL,                      -- e.g. 2026-09, from usage_date
    user_id       TEXT NOT NULL REFERENCES users (user_id),
    group_id      TEXT NOT NULL REFERENCES groups (group_id),  -- from the platform identifier on the row (D6)
    model         TEXT NOT NULL,                      -- claude-opus-5-5 | gemini-2.5-pro | ...
    product       TEXT NOT NULL,                      -- Claude: chat | claude_code | cowork; Gemini: 'agent' label
    input_tokens  INTEGER NOT NULL,                   -- Claude: uncached + cache read + cache writes; Gemini: Input SKU
    output_tokens INTEGER NOT NULL,
    total_tokens  INTEGER NOT NULL,                   -- input_tokens + output_tokens
    requests      INTEGER,                            -- Claude only; Gemini billing has no request count
    cost_nanousd  INTEGER NOT NULL,                   -- USD x 1e9, exact for both sources (D3)
    metadata      TEXT NOT NULL,                      -- platform-specific detail as JSON (cache split, web search, SKUs, location...)
    raw_refs      TEXT NOT NULL,                      -- JSON: raw table -> ids this fact was built from
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by    TEXT NOT NULL,
    UNIQUE (platform, usage_date, user_id, group_id, model, product)
);

CREATE INDEX ix_usage_fact_group_date ON usage_fact (group_id, usage_date);
CREATE INDEX ix_usage_fact_user_date ON usage_fact (user_id, usage_date);

-- Raw records that could not become facts (severity 'error', excluded from totals) and
-- facts built with a caveat (severity 'warning'). Derived alongside usage_fact, per
-- (platform, usage_date), so an issue disappears once the data that caused it is fixed.
--   error:   unknown_user, unknown_group, token_total_mismatch, unknown_sku
--   warning: group_mismatch, cost_pending (tokens without cost: cost 0 until it arrives),
--            usage_missing (cost without tokens: tokens 0)
CREATE TABLE ingest_issue (
    id             INTEGER PRIMARY KEY,
    platform       TEXT NOT NULL CHECK (platform IN ('claude', 'gemini')),
    usage_date     TEXT NOT NULL,                     -- partition the issue belongs to
    severity       TEXT NOT NULL CHECK (severity IN ('error', 'warning')),
    code           TEXT NOT NULL CHECK (code IN (
                       'unknown_user', 'unknown_group', 'group_mismatch', 'cost_pending',
                       'usage_missing', 'token_total_mismatch', 'unknown_sku')),
    detail         TEXT NOT NULL,                     -- human-readable explanation
    raw_table      TEXT NOT NULL,                     -- raw_claude_usage | raw_claude_cost | raw_gemini_billing
    raw_ids        TEXT NOT NULL,                     -- JSON list of raw ids involved
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by     TEXT NOT NULL
);

CREATE INDEX ix_ingest_issue_partition ON ingest_issue (platform, usage_date);
