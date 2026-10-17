"""The MCP surface: tool listing and tool calls, on the SDK's low-level Server so the advertised
input schemas are the contract's own (not re-derived from Python signatures)."""

import json
from typing import Any

import mcp_types as types
from mcp.server import Server, ServerRequestContext

from app.connector.tools import Outcome, UsageConnector
from app.core.contract import TOOL_NAMES, ToolName, input_schema, output_schema

INSTRUCTIONS = """\
Meridian AI usage and capability controls. This server acts as one fixed person from the \
company directory; their role and group decide what it may show or change, and no argument \
can change who they are. Periods: last_7_days, last_30_days, an ISO week such as 2026-W36, or \
a month such as 2026-09. {window} When a result has "error": "permission_denied", the \
refusal is final: tell the user the reason in plain words and do not retry the same request \
with other wording or another tool."""


def instructions(periods: dict[str, Any]) -> str:
    """Relative dates are about the data, not today (README: periods). 'Last month' is the
    newest month in the data: the export is the assistant's 'now'."""
    months = [p for p in periods.get("periods", []) if len(p) == 7 and p[4] == "-"]
    last_day = periods.get("data_to_exclusive", "?")
    window = (
        f"Usage data runs from {periods.get('data_from', '?')} up to (not including) {last_day};"
        " relative periods end there, not today."
    )
    if months:
        window += f' When the user says "last month", use {months[0]}.'
    return INSTRUCTIONS.format(window=window)


DESCRIPTIONS: dict[ToolName, str] = {
    "usage_summary": "Tokens and cost (USD) for one group over a period, per platform (Claude, "
    "Gemini) and in total. Omit 'group' for the caller's own group.",
    "top_users": "The heaviest users in a period, ranked by total tokens, with their cost. "
    "Omit 'group' for every group the caller may see. 'limit' is 1-25 (default 10).",
    "capability_status": "Whether each capability (usage-connector, web-search, "
    "code-execution) is switched on for a group, who last changed it and when. Omit 'group' "
    "for every group the caller may see.",
    "set_capability": "Switch a capability on or off for a group. Needs the capabilities:write "
    "permission in this environment. Returns the new state with who changed it and when.",
}

ANNOTATIONS: dict[ToolName, types.ToolAnnotations] = {
    t: types.ToolAnnotations(read_only_hint=True, open_world_hint=False)
    for t in ("usage_summary", "top_users", "capability_status")
} | {
    "set_capability": types.ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    )
}


def _structured_output_schema(tool: ToolName) -> dict[str, Any]:
    """MCP structured content must be an object; array outputs are wrapped as {"result": [...]}
    (the SDK's convention). The text content carries the contract shape unwrapped."""
    schema = output_schema(tool)
    if schema.get("type") == "object":
        return schema
    defs: dict[str, Any] = {k: schema.pop(k) for k in ("$schema", "$defs") if k in schema}
    return {**defs, "type": "object", "properties": {"result": schema}, "required": ["result"]}


def tool_list() -> list[types.Tool]:
    return [
        types.Tool(
            name=t,
            description=DESCRIPTIONS[t],
            input_schema=input_schema(t),
            output_schema=_structured_output_schema(t),
            annotations=ANNOTATIONS[t],
        )
        for t in TOOL_NAMES
    ]


def to_result(outcome: Outcome) -> types.CallToolResult:
    text: list[types.ContentBlock] = [
        types.TextContent(type="text", text=json.dumps(outcome.payload, indent=2))
    ]
    if outcome.kind != "result":
        # Denials and errors are error results (the contract's "as an error result").
        return types.CallToolResult(content=text, structured_content=outcome.payload, is_error=True)
    payload = outcome.payload
    structured = payload if isinstance(payload, dict) else {"result": payload}
    return types.CallToolResult(content=text, structured_content=structured)


def build_server(
    connector: UsageConnector, name: str, version: str, periods: dict[str, Any] | None = None
) -> Server[Any]:
    async def list_tools(
        ctx: ServerRequestContext[Any], params: types.PaginatedRequestParams | None
    ) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tool_list())

    async def call_tool(
        ctx: ServerRequestContext[Any], params: types.CallToolRequestParams
    ) -> types.CallToolResult:
        return to_result(await connector.call(params.name, dict(params.arguments or {})))

    return Server(
        name,
        version=version,
        instructions=instructions(periods or {}),
        on_list_tools=list_tools,
        on_call_tool=call_tool,
    )
