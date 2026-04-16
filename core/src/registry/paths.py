"""Path utilities for registry layout."""

from __future__ import annotations

from pathlib import Path

from compiler.config import (
    ONTOLOGY_ROOT,
    ONTOLOGY_SYSTEM_DIR,
    ONTOLOGY_AUTHOR_DIR,
    SKILLS_DIR,
    SKILLS_AUTHOR_DIR,
)


def ontology_root() -> Path:
    """Get the resolved ontology root directory."""
    return Path(ONTOLOGY_ROOT).resolve()


def skills_root(root: Path | None = None) -> Path:
    """Get the skills root directory."""
    if root is None:
        return Path(SKILLS_DIR).resolve()
    ontology_base = Path(root).resolve()
    return (ontology_base.parent / "skills").resolve()


def system_dir(root: Path | None = None) -> Path:
    """Get the system directory within the ontology root."""
    base = ontology_root() if root is None else Path(root).resolve()
    return base / Path(ONTOLOGY_SYSTEM_DIR).name


def skills_author_dir(root: Path | None = None) -> Path:
    """Get the skills author directory."""
    base = skills_root(root)
    return base / Path(SKILLS_AUTHOR_DIR).name


def ontology_author_dir(root: Path | None = None) -> Path:
    """Get the ontology author directory."""
    base = ontology_root() if root is None else Path(root).resolve()
    return base / Path(ONTOLOGY_AUTHOR_DIR).name


def enabled_index_path(root: Path | None = None) -> Path:
    """Get the path to the enabled skills index."""
    return system_dir(root) / "index.enabled.ttl"


def state_dir(root: Path | None = None) -> Path:
    """Get the state directory (sibling of ontology root).

    Matches the JS CLI layout: ~/.ontoskills/state/
    """
    base = ontology_root() if root is None else Path(root).resolve()
    return base.parent / "state"


def registry_lock_path(root: Path | None = None) -> Path:
    """Get the path to the registry lock file."""
    return state_dir(root) / "registry.lock.json"


def registry_sources_path(root: Path | None = None) -> Path:
    """Get the path to the registry sources configuration."""
    return state_dir(root) / "registry.sources.json"


def ensure_registry_layout(root: Path | None = None) -> Path:
    """Ensure required directories exist and return the ontology root."""
    base = ontology_root() if root is None else Path(root).resolve()
    base.mkdir(parents=True, exist_ok=True)
    system_dir(base).mkdir(parents=True, exist_ok=True)
    state_dir(base).mkdir(parents=True, exist_ok=True)
    return base
