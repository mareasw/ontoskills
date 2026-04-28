#!/usr/bin/env python3
"""Content coverage benchmark — line-level and knowledge-yield metrics.

Level 1 — Parser coverage: what % of non-blank SKILL.md lines fall within a
FlatBlock range.  Target: >=95%.

Level 2 — Knowledge yield (optional, requires --ttl-dir): for compiled skills
(TTL files), count epistemic and operational knowledge nodes by type and
compute operational density and type coverage.

Usage:
    python benchmark/content_coverage.py --verbose
    python benchmark/content_coverage.py --json results.json
    python benchmark/content_coverage.py --ttl-dir ./ontoskills --verbose
    python benchmark/content_coverage.py --target 95
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Add core to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "core" / "src"))

from compiler.content_parser import extract_flat_blocks, extract_structural_content

# ---------------------------------------------------------------------------
# Level 2 constants
# ---------------------------------------------------------------------------

OC = "https://ontoskills.sh/ontology#"

EPISTEMIC_DIMENSIONS = [
    "Observability", "ResilienceTactic", "ResourceProfile", "TrustMetric",
    "CognitiveBoundary", "ExecutionPhysics", "LifecycleHook", "NormativeRule",
    "SecurityGuardrail", "StrategicInsight",
]

OPERATIONAL_TYPES = [
    "Procedure", "CodePattern", "OutputFormat", "Command", "Prerequisite",
]

# SPARQL: count instances of any rdfs:subClassOf a given top-level dimension.
# We enumerate the top-level class directly plus all known subclasses via
# property-path rdfs:subClassOf*.
_SPARQL_EPISTEMIC = """
PREFIX oc: <https://ontoskills.sh/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?dimension (COUNT(?node) AS ?cnt) WHERE {
    ?node a ?dtype .
    ?dtype rdfs:subClassOf* ?dimension .
    FILTER (?dimension IN (
        oc:Observability, oc:ResilienceTactic, oc:ResourceProfile,
        oc:TrustMetric, oc:CognitiveBoundary, oc:ExecutionPhysics,
        oc:LifecycleHook, oc:NormativeRule, oc:SecurityGuardrail,
        oc:StrategicInsight
    ))
} GROUP BY ?dimension
"""

_SPARQL_OPERATIONAL = """
PREFIX oc: <https://ontoskills.sh/ontology#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?otype (COUNT(?node) AS ?cnt) WHERE {
    ?node a ?dtype .
    ?dtype rdfs:subClassOf* ?otype .
    FILTER (?otype IN (
        oc:Procedure, oc:CodePattern, oc:OutputFormat,
        oc:Command, oc:Prerequisite
    ))
} GROUP BY ?otype
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _env_path(name, fallback):
    value = os.environ.get(name)
    return Path(value).expanduser() if value else Path(fallback)


_SKILLS_DIR = _env_path("ONTOSKILLS_BENCH_DIR", str(
    Path(__file__).resolve().parent.parent / ".agents" / "skills"))


def collect_skill_paths():
    paths = []
    skills_dir = _SKILLS_DIR
    if not skills_dir.is_dir():
        return paths
    for p in sorted(skills_dir.rglob("SKILL.md")):
        vendor = p.parent.parent.parent.name if len(p.parts) > 5 else "local"
        paths.append((vendor, p))
    return paths


def calc_line_coverage(md, blocks):
    """Line-level coverage: what % of non-blank lines fall within a FlatBlock range."""
    lines = md.splitlines()
    covered = set()
    for b in blocks:
        for line_no in range(b.line_start - 1, b.line_end):
            if 0 <= line_no < len(lines):
                covered.add(line_no)
    total_content = sum(
        1 for i, l in enumerate(lines)
        if l.strip() and l.strip() not in ("---", "***", "___")
    )
    covered_content = sum(
        1 for i in covered
        if i < len(lines) and lines[i].strip() and lines[i].strip() not in ("---", "***", "___")
    )
    return covered_content / total_content * 100 if total_content else 100.0


# ---------------------------------------------------------------------------
# Level 2 — Knowledge Yield
# ---------------------------------------------------------------------------

def _local_name(uri: str) -> str:
    """Extract the fragment after '#' or last '/' from a URI."""
    return uri.split("#")[-1] if "#" in uri else uri.rsplit("/", 1)[-1]


