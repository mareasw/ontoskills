# Registry Output Structure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix output directory structure to mirror input exactly, add path-based package ID inference, generate `system/index.json` registry with per-skill metadata, and migrate `generated_by` from TTL to JSON.

**Architecture:** Replace `resolve_package_id()` config-file lookup with path-based inference from the directory structure. Add `DEFAULT_SKILLS_AUTHOR` env var fallback. Generate `system/index.json` with merge/upsert logic at end of compilation. Remove `oc:generatedBy` from TTL serialization.

**Tech Stack:** Python, rdflib, Pydantic, JSON, Click CLI

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `core/src/config.py` | Modify | Add `DEFAULT_SKILLS_AUTHOR` constant from env |
| `.env` | Modify | Add `DEFAULT_SKILLS_AUTHOR=mareasw` |
| `core/src/extractor.py` | Modify | Rewrite `resolve_package_id()` for path-based inference |
| `core/src/cli/compile.py` | Modify | Track per-skill metadata; generate index.json; fix package_id usage |
| `core/src/serialization.py` | Modify | Remove `oc:generatedBy` triple |
| `core/src/storage.py` | Modify | Add `generate_registry_json()` function |
| `core/tests/test_config.py` | Modify | Add test for `DEFAULT_SKILLS_AUTHOR` |
| `core/tests/test_storage.py` | Modify | Add test for `generate_registry_json()` |

---

### Task 1: Add `DEFAULT_SKILLS_AUTHOR` to config

**Files:**
- Modify: `core/src/config.py` (after line ~27, near other env vars)
- Modify: `.env`
- Modify: `core/tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to `core/tests/test_config.py`:

```python
def test_default_skills_author():
    """Verify DEFAULT_SKILLS_AUTHOR is None when env var not set."""
    import sys
    for mod in list(sys.modules.keys()):
        if mod.startswith('config') or mod.startswith('compiler'):
            del sys.modules[mod]

    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop('DEFAULT_SKILLS_AUTHOR', None)
        with patch('compiler.env.load_local_env'):
            from compiler import config
        assert config.DEFAULT_SKILLS_AUTHOR is None


def test_custom_skills_author():
    """Verify custom DEFAULT_SKILLS_AUTHOR from environment variable."""
    with patch.dict(os.environ, {'DEFAULT_SKILLS_AUTHOR': 'mareasw'}):
        import importlib
        from compiler import config
        importlib.reload(config)
        assert config.DEFAULT_SKILLS_AUTHOR == 'mareasw'
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest core/tests/test_config.py::test_default_skills_author -v`
Expected: FAIL (AttributeError: module has no attribute 'DEFAULT_SKILLS_AUTHOR')

- [ ] **Step 3: Implement config constant**

In `core/src/config.py`, add after the other env-var reads (around line 27, after `SECURITY_MODEL`):

```python
DEFAULT_SKILLS_AUTHOR = os.environ.get('DEFAULT_SKILLS_AUTHOR')
```

- [ ] **Step 4: Add to `.env`**

Add line to `.env`:

```
DEFAULT_SKILLS_AUTHOR=mareasw
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest core/tests/test_config.py::test_default_skills_author core/tests/test_config.py::test_custom_skills_author -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add core/src/config.py core/tests/test_config.py .env
git commit -m "feat(config): add DEFAULT_SKILLS_AUTHOR env var for package ID fallback"
```

---

### Task 2: Rewrite `resolve_package_id()` for path-based inference

**Files:**
- Modify: `core/src/extractor.py` — replace `resolve_package_id()` function (lines 92-137)

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_package_id_inference.py`:

