"""Small builders for transform tests: a two-person directory and source records."""

import json
from typing import Any

from app.models.domain import Group, User
from app.services.ingestion.attribute import DirectoryIndex

PRIYA = User(
    user_id="user_priya",
    email="priya@x.example",
    name="Priya",
    role="team_lead",
    group_ids=["clinical-operations"],
    active=True,
)
RAVI = User(
    user_id="user_ravi",
    email="ravi@x.example",
    name="Ravi",
    role="member",
    group_ids=["finance"],
    active=True,
)
CLINOPS = Group(
    group_id="clinical-operations",
    name="Clinical Operations",
    team_lead_user_id="user_priya",
    claude_rbac_group_id="rbac_clinops",
    gcp_project_id="proj-clinops",
    cost_centre="CC-1",
    active=True,
)
FINANCE = Group(
    group_id="finance",
    name="Finance",
    team_lead_user_id="user_ravi",
    claude_rbac_group_id="rbac_finance",
    gcp_project_id="proj-finance",
    cost_centre="CC-2",
    active=True,
)


def index() -> DirectoryIndex:
    users, groups = [PRIYA, RAVI], [CLINOPS, FINANCE]
    return DirectoryIndex(
        users_by_id={u.user_id: u for u in users},
        users_by_email={u.email: u for u in users},
        groups_by_rbac_id={g.claude_rbac_group_id: g for g in groups},
        groups_by_project_id={g.gcp_project_id: g for g in groups},
    )


def _bucket(user_id: str | None, rbac: str, **overrides: Any) -> dict[str, Any]:
    return {
        "actor": {"type": "user_actor", "user_id": user_id, "email": None},
        "starting_at": "2026-08-03T00:00:00.000Z",
        "ending_at": "2026-08-04T00:00:00.000Z",
        "product": "chat",
        "model": "claude-opus-5-5",
        "rbac_group_id": rbac,
        "requests": 7,
    } | overrides


def claude_usage(
    user_id: str | None = "user_priya", rbac: str = "rbac_clinops", **overrides: Any
) -> str:
    return json.dumps(
        _bucket(user_id, rbac)
        | {
            "uncached_input_tokens": 100,
            "cache_read_input_tokens": 20,
            "cache_creation": {"ephemeral_5m_input_tokens": 3, "ephemeral_1h_input_tokens": 2},
            "output_tokens": 50,
            "total_tokens": 175,
            "server_tool_use": {"web_search_requests": 1},
        }
        | overrides
    )


def claude_cost(
    amount: str, cost_type: str = "tokens", user_id: str = "user_priya", rbac: str = "rbac_clinops"
) -> str:
    return json.dumps(
        _bucket(user_id, rbac)
        | {"cost_type": cost_type, "amount": amount, "list_amount": amount, "currency": "USD"}
    )


def gemini_row(
    direction: str,
    amount: int,
    cost: str,
    owner: str | None = "priya@x.example",
    project: str = "proj-clinops",
    sku: str | None = None,
    credits: list[str] | None = None,
) -> str:
    labels = [
        {"key": "agent", "value": "site-monitor"},
        {"key": "model", "value": "gemini-2.5-flash"},
    ]
    if owner is not None:
        labels.append({"key": "owner", "value": owner})
    # Cost written as a JSON number with full precision, as BigQuery exports it.
    row = {
        "service": {"id": "svc", "description": "Vertex AI"},
        "sku": {
            "id": f"sku-{direction}",
            "description": sku or f"Gemini 2.5 Flash Text {direction} Tokens - Predictions",
        },
        "usage_start_time": "2026-08-05 00:00:00 UTC",
        "usage_end_time": "2026-08-06 00:00:00 UTC",
        "project": {"id": project, "labels": [{"key": "team", "value": "x"}]},
        "labels": labels,
        "location": {"region": "us-central1"},
        "export_time": "2026-08-06 03:41:17.882 UTC",
        "cost": "__COST__",
        "currency": "USD",
        "usage": {"amount": float(amount), "unit": "count"},
        "credits": [{"name": "promo", "amount": "__CREDIT__"}] if credits else [],
        "invoice": {"month": "202608"},
        "cost_type": "regular",
    }
    text = json.dumps(row).replace('"__COST__"', cost)
    for credit in credits or []:
        text = text.replace('"__CREDIT__"', credit, 1)
    return text
