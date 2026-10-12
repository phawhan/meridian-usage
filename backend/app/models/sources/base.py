from pydantic import BaseModel, ConfigDict


class SourceModel(BaseModel):
    """Base for shapes of files we receive. Unknown fields are ignored so a richer export
    doesn't break ingestion; the fields the service relies on are required."""

    model_config = ConfigDict(extra="ignore", frozen=True)
