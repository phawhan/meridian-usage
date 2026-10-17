"""Repo files the connector reads at runtime: the tool contract and the rendered permissions
manifests. The wheel carries copies under app/_shipped/ (pyproject force-include), so a
connector installed with uvx finds them without a checkout; in the repo, the originals are used.
"""

from pathlib import Path

from app.core.config import REPO_ROOT

PACKAGED_DIR = Path(__file__).resolve().parents[1] / "_shipped"


def shipped(relative: str) -> Path:
    packaged = PACKAGED_DIR / relative
    return packaged if packaged.exists() else REPO_ROOT / relative
