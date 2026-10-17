"""environments/<env>.yaml -> Policy.

The three YAML files share one contract (EnvConfig) and differ only in values, so code never
asks "am I in prod?"; it asks the Policy. Loaded once at startup; an invalid file stops the
server. Scopes are always taken from the file (policy); capability_defaults only seed
switches that don't exist yet (baseline) (D5).
"""

import hashlib
from dataclasses import dataclass
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from app.core.config import Environment, Settings
from app.models.domain import CAPABILITIES, Capability, Role

Scope = Literal["usage:read", "capabilities:write"]
SCOPES: tuple[Scope, ...] = ("usage:read", "capabilities:write")
Visibility = Literal["all", "own_group"]


class PolicyError(RuntimeError):
    """The environment config is missing, malformed or inconsistent."""


class _Strict(BaseModel):
    # A typo such as 'group_visiblity' must fail, not be silently ignored.
    model_config = ConfigDict(extra="forbid", frozen=True)


class ScopeRule(_Strict):
    roles: list[Role]
    # own_group: callers see their own group; platform admins see every group.
    # Missing means own_group: fail closed (D10).
    group_visibility: Visibility = "own_group"


class EnabledFor(_Strict):
    enabled_for: list[str]


class HostConfig(_Strict):
    server_name: str  # the MCP server's name in host registration config
    api_url: str  # where this environment's usage service listens; the connector calls it


class EnvConfig(_Strict):
    environment: Environment
    scopes: dict[Scope, ScopeRule]
    capability_defaults: dict[Capability, Literal["enabled", "disabled"] | EnabledFor]
    host: HostConfig

    @model_validator(mode="after")
    def _complete(self) -> "EnvConfig":
        missing: list[str] = [s for s in SCOPES if s not in self.scopes]
        missing += [c for c in CAPABILITIES if c not in self.capability_defaults]
        if missing:
            raise ValueError(f"must define every scope and capability; missing {missing}")
        return self


@dataclass(frozen=True)
class Policy:
    environment: Environment
    scopes: dict[Scope, ScopeRule]
    defaults: dict[Capability, Literal["enabled", "disabled"] | EnabledFor]
    server_name: str
    api_url: str
    path: str  # e.g. environments/prod.yaml
    sha256: str

    def roles_with(self, scope: Scope) -> list[Role]:
        return self.scopes[scope].roles

    def default_for(self, group_id: str, capability: Capability) -> bool:
        value = self.defaults[capability]
        if isinstance(value, EnabledFor):
            return group_id in value.enabled_for
        return value == "enabled"

    def groups_named(self) -> set[str]:
        """Every group the baseline names explicitly, for checking against the directory."""
        return {
            g for v in self.defaults.values() if isinstance(v, EnabledFor) for g in v.enabled_for
        }


def load_policy(settings: Settings) -> Policy:
    path = settings.env_config_file
    if not path.is_file():
        raise PolicyError(f"environment config not found: {path}")
    content = path.read_bytes()
    try:
        config = EnvConfig.model_validate(yaml.safe_load(content))
    except (yaml.YAMLError, ValidationError) as exc:
        raise PolicyError(f"{path.name} is invalid: {exc}") from exc
    if config.environment != settings.app_env:
        raise PolicyError(
            f"{path.name} declares environment '{config.environment}', started as"
            f" '{settings.app_env}'"
        )
    return Policy(
        environment=config.environment,
        scopes=config.scopes,
        defaults=config.capability_defaults,
        server_name=config.host.server_name,
        api_url=config.host.api_url,
        path=path.relative_to(settings.env_dir.parent).as_posix(),
        sha256=hashlib.sha256(content).hexdigest(),
    )
