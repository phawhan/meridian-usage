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
- D11 Versioned migrations: one timestamped file per change in `backend/database/` (`YYYYMMDDHHMMSS_name.sql`), applied once in order, each in its own transaction, tracked with a checksum in `schema_migration`; an applied file that changes stops startup. The environment marker is checked before migrating. No down-migrations: in dev, delete `var/<env>.db`.
- D12 Plain `sqlite3`, no ORM: about 10 tables, SQL stays readable for reviewers.
- D13 The frontend calls only relative `/api`; Vite proxies to FastAPI in dev, so there's no CORS configuration to get wrong.
- D14 Directory rows are never deleted. Users and groups missing from a newer snapshot get `deactivated_at`; usage history keeps its foreign keys, and inactive users cannot be callers.
- D15 One bookkeeping model for everything taken in: `sync_run` (one per pass) and `source_file` (one per file version, any kind). Skip rule compares against the latest version recorded at the same path (applied or rejected): the same bytes get one verdict, logged once, and a re-delivered older snapshot rolls the mirror back. `contracts/` is excluded because nothing reads it at runtime in Part A.
- D16 Audit columns (`created_at/by`, `updated_at/by`) and table/column comments on every table; `*_by` is a user_id or `system:<process>`. `updated_*` is set by the application, not by triggers, since it must supply `updated_by` anyway.
- D17 Raw upserts keep the version with the newer source timestamp (Claude file `data_refreshed_at`, Gemini row `export_time`), not the later-arriving file. A file with two records sharing a natural key is rejected whole in `source_file`. Facts and issues are derived per (platform, usage_date) and rebuilt when that day's raw rows change.
- D18 Gemini cost = `cost` + `credits` (credits are negative). GCP documents `cost` as before credits; the starter README says "after credits". With no credits in the data the two readings agree; we follow GCP and keep both figures in fact metadata.
- D19 Derived data depends on two inputs, so a directory change re-derives every usage partition: a quarantined row from an unknown owner becomes a fact as soon as the directory knows them.
- D20 Claude usage without cost (`cost_pending`) is kept with cost 0 and a warning, not excluded: excluding would undercount tokens; the warning lets the admin page flag understated cost. Cost without usage (`usage_missing`) is kept with 0 tokens, same reasoning.
- D21 Gemini JSON is parsed with `parse_float=Decimal`: Pydantic turns a JSON number into a float on its way to Decimal and loses digits beyond ~16 significant figures (verified).
- D22 Claude input tokens = uncached + cache read + cache creation (5m + 1h); the split is kept in metadata. A row whose parts don't add up to the source's `total_tokens` is quarantined, not trusted.
- D23 Every refused request is logged in `access_denial` (401s and 403s, channel api or connector), committed even though the request fails. `authorize()` stays pure; `enforce()` wraps it and logs, so the decision logic is tested without a database.
- D24 A non-admin asking about a group that doesn't exist gets the same denial as for another team's group, so callers can't probe which groups exist.
- D25 Setting a switch to its current value changes nothing and writes no audit row (safe to repeat). A reset returns a switch to the environment baseline and is audited as `reset`.
- D26 Each audit row records `policy_file_id`, the environment config version in force, so "who changed what under which rules" is answerable from the database.
- D27 D2 holds regardless of YAML: even if `capabilities:write` were given `group_visibility: all`, team leads can only change their own group. Platform admins change any group.
- D28 The environment config is validated strictly (unknown keys, roles or capabilities, a missing scope or capability, `environment:` not matching `APP_ENV`, `enabled_for` naming a group the directory doesn't have): any of these stops startup.