```python
"""Tests for path-based package ID inference."""
import pytest
from pathlib import Path
from unittest.mock import patch


def test_resolve_package_id_from_path():
    """Package ID derived from directory structure between input and skill dir."""
    from compiler.extractor import resolve_package_id

    input_path = Path("/tmp/skills/obra")
    skill_dir = Path("/tmp/skills/obra/superpowers/brainstorming")

    result = resolve_package_id(skill_dir, input_path)
    assert result == "obra/superpowers"


def test_resolve_package_id_vendor_skill():
    """Vendor/skill structure → package_id = vendor."""
    from compiler.extractor import resolve_package_id

    input_path = Path("/tmp/skills/coinbase")
    skill_dir = Path("/tmp/skills/coinbase/agentic-wallet-skills/trade")

    result = resolve_package_id(skill_dir, input_path)
    assert result == "coinbase/agentic-wallet-skills"


def test_resolve_package_id_deep_nesting():
    """Deep nesting includes all intermediate levels."""
    from compiler.extractor import resolve_package_id

    input_path = Path("/tmp/skills/remotion-dev")
    skill_dir = Path("/tmp/skills/remotion-dev/skills/remotion-best-practices")

    result = resolve_package_id(skill_dir, input_path)
    assert result == "remotion-dev/skills"


def test_resolve_package_id_no_vendor():
    """Skill at root of input → uses DEFAULT_SKILLS_AUTHOR."""
    from compiler.extractor import resolve_package_id

    input_path = Path("/tmp/skills/my-skill")
    skill_dir = Path("/tmp/skills/my-skill")

    with patch.dict('os.environ', {'DEFAULT_SKILLS_AUTHOR': 'mareasw'}):
        result = resolve_package_id(skill_dir, input_path)
        assert result == "mareasw"


def test_resolve_package_id_no_vendor_no_env():
    """Skill at root with no DEFAULT_SKILLS_AUTHOR → falls back to 'local'."""
    from compiler.extractor import resolve_package_id

    input_path = Path("/tmp/skills/my-skill")
    skill_dir = Path("/tmp/skills/my-skill")

    with patch.dict('os.environ', {}, clear=False):
        import os
        os.environ.pop('DEFAULT_SKILLS_AUTHOR', None)
        result = resolve_package_id(skill_dir, input_path)
        assert result == "local"


def test_resolve_package_id_normalization():
    """Package ID segments are normalized (lowercase, dashes)."""
    from compiler.extractor import resolve_package_id

    input_path = Path("/tmp/skills")
    skill_dir = Path("/tmp/skills/My_Vendor/My_Repo/skill-name")

    result = resolve_package_id(skill_dir, input_path)
    assert result == "my-vendor/my-repo"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest core/tests/test_package_id_inference.py -v`
Expected: FAIL (function signature mismatch — current `resolve_package_id` takes only `skill_dir`)

- [ ] **Step 3: Rewrite `resolve_package_id()` in `core/src/extractor.py`**

Replace the entire `resolve_package_id()` function (lines 92-137) with:

```python
def resolve_package_id(skill_dir: Path, input_path: Path | None = None) -> str:
    """Resolve package ID from directory structure.

    The package_id is the path between input_path and skill_dir,
    representing vendor/repo. Falls back to DEFAULT_SKILLS_AUTHOR
    env var if skill is at root of input, or 'local' if unset.

    Args:
        skill_dir: Path to the skill directory
        input_path: Root input directory (e.g., .agents/skills/obra/)

    Returns:
        Package ID string (e.g., "obra/superpowers", "coinbase/agentic-wallet-skills")
    """
    if input_path is None:
        # Legacy behavior: search for package.json/toml
        return _resolve_package_id_from_manifest(skill_dir)

    try:
        rel = skill_dir.resolve().relative_to(input_path.resolve())
    except ValueError:
        # skill_dir is not under input_path
        return _resolve_package_id_from_manifest(skill_dir)

    # All segments except the last (which is the skill directory)
    parts = rel.parts[:-1] if rel.parts and rel.parts[-1] != '.' else ()

    if not parts:
        # Skill is at root of input — use DEFAULT_SKILLS_AUTHOR
        import os
        author = os.environ.get('DEFAULT_SKILLS_AUTHOR')
        if author:
            return author
        logger.warning(
            "Skill at root of input (%s) with no DEFAULT_SKILLS_AUTHOR set. "
            "Falling back to 'local'. Set DEFAULT_SKILLS_AUTHOR env var.",
            skill_dir,
        )
        return "local"

    # Normalize each segment
    normalized = [normalize_package_id_segment(p) for p in parts]
    return "/".join(normalized)


def normalize_package_id_segment(segment: str) -> str:
    """Normalize a single path segment for use in package IDs."""
    slug = segment.lower()
    slug = re.sub(r'[\s_]+', '-', slug)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    slug = re.sub(r'-+', '-', slug)
    slug = slug.strip('-')
    return slug


def _resolve_package_id_from_manifest(skill_dir: Path) -> str:
    """Legacy fallback: search for package.json or ontoskills.toml."""
    candidate = skill_dir.resolve()
    for _ in range(8):
        if candidate == candidate.parent:
            break
        pkg_json = candidate / "package.json"
        if pkg_json.exists():
            try:
                data = json.loads(pkg_json.read_text(encoding="utf-8"))
                if "name" in data:
                    return normalize_package_id(data["name"])
            except (json.JSONDecodeError, OSError):
                pass
        toml_file = candidate / "ontoskills.toml"
        if toml_file.exists():
            try:
                import tomllib
                with open(toml_file, "rb") as f:
                    data = tomllib.load(f)
                if "name" in data:
                    return normalize_package_id(data["name"])
            except Exception:
                pass
        candidate = candidate.parent
    return "local"
```

