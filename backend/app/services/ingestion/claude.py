"""Claude raw rows -> facts. Pure: no database access.

One fact per user x day x product x model, joining the usage record with its cost records
(tokens, plus web_search when present). Mapping rules (README "Mapping decisions"):
  input_tokens  = uncached + cache_read + cache_creation (5m + 1h)
  output_tokens = output_tokens; total must equal the source's total_tokens
  cost          = sum of cost amounts (cents) -> nano-USD; web search cost included
"""

from collections import defaultdict
from datetime import date
from decimal import Decimal

from app.core.money import cents_to_nano
from app.core.timestamps import iso_week, month, parse_rfc3339
from app.models.sources.claude import ClaudeBucket, ClaudeCostRecord, ClaudeUsageRecord
from app.repositories.facts import FactRow, IssueRow
from app.services.ingestion.attribute import Context, DirectoryIndex, attribute

Key = tuple[str, str, str, str]  # actor, bucket start, product, model


def _key(record: ClaudeBucket) -> Key:
    actor = record.actor.user_id or record.actor.email or record.actor.type
    return (actor, record.starting_at, record.product, record.model)


def build_facts(
    usage_rows: list[tuple[int, str]],
    cost_rows: list[tuple[int, str]],
    index: DirectoryIndex,
) -> tuple[list[FactRow], list[IssueRow]]:
    usage: dict[Key, tuple[int, ClaudeUsageRecord]] = {}
    for raw_id, payload in usage_rows:
        record = ClaudeUsageRecord.model_validate_json(payload)
        usage[_key(record)] = (raw_id, record)
    costs: dict[Key, list[tuple[int, ClaudeCostRecord]]] = defaultdict(list)
    for raw_id, payload in cost_rows:
        cost = ClaudeCostRecord.model_validate_json(payload)
        costs[_key(cost)].append((raw_id, cost))

    facts: list[FactRow] = []
    issues: list[IssueRow] = []
    for key in sorted(usage.keys() | costs.keys()):
        fact, found = _build_one(usage.get(key), costs.get(key, []), index)
        issues += found
        if fact is not None:
            facts.append(fact)
    return facts, issues


def _build_one(
    usage: tuple[int, ClaudeUsageRecord] | None,
    costs: list[tuple[int, ClaudeCostRecord]],
    index: DirectoryIndex,
) -> tuple[FactRow | None, list[IssueRow]]:
    record: ClaudeBucket = usage[1] if usage else costs[0][1]
    day: date = parse_rfc3339(record.starting_at).date()
    usage_ids = [usage[0]] if usage else []
    cost_ids = [raw_id for raw_id, _ in costs]
    # Issues point at the usage row when there is one, otherwise at the cost rows.
    context = Context(
        platform="claude",
        usage_date=day.isoformat(),
        raw_table="raw_claude_usage" if usage else "raw_claude_cost",
        raw_ids=tuple(usage_ids or cost_ids),
    )
    issues: list[IssueRow] = []

    input_tokens = output_tokens = 0
    metadata: dict[str, object] = {}
    if usage:
        u = usage[1]
        input_tokens = (
            u.uncached_input_tokens
            + u.cache_read_input_tokens
            + u.cache_creation.ephemeral_5m_input_tokens
            + u.cache_creation.ephemeral_1h_input_tokens
        )
        output_tokens = u.output_tokens
        if input_tokens + output_tokens != u.total_tokens:
            detail = f"input {input_tokens} + output {output_tokens} != total {u.total_tokens}"
            return None, [context.issue("error", "token_total_mismatch", detail)]
        metadata |= {
            "uncached_input_tokens": u.uncached_input_tokens,
            "cache_read_input_tokens": u.cache_read_input_tokens,
            "cache_creation_5m_input_tokens": u.cache_creation.ephemeral_5m_input_tokens,
            "cache_creation_1h_input_tokens": u.cache_creation.ephemeral_1h_input_tokens,
            "web_search_requests": u.server_tool_use.web_search_requests,
        }
    else:
        issues.append(context.issue("warning", "usage_missing", "cost without a usage record"))
    if not costs:
        issues.append(
            context.issue(
                "warning", "cost_pending", "usage without cost records; cost counted as 0"
            )
        )

    cents_by_type: dict[str, Decimal] = defaultdict(Decimal)
    list_cents = Decimal(0)
    for _, cost in costs:
        cents_by_type[cost.cost_type] += cost.amount
        list_cents += cost.list_amount if cost.list_amount is not None else cost.amount
    metadata |= {
        "cost_usd_by_type": {t: str(c / 100) for t, c in sorted(cents_by_type.items())},
        "list_cost_usd": str(list_cents / 100),
        "rbac_group_id": record.rbac_group_id,
        "context_window": record.context_window,
        "inference_geo": record.inference_geo,
        "speed": record.speed,
    }

    actor = record.actor
    user = index.users_by_id.get(actor.user_id or "") or index.users_by_email.get(
        (actor.email or "").lower()
    )
    attribution, found = attribute(
        context,
        user=user,
        user_ref=f"actor {actor.user_id or actor.email or actor.type}",
        group=index.groups_by_rbac_id.get(record.rbac_group_id or ""),
        group_ref=f"rbac_group_id {record.rbac_group_id}",
    )
    issues += found
    if attribution is None:
        return None, issues

    raw_refs = {"raw_claude_usage": usage_ids, "raw_claude_cost": cost_ids}
    return FactRow(
        platform="claude",
        usage_date=day.isoformat(),
        iso_week=iso_week(day),
        month=month(day),
        user_id=attribution.user_id,
        group_id=attribution.group_id,
        model=record.model,
        product=record.product,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        requests=usage[1].requests if usage else record.requests,
        cost_nanousd=cents_to_nano(sum(cents_by_type.values(), Decimal(0))),
        metadata=metadata,
        raw_refs={table: ids for table, ids in raw_refs.items() if ids},
    ), issues
