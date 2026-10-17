"""The four tools. Each call goes through the same steps, in order:

  1. arguments are validated against the contract's input schema (closed: unknown names fail);
  2. authz.authorize() runs locally with the manifest's policy: a refusal here sends no
     request to the service at all, so no data can come back;
  3. the service is called as the connector's fixed user; it checks the same rules again,
     plus the live usage-connector switch, and may still refuse;
  4. the answer is validated against the contract's output schema before it is returned.

The caller is fixed when the connector starts and is never read from the arguments.
"""

import json
import logging
from dataclasses import dataclass
from functools import cache
from typing import Any, Literal

from jsonschema import Draft202012Validator

from app.connector.service import ServiceError, UsageService
from app.core.contract import TOOL_NAMES, ToolName, input_schema, output_schema
from app.core.env_config import Policy
from app.models.denial import Denial
from app.models.domain import User
from app.services.authz import Action, authorize

log = logging.getLogger("meridian.connector")

TOOL_ACTION: dict[ToolName, Action] = {
    "usage_summary": "read_usage",
    "top_users": "read_usage",
    "capability_status": "read_capabilities",
    "set_capability": "write_capability",
}

OutcomeKind = Literal["result", "denial", "error"]


@dataclass(frozen=True)
class Outcome:
    kind: OutcomeKind
    payload: Any  # contract output, a Denial dict, or {"error": ..., "reason": ...}


def _error(code: str, reason: str) -> Outcome:
    return Outcome("error", {"error": code, "reason": reason})


@cache
def _input_validator(tool: ToolName) -> Draft202012Validator:
    return Draft202012Validator(input_schema(tool))


@cache
def _output_validator(tool: ToolName) -> Draft202012Validator:
    return Draft202012Validator(output_schema(tool))


class UsageConnector:
    def __init__(self, caller: User, policy: Policy, service: UsageService) -> None:
        self.caller = caller
        self.policy = policy
        self.service = service
        self.periods: dict[str, Any] = {}  # GET /periods at startup, for the instructions

    async def call(self, name: str, arguments: dict[str, Any]) -> Outcome:
        if name not in TOOL_NAMES:
            return _error("unknown_tool", f"no tool named {name!r}")
        tool: ToolName = name
        problems = sorted(_input_validator(tool).iter_errors(arguments), key=str)
        if problems:
            return _error("invalid_arguments", "; ".join(p.message for p in problems))

        own = self.caller.group_ids[0] if self.caller.group_ids else ""
        target = arguments.get("group") or own
        denial = authorize(self.caller, TOOL_ACTION[tool], target, self.policy)
        if denial is not None:
            self._log_refusal(tool, target, denial, "connector")
            return Outcome("denial", denial.model_dump(exclude_none=True))

        try:
            answer = await self._ask_service(tool, arguments)
        except ServiceError as exc:
            return _error("service_unavailable", str(exc))
        if isinstance(answer, Denial):
            self._log_refusal(tool, target, answer, "service")
            return Outcome("denial", answer.model_dump(exclude_none=True))

        problems = list(_output_validator(tool).iter_errors(answer))
        if problems:  # never hand the model something the contract doesn't promise
            log.error("contract violation from service for %s: %s", tool, problems[0].message)
            return _error("contract_violation", "the usage service returned an unexpected shape")
        return Outcome("result", answer)

    async def _ask_service(self, tool: ToolName, args: dict[str, Any]) -> Any | Denial:
        group, period = args.get("group"), args.get("period")
        match tool:
            case "usage_summary":
                return await self.service.get("/usage/summary", period=period, group=group)
            case "top_users":
                limit = args.get("limit", 10)
                return await self.service.get(
                    "/usage/top-users", period=period, group=group, limit=limit
                )
            case "capability_status":
                return await self.service.get("/capabilities", group=group)
            case "set_capability":
                path = f"/capabilities/{args['group']}/{args['capability']}"
                return await self.service.put(path, {"enabled": args["enabled"]})

    def _log_refusal(self, tool: str, group: str, denial: Denial, by: str) -> None:
        # stderr only: stdout is the MCP channel. Claude Desktop keeps this per server.
        record = {"event": "denied", "by": by, "caller": self.caller.user_id, "tool": tool}
        log.warning(json.dumps(record | {"group": group, "reason": denial.reason}))
