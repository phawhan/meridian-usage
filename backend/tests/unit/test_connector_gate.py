"""authorize_connector(): the usage-connector switch is checked on the caller's own groups."""

import pytest

from app.core.config import REPO_ROOT, Settings
from app.core.env_config import Policy, load_policy
from app.models.domain import User
from app.services.authz import authorize_connector


def lead(*groups: str) -> User:
    return User(
        user_id="u", email="u@x", name="U", role="team_lead", group_ids=list(groups), active=True
    )


@pytest.fixture(scope="module")
def prod() -> Policy:
    return load_policy(Settings(app_env="prod", env_dir=REPO_ROOT / "environments"))


def test_switch_on_for_own_group_allows(prod: Policy) -> None:
    assert authorize_connector(lead("finance"), {"finance": True}, prod) is None


def test_switch_off_refuses_without_a_scope(prod: Policy) -> None:
    denial = authorize_connector(lead("finance"), {"finance": False}, prod)
    assert denial is not None
    assert denial.required_scope is None
    assert denial.reason == (
        "the usage connector is switched off for your group (finance) in prod;"
        " a platform admin can switch it on"
    )


def test_unknown_switch_state_refuses(prod: Policy) -> None:
    assert authorize_connector(lead("finance"), {}, prod) is not None


def test_every_own_group_must_have_it_on(prod: Policy) -> None:
    denial = authorize_connector(lead("finance", "hr"), {"finance": True, "hr": False}, prod)
    assert denial is not None and "(hr)" in denial.reason


def test_caller_without_a_group_is_refused(prod: Policy) -> None:
    denial = authorize_connector(lead(), {"finance": True}, prod)
    assert denial is not None and "callers without a group" in denial.reason


def test_other_groups_switches_do_not_matter(prod: Policy) -> None:
    assert authorize_connector(lead("finance"), {"finance": True, "hr": False}, prod) is None