Also add `import logging` and `logger = logging.getLogger(__name__)` at the top of extractor.py if not present.

- [ ] **Step 4: Update callers of `resolve_package_id()`**

In `core/src/cli/compile.py`, there are two call sites that need the `input_path` parameter:

**Call site 1** — parent map building (~line 310):
```python
package_id = resolve_package_id(skill_dir)
```
Change to:
```python
package_id = resolve_package_id(skill_dir, input_path)
```

**Call site 2** — fallback in main skill loop (~line 339):
```python
package_id = resolve_package_id(skill_dir)
```
Change to:
```python
package_id = resolve_package_id(skill_dir, input_path)
```

**Call site 3** — sub-skill section: `resolve_package_id` is not called directly (package_id comes from `resolved_parent_map`), so no change needed.

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest core/tests/test_package_id_inference.py -v`
Expected: ALL PASS

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest core/tests/ -q --tb=short`
Expected: No new failures

- [ ] **Step 7: Commit**

```bash
git add core/src/extractor.py core/tests/test_package_id_inference.py core/src/cli/compile.py
git commit -m "refactor(extractor): path-based package ID inference with DEFAULT_SKILLS_AUTHOR fallback"
```

---

### Task 3: Add `generate_registry_json()` to storage

**Files:**
- Modify: `core/src/storage.py` — add new function after `generate_index_manifest()`
- Modify: `core/tests/test_storage.py` — add tests

- [ ] **Step 1: Write the failing test**

Add to `core/tests/test_storage.py`:

```python
def test_generate_registry_json_creates_file(tmp_path):
    """generate_registry_json creates index.json with correct structure."""
    from compiler.storage import generate_registry_json

    # Create a dummy TTL file
    skill_dir = tmp_path / "packages" / "obra" / "superpowers" / "brainstorming"
    skill_dir.mkdir(parents=True)
    (skill_dir / "ontoskill.ttl").write_text("@prefix oc: <https://ontoskills.sh/ontology#> .")

    output_root = tmp_path
    index_path = tmp_path / "system" / "index.json"

    compiled_skills = [
        {
            "skill_id": "brainstorming",
            "package_id": "obra/superpowers",
            "manifest_url": "./packages/obra/superpowers/brainstorming/ontoskill.ttl",
            "generated_by": "glm-5.1",
            "generated_at": "2026-04-04T16:30:00",
        }
    ]

    generate_registry_json(compiled_skills, index_path, output_root)

    import json
    data = json.loads(index_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert len(data["packages"]) == 1
    assert data["packages"][0]["package_id"] == "obra/superpowers"
    assert len(data["packages"][0]["skills"]) == 1
    assert data["packages"][0]["skills"][0]["skill_id"] == "brainstorming"


def test_generate_registry_json_upsert(tmp_path):
    """generate_registry_json merges with existing index.json."""
    from compiler.storage import generate_registry_json
    import json

    index_path = tmp_path / "system" / "index.json"
    index_path.parent.mkdir(parents=True)

    # Pre-existing data
    existing = {
        "version": 1,
        "packages": [
            {
                "package_id": "obra/superpowers",
                "trust_tier": "community",
                "source_kind": "ontology",
                "skills": [
                    {
                        "skill_id": "brainstorming",
                        "manifest_url": "./old/path.ttl",
                        "generated_by": "old-model",
                        "generated_at": "2026-01-01T00:00:00",
                    }
                ],
            }
        ],
    }
    index_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    # Upsert: same package, same skill → update
    compiled_skills = [
        {
            "skill_id": "brainstorming",
            "package_id": "obra/superpowers",
            "manifest_url": "./packages/obra/superpowers/brainstorming/ontoskill.ttl",
            "generated_by": "glm-5.1",
            "generated_at": "2026-04-04T16:30:00",
        }
    ]

    generate_registry_json(compiled_skills, index_path, tmp_path)

    data = json.loads(index_path.read_text(encoding="utf-8"))
    assert len(data["packages"]) == 1
    skill = data["packages"][0]["skills"][0]
    assert skill["generated_by"] == "glm-5.1"  # Updated
    assert skill["generated_at"] == "2026-04-04T16:30:00"  # Updated
    assert skill["manifest_url"] == "./packages/obra/superpowers/brainstorming/ontoskill.ttl"


def test_generate_registry_json_new_skill_in_existing_package(tmp_path):
    """Adding a new skill to an existing package."""
    from compiler.storage import generate_registry_json
    import json

    index_path = tmp_path / "system" / "index.json"
    index_path.parent.mkdir(parents=True)

    existing = {
        "version": 1,
        "packages": [
            {
                "package_id": "obra/superpowers",
                "trust_tier": "community",
                "source_kind": "ontology",
                "skills": [
                    {"skill_id": "brainstorming", "manifest_url": "./p.ttl", "generated_by": "glm-5.1", "generated_at": "2026-04-04T16:30:00"},
                ],
            }
        ],
    }
    index_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")

    compiled_skills = [
        {
            "skill_id": "tdd",
            "package_id": "obra/superpowers",
            "manifest_url": "./packages/obra/superpowers/tdd/ontoskill.ttl",
            "generated_by": "glm-5.1",
            "generated_at": "2026-04-04T16:35:00",
        }
    ]

    generate_registry_json(compiled_skills, index_path, tmp_path)

    data = json.loads(index_path.read_text(encoding="utf-8"))
    assert len(data["packages"]) == 1
    assert len(data["packages"][0]["skills"]) == 2
    skill_ids = [s["skill_id"] for s in data["packages"][0]["skills"]]
    assert "brainstorming" in skill_ids
    assert "tdd" in skill_ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest core/tests/test_storage.py::test_generate_registry_json_creates_file -v`
