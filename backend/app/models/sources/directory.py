"""Shapes of the identity provider snapshot files in data/directory/."""

from pydantic import field_validator

from app.models.domain import Role
from app.models.sources.base import SourceModel


class DirectoryUser(SourceModel):
    user_id: str
    email: str
    name: str
    role: Role
    group_ids: list[str]
    claude_seat: bool
    gcp_principal: str | None = None

    @field_validator("email")
    @classmethod
    def _lowercase(cls, value: str) -> str:
        # Gemini's 'owner' label is matched case-insensitively against this.
        return value.strip().lower()


class DirectoryGroup(SourceModel):
    group_id: str
    name: str
    team_lead_user_id: str
    claude_rbac_group_id: str
    gcp_project_id: str
    gcp_project_number: str
    cost_centre: str


class UsersFile(SourceModel):
    exported_at: str
    users: list[DirectoryUser]


class GroupsFile(SourceModel):
    exported_at: str
    groups: list[DirectoryGroup]
