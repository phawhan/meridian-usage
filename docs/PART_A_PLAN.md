# Part A plan: usage and admin service

Assignment ID: Fullstack-ClaudeGemini-UsageConnector-v1

Stack: FastAPI + SQLite backend (Python 3.13, uv), React + Vite + TypeScript frontend.
Template: each story has a user story, acceptance criteria (AC), and sub-tasks with their tests. Tests ship with each story; S6 adds only the cross-cutting gates.
Ran on: macOS (Darwin 25.6, arm64), uv 0.7.14, Python 3.13.5, Node 22.14, npm 10.9.

---

## 1. Repo layout (standard FastAPI + Vite structure)

```
meridian-usage/
├── README.md
├── Makefile                      setup | ingest | run | test | lint | dev-web
├── .github/workflows/ci.yml
├── data/                         copied from starter-kit; drop new/delta files here
│   ├── directory/                users.json, groups.json
│   ├── claude/                   Analytics API exports
│   └── gemini/                   GCP billing exports (.jsonl)
├── environments/                 dev.yaml, staging.yaml, prod.yaml (unchanged from starter kit)
├── contracts/                    tools.schema.json
├── docs/
│   ├── decisions.md              running decisions log (feeds README)
│   └── ai-usage-log.md           what AI did, what you overruled (feeds README; written by you)
├── backend/
│   ├── pyproject.toml
│   ├── database/             timestamped SQL migrations + README (conventions)
│   ├── uv.lock
│   ├── app/
│   │   ├── main.py               FastAPI app + lifespan (load config, sync directory, ingest, seed)
│   │   ├── cli.py                `meridian sync` (one pass: directory now, usage exports in S2)
│   │   ├── core/                 config.py (settings), env_config.py (YAML -> Policy), periods.py, money.py
│   │   ├── db/                   session.py (connection, env marker), migrations.py (runner)
│   │   ├── models/               pydantic: sources/ (one module per source), domain.py, api.py, denial.py
│   │   ├── repositories/         sync_log.py, directory.py, raw.py, facts.py, capabilities.py
│   │   ├── services/
│   │   │   ├── sync.py           one pass, recorded as a sync_run
│   │   │   ├── directory_sync.py
│   │   │   ├── ingestion/        discover.py, claude.py, gemini.py, attribute.py, pipeline.py
│   │   │   ├── authz.py
│   │   │   ├── capabilities.py
│   │   │   └── usage.py
│   │   └── api/
│   │       ├── deps.py           caller from X-User-Id, policy, db
│   │       └── routes/           meta.py, usage.py, capabilities.py, directory.py
│   └── tests/
│       ├── conftest.py
│       ├── fixtures/             tiny hand-built source files
│       ├── unit/                 mapping, periods, env_config, authz
│       └── integration/          pipeline, reconciliation, api
└── frontend/
    ├── package.json  vite.config.ts  tsconfig.json  index.html
    └── src/
        ├── main.tsx  App.tsx
        ├── api/                  client.ts (injects X-User-Id), types.ts
        ├── hooks/                usePersona.ts, queries.ts
        ├── components/           PersonaSwitcher, PeriodPicker, UsageTable, CapabilityGrid, DenialBanner
        └── pages/                UsagePage.tsx, CapabilitiesPage.tsx
```

Part B will add `connector/` (MCP server), `provisioning/` and `dist/` alongside these. Part A doesn't touch them.

### `backend/pyproject.toml`
```toml
[project]
name = "meridian-usage"
version = "0.1.0"
description = "Usage and admin service for Meridian's Claude and Gemini assistant"
requires-python = ">=3.13"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "pyyaml>=6.0.2",
]

[project.scripts]
meridian = "app.cli:main"

[dependency-groups]
dev = ["pytest>=8.3", "httpx2>=2.13", "ruff>=0.8", "mypy>=1.13", "types-pyyaml"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app"]

[tool.ruff]
line-length = 100
target-version = "py313"

[tool.ruff.lint]
select = ["E", "F", "I", "B", "UP", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.mypy]
python_version = "3.13"
strict = true
```
The store uses stdlib `sqlite3` with no ORM: about 10 tables, readable SQL, one fewer dependency. The CLI uses stdlib `argparse`.

