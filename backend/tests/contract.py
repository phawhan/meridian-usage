"""Validate API responses against contracts/tools.schema.json (the Part B tool contract)."""

import json
from functools import cache
from typing import Any

from jsonschema import Draft202012Validator

from app.core.config import REPO_ROOT


@cache
def _contract() -> dict[str, Any]:
    contract: dict[str, Any] = json.loads(
        (REPO_ROOT / "contracts" / "tools.schema.json").read_text()
    )
    return contract


def assert_tool_output(tool: str, payload: object) -> None:
    contract = _contract()
    schema = {"$defs": contract["$defs"], **contract["tools"][tool]["output"]}
    Draft202012Validator(schema).validate(payload)


def assert_denial(payload: object) -> None:
    contract = _contract()
    Draft202012Validator({"$defs": contract["$defs"], "$ref": "#/$defs/Denial"}).validate(payload)