Expected: FAIL (ImportError: cannot import name 'generate_registry_json')

- [ ] **Step 3: Implement `generate_registry_json()` in `core/src/storage.py`**

Add to `core/src/storage.py` after `generate_index_manifest()`:

```python
def generate_registry_json(
    compiled_skills: list[dict],
    index_path: Path,
    output_root: Path,
) -> None:
    """Generate or update system/index.json with per-skill registry metadata.

    Implements merge/upsert logic:
    - Existing packages are updated by package_id
    - Existing skills within a package are updated by skill_id
    - New packages and skills are appended

    Args:
        compiled_skills: List of dicts with keys:
            skill_id, package_id, manifest_url, generated_by, generated_at
        index_path: Path to system/index.json
        output_root: Root output directory for relative manifest_url computation
    """
    import json

    # Read existing index or start fresh
    registry: dict = {"version": 1, "packages": []}
    if index_path.exists():
        try:
            registry = json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass

    packages: list[dict] = registry.get("packages", [])
    pkg_index: dict[str, dict] = {p["package_id"]: p for p in packages}

    for skill_entry in compiled_skills:
        pkg_id = skill_entry["package_id"]

        if pkg_id not in pkg_index:
            # New package
            pkg_index[pkg_id] = {
                "package_id": pkg_id,
                "trust_tier": "community",
                "source_kind": "ontology",
                "skills": [],
            }
            packages.append(pkg_index[pkg_id])

        pkg = pkg_index[pkg_id]

        # Upsert skill by skill_id
        existing_skills = {s["skill_id"]: s for s in pkg["skills"]}
        skill_data = {
            "skill_id": skill_entry["skill_id"],
            "manifest_url": skill_entry["manifest_url"],
            "generated_by": skill_entry["generated_by"],
            "generated_at": skill_entry["generated_at"],
        }

        if skill_entry["skill_id"] in existing_skills:
            existing_skills[skill_entry["skill_id"]].update(skill_data)
        else:
            pkg["skills"].append(skill_data)

    registry["packages"] = packages

    # Write atomically
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest core/tests/test_storage.py -k registry_json -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add core/src/storage.py core/tests/test_storage.py
git commit -m "feat(storage): add generate_registry_json with merge/upsert logic"
```

---

### Task 4: Wire index.json generation into compile.py and track per-skill metadata

**Files:**
- Modify: `core/src/cli/compile.py`

- [ ] **Step 1: Add import**

In `core/src/cli/compile.py`, update the storage import to include `generate_registry_json`:

```python
from compiler.storage import (
    generate_index_manifest,
    clean_orphaned_files,
    generate_registry_json,
)
```

- [ ] **Step 2: Add model name import and metadata collector**

After the existing `from compiler.config import ...` line, add `ANTHROPIC_MODEL`:

```python
from compiler.config import CORE_ONTOLOGY_FILENAME, SKILLS_DIR, OUTPUT_DIR, resolve_ontology_root, ANTHROPIC_MODEL
```

Add a metadata collector alongside the existing counters (near line ~295):

```python
    # Counters for summary
    skills_serialized = 0
    sub_skills_serialized = 0
    assets_copied = 0
    compiled_skills = []  # Track extracted skills for summary display
    _registry_entries = []  # Per-skill metadata for index.json
```

- [ ] **Step 3: Record metadata after main skill serialization**

