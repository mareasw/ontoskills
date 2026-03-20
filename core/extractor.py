import re
import hashlib
from pathlib import Path


def generate_skill_id(directory_name: str) -> str:
    slug = directory_name.lower()
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug[:64]


def generate_qualified_skill_id(package_id: str, skill_id: str) -> str:
    """
    Build a Qualified ID from package and skill components.

    Format: {package_id}/{skill_id}
    Example: obra/superpowers/brainstorming
    """
    return f"{package_id}/{skill_id}"


def generate_sub_skill_id(package_id: str, parent_skill_id: str, filename: str) -> str:
    """
    Build a Qualified ID for a sub-skill.

    Format: {package_id}/{parent_skill_id}/{sub_skill_name}
    Example: obra/superpowers/brainstorming/planning

    Args:
        package_id: The package namespace (e.g., "obra/superpowers")
        parent_skill_id: The parent skill's local ID (e.g., "brainstorming")
        filename: The markdown filename (e.g., "planning.md")
    """
    # Strip .md extension and slugify
    sub_name = Path(filename).stem
    sub_slug = generate_skill_id(sub_name)

    return f"{package_id}/{parent_skill_id}/{sub_slug}"


def compute_skill_hash(skill_dir: Path) -> str:
    hasher = hashlib.sha256()
    files = sorted(
        f for f in skill_dir.rglob('*')
        if f.is_file() and not f.name.startswith('.')
    )
    for file_path in files:
        rel_path = file_path.relative_to(skill_dir)
        hasher.update(str(rel_path).encode('utf-8'))
        hasher.update(file_path.read_bytes())
    return hasher.hexdigest()
