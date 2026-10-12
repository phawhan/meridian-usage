"""Shape of a Google Cloud standard usage cost export row (BigQuery), as JSONL in data/gemini/.

Parse lines with json.loads(..., parse_float=Decimal) before validating: Pydantic turns a
JSON number into a float on the way to Decimal and loses digits.
"""

from decimal import Decimal

from app.models.sources.base import SourceModel


class Label(SourceModel):
    key: str
    value: str


class Described(SourceModel):
    id: str
    description: str


class Project(SourceModel):
    id: str
    number: str | None = None
    labels: list[Label] = []


class Usage(SourceModel):
    amount: Decimal  # token count for Gemini token SKUs
    unit: str


class Credit(SourceModel):
    name: str | None = None
    amount: Decimal  # negative


class Location(SourceModel):
    region: str | None = None


class Invoice(SourceModel):
    month: str  # YYYYMM


class GeminiBillingRow(SourceModel):
    service: Described
    sku: Described  # e.g. "Gemini 2.5 Flash Text Input Tokens - Predictions"
    usage_start_time: str  # 'YYYY-MM-DD HH:MM:SS UTC'
    usage_end_time: str
    project: Project
    labels: list[Label] = []  # resource labels: owner, agent, model
    location: Location | None = None
    export_time: str  # 'YYYY-MM-DD HH:MM:SS.fff UTC'
    cost: Decimal  # USD before credits (GCP semantics; credits are separate negatives)
    currency: str
    usage: Usage
    credits: list[Credit] = []
    invoice: Invoice
    cost_type: str  # regular | adjustment | tax | ...
    cost_at_list: Decimal | None = None

    def label(self, key: str) -> str | None:
        return next((item.value for item in self.labels if item.key == key), None)
