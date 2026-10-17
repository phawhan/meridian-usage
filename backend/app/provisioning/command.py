"""`meridian provision [--check]`: render all three environments, validate, then write them
(or, with --check, compare them with what is committed and fail on any difference)."""

from pathlib import Path

from app.core.config import REPO_ROOT
from app.provisioning.render import Rendering, render_all
from app.provisioning.validate import validate

GENERATED_DIRS = ("deploy",)  # everything under these is rendered; nothing else may live there


def _on_disk(root: Path) -> set[str]:
    return {
        p.relative_to(root).as_posix()
        for d in GENERATED_DIRS
        for p in (root / d).rglob("*")
        if p.is_file()
    }


def differences(rendering: Rendering, root: Path) -> list[str]:
    diffs = []
    for path, content in sorted(rendering.files.items()):
        target = root / path
        if not target.is_file():
            diffs.append(f"missing: {path}")
        elif target.read_text() != content:
            diffs.append(f"differs: {path}")
    diffs += [
        f"not rendered (hand-made?): {p}" for p in sorted(_on_disk(root) - set(rendering.files))
    ]
    return diffs


def provision(check: bool, root: Path = REPO_ROOT) -> int:
    rendering = render_all()
    problems = validate(rendering.files, rendering.policies, rendering.groups, rendering.version)
    if problems:
        print("provision: invalid configuration, nothing written:")
        print("\n".join(f"  {p}" for p in problems))
        return 1
    envs = ", ".join(rendering.policies)
    if check:
        diffs = differences(rendering, root)
        if diffs:
            print(
                "provision --check: committed config differs from what the inputs render;"
                " run `make provision`:"
            )
            print("\n".join(f"  {d}" for d in diffs))
            return 1
        print(f"provision --check: {len(rendering.files)} files valid and up to date ({envs})")
        return 0
    for stale in _on_disk(root) - set(rendering.files):
        (root / stale).unlink()
    for path, content in rendering.files.items():
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(content)
    print(
        f"provision: rendered and validated {len(rendering.files)} files"
        f" ({envs}, v{rendering.version})"
    )
    return 0