def compute_knowledge_yield(ttl_dir: Path) -> dict:
    """Analyse compiled TTL files and return knowledge-yield statistics.

    Parameters
    ----------
    ttl_dir : Path
        Directory (searched recursively) containing .ttl files with compiled
        skill instance data.

    Returns
    -------
    dict
        ``total_epistemic``, ``total_operational``, ``avg_operational_per_skill``,
        ``type_distribution``, ``operational_density``, ``epistemic_distribution``,
        ``skills_analyzed``, ``type_coverage_avg``.
    """
    from rdflib import Graph, Namespace

    oc = Namespace(OC)

    # Collect all .ttl files (skip the core TBox for counting, but load it
    # for the rdfs:subClassOf hierarchy needed by SPARQL property paths).
    ttl_files = sorted(
        p for p in ttl_dir.rglob("*.ttl")
        if p.name != "core.ttl"
    )

    if not ttl_files:
        return {
            "skills_analyzed": 0,
            "total_epistemic": 0,
            "total_operational": 0,
            "avg_operational_per_skill": 0.0,
            "operational_density": 0.0,
            "type_coverage_avg": 0.0,
            "type_distribution": {},
            "epistemic_distribution": {},
        }

    # Merge all TTLs into a single graph for efficient querying.
    g = Graph()
    g.bind("oc", oc)

    # Load core.ttl for the class hierarchy (rdfs:subClassOf axioms).
    core_ttl = ttl_dir / "core.ttl"
    if not core_ttl.exists():
        for p in ttl_dir.rglob("core.ttl"):
            core_ttl = p
            break
    # Also check the project source tree.
    if not core_ttl.exists():
        project_core = Path(__file__).resolve().parent.parent / "ontoskills" / "core.ttl"
        if project_core.exists():
            core_ttl = project_core
    if core_ttl.exists():
        try:
            g.parse(str(core_ttl), format="turtle")
        except Exception as exc:
            print(f"  Warning: failed to parse {core_ttl}: {exc}", file=sys.stderr)

    for tf in ttl_files:
        try:
            g.parse(str(tf), format="turtle")
        except Exception as exc:
            print(f"  Warning: failed to parse {tf}: {exc}", file=sys.stderr)

    # --- Epistemic counts ---
    epistemic_raw: dict[str, int] = {}
    for row in g.query(_SPARQL_EPISTEMIC):
        dim = _local_name(str(row.dimension))
        epistemic_raw[dim] = int(row.cnt)

    # Fill zeros for dimensions with no instances.
    for dim in EPISTEMIC_DIMENSIONS:
        epistemic_raw.setdefault(dim, 0)

    total_epistemic = sum(epistemic_raw.values())

    # --- Operational counts ---
    operational_raw: dict[str, int] = {}
    for row in g.query(_SPARQL_OPERATIONAL):
        otype = _local_name(str(row.otype))
        operational_raw[otype] = int(row.cnt)

    for otype in OPERATIONAL_TYPES:
        operational_raw.setdefault(otype, 0)

    total_operational = sum(operational_raw.values())

    # --- Derived metrics ---
    n_skills = len(ttl_files)
    avg_operational = round(total_operational / n_skills, 2) if n_skills else 0.0
    operational_density = round(total_operational / total_epistemic, 2) if total_epistemic else 0.0

    types_present = sum(1 for v in operational_raw.values() if v > 0)
    type_coverage_avg = round(types_present / len(OPERATIONAL_TYPES) * 100, 1)

    return {
        "skills_analyzed": n_skills,
        "total_epistemic": total_epistemic,
        "total_operational": total_operational,
        "avg_operational_per_skill": avg_operational,
        "operational_density": operational_density,
        "type_coverage_avg": type_coverage_avg,
        "type_distribution": operational_raw,
        "epistemic_distribution": epistemic_raw,
    }


# ---------------------------------------------------------------------------
# Main benchmark runner
# ---------------------------------------------------------------------------

