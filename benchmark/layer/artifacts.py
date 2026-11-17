"""What a build actually left on disk, measured once, the same way for everyone.

`LAYER.md` §5 requires the artifact size to be read after the build with caches
excluded, because a framework that writes a 400 MB embedding cache has not
produced a 400 MB knowledge base: it has produced a knowledge base plus a cache
it can rebuild. Counting the two together would rank systems by how eagerly they
cache.

The exclusion is by directory name, and each system declares its own list:

    python3 -m benchmark.layer.artifacts --root /tmp/layer/graphrag \\
        --exclude cache logs input --json

Nothing here guesses: the names come from the framework's own configuration, and
a name that matches nothing is reported rather than ignored, so a wrong exclusion
is visible instead of silently shrinking the number.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def directory_size(root: Path, exclude: tuple[str, ...] = ()) -> int:
    """Bytes of every file under ``root``, minus the excluded top-level names."""
    root = Path(root)
    total = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if relative.parts and relative.parts[0] in exclude:
            continue
        total += path.stat().st_size
    return total


def describe(root: Path, exclude: tuple[str, ...] = ()) -> dict:
    """The artifact record the report table reads."""
    root = Path(root)
    present = {path.name for path in root.iterdir()} if root.is_dir() else set()
    missing = [name for name in exclude if name not in present]
    files = sum(
        1
        for path in root.rglob("*")
        if path.is_file() and path.relative_to(root).parts[0] not in exclude
    )
    return {
        "root": str(root),
        "excluded": list(exclude),
        "excluded_not_found": missing,
        "artifact_bytes": directory_size(root, exclude),
        "files": files,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--exclude", nargs="*", default=[])
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    record = describe(args.root, tuple(args.exclude))
    if args.json:
        print(json.dumps(record, indent=1))
    else:
        print(f"{record['artifact_bytes']} bytes in {record['files']} files")
        if record["excluded_not_found"]:
            print(f"declared but absent: {', '.join(record['excluded_not_found'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
