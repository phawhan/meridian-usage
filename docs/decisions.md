# Decisions log

Running log; each entry feeds the README. Format: ID, decision, why.

- D1 Capability switches gate the assistant (Part B), not the admin service.
- D2 Team leads write only their own group, even where they hold `capabilities:write`.
- D3 Money stored as integer nano-USD (exact for both sources); API returns `cost_usd` rounded to 6 dp.
- D4 Periods anchored to the data window end (2026-09-28), not the wall clock.
- D5 YAML `scopes` = policy, always authoritative; `capability_defaults` = baseline, fills missing rows only.
- D6 A fact's group comes from the platform identifier on the row, not the user's current directory group.
- D7 Starter doc says Gemini is "per project x day x SKU"; the data has up to 5 rows per key. Aggregate, don't dedupe.
- D8 Directory mirrored into read-only tables (joins, FK integrity); no API writes to it.
- D9 One DB per environment, with an env marker guard.
- D10 Missing `group_visibility` in YAML defaults to `own_group` (fail closed).
- D11 Schema grows per story in one idempotent `schema.sql` (CREATE ... IF NOT EXISTS). No migration tool: in dev, delete `var/<env>.db` after a schema change. Real deployment would add Alembic-style migrations.
- D12 Plain `sqlite3`, no ORM: about 10 tables, SQL stays readable for reviewers.
- D13 The frontend calls only relative `/api`; Vite proxies to FastAPI in dev, so there's no CORS configuration to get wrong.
- D14 Directory rows are never deleted. Users and groups missing from a newer snapshot get `deactivated_at`; usage history keeps its foreign keys, and inactive users cannot be callers.
- D15 One bookkeeping model for everything taken in: `sync_run` (one per pass) and `source_file` (one per file version, any kind). Skip rule compares against the latest version recorded at the same path (applied or rejected): the same bytes get one verdict, logged once, and a re-delivered older snapshot rolls the mirror back. `contracts/` is excluded because nothing reads it at runtime in Part A.
- D16 Audit columns (`created_at/by`, `updated_at/by`) and table/column comments on every table; `*_by` is a user_id or `system:<process>`. `updated_*` is set by the application, not by triggers, since it must supply `updated_by` anyway.