def run_benchmark(target=95.0, verbose=False, json_output=None, ttl_dir=None):
    paths = collect_skill_paths()
    if len(paths) < 10:
        print(f"Warning: only {len(paths)} skills found. Expected 30+.")

    results = []
    for source, path in paths:
        md = path.read_text(encoding="utf-8")
        blocks = extract_flat_blocks(md)
        coverage = calc_line_coverage(md, blocks)
        results.append({"source": source, "name": path.parent.name, "coverage": round(coverage, 1)})

    avg = sum(r["coverage"] for r in results) / len(results) if results else 0
    below_target = [r for r in results if r["coverage"] < target]

    # --- Level 2 (optional) ---
    knowledge_yield = None
    if ttl_dir is not None:
        ttl_path = Path(ttl_dir)
        if ttl_path.is_dir():
            knowledge_yield = compute_knowledge_yield(ttl_path)
        else:
            print(f"Warning: --ttl-dir {ttl_dir} is not a directory; skipping Level 2.")

    if verbose:
        print(f"\n{'=' * 70}")
        print(f"LEVEL 1: PARSER COVERAGE — {len(results)} skills")
        print(f"{'=' * 70}")
        has_api_key = bool(os.environ.get("ANTHROPIC_API_KEY"))
        print(f"  Skeleton LLM: {'ACTIVE' if has_api_key else 'INACTIVE (set ANTHROPIC_API_KEY)'}")
        print()
        for r in sorted(results, key=lambda x: x["coverage"]):
            marker = " <<<" if r["coverage"] < target else ""
            print(f"  {r['source']:>3} {r['name']:<38} {r['coverage']:>6.1f}%{marker}")
        print(f"\n  Average: {avg:.1f}%")
        if below_target:
            print(f"  Below {target}%: {len(below_target)} skills")

        if knowledge_yield and knowledge_yield["skills_analyzed"] > 0:
            ky = knowledge_yield
            print(f"\n{'=' * 70}")
            print(f"LEVEL 2: KNOWLEDGE YIELD — {ky['skills_analyzed']} compiled skills")
            print(f"{'=' * 70}")
            print(f"  Total epistemic nodes : {ky['total_epistemic']}")
            print(f"  Total operational nodes: {ky['total_operational']}")
            print(f"  Operational density    : {ky['operational_density']}")
            print(f"  Avg operational/skill  : {ky['avg_operational_per_skill']}")
            print(f"  Type coverage          : {ky['type_coverage_avg']}%\n")

            print("  Epistemic distribution:")
            for dim in EPISTEMIC_DIMENSIONS:
                count = ky["epistemic_distribution"].get(dim, 0)
                print(f"    {dim:<22} {count}")

            print("\n  Operational distribution:")
            for otype in OPERATIONAL_TYPES:
                count = ky["type_distribution"].get(otype, 0)
                print(f"    {otype:<22} {count}")

        print(f"\n{'=' * 70}")

    if json_output:
        payload = {
            "parser_coverage_avg": round(avg, 1),
            "target": target,
            "skills_analyzed": len(results),
            "skills": results,
        }
        if knowledge_yield:
            payload["knowledge_yield"] = knowledge_yield
        with open(json_output, "w") as f:
            json.dump(payload, f, indent=2)
        if verbose:
            print(f"  Results written to {json_output}")

    # Exit code
    if avg < target:
        print(f"\nFAIL: Average coverage {avg:.1f}% below target {target}%")
        return 1

    print(f"\nPASS: Average coverage {avg:.1f}% >= {target}%")
    return 0


def main():
    parser = argparse.ArgumentParser(description="Content coverage benchmark")
    parser.add_argument("--verbose", "-v", action="store_true", help="Per-skill report")
    parser.add_argument("--json", dest="json_output", help="Write results to JSON file")
    parser.add_argument("--target", type=float, default=95.0, help="Coverage target %% (default: 95)")
    parser.add_argument("--ttl-dir", default=None,
                        help="Directory with compiled .ttl files for Level 2 knowledge yield")
    args = parser.parse_args()

    if not _SKILLS_DIR.is_dir():
        print(f"Error: Skills directory not found: {_SKILLS_DIR}")
        print(f"Set ONTOSKILLS_BENCH_DIR to override.")
        sys.exit(1)

    sys.exit(run_benchmark(
        target=args.target,
        verbose=args.verbose,
        json_output=args.json_output,
        ttl_dir=args.ttl_dir,
    ))


if __name__ == "__main__":
    main()
