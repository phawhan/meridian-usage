"""The permissions manifest: one JSON file per environment, rendered from environments/<env>.yaml,
the directory and the tool contract. It is what the connector enforces locally, and it is
written to be read by a platform owner: which roles may call which tool, and which groups
start with which capability.
"""

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.config import Environment
from app.core.contract import TOOL_NAMES, ToolName, tool_scope
from app.core.env_config import EnabledFor, Policy, Scope, ScopeRule
from app.models.domain import CAPABILITIES, Capability, Role

MANIFEST_VERSION: Literal[1] = 1


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceRef(_Strict):
    path: str  # environments/<env>.yaml
    sha256: str  # must match the running service's policy (GET /healthz)


class ToolGrant(_Strict):
    scope: Scope
    roles: list[Role]  # roles holding the scope in this environment


class PermissionsManifest(_Strict):
    manifest_version: Literal[1]
    environment: Environment
    server_name: str
    api_url: str
    source: SourceRef
    scopes: dict[Scope, ScopeRule]
    tools: dict[ToolName, ToolGrant]
    capability_defaults: dict[Capability, Literal["enabled", "disabled"] | EnabledFor]
    baseline: dict[str, dict[Capability, bool]]  # group -> capability -> starts enabled

    def policy(self) -> Policy:
        return Policy(
            environment=self.environment,
            scopes=self.scopes,
            defaults=self.capability_defaults,
            server_name=self.server_name,
            api_url=self.api_url,
            path=self.source.path,
            sha256=self.source.sha256,
        )


def build_manifest(policy: Policy, group_ids: list[str]) -> PermissionsManifest:
    return PermissionsManifest(
        manifest_version=MANIFEST_VERSION,
        environment=policy.environment,
        server_name=policy.server_name,
        api_url=policy.api_url,
        source=SourceRef(path=policy.path, sha256=policy.sha256),
        scopes=policy.scopes,
        tools={
            t: ToolGrant(scope=tool_scope(t), roles=policy.roles_with(tool_scope(t)))
            for t in TOOL_NAMES
        },
        capability_defaults=policy.defaults,
        baseline={
            g: {c: policy.default_for(g, c) for c in CAPABILITIES} for g in sorted(group_ids)
        },
    )


def dump_manifest(manifest: PermissionsManifest) -> str:
    """Deterministic text: same inputs, byte-identical file (CI diffs it)."""
    return json.dumps(manifest.model_dump(mode="json"), indent=2) + "\n"


def load_manifest(path: Path) -> PermissionsManifest:
    return PermissionsManifest.model_validate_json(path.read_text())
