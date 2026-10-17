"""Validate API responses against contracts/tools.schema.json (the Part B tool contract)."""

from jsonschema import Draft202012Validator

from app.core.contract import ToolName, denial_schema, output_schema


def assert_tool_output(tool: ToolName, payload: object) -> None:
    Draft202012Validator(output_schema(tool)).validate(payload)


def assert_denial(payload: object) -> None:
    Draft202012Validator(denial_schema()).validate(payload)
