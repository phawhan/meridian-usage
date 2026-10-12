from app.repositories.facts import IssueRow
from app.services.ingestion.claude import build_facts
from tests.factories import claude_cost, claude_usage, index


def codes(issues: list[IssueRow]) -> list[tuple[str, str]]:
    return [(i.severity, i.code) for i in issues]


def test_usage_and_both_cost_types_join_into_one_fact() -> None:
    facts, issues = build_facts(
        [(1, claude_usage())],
        [(10, claude_cost("88.900050")), (11, claude_cost("1.000000", cost_type="web_search"))],
        index(),
    )

    assert issues == []
    [fact] = facts
    assert (fact.user_id, fact.group_id, fact.product, fact.model) == (
        "user_priya",
        "clinical-operations",
        "chat",
        "claude-opus-5-5",
    )
    assert (fact.input_tokens, fact.output_tokens, fact.total_tokens) == (125, 50, 175)
    assert fact.requests == 7
    assert fact.cost_nanousd == 899_000_500  # (88.900050 + 1.000000) cents
    assert fact.metadata["cost_usd_by_type"] == {"tokens": "0.8890005", "web_search": "0.010000"}
    assert fact.metadata["cache_read_input_tokens"] == 20
    assert fact.raw_refs == {"raw_claude_usage": [1], "raw_claude_cost": [10, 11]}
    assert (fact.usage_date, fact.iso_week, fact.month) == ("2026-08-03", "2026-W32", "2026-08")


def test_token_total_mismatch_quarantines_the_row() -> None:
    facts, issues = build_facts([(1, claude_usage(total_tokens=999))], [], index())
    assert facts == []
    assert codes(issues) == [("error", "token_total_mismatch")]


def test_usage_without_cost_is_kept_with_zero_cost_and_a_warning() -> None:
    facts, issues = build_facts([(1, claude_usage())], [], index())
    assert facts[0].cost_nanousd == 0 and facts[0].total_tokens == 175
    assert codes(issues) == [("warning", "cost_pending")]


def test_cost_without_usage_is_kept_with_zero_tokens_and_a_warning() -> None:
    facts, issues = build_facts([], [(10, claude_cost("50"))], index())
    assert facts[0].total_tokens == 0 and facts[0].cost_nanousd == 500_000_000
    assert codes(issues) == [("warning", "usage_missing")]
    assert issues[0].raw_table == "raw_claude_cost" and issues[0].raw_ids == (10,)


def test_unknown_user_and_group_are_quarantined_not_guessed() -> None:
    facts, issues = build_facts(
        [(1, claude_usage(user_id="user_ghost", rbac="rbac_unknown"))], [], index()
    )
    assert facts == []
    assert ("error", "unknown_user") in codes(issues)
    assert ("error", "unknown_group") in codes(issues)


def test_group_comes_from_the_row_and_a_mismatch_is_a_warning() -> None:
    # Priya sits in clinical-operations, but this row was billed to Finance's RBAC group.
    facts, issues = build_facts(
        [(1, claude_usage(rbac="rbac_finance"))], [(10, claude_cost("1"))], index()
    )
    assert facts[0].group_id == "finance"
    assert codes(issues) == [("warning", "group_mismatch")]


def test_actor_without_user_id_falls_back_to_email() -> None:
    usage = claude_usage(user_id=None)
    usage = usage.replace('"email": null', '"email": "RAVI@x.example"')
    facts, _ = build_facts([(1, usage)], [], index())
    assert facts[0].user_id == "user_ravi"
