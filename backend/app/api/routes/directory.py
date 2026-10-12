from fastapi import APIRouter

from app.api.deps import Db
from app.models.api import DirectoryEntry
from app.repositories import directory

router = APIRouter(prefix="/directory", tags=["identity"])


@router.get("/users", response_model=list[DirectoryEntry])
def users(conn: Db) -> list[DirectoryEntry]:
    """Active users, for the admin page's persona switcher.

    Exists only because identity is simulated: it lets anyone list names and roles, which a
    real deployment (identity from SSO) would not expose. See README "In the real enterprise
    version"."""
    return [
        DirectoryEntry(user_id=u.user_id, name=u.name, role=u.role, group_ids=u.group_ids)
        for u in directory.list_users(conn)
        if u.active
    ]
