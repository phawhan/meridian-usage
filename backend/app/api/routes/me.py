from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import Caller, CurrentPolicy, Db
from app.core.env_config import SCOPES
from app.repositories import directory
from app.services.authz import visible_groups

router = APIRouter(tags=["identity"])


class Me(BaseModel):
    user_id: str
    name: str
    email: str
    role: str
    group_ids: list[str]
    environment: str
    scopes: list[str]
    readable_groups: list[str]
    writable_groups: list[str]


@router.get("/me", response_model=Me)
def me(caller: Caller, policy: CurrentPolicy, conn: Db) -> Me:
    """Who the server thinks you are and what the policy lets you do. The admin page uses
    this to decide what to show; the server still checks every request on its own."""
    groups = [g.group_id for g in directory.list_groups(conn) if g.active]
    return Me(
        user_id=caller.user_id,
        name=caller.name,
        email=caller.email,
        role=caller.role,
        group_ids=caller.group_ids,
        environment=policy.environment,
        scopes=[s for s in SCOPES if caller.role in policy.roles_with(s)],
        readable_groups=visible_groups(caller, "read_usage", policy, groups),
        writable_groups=visible_groups(caller, "write_capability", policy, groups),
    )
