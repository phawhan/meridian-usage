"""Request dependencies: database connection, policy, and the simulated caller identity.

Identity is simulated (the brief allows it): the caller names themselves in the X-User-Id
header and is looked up in the directory mirror. What they may do is never taken from the
request; it comes from their directory role and the environment policy (services.authz).
"""

import sqlite3
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, Request

from app.core.config import Settings
from app.core.env_config import Policy
from app.db.session import connect
from app.models.domain import User
from app.repositories import access_log, directory


class Unidentified(Exception):
    """No usable identity on the request (401); no policy question was asked."""


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_policy(request: Request) -> Policy:
    policy: Policy = request.app.state.policy
    return policy


def get_policy_file_id(request: Request) -> int:
    file_id: int = request.app.state.policy_file_id
    return file_id


def get_db(settings: Annotated[Settings, Depends(get_settings)]) -> Iterator[sqlite3.Connection]:
    conn = connect(settings.database_file)
    try:
        yield conn
    finally:
        conn.close()


Db = Annotated[sqlite3.Connection, Depends(get_db)]
CurrentPolicy = Annotated[Policy, Depends(get_policy)]
PolicyFileId = Annotated[int, Depends(get_policy_file_id)]


def get_caller(
    conn: Db,
    x_user_id: Annotated[
        str | None, Header(description="Simulated identity: a directory user_id")
    ] = None,
) -> User:
    user = directory.get_user(conn, x_user_id) if x_user_id else None
    if user is not None and user.active:
        return user
    reason = (
        "send the X-User-Id header with a directory user_id"
        if not x_user_id
        else f"'{x_user_id}' is not an active user in the directory"
    )
    access_log.record(
        conn,
        channel="api",
        caller=x_user_id,
        action="identify",
        target_group=None,
        required_scope=None,
        reason=reason,
    )
    raise Unidentified(reason)


Caller = Annotated[User, Depends(get_caller)]
