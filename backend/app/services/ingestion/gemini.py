"""Gemini billing rows -> facts. Pure: no database access.

Billing rows are per project x day x SKU x labels, with input and output tokens on
separate SKUs. One fact per project x day x owner x agent x model, pivoting the Input and
Output SKU rows into one (README "Mapping decisions"):
  model         = parsed from the SKU ("Gemini 2.5 Flash Text Input Tokens" -> gemini-2.5-flash)
  input/output  = usage.amount of the Input / Output SKU rows
  cost          = cost + credits (GCP's cost is before credits) -> nano-USD
  user          = 'owner' resource label (email); group = project.id
"""

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from app.core.money import usd_to_nano
from app.core.timestamps import iso_week, month, parse_bigquery, to_iso
from app.models.sources.gemini import GeminiBillingRow
from app.repositories.facts import FactRow, IssueRow
from app.services.ingestion.attribute import Context, DirectoryIndex, attribute

_SKU = re.compile(r"^Gemini (?P<model>.+?) Text (?P<direction>Input|Output) Tokens\b")
NO_AGENT = "unlabelled"


@dataclass(frozen=True)
class _Sku:
    model: str
    direction: str


def parse_sku(description: str) -> _Sku | None:
    match = _SKU.match(description)
    if match is None:
        return None
    model = "gemini-" + match["model"].lower().replace(" ", "-")
    return _Sku(model=model, direction=match["direction"])


def build_facts(
    rows: list[tuple[int, str]], index: DirectoryIndex
) -> tuple[list[FactRow], list[IssueRow]]:
    groups: dict[tuple[str, str, str, str, str], list[tuple[int, GeminiBillingRow, _Sku]]] = (
        defaultdict(list)
    )
    issues: list[IssueRow] = []
    for raw_id, payload in rows:
        row = GeminiBillingRow.model_validate(json.loads(payload, parse_float=Decimal))
        day = parse_bigquery(row.usage_start_time).date().isoformat()
        sku = parse_sku(row.sku.description)
        if sku is None:
            context = Context("gemini", day, "raw_gemini_billing", (raw_id,))
            issues.append(
                context.issue(
                    "error", "unknown_sku", f"not a Gemini token SKU: {row.sku.description!r}"
                )
            )
            continue
        owner = (row.label("owner") or "").strip().lower()
        key = (row.project.id, day, owner, row.label("agent") or NO_AGENT, sku.model)
        groups[key].append((raw_id, row, sku))

    facts: list[FactRow] = []
    for key in sorted(groups):
        fact, found = _build_one(key, groups[key], index)
        issues += found
        if fact is not None:
            facts.append(fact)
    return facts, issues


def _build_one(
    key: tuple[str, str, str, str, str],
    members: list[tuple[int, GeminiBillingRow, _Sku]],
    index: DirectoryIndex,
) -> tuple[FactRow | None, list[IssueRow]]:
    project_id, day_text, owner, agent, model = key
    raw_ids = tuple(raw_id for raw_id, _, _ in members)
    context = Context("gemini", day_text, "raw_gemini_billing", raw_ids)

    tokens = {"Input": 0, "Output": 0}
    cost = credits = cost_at_list = Decimal(0)
    for _, row, sku in members:
        tokens[sku.direction] += int(row.usage.amount)
        cost += row.cost
        credits += sum((credit.amount for credit in row.credits), Decimal(0))
        cost_at_list += row.cost_at_list if row.cost_at_list is not None else row.cost

    first = members[0][1]
    attribution, issues = attribute(
        context,
        user=index.users_by_email.get(owner),
        user_ref=f"owner label {owner!r}" if owner else "a row with no owner label",
        group=index.groups_by_project_id.get(project_id),
        group_ref=f"project {project_id}",
    )
    if attribution is None:
        return None, issues

    day = parse_bigquery(first.usage_start_time).date()
    return FactRow(
        platform="gemini",
        usage_date=day_text,
        iso_week=iso_week(day),
        month=month(day),
        user_id=attribution.user_id,
        group_id=attribution.group_id,
        model=model,
        product=agent,
        input_tokens=tokens["Input"],
        output_tokens=tokens["Output"],
        requests=None,
        cost_nanousd=usd_to_nano(cost + credits),
        metadata={
            "project_id": project_id,
            "project_labels": {label.key: label.value for label in first.project.labels},
            "model_label": first.label("model"),
            "skus": sorted({row.sku.description for _, row, _ in members}),
            "region": first.location.region if first.location else None,
            "invoice_months": sorted({row.invoice.month for _, row, _ in members}),
            "cost_before_credits_usd": str(cost),
            "credits_usd": str(credits),
            "cost_at_list_usd": str(cost_at_list),
            "latest_export_time": max(to_iso(parse_bigquery(r.export_time)) for _, r, _ in members),
        },
        raw_refs={"raw_gemini_billing": list(raw_ids)},
    ), issues
