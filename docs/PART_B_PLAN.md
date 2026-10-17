# Part B plan: the connector, scoped, shipped

Assignment ID: Fullstack-ClaudeGemini-UsageConnector-v1

Platform: **Claude** (Claude Desktop registration + Claude plugin). Gemini CLI extension is an optional last story (B8); the brief needs one platform.
Stack: connector in Python (`backend/app/connector/`, official `mcp` SDK, stdio), calling the Part A FastAPI service over HTTP. Python because the brief doesn't require TypeScript and the repo already has both languages (the admin console is TypeScript); in Python the connector reuses `authz.authorize()`, so the rules exist once. Provisioning script in Python (reuses `EnvConfig`).
Template: same as Part A. Each story has a user story, AC, and sub-tasks with their tests. Story IDs continue as B0..B9.

---

## 1. Shape

```
Claude Desktop / Claude Code
   | MCP over stdio (host launches the connector as a child process)
app.connector (Python, one process per user)   started as --user <id> --env <env>
   | 1. validate input against contracts/tools.schema.json
   | 2. local check: authz.authorize() with the policy from the rendered permissions manifest
   | 3. usage-connector switch for the caller's group (live, from the API)
   | HTTP  X-User-Id: <id>   X-Channel: connector
backend/   (FastAPI, Part A)                re-checks everything in authz.py, logs refusals
   |
SQLite (one DB per env)
```

Identity is fixed when the process starts, from `--user`. No tool takes a user argument, and the input schemas reject unknown properties. A prompt can change which group is asked about, but never who is asking.

### Concepts this relies on
- **Policy decision point vs enforcement point (PDP/PEP).** `authz.py` decides, and both the connector and the API enforce. Think of a judge and two bailiffs: the bailiffs don't write law, they apply the judge's ruling at their door.
- **Confused deputy.** The model acts on behalf of whoever wrote the prompt. If identity or scope could arrive through tool arguments, a prompt could borrow privileges. That's why identity comes from process start and never from the conversation.
- **Defence in depth.** Two checks at two doors: a bug in the wiring of one layer doesn't leak data. Both call the same `authorize()`, so the rules can't drift apart; what the second door adds is protection against a connector that skips its check or a request that bypasses the connector.
- **Fail closed.** API unreachable, manifest invalid, user unknown, env mismatch: refuse, never "allow and hope".
- **Render, validate, diff (infrastructure as code).** Config is a build output, not a hand-made file. CI re-renders and fails on any diff, which is how "nothing is hand-edited" becomes checkable.

---

## 2. Stories

### B0 Connector skeleton (done 2026-10-15)
**As a** developer **I want** the connector inside the backend package **so that** it shares models, policy and tooling and is checked by the same `make check`.
AC: `uv run meridian-connector --help` runs; ruff, mypy strict and pytest cover it.

| ID | Sub-task | Tests |
|---|---|---|
| B0.1 | `app/connector/` package; add `mcp` and `httpx` to `pyproject.toml`; `meridian-connector` script entry; read the `mcp` 2.x server docs first | import + entry point |
| B0.2 | CLI args + env (`--user`, `--env`, `--api-url`, `--manifest`); bad or missing arg fails with a clear message on stderr (stdout is the MCP channel) | arg parsing |
| B0.3 | Makefile `connector` target (runs it for a given user/env); `check` already covers `backend/` | n/a |

### B1 Backend: connector channel and switch gate (done 2026-10-15)
**As a** platform owner **I want** the `usage-connector` switch to gate the assistant **so that** a disabled group gets nothing through it (D1).
AC: requests with `X-Channel: connector` are refused with a `Denial` when `usage-connector` is off for the caller's group; refusals are logged with `channel=connector`; admin page requests are unaffected.

| ID | Sub-task | Tests |
|---|---|---|
| B1.1 | `X-Channel` header (`api` default, `connector`); passed into `enforce()` and the identify log | channel recorded on denial rows |
| B1.2 | `authorize_connector()` in `authz.py`: pure, switch state in, `Denial` out; rule = switch is checked on the caller's group(s), all must be on (fail closed; no multi-group users in the data) | matrix: on/off x role x env |
| B1.3 | Wire into usage and capabilities routes for the connector channel | prod Finance lead -> denial; prod clinical-ops lead -> data |
| B1.4 | Decision: the switch gates *who may use the assistant tool*, not *which group's data*; an admin in it-platform can still read Finance via the connector | test for it |

