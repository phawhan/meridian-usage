"""contracts/tools.schema.json, the Part B tool contract. The connector advertises and validates
exactly these schemas, provisioning reads each tool's scope from it, and tests check API
responses against it, so the file is the single definition of the four tools."""

import json
from functools import cache
from typing import Any, Literal, cast, get_args

from app.core.env_config import SCOPES, Scope
from app.core.resources import shipped

CONTRACT_FILE = shipped("contracts/tools.schema.json")

ToolName = Literal["usage_summary", "top_users", "capability_status", "set_capability"]
TOOL_NAMES: tuple[ToolName, ...] = get_args(ToolName)


@cache
def contract() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(CONTRACT_FILE.read_text())
    if sorted(loaded["tools"]) != sorted(TOOL_NAMES):
        raise ValueError(f"{CONTRACT_FILE.name} defines {sorted(loaded['tools'])}")
    return loaded


def _with_defs(schema: dict[str, Any]) -> dict[str, Any]:
    return {"$schema": contract()["$schema"], "$defs": contract()["$defs"], **schema}


def input_schema(tool: ToolName) -> dict[str, Any]:
    """The contract's input schema, closed: an argument the contract doesn't name (say 'user'
    or 'as_admin') is rejected, not ignored."""
    return _with_defs({**contract()["tools"][tool]["input"], "additionalProperties": False})


def output_schema(tool: ToolName) -> dict[str, Any]:
    return _with_defs(contract()["tools"][tool]["output"])


def denial_schema() -> dict[str, Any]:
    return _with_defs({"$ref": "#/$defs/Denial"})


def tool_scope(tool: ToolName) -> Scope:
    scope = contract()["tools"][tool]["scope"]
    if scope not in SCOPES:
        raise ValueError(f"{tool} needs unknown scope {scope!r}")
    return cast(Scope, scope)
