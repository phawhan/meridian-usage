from typing import Literal

from pydantic import BaseModel


class Denial(BaseModel):
    """The refusal shape from contracts/tools.schema.json, used by the API and the connector."""

    error: Literal["permission_denied"] = "permission_denied"
    reason: str
    required_scope: str | None = None


class Unidentified(BaseModel):
    """401 body: the caller could not be identified, so no policy question was asked."""

    error: Literal["unauthenticated"] = "unauthenticated"
    reason: str
