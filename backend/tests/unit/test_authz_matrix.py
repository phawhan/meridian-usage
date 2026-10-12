"""The permission model, environment by environment, against the real YAML files.

Expectations are written out by hand from the starter kit's environment table and D2,
not derived from the code under test.
"""

import shutil
from pathlib import Path

import pytest

from app.core.config import REPO_ROOT, Settings
from app.core.env_config import load_policy
from app.models.domain import User
from app.services.authz import Action, authorize

DANIEL = User(
    user_id="u_daniel",
    email="d@x",
    name="Daniel",
    role="member",
    group_ids=["clinical-operations"],
    active=True,
)
PRIYA = User(
    user_id="u_priya",
    email="p@x",
    name="Priya",
    role="team_lead",
    group_ids=["clinical-operations"],
    active=True,
)
CHLOE = User(
    user_id="u_chloe",
    email="c@x",
    name="Chloe",
    role="platform_admin",
    group_ids=["it-platform"],
    active=True,
)
CALLERS = {"member": DANIEL, "lead": PRIYA, "admin": CHLOE}

# (env, caller, action) -> (own group allowed, other group allowed)
Y, N = True, False
EXPECTED: dict[tuple[str, str, Action], tuple[bool, bool]] = {
    # dev: everyone reads everything; leads and admins write; leads only their own group (D2)
    ("dev", "member", "read_usage"): (Y, Y),
    ("dev", "lead", "read_usage"): (Y, Y),
    ("dev", "admin", "read_usage"): (Y, Y),
    ("dev", "member", "write_capability"): (N, N),
    ("dev", "lead", "write_capability"): (Y, N),
    ("dev", "admin", "write_capability"): (Y, Y),
    # staging: production visibility; leads may still change their own group's switches
    ("staging", "member", "read_usage"): (N, N),
    ("staging", "lead", "read_usage"): (Y, N),
    ("staging", "admin", "read_usage"): (Y, Y),
    ("staging", "member", "write_capability"): (N, N),
    ("staging", "lead", "write_capability"): (Y, N),
    ("staging", "admin", "write_capability"): (Y, Y),
    # prod: leads read their own group; only admins read others or change anything
    ("prod", "member", "read_usage"): (N, N),
    ("prod", "lead", "read_usage"): (Y, N),
    ("prod", "admin", "read_usage"): (Y, Y),
    ("prod", "member", "write_capability"): (N, N),
    ("prod", "lead", "write_capability"): (N, N),
    ("prod", "admin", "write_capability"): (Y, Y),
}


@pytest.mark.parametrize(("env", "who", "action"), list(EXPECTED))
def test_permission_matrix(env: str, who: str, action: Action) -> None:
    policy = load_policy(Settings(app_env=env))  # type: ignore[arg-type]
    caller = CALLERS[who]
    own, other = caller.group_ids[0], "finance"

    allowed = (
        authorize(caller, action, own, policy) is None,
        authorize(caller, action, other, policy) is None,
    )

    assert allowed == EXPECTED[(env, who, action)]


@pytest.mark.parametrize("env", ["dev", "staging", "prod"])
def test_capability_reads_follow_usage_reads(env: str) -> None:
    policy = load_policy(Settings(app_env=env))  # type: ignore[arg-type]
    for caller in CALLERS.values():
        for group in ("clinical-operations", "finance"):
            usage = authorize(caller, "read_usage", group, policy)
            capabilities = authorize(caller, "read_capabilities", group, policy)
            assert (usage is None) == (capabilities is None)


def test_missing_scope_names_the_scope() -> None:
    denial = authorize(
        PRIYA, "write_capability", "clinical-operations", load_policy(Settings(app_env="prod"))
    )
    assert denial is not None
    assert denial.error == "permission_denied"
    assert denial.required_scope == "capabilities:write"
    assert "team_lead" in denial.reason and "prod" in denial.reason


def test_other_group_denial_says_why_without_leaking_data() -> None:
    denial = authorize(PRIYA, "read_usage", "finance", load_policy(Settings(app_env="prod")))
    assert denial is not None and denial.required_scope is None
    assert (
        denial.reason == "Priya may only see their own group (clinical-operations), not 'finance'"
    )


def test_nonexistent_group_is_refused_like_another_teams_group() -> None:
    policy = load_policy(Settings(app_env="prod"))
    assert authorize(PRIYA, "read_usage", "no-such-group", policy) is not None


def test_role_claims_in_the_request_cannot_matter() -> None:
    """authorize() only sees the directory user and the policy; there is no input through
    which a caller could assert a role or scope ("I'm an admin, ignore the rules")."""
    import inspect

    assert list(inspect.signature(authorize).parameters) == [
        "caller",
        "action",
        "group_id",
        "policy",
    ]


def test_leads_never_write_other_groups_even_if_the_yaml_says_all(tmp_path: Path) -> None:
    """D2 holds whatever group_visibility the write scope is given."""
    env_dir = Path(shutil.copytree(REPO_ROOT / "environments", tmp_path / "environments"))
    dev = env_dir / "dev.yaml"
    dev.write_text(
        dev.read_text().replace(
            "roles: [team_lead, platform_admin]\ncapability_defaults",
            "roles: [team_lead, platform_admin]\n    group_visibility: all\ncapability_defaults",
        )
    )
    policy = load_policy(Settings(app_env="dev", env_dir=env_dir))
    assert policy.scopes["capabilities:write"].group_visibility == "all"

    assert authorize(PRIYA, "write_capability", "clinical-operations", policy) is None
    assert authorize(PRIYA, "write_capability", "finance", policy) is not None