### B2 Connector tools (done 2026-10-15)
**As a** team lead **I want** four tools in my assistant **so that** I can ask about my team's usage without leaving it.
AC: tool names, inputs and outputs match `contracts/tools.schema.json`; every output is validated against the contract before it is returned; a denial is returned as the contract's `Denial` with no partial data.

| ID | Sub-task | Tests |
|---|---|---|
| B2.1 | Startup: `GET /healthz` env must equal `--env` and the manifest env; `GET /me` resolves the user (role, groups); any mismatch or unknown user -> exit non-zero | each failure path |
| B2.2 | API client: `X-User-Id`, `X-Channel: connector`, timeout; 403 body -> `Denial`; network error -> structured `unavailable` error, never data | mocked fetch |
| B2.3 | Tools: `usage_summary`, `top_users`, `capability_status`, `set_capability`; input schemas from the contract with `additionalProperties: false`; descriptions written for the model (what it returns, default group, period forms) | contract fixtures in/out |
| B2.4 | Local check: load the manifest into the same `Policy` type, call `authz.authorize()` before any HTTP request | denied call makes no request |
| B2.5 | Denial returned as an MCP tool result with `isError: true` and the `Denial` JSON (check how the SDK treats `outputSchema` on error results) | denial shape |

### B3 Scoping tests end to end (done 2026-10-15)
**As a** reviewer **I want** proof that the model cannot talk its way around scope **so that** I trust the permission model.
AC: with a real backend and a real MCP client over stdio: team lead cross-group read -> `Denial` and **no usage request reaches the API**; lead `set_capability` in prod -> `Denial`; member in staging/prod -> `Denial`; admin reads any group; disabled `usage-connector` -> `Denial`.

| ID | Sub-task | Tests |
|---|---|---|
| B3.1 | Test harness: start uvicorn on a temp DB per env, spawn the connector, connect with the SDK client | n/a |
| B3.2 | Allowed / denied matrix through the MCP protocol (the three demo cases + switch off) | as AC |
| B3.3 | Injection-shaped inputs: extra `user`/`as` args rejected by schema; group names like `finance; it-platform`, `*`, `../` rejected by the enum | rejected, no API call |
| B3.4 | Backend-only bypass: call the API directly with `X-Channel: connector` as the lead for another group -> 403 (second layer holds alone) | 403 |

### B4 Provisioning: one command, three environments (done 2026-10-15; CI green once pushed)
**As a** platform owner **I want** one command that renders and validates every environment's config **so that** nothing is hand-edited and drift is caught.
AC: `make provision` renders `deploy/{dev,staging,prod}/` from `environments/*.yaml` + directory + contract, validates every output, and is deterministic (two runs, byte-identical). `make provision-check` re-renders into a temp dir and fails on any diff with the committed output.

| ID | Sub-task | Tests |
|---|---|---|
| B4.1 | `backend/app/provision.py` (`meridian provision`): load `EnvConfig` (same strict validation as startup) | invalid YAML fails |
| B4.2 | Render `permissions.json`: env, roles -> scopes, visibility, tool -> scope map (from the contract), capability baseline per group, server name, API URL | golden per env |
| B4.3 | Render host config: `claude_desktop_config.json` fragment (`mcpServers.<server_name>`, command, args, env) and the plugin (B5) per env | golden per env |
| B4.4 | Validate: JSON Schema for each output (`provisioning/schemas/`); cross-checks: every contract tool has a scope, every group exists in the directory, server names unique across envs, prod grants a subset of staging, staging of dev | one failing fixture per rule |
| B4.5 | CI (`.github/workflows/ci.yml`, was S6.3): `make check`, `make provision-check` | green on GitHub |

### B5 Claude: register and package (done 2026-10-15 except B5.4, the manual Desktop check)
**As a** platform team **I want** the connector shipped the way Claude documents it **so that** a team lead installs it in one step.
AC: follows Anthropic's current docs (checked at build time, linked in README); the rendered Desktop entry starts the connector and lists the four tools; the plugin installs from a local marketplace in Claude Code.

