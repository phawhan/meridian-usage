-- ---------------------------------------------------------------------------
-- S2 Usage ingestion: raw (bronze) -> usage_fact (silver). Aggregates are computed at
-- query time. Written only by the ingestion job (system:ingest).
-- ---------------------------------------------------------------------------

-- Raw tables hold every source record verbatim (payload) plus the typed natural-key
-- columns used to upsert it. When the same key arrives again, the version with the newer
-- source timestamp wins (source_refreshed_at), regardless of which file is processed
-- first. A file with two records sharing a key is malformed for its grain and is rejected
-- as a whole in source_file, like an invalid directory snapshot (D17).

-- Claude Enterprise Analytics API, user_usage_report: one record per
-- user x day x product x model, token counts and requests.
CREATE TABLE raw_claude_usage (
    id                  INTEGER PRIMARY KEY,
    actor_user_id       TEXT NOT NULL,                -- actor.user_id
    bucket_start        TEXT NOT NULL,                -- starting_at, RFC 3339 UTC as delivered
    product             TEXT NOT NULL,                -- chat | claude_code | cowork
    model               TEXT NOT NULL,                -- e.g. claude-opus-5-5
    usage_date          TEXT NOT NULL,                -- UTC day of the bucket, YYYY-MM-DD; partition key
    payload             TEXT NOT NULL,                -- the record exactly as delivered (JSON)
    source_refreshed_at TEXT NOT NULL,                -- file-level data_refreshed_at
    source_file_id      INTEGER NOT NULL REFERENCES source_file (id),  -- file that last wrote it
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by          TEXT NOT NULL,
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_by          TEXT NOT NULL,
    UNIQUE (actor_user_id, bucket_start, product, model)
);

-- Claude Enterprise Analytics API, user_cost_report: same grain plus cost_type
-- (tokens | web_search). Amounts are decimal strings in cents, kept as delivered in payload.
CREATE TABLE raw_claude_cost (
    id                  INTEGER PRIMARY KEY,
    actor_user_id       TEXT NOT NULL,
    bucket_start        TEXT NOT NULL,
    product             TEXT NOT NULL,
    model               TEXT NOT NULL,
    cost_type           TEXT NOT NULL,                -- tokens | web_search
    usage_date          TEXT NOT NULL,                -- UTC day of the bucket, YYYY-MM-DD; partition key
    payload             TEXT NOT NULL,
    source_refreshed_at TEXT NOT NULL,                -- file-level data_refreshed_at
    source_file_id      INTEGER NOT NULL REFERENCES source_file (id),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by          TEXT NOT NULL,
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_by          TEXT NOT NULL,
    UNIQUE (actor_user_id, bucket_start, product, model, cost_type)
);

-- Google Cloud billing export (BigQuery standard usage cost), Vertex AI Gemini SKUs.
-- The export aggregates by project x SKU x usage window x labels, so labels are part of
-- the key: the starter doc's "project x day x SKU" has up to 5 rows per key (D7).
CREATE TABLE raw_gemini_billing (
    id                  INTEGER PRIMARY KEY,
    project_id          TEXT NOT NULL,                -- project.id
    sku_id              TEXT NOT NULL,                -- sku.id
    usage_start_time    TEXT NOT NULL,                -- as delivered, 'YYYY-MM-DD HH:MM:SS UTC'
    labels_key          TEXT NOT NULL,                -- resource labels as sorted canonical JSON
    cost_type           TEXT NOT NULL,                -- regular | adjustment | ...
    usage_date          TEXT NOT NULL,                -- UTC day of the bucket, YYYY-MM-DD; partition key
    payload             TEXT NOT NULL,
    source_refreshed_at TEXT NOT NULL,                -- row-level export_time
    source_file_id      INTEGER NOT NULL REFERENCES source_file (id),
    created_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    created_by          TEXT NOT NULL,
    updated_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_by          TEXT NOT NULL,
    UNIQUE (project_id, sku_id, usage_start_time, labels_key, cost_type)
);

CREATE INDEX ix_raw_claude_usage_date ON raw_claude_usage (usage_date);
CREATE INDEX ix_raw_claude_cost_date ON raw_claude_cost (usage_date);
CREATE INDEX ix_raw_gemini_billing_date ON raw_gemini_billing (usage_date);
