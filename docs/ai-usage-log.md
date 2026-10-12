# AI usage log

Raw notes, kept as work happens. The README section is written from these in my own words.
Tool: Claude Code (VS Code extension). Format: date | what AI did | what I decided / overruled.

## 2026-10-12 Planning

| What AI did | What I decided |
|---|---|
| Profiled the starter data (row counts, join keys, orphans, token totals) before planning | Accepted. Found the Gemini "per project x day x SKU" doc mismatch (D7) |
| Proposed keeping the directory in memory | **Overruled.** Mirrored into read-only tables for joins and FK integrity (D8) |
| Proposed Python service + TS connector, plain HTML admin page | **Changed.** React admin console with mocked identity; Python + TS still covered |
| Listed "tests" as a final story | **Overruled by AI pushback, I agreed.** Tests ship inside each story; S6 holds only cross-cutting gates |
| Started describing env YAML validation as a richer contract | **Trimmed.** Role management is out of scope; loader only reads, normalises, fails fast |
| Explained YAML `scopes` vs `capability_defaults` vs DB state | Adopted the policy / baseline / live-state split (D5) and one DB per env (D9) |
| Claimed in chat it had rewritten the plan file when it had not | **Caught.** AI corrected itself the next turn. Lesson: verify file changes, don't trust the summary |
| Recommended Gemini CLI extension as primary platform after reading the JD | Accepted; Claude Desktop config as a rendered bonus |

## Build log

| What AI did | What I decided |
|---|---|
| S0.2 scaffold: AI swapped dev dep `httpx` -> `httpx2` after a Starlette 1.7 deprecation warning, verified in the installed source first | Accepted |
| S0.4 tests: AI's first version leaked SQLite connections (Python 3.13 ResourceWarning) | Fixed with `closing()`; pytest now turns ResourceWarning into a failure so leaks can't come back |
| S0 smoke test: env-guard check printed nothing; AI re-ran it rather than assuming success (macOS has no `timeout`) | Guard confirmed: `database belongs to 'prod', refusing to start as 'dev'` |
| S0.5: `create-vite` now ships oxlint instead of ESLint, TS 6, Vite 8 | Kept the template defaults rather than swapping tooling |
| S1 schema: AI's first draft had no audit columns or comments | **Overruled.** Audit columns (`created_*/updated_*`) and table/column comments on every table (D16) |
| S1 schema: AI proposed a per-directory `directory_sync` log table | **Overruled.** One `source_file` row per file of any kind + `sync_run` per pass (D15); AI refined the skip rule (latest version at the path, any status) |
| S1 design: AI changed plan's "replace-all" to upsert + soft-deactivate, foreseeing S2's FK from facts to users | Accepted (D14) |
| S1 lint: ruff suggested `for k in row` instead of `row.keys()` on `sqlite3.Row` | **AI rejected the auto-fix** (iterating a Row yields values, not keys); mapped columns explicitly |
| S1 tests: all 29 passed first run; AI injected 3 bugs (duplicate check, deactivation, skip rule) to prove the tests catch them | Each caught; code restored |