---

## 2. Startup sequence (same code, any env)
```
APP_ENV=prod DB_PATH=./var/prod.db  uv run uvicorn app.main:app
  1. load environments/prod.yaml -> validate against EnvConfig -> normalise to Policy   (invalid: refuse to start)
  2. open prod.db, apply schema; check env marker == "prod"                          (mismatch: refuse to start)
  3. sync directory (if snapshot hash changed)
  4. ingest new files in data/claude, data/gemini
  5. seed capability_state rows that don't exist yet, from Policy.defaults
```
YAML `scopes` = policy, reloaded in full every start. YAML `capability_defaults` = baseline, fills missing rows only. The DB holds the live switch state. Roles are read-only from the directory; this service doesn't manage roles.

---

## 3. Tables
| Table | Written by | Purpose |
|---|---|---|
| `meta` | S0 | env marker, schema version |
| `sync_run`, `source_file` | S1 (used by S2) | every sync pass and every file version taken in: directory, usage exports, env config (D15) |
| `groups`, `users`, `user_groups` | S1 only | read-only mirror of the IdP snapshot; soft-deactivated, never deleted (D14) |
| `ingest_issue` | S2 | quarantined rows and warnings, per `source_file`
| `raw_claude_usage`, `raw_claude_cost`, `raw_gemini_billing` | S2 | verbatim source rows (JSON), unique on natural key |
| `usage_fact` | S2 | unified model |
| `capability_state`, `capability_audit` | S3 (API) | live switches + change history |

`usage_fact`: `platform, usage_date, iso_week, month, user_id FK, group_id FK, model, product, input_tokens, output_tokens, total_tokens, requests NULL, cost_nanousd, metadata JSON, raw_refs JSON`, unique on `(platform, usage_date, user_id, model, product)`.

---

## 4. Stories

### S0 Foundations (done 2026-10-12)
**As a** developer **I want** a runnable skeleton **so that** every story lands in a known place.
AC: `make setup && make test` green; `make run` serves `/api/v1/healthz`; `make dev-web` proxies to the backend.

| ID | Sub-task | Tests |
|---|---|---|
| S0.1 | `git init`, layout, `.gitignore`, copy starter-kit data/environments/contracts | n/a |
| S0.2 | `backend/pyproject.toml` (above), `uv sync`, empty app with `/api/v1/healthz` | healthz test |
| S0.3 | `core/config.py` (pydantic-settings): `APP_ENV`, `DB_PATH`, `DATA_DIR`, `ENV_DIR` | bad `APP_ENV` fails |
| S0.4 | `db/session.py` + `db/migrations.py` running `backend/database/*.sql` (D11), env marker guard | applied once; edited migration refused; failed migration rolls back; wrong env refused before migrating |
| S0.5 | Frontend: `npm create vite` (react-ts), TanStack Query, `/api` proxy | `npm run build` passes |
| S0.6 | Makefile, `docs/decisions.md`, `docs/ai-usage-log.md` | n/a |

### S1 Directory sync (done 2026-10-12)
**As a** platform owner **I want** the identity snapshot mirrored locally **so that** usage resolves to real people and groups.
AC: a changed snapshot is applied in one transaction (upsert present, deactivate missing, membership diff); unchanged = no new `source_file` row; invalid snapshot recorded as `rejected` with its errors and the old mirror kept; every write fills the audit columns.

| ID | Sub-task | Tests |
|---|---|---|
| S1.1 | Source models for users.json / groups.json | malformed rejected |
| S1.2 | Validation: unique lowercased emails, group refs exist, lead exists and is in their group | one failing fixture per rule |
| S1.3 | `sync_run` + `source_file` bookkeeping; skip when the latest version recorded at the same path (applied or rejected) has the same sha256; apply users + groups as a pair | same hash skipped; older snapshot re-delivered is re-applied; leaver deactivated, not deleted |
| S1.4 | Lookups: user_id, email, rbac_group_id, gcp_project_id | lookup tests |

