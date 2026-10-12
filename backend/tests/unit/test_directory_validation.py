from typing import Any

import pytest

from app.core.config import REPO_ROOT
from app.models.sources.directory import GroupsFile, UsersFile
from app.services.directory_sync import validate_snapshot

DIRECTORY = REPO_ROOT / "data" / "directory"
PRIYA = "user_E7691888F28227066DD2FB86"  # team lead of clinical-operations
DANIEL = "user_699C48763F6FA2958D2CDB5D"  # member of clinical-operations


@pytest.fixture
def raw() -> dict[str, Any]:
    """The real snapshot as plain dicts, so each test can break one thing."""
    users = UsersFile.model_validate_json((DIRECTORY / "users.json").read_bytes())
    groups = GroupsFile.model_validate_json((DIRECTORY / "groups.json").read_bytes())
    return {"users": users.model_dump(), "groups": groups.model_dump()}


def errors_for(raw: dict[str, Any]) -> list[str]:
    return validate_snapshot(
        UsersFile.model_validate(raw["users"]), GroupsFile.model_validate(raw["groups"])
    )


def user(raw: dict[str, Any], user_id: str) -> dict[str, Any]:
    return next(u for u in raw["users"]["users"] if u["user_id"] == user_id)


def test_starter_snapshot_is_valid(raw: dict[str, Any]) -> None:
    assert errors_for(raw) == []


def test_emails_are_lowercased_on_read(raw: dict[str, Any]) -> None:
    user(raw, DANIEL)["email"] = "  Daniel.Okafor@MeridianLS.example "
    assert (
        UsersFile.model_validate(raw["users"]).users[1].email == "daniel.okafor@meridianls.example"
    )


def test_duplicate_email_is_caught_case_insensitively(raw: dict[str, Any]) -> None:
    user(raw, DANIEL)["email"] = "PRIYA.NAIR@meridianls.example"
    assert "duplicate email 'priya.nair@meridianls.example'" in errors_for(raw)


def test_unknown_group_reference(raw: dict[str, Any]) -> None:
    user(raw, DANIEL)["group_ids"] = ["legal"]
    assert f"user {DANIEL} references unknown group 'legal'" in errors_for(raw)


def test_user_without_group(raw: dict[str, Any]) -> None:
    user(raw, DANIEL)["group_ids"] = []
    assert f"user {DANIEL} belongs to no group" in errors_for(raw)


def test_lead_must_be_member_of_their_group(raw: dict[str, Any]) -> None:
    user(raw, PRIYA)["group_ids"] = ["finance"]
    assert f"group clinical-operations: lead {PRIYA} is not a member" in errors_for(raw)


def test_lead_must_have_team_lead_role(raw: dict[str, Any]) -> None:
    user(raw, PRIYA)["role"] = "member"
    assert f"group clinical-operations: lead {PRIYA} has role member" in errors_for(raw)


def test_lead_must_exist(raw: dict[str, Any]) -> None:
    raw["users"]["users"] = [u for u in raw["users"]["users"] if u["user_id"] != PRIYA]
    assert f"group clinical-operations: lead {PRIYA} is not a user" in errors_for(raw)


def test_platform_identifiers_must_be_unique(raw: dict[str, Any]) -> None:
    finance, hr = raw["groups"]["groups"][2], raw["groups"]["groups"][3]
    hr["claude_rbac_group_id"] = finance["claude_rbac_group_id"]
    hr["gcp_project_id"] = finance["gcp_project_id"]
    problems = errors_for(raw)
    assert f"duplicate claude_rbac_group_id {finance['claude_rbac_group_id']!r}" in problems
    assert f"duplicate gcp_project_id {finance['gcp_project_id']!r}" in problems


def test_empty_snapshot_is_refused_rather_than_deactivating_everyone(raw: dict[str, Any]) -> None:
    raw["users"]["users"] = []
    assert "users.json lists no users; refusing to deactivate everyone" in errors_for(raw)


def test_all_problems_are_reported_together(raw: dict[str, Any]) -> None:
    user(raw, DANIEL)["group_ids"] = []
    user(raw, PRIYA)["role"] = "member"
    assert len(errors_for(raw)) == 2
