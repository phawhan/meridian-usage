# Database migrations (SQLite)

Each file is one schema change, applied once, in filename order, by `app/db/migrations.py` on every server start and `meridian sync`.

## Naming
`YYYYMMDDHHMMSS_<snake_case_name>.sql`, e.g. `20261012110000_create_raw_usage.sql`. The timestamp is the version.

## Rules
- **Never edit a file that has been applied.** The runner stores each file's sha256 in `schema_migration` and refuses to start if an applied file changes. Add a new file instead.
- Each file runs in one transaction with its `schema_migration` row: it applies completely or not at all.
- Use plain `CREATE TABLE` (no `IF NOT EXISTS`). A migration runs once; if the database isn't in the state it expects, it should fail loudly.
- No down-migrations. In dev, delete `var/<env>.db` to start again.

## Table conventions
- Every table has a comment above it saying what it holds and who writes it; every column whose meaning isn't obvious from its name has an inline comment, including which platform field it joins to.
- Timestamps are ISO 8601 UTC text, e.g. `2026-10-12T09:30:00.000Z`.
- Audit columns on every table:
  - `created_at` / `created_by`: set once on insert
  - `updated_at` / `updated_by`: set by the application on every update (not by triggers, because the application must supply `updated_by` anyway)
  - "by" is a directory `user_id` for human actions, or `system:<process>` for jobs (`system:startup`, `system:directory-sync`, `system:ingest`)
- Append-only logs and derived tables that are replaced rather than updated carry only `created_*`.
- Nothing is hard-deleted from mirror tables; see `deactivated_at` (D14).
- Every mirrored or ingested row points at the `source_file` version that wrote it, so any number traces back: fact -> raw row -> file -> sync run (D15).

## Files
| Version | Story | Tables |
|---|---|---|
| 20261012090000 | S0 | `meta` |
| 20261012100000 | S1 | `sync_run`, `source_file` |
| 20261012100100 | S1 | `groups`, `users`, `user_groups` |
| 20261012110000 | S2 | `raw_claude_usage`, `raw_claude_cost`, `raw_gemini_billing` |
| 20261012110100 | S2 | `usage_fact`, `ingest_issue` |
| 20261012120000 | S3 | `capability_state`, `capability_audit` |
| 20261012120100 | S3 | `access_denial` |