### S2 Usage ingestion pipeline (done 2026-10-12)
**As a** platform owner **I want** both exports merged into one model **so that** I can compare usage and cost across platforms.
Stages: **discover -> extract (raw) -> transform -> attribute -> load (facts) -> report**
AC: re-run with no new files changes nothing; a delta file updates only its days; sum(facts) == sum(raw) for tokens and cost per platform; every raw row lands in a fact or in `ingest_issue`; every raw row carries its `source_file_id`; runs at startup and via `meridian ingest`.

| ID | Sub-task | Tests |
|---|---|---|
| S2.1 | Discover: scan folders, sha256, skip per the S1.3 rule, record in `source_file` | seen skipped, new picked |
| S2.2 | Extract: source models; upsert raw on natural key (Claude: user, day, product, model[, cost_type]; Gemini: project, day, sku, owner, agent); later delivery wins | re-delivery replaces, no duplicate |
| S2.3 | Transform Claude: join usage + cost; cents string -> Decimal -> nano-USD; input = uncached + cache_read + cache_5m + cache_1h; check `total_tokens`; web_search cost folded in, breakdown in metadata | conversions; web_search join; total mismatch raises; usage without cost -> `cost_pending` issue |
| S2.4 | Transform Gemini: labels -> dict; SKU -> direction; pivot Input/Output; USD -> nano-USD; `requests = NULL`; product = agent | pivot; SKU parse; BigQuery timestamp parse |
| S2.5 | Attribute: user via user_id / owner email; group via rbac_group_id / project.id; mismatch -> warning; unknown -> quarantine | quarantine + warning fixtures |
| S2.6 | Load: partition overwrite of (platform, date) in one transaction | delta touches only its days |
| S2.7 | Report: `rows_*` counts on `source_file`, run status on `sync_run` | counts match |
| S2.8 | Add ingestion to `services/sync.run_sync` (already called by lifespan + `meridian sync`) | startup ingests once |

### S3 Policy and capability controls (done 2026-10-12)
**As a** platform admin **I want** per-group capability switches with enforced rules **so that** only the right people can see and change them.
AC: invalid env YAML stops startup; missing/unknown `X-User-Id` -> 401; missing scope or invisible group -> 403 `Denial`; team leads write only their own group (D2); baseline fills missing rows only; every change audited.

| ID | Sub-task | Tests |
|---|---|---|
| S3.1 | `core/env_config.py`: `EnvConfig` contract (accepts `enabled` / `disabled` / `enabled_for`), normalise to `Policy` with an explicit group x capability default; missing `group_visibility` = `own_group` | all 3 envs load; prod Finance connector default false; typo key fails |
| S3.2 | `services/authz.py`: `authorize(caller, action, group, policy) -> Allow \| Denial`, pure | see S6.2 |
| S3.3 | `api/deps.py`: header -> `Caller` | 401 cases |
| S3.4 | `services/capabilities.py`: seed, get, set (transaction + audit) | fresh prod DB matches baseline; write survives a new app instance; audit row |
| S3.5 | Drift flag (live != baseline) + admin-only reset | drift shown; reset audited |

### S4 Usage and admin API (`/api/v1`)
**As a** platform owner **I want** usage and cost sliced by platform, group, week, month, model and product **so that** I can see who uses what and at what cost.
AC: every route goes through `authz`; typed responses in OpenAPI; `Denial` shape matches `contracts/tools.schema.json`.

| ID | Sub-task | Tests |
|---|---|---|
| S4.1 | `core/periods.py`: `last_7_days`, `last_30_days`, `YYYY-Www`, `YYYY-MM` -> [start, end); anchor = max data date + 1 (2026-09-28); `coverage` when partial | boundaries; partial month |
| S4.2 | `services/usage.py`: summary, breakdown (`by` whitelist), top users | golden values on fixtures |
| S4.3 | Routes: `GET /me`, `/usage/summary`, `/usage/breakdown`, `/usage/top-users`, `/capabilities`, `PUT /capabilities/{group}/{capability}`, `/capabilities/audit`, `/ingest/runs`, `/healthz` | TestClient happy + denied |
| S4.4 | `GET /directory/users` for the persona switcher (simulated-identity affordance, flagged in README) | returns 22 |

