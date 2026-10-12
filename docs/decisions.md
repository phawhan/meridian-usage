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
