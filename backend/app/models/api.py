"""API response shapes. Where the MCP tool contract (contracts/tools.schema.json) defines an
output, these match it field for field, so the Part B connector can pass them through."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from app.models.domain import Capability

Platform = Literal["claude", "gemini"]
Dimension = Literal["platform", "group", "week", "month", "model", "product"]


class PeriodOut(BaseModel):
    label: str
    start: date
    end_exclusive: date
    complete: bool  # False when the data doesn't cover the whole period


class PlatformTotals(BaseModel):
    platform: Platform
    requests: int | None  # Gemini billing has no request count
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float


class Totals(BaseModel):
    total_tokens: int
    cost_usd: float


class UsageSummary(BaseModel):
    group: str
    period: PeriodOut
    platforms: list[PlatformTotals]
    totals: Totals


class BreakdownRow(BaseModel):
    platform: Platform | None = None
    group: str | None = None
    week: str | None = None
    month: str | None = None
    model: str | None = None
    product: str | None = None
    requests: int | None
    input_tokens: int
    output_tokens: int
    total_tokens: int
    cost_usd: float


class Breakdown(BaseModel):
    period: PeriodOut
    groups: list[str]  # the groups included: those asked for, or every group the caller may see
    by: list[Dimension]
    rows: list[BreakdownRow]
    totals: Totals


class TopUser(BaseModel):
    user_id: str
    name: str
    email: str
    group: str
    total_tokens: int
    cost_usd: float


class CapabilityStatus(BaseModel):
    group: str
    capability: Capability
    enabled: bool
    baseline: bool  # the environment's default for this group
    drift: bool  # changed away from the baseline
    updated_at: str | None
    updated_by: str | None


class CapabilityChange(BaseModel):
    enabled: bool


class AuditEntry(BaseModel):
    group: str
    capability: str
    action: Literal["seed", "set", "reset"]
    old_enabled: bool | None
    new_enabled: bool
    policy_file_id: int
    at: str
    by: str


class DirectoryEntry(BaseModel):
    user_id: str
    name: str
    role: str
    group_ids: list[str]