### S5 Admin console (React, mocked identity)
**As a** platform owner **I want** a plain console **so that** I can read usage and flip switches without curl.
AC: switching persona changes exactly what the API allows; denials shown as messages, never blank screens; toggles disabled without write scope (the server still enforces).

| ID | Sub-task |
|---|---|
| S5.1 | `api/client.ts`: injects `X-User-Id`, typed responses, maps 403 to `Denial` |
| S5.2 | PersonaSwitcher (22 users grouped by team, remembered in localStorage) |
| S5.3 | UsagePage: period picker, totals, breakdown tables (platform / group / week / model / product), top users |
| S5.4 | CapabilitiesPage: grid of toggles, updated_by/at, drift badge, audit list |
| S5.5 | DenialBanner |
Manual check script: Chloe (admin), Priya (lead), Daniel (member) in each env.

### S6 Quality gates
| ID | Sub-task |
|---|---|
| S6.1 | Reconciliation test on the full starter data, golden totals computed independently from raw files |
| S6.2 | Authz matrix: role x env x action x own/other group -> expected result, parametrised |
| S6.3 | `.github/workflows/ci.yml`: backend `ruff check`, `mypy`, `pytest`; frontend `tsc --noEmit`, `npm run build` (Part B adds provisioning validation) |

### S7 Part A write-up
**As a** reviewer **I want** the Part A reasoning documented **so that** I can judge the decisions, not just the code.
| ID | Sub-task |
|---|---|
| S7.1 | README: setup, architecture diagram (Part A half), mapping decisions, permission model |
| S7.2 | README: technical decisions, standards followed and skipped, environment versions |
| S7.3 | Move `docs/decisions.md` and `docs/ai-usage-log.md` highlights into README (in your words) |

---

## 5. Submission tracker (from ASSIGNMENT.md)

| Required item | Covered by | Part |
|---|---|---|
| GitHub repo, Python and TypeScript | backend (Py), frontend (TS); connector in TS later | A + B |
| README: quick setup | S7.1 | A |
| README: architecture diagram | S7.1 (extended in B) | A + B |
| README: mapping decisions (exports -> model, rows -> people/groups) | S2 + S7.1, from `decisions.md` | A |
| README: permission model + where enforced | S3 + S7.1 | A + B |
| README: platform built for + exactly what you ran it on | header of this plan + B | B |
| README: key technical decisions | `decisions.md` -> S7.2 | A + B |
| README: standards followed and skipped | S7.2 | A + B |
| README: how you used AI tools + what you overruled | `ai-usage-log.md` -> S7.3 | A + B |
| README: what you'd do with more time | end of B | B |
| README: *In the real enterprise version* | end of B | B |
| Recording / transcript (allowed read, denied cross-group, denied write) | B | B |
| Note to team leads | B | B |
| CI green, one-command provisioning, nothing hand-edited | S6.3 now; provisioning in B | A + B |

**Write the AI usage log now, not at the end.** Some of it has already happened in this planning session: you overruled keeping the directory in memory (it's now tables), you rejected role-management scope, and you split tests into each story. Those are real entries.

---

## 6. Decisions log (seed for `docs/decisions.md`)
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

## 7. Edge cases to acknowledge in README (not all handled)
- Claude usage file arrives without its cost file -> `cost_pending` issue, cost excluded until it arrives.
- Gemini billing restatements / credits (none in the data; `credits` and `cost_at_list` kept in metadata).
- A user in more than one group (none in the data; schema supports it via `user_groups`, authz uses all of a lead's groups).
- Deleted Claude actors (none in the data; the `deleted` flag is kept in metadata).
- Timezones: both sources are UTC daily buckets; no local-time reporting.
