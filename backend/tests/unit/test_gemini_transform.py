from app.services.ingestion.gemini import build_facts, parse_sku
from tests.factories import gemini_row, index


def test_sku_description_gives_model_and_direction() -> None:
    sku = parse_sku("Gemini 2.5 Flash Text Input Tokens - Predictions")
    assert sku is not None and (sku.model, sku.direction) == ("gemini-2.5-flash", "Input")
    pro = parse_sku("Gemini 2.5 Pro Text Output Tokens - Predictions")
    assert pro is not None and (pro.model, pro.direction) == ("gemini-2.5-pro", "Output")
    assert parse_sku("Vertex AI Search Queries") is None


def test_input_and_output_sku_rows_pivot_into_one_fact() -> None:
    facts, issues = build_facts(
        [(1, gemini_row("Input", 358546, "0.107564")), (2, gemini_row("Output", 1200, "0.003"))],
        index(),
    )

    assert issues == []
    [fact] = facts
    assert (fact.user_id, fact.group_id, fact.model, fact.product) == (
        "user_priya",
        "clinical-operations",
        "gemini-2.5-flash",
        "site-monitor",
    )
    assert (fact.input_tokens, fact.output_tokens, fact.total_tokens) == (358546, 1200, 359746)
    assert fact.requests is None
    assert fact.cost_nanousd == 110_564_000
    assert fact.raw_refs == {"raw_gemini_billing": [1, 2]}
    assert fact.metadata["region"] == "us-central1"


def test_cost_keeps_full_decimal_precision() -> None:
    # 17 significant digits: more than a float holds. Via float this becomes ...790.
    facts, _ = build_facts([(1, gemini_row("Input", 1, "12345678.123456789"))], index())
    assert facts[0].cost_nanousd == 12_345_678_123_456_789


def test_credits_are_netted_off_cost() -> None:
    facts, _ = build_facts([(1, gemini_row("Input", 10, "1.00", credits=["-0.25"]))], index())
    assert facts[0].cost_nanousd == 750_000_000
    assert facts[0].metadata["credits_usd"] == "-0.25"


def test_owner_label_matches_case_insensitively() -> None:
    facts, _ = build_facts([(1, gemini_row("Input", 10, "1", owner="Priya@X.example"))], index())
    assert facts[0].user_id == "user_priya"


def test_missing_owner_and_unknown_project_are_quarantined() -> None:
    facts, issues = build_facts(
        [(1, gemini_row("Input", 10, "1", owner=None, project="proj-unknown"))], index()
    )
    assert facts == []
    assert {i.code for i in issues} == {"unknown_user", "unknown_group"}
    assert all(i.severity == "error" for i in issues)


def test_non_token_sku_is_quarantined() -> None:
    facts, issues = build_facts(
        [(1, gemini_row("Input", 10, "1", sku="Vertex AI Search Queries"))], index()
    )
    assert facts == []
    assert [(i.code, i.raw_ids) for i in issues] == [("unknown_sku", (1,))]
