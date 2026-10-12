from typing import Literal

from pydantic import BaseModel

Role = Literal["member", "team_lead", "platform_admin"]


class User(BaseModel):
    user_id: str
    email: str
    name: str
    role: Role
    group_ids: list[str]
    active: bool


class Group(BaseModel):
    group_id: str
    name: str
    team_lead_user_id: str
    claude_rbac_group_id: str
    gcp_project_id: str
    cost_centre: str
    active: bool
