"""Shapes of Claude Enterprise Analytics API exports in data/claude/.

GET /v1/organizations/analytics/user_usage_report and .../user_cost_report with
bucket_width=1d, group_by product and model (cost also by cost_type), pages concatenated.
"""

from decimal import Decimal

from app.models.sources.base import SourceModel


class ClaudeActor(SourceModel):
    type: str  # user_actor for seat holders; other actor types have no user_id
    user_id: str | None = None
    email: str | None = None
    name: str | None = None
    deleted: bool = False


class ClaudeBucket(SourceModel):
    actor: ClaudeActor
    starting_at: str  # RFC 3339 UTC, start of the daily bucket
    ending_at: str
    product: str  # chat | claude_code | cowork
    model: str
    rbac_group_id: str | None = None
    requests: int | None = None
    context_window: str | None = None
    inference_geo: str | None = None
    speed: str | None = None


class CacheCreation(SourceModel):
    ephemeral_5m_input_tokens: int = 0
    ephemeral_1h_input_tokens: int = 0


class ServerToolUse(SourceModel):
    web_search_requests: int = 0


class ClaudeUsageRecord(ClaudeBucket):
    uncached_input_tokens: int
    cache_read_input_tokens: int
    cache_creation: CacheCreation
    output_tokens: int
    total_tokens: int
    server_tool_use: ServerToolUse = ServerToolUse()


class ClaudeCostRecord(ClaudeBucket):
    cost_type: str  # tokens | web_search
    amount: Decimal  # cents, delivered as a decimal string: "88.900050" is $0.889
    list_amount: Decimal | None = None
    currency: str


class ClaudeUsageReport(SourceModel):
    data_refreshed_at: str
    data: list[ClaudeUsageRecord]


class ClaudeCostReport(SourceModel):
    data_refreshed_at: str
    data: list[ClaudeCostRecord]