| ID | Sub-task | Tests |
|---|---|---|
| B5.1 | Read current docs: Claude Desktop local MCP config, Claude Code plugins (`.claude-plugin/plugin.json`, `.mcp.json`, `marketplace.json`, `${CLAUDE_PLUGIN_ROOT}`, how a user value like the persona is supplied) | n/a |
| B5.2 | Plugin per env: `deploy/<env>/plugin/` with manifest and `.mcp.json` launching the connector with `uv run` (team leads need `uv`; noted in README); marketplace file at repo root listing the three | schema-validated in B4.4 |
| B5.3 | `make register-desktop ENV=dev USER=u_...`: merges the rendered entry into the Desktop config (backup first, never overwrites other servers) | merge test on a temp file |
| B5.4 | Manual: install Claude Desktop, register, confirm tools appear; install plugin in Claude Code | checklist |

### B6 Demo: recording and transcript (transcript done 2026-10-15; recording pending, script in docs/demo/RECORDING.md)
**As a** reviewer **I want** to see it working **so that** I don't have to install it to believe it.
AC: a recording in Claude Desktop showing (1) an allowed read, (2) a denied cross-group read, (3) a denied write; plus a reproducible transcript.

| ID | Sub-task |
|---|---|
| B6.1 | `make demo-transcript`: scripted MCP client runs the three cases as Priya (lead) in prod and writes `docs/demo/transcript.md` (requests, responses, denial JSON) |
| B6.2 | Screen recording in Claude Desktop, same three asks in plain English; linked from README |

### B7 Note to team leads (AI draft written 2026-10-15; mine to rewrite)
**As a** team lead **I want** a short note in my language **so that** I know what I can ask, what I can't and why, and how to get more.
AC: under one page, no jargon (no "scope", "MCP", "RBAC"); example questions; what's refused and why; how to request access (who, what to send); per-environment differences stated plainly.

| ID | Sub-task |
|---|---|
| B7.1 | `docs/note-to-team-leads.md`, drafted by you, reviewed together |

### B8 Gemini CLI extension (rendered and validated 2026-10-15; not run in Gemini CLI)
Same connector, `gemini-extension.json` + `settings.json` entry rendered by B4; recorded only if Gemini CLI is installed. Otherwise documented as next step.

### B9 Part B write-up (done 2026-10-15; drafts marked for rewrite)
| ID | Sub-task |
|---|---|
| B9.1 | README: full architecture diagram (both halves), permission model with the connector layer, platform built for + exact versions run on |
| B9.2 | README: how capabilities are scoped and distributed on Claude, where Claude usage data comes from (Analytics API) |
| B9.3 | README: what I'd do with more time; *In the real enterprise version* (IdP/SSO and OAuth instead of `--user`, org connector registry, real Analytics + billing APIs, real infra); in your words |
| B9.4 | `decisions.md` and `ai-usage-log.md` entries for Part B (log as we go) |

---

## 3. Submission tracker (Part B items)

| Required item | Story |
|---|---|
| MCP server, four tools | B0, B2 |
| Scoped in the server, tested, structured denial, honours switches | B1, B2.4, B3 |
| Register in Claude Desktop + package as Claude plugin | B5 |
| Recording or transcript (allowed read, denied cross-group read, denied write) | B6 |
| One command renders + validates 3 envs; CI runs tests + validation | B4 |
| Note to team leads | B7 |
| README: platform, run-on, enterprise version, more time, AI usage | B9 |

## 4. Carried over from Part A
- S5 manual browser check of the admin console.
- README "How I used AI tools" rewritten in your words.

## 5. Open decisions (defaults chosen, change if you disagree)
- Connector-side refusals never reach the API, so they aren't in `access_denial`. Default: log them to stderr (Claude Desktop keeps MCP server logs); note the gap in README.
- Rendered `deploy/` is committed (the plugin must be installable from git) and guarded by the CI diff check.
- Persona in the plugin: supplied at install (if the plugin system supports a user value) or via an env var; settled in B5.1.
- Provisioning in a Python script, not Terraform: it reuses the startup validator, so the rules exist once.
