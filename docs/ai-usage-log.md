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
<!-- one row per story as it lands -->