In the main skill extraction block, after the `serialize_skill_to_module` call inside `if not dry_run:`, add metadata tracking. Find this block:

```python
            # Serialize immediately to disk (unless dry_run)
            if not dry_run:
                _, pkg_id = skill_parent_map.get(skill_dir, (skill_id, "local"))
                qualified_id = f"{pkg_id}/{compiled.id}"
```

Change it to:

```python
            # Serialize immediately to disk (unless dry_run)
            if not dry_run:
                package_id = resolve_package_id(skill_dir, input_path)
                qualified_id = f"{package_id}/{compiled.id}"
```

And after the `skills_serialized += 1` line, add:

```python
                    # Track for registry index.json
                    rel_skill_path = output_skill_path.relative_to(output_path)
                    _registry_entries.append({
                        "skill_id": compiled.id,
                        "package_id": package_id,
                        "manifest_url": f"./{rel_skill_path}",
                        "generated_by": ANTHROPIC_MODEL,
                        "generated_at": datetime.now().isoformat(),
                    })
```

- [ ] **Step 4: Record metadata after sub-skill serialization**

Similarly, after `sub_skills_serialized += 1` in the sub-skill block, add:

```python
                    # Track for registry index.json
                    rel_sub_path = output_ttl_path.relative_to(output_path)
                    _registry_entries.append({
                        "skill_id": extracted.id,
                        "package_id": package_id,
                        "manifest_url": f"./{rel_sub_path}",
                        "generated_by": ANTHROPIC_MODEL,
                        "generated_at": datetime.now().isoformat(),
                    })
```

Note: `package_id` is already available in the sub-skill loop from `resolved_parent_map`.

- [ ] **Step 5: Generate index.json at end of compilation**

After the existing `rebuild_registry_indexes(ontology_root)` line, add:

```python
    # Generate registry index.json
    if _registry_entries:
        registry_path = ontology_root / "system" / "index.json"
        generate_registry_json(_registry_entries, registry_path, output_path)
```

- [ ] **Step 6: Verify compilation still works**

Run: `python -c "from compiler.cli.compile import compile_cmd; print('OK')"`
Expected: OK

- [ ] **Step 7: Commit**

```bash
git add core/src/cli/compile.py
git commit -m "feat(compile): wire index.json generation with per-skill metadata tracking"
```

---

### Task 5: Remove `oc:generatedBy` from TTL serialization

**Files:**
- Modify: `core/src/serialization.py` — remove lines 172-174

- [ ] **Step 1: Remove the generatedBy block**

In `core/src/serialization.py`, delete these lines:

```python
    # LLM attestation
    if skill.generated_by and skill.generated_by != "unknown":
        graph.add((skill_uri, oc.generatedBy, Literal(skill.generated_by)))
```

- [ ] **Step 2: Verify no other code references generatedBy in serialization**

Run: `grep -r "generatedBy" core/src/`
Expected: No results in serialization.py. (It may still exist in schemas.py as a field — that's fine, the field stays for backward compat, just no longer written to TTL.)

- [ ] **Step 3: Run tests**

Run: `python -m pytest core/tests/ -q --tb=short`
Expected: No new failures

- [ ] **Step 4: Commit**

```bash
git add core/src/serialization.py
git commit -m "refactor(serialization): remove oc:generatedBy from TTL (moved to index.json)"
```

---

### Task 6: End-to-end verification

- [ ] **Step 1: Clean compile remotion-dev**

```bash
rm -rf ontostore/
python -m compiler.cli compile -i .agents/skills/remotion-dev/ -o ontostore/packages/ -f -y
```

Verify:
- `ontostore/packages/remotion-dev/skills/remotion-best-practices/ontoskill.ttl` exists
- `ontostore/packages/remotion-dev/skills/remotion-best-practices/rules/*.ttl` exists (37 files)
- `ontostore/system/index.json` exists with package_id `remotion-dev/skills`
- No `skills/` spurious directory at wrong level
- TTL files do NOT contain `oc:generatedBy`

- [ ] **Step 2: Compile coinbase (append to same index.json)**

```bash
python -m compiler.cli compile -i .agents/skills/coinbase/ -o ontostore/packages/ -f -y
```

Verify:
- `ontostore/packages/coinbase/agentic-wallet-skills/trade/ontoskill.ttl` exists
- `ontostore/system/index.json` now has 2 packages (remotion-dev/skills + coinbase/agentic-wallet-skills)
- Each skill entry has `generated_by`, `generated_at`, `manifest_url`

- [ ] **Step 3: Run full test suite**

```bash
python -m pytest core/tests/ -q --tb=short
```

Expected: No new failures

- [ ] **Step 4: Commit any fixups**
