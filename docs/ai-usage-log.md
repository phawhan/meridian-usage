# AI usage log

My working notes on how I used AI while building this, kept as I went. The README section is written from them.

**Tool:** Claude Code (VS Code extension), used as a pair programmer. I set the scope, the structure and the standards, reviewed every schema before code was written against it, and decided what to keep. The AI drafted code and tests, profiled data, and proposed designs.

**How I kept it honest:** I reviewed every schema before any code depended on it. I made the AI prove claims instead of trusting summaries: reconcile totals against the source files, re-run checks that printed nothing, and inject deliberate bugs to show the tests catch them. I recorded below every place where I overruled it or it got something wrong.

## Planning

| AI proposal or action | My call |
|---|---|
| Profiled the starter data (row counts, join keys, orphans, token totals) before any design | **Accepted** as the starting point. It surfaced the Gemini "per project x day x SKU" mismatch in the starter README (D7) |
| Recommended the Gemini CLI extension as the primary platform after reading the job description | **Accepted.** Gemini is the role's platform; Claude Desktop config is a rendered bonus |
| Proposed a plain HTML admin page | **Changed.** I chose a React admin console with a mocked identity switcher, over a FastAPI backend |
| Proposed keeping the directory in memory | **Overruled.** I wanted it in tables: joins for names, and foreign keys from usage to users (D8) |
| Listed "tests" as a final story | **Accepted its pushback** after discussion: tests ship inside each story; only cross-cutting gates are separate |
| Started expanding environment-config validation into a richer contract | **Trimmed.** Role management isn't part of the problem; the loader only reads, normalises and fails fast |
| Explained the YAML `scopes` vs `capability_defaults` vs database state | Settled the split myself after questioning it: policy reloaded every start, defaults only fill missing switches, one database per environment (D5, D9) |
| I asked for the plan as stories with sub-tasks, and named the stories | The AI restructured the plan to my template |
| Claimed in chat that it had rewritten the plan file when it hadn't | **Noted.** It corrected itself the next turn. From then on I checked files, not summaries |

## Build

| AI proposal or action | My call |
|---|---|
| S0: swapped `httpx` for `httpx2` after a Starlette 1.7 deprecation warning, after checking Starlette's installed source | **Accepted** |
| S0: its first tests leaked SQLite connections (Python 3.13 ResourceWarning) | **Accepted the fix** and the stricter pytest setting that turns leaks into failures |
| S0: an environment-guard smoke test printed nothing (macOS has no `timeout`) | **Required a re-run** rather than assuming success; the guard was confirmed working |
| S0: `create-vite` now ships oxlint, TypeScript 6, Vite 8 | **Kept** the template defaults rather than swapping tooling |
| S1: first schema draft had no audit columns or comments | **Overruled.** I required audit columns (`created_*`, `updated_*`) and comments on every table and column (D16) |
| S1: proposed a directory-only `directory_sync` log table | **Overruled.** I asked for one table tracking every file of any kind; it became `source_file` + `sync_run` (D15). Accepted its refinement of the skip rule |
| S1: changed the plan's "replace-all" directory sync to upsert + soft-deactivate, because usage facts would reference users | **Accepted** (D14) |
| S1: ruff suggested `for k in row` instead of `row.keys()` on a `sqlite3.Row` | **Rejected the auto-fix** with the AI: iterating a Row yields values, not keys |
| S1: all tests passed first time | **Asked for proof:** 3 deliberate bugs injected, all caught |
| S2: kept growing one idempotent `schema.sql` | **Overruled.** I asked for timestamped migration files in `backend/database/` (D11). Wiring it in exposed that the environment check ran *after* the schema was applied, which with migrations would touch prod's database before refusing a dev start; reordered and tested |
| S2: proposed quarantining duplicate keys within a file | **Accepted its revision** on review: duplicates can't be referenced, so the whole file is rejected (D17) |
| S2: checked how Pydantic parses JSON numbers into Decimal before writing models: via float, losing digits | **Accepted** parsing with `parse_float=Decimal` (D21) |
| S2: added a `usage_date` column to the not-yet-applied raw-table migration | **Accepted** (editing is safe only before a migration is applied) |
| S2: `cost_pending` (Claude usage without its cost): keep with cost 0 and a warning, or exclude | **Chose** keep-with-warning (D20) |
| S2: two test expectations were wrong while the code was right (Python 3.12 `sum()`, Decimal trailing zeros) | **Fixed the tests, not the code** |
| S2: its precision test still passed with a float-parsing bug injected, so it tested nothing | **Caught by the deliberate-bug check;** rewritten with a 17-digit cost. 8 injected bugs, 8 caught |
| S2: fact totals reconciled against totals computed straight from the files (Claude $2,830.28776008, Gemini $287.839433) | **Kept as a regression test** |
| S3: offered an `access_denial` log of every refused request as an option | **Chose** to add it: evidence for security review and for the Part B denial demo (D23) |
| S3: wrote the permission matrix test as a hand-filled table from the starter kit's environment table, not derived from the code | **Accepted**; a test that computes expectations from the code can't catch the code being wrong |
| S3: deliberate-bug check on the permission model: 2 of 6 bugs survived (leads writing other groups if the YAML ever said `all`; deactivated users still accepted) | **Required tests for both;** now 6 of 6 caught (D27) |
| S3: a test helper leaked a SQLite connection (`with sqlite3.connect()` commits but doesn't close) | **Caught by the strict pytest setting** I kept from S0; fixed |
| S4: added `jsonschema` so API tests validate responses against `contracts/tools.schema.json` | **Accepted**: the contract Part B must honour is tested from Part A (D33) |
| S4: golden test computes one group-week's tokens and cost straight from the export files and compares with the API | **Kept** as the end-to-end check from file to API |
| S4: deliberate-bug check on access paths (skipped check, all-groups leak, 404-before-403, ranking, contract drift, period anchoring): 6 of 6 caught | **Accepted** |
| S4: when I asked to commit, flagged that `make check` was red (an unused import, then strict type errors in a test) | **Held the commit** until the check was green |
