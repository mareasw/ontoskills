"""
Ontoclaw Compiler CLI.

Click-based command-line interface for compiling skills
to modular OWL 2 RDF/Turtle ontology.
"""

import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from rdflib import Graph, RDF

from compiler.extractor import generate_skill_id, compute_skill_hash
from compiler.transformer import tool_use_loop
from compiler.security import security_check, SecurityError
from compiler.core_ontology import get_oc_namespace, create_core_ontology
from compiler.serialization import serialize_skill_to_module
from compiler.storage import (
    generate_index_manifest,
    clean_orphaned_skills,
)
from compiler.sparql import execute_sparql, format_results
from compiler.exceptions import (
    SkillETLError,
    ExtractionError,
    SPARQLError,
    SkillNotFoundError,
)
from compiler.differ import compute_diff
from compiler.drift_report import print_report, export_json
from compiler.snapshot import save_snapshot, get_latest_snapshot
from compiler.linter import lint_ontology, LintIssue
from compiler.graph_export import build_graph
from compiler.config import SKILLS_DIR, OUTPUT_DIR

# Configure logging
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
LOG_DATE_FORMAT = "%H:%M:%S"

console = Console()


def setup_logging(verbose: bool, quiet: bool):
    """Configure logging based on verbosity flags."""
    if quiet:
        level = logging.WARNING
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        datefmt=LOG_DATE_FORMAT
    )


@click.group()
@click.version_option(version="0.2.0", prog_name="ontoclaw-compiler")
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def cli(ctx, verbose, quiet):
    """Ontoclaw Compiler - Compile markdown skills to modular OWL 2 ontology."""
    setup_logging(verbose, quiet)
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    ctx.obj['quiet'] = quiet


@cli.command()
@click.argument('skill_name', required=False)
@click.option('-i', '--input', 'input_dir', default=SKILLS_DIR,
              type=click.Path(exists=False), help='Input skills directory')
@click.option('-o', '--output', 'output_dir', default=OUTPUT_DIR,
              type=click.Path(), help='Output directory for ontoskills')
@click.option('--dry-run', is_flag=True, help='Preview without saving')
@click.option('--skip-security', is_flag=True, help='Skip security checks')
@click.option('-f', '--force', is_flag=True,
              help='Force recompilation of all skills (bypass cache)')
@click.option('-y', '--yes', is_flag=True, help='Skip confirmation prompt')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def compile(ctx, skill_name, input_dir, output_dir, dry_run, skip_security, force, yes, verbose, quiet):
    """Compile skills into modular ontology.

    Without SKILL_NAME: Compile all skills in input directory.
    With SKILL_NAME: Compile specific skill.

    Output structure:
      ontoskills/
      ├── ontoclaw-core.ttl
      ├── index.ttl
      └── <mirrored paths>/skill.ttl
    """
    setup_logging(verbose or ctx.obj.get('verbose', False), quiet or ctx.obj.get('quiet', False))
    logger = logging.getLogger(__name__)

    input_path = Path(input_dir)
    output_path = Path(output_dir)

    # Ensure core ontology exists
    core_path = output_path / "ontoclaw-core.ttl"
    if not core_path.exists():
        logger.info("Creating core ontology...")
        create_core_ontology(core_path)

    # Find skills to compile
    if skill_name:
        # Single skill
        skill_dir = input_path / skill_name
        if not skill_dir.exists():
            raise SkillNotFoundError(f"Skill directory not found: {skill_dir}")
        skill_dirs = [skill_dir]
    else:
        # All skills - find directories containing SKILL.md
        if not input_path.exists():
            console.print(f"[yellow]No skills directory found at {input_path}[/yellow]")
            return

        skill_dirs = [
            d for d in input_path.rglob("*")
            if d.is_dir() and (d / "SKILL.md").exists()
        ]

        if not skill_dirs:
            console.print("[yellow]No SKILL.md files found in input directory[/yellow]")
            return

    logger.info(f"Found {len(skill_dirs)} skill(s) to compile")

    # Clean orphaned skills before compilation
    orphans_removed = clean_orphaned_skills(input_path, output_path, dry_run=dry_run)
    if orphans_removed > 0:
        console.print(f"[yellow]Cleaned {orphans_removed} orphaned skill file(s)[/yellow]")

    # Process each skill
    compiled_skills = []
    skill_output_paths = []

    for skill_dir in skill_dirs:
        skill_id = generate_skill_id(skill_dir.name)
        skill_hash = compute_skill_hash(skill_dir)

        logger.info(f"Processing skill: {skill_id}")

        # Check if skill is unchanged (unless --force)
        output_skill_path = output_path / skill_dir.relative_to(input_path) / "skill.ttl"
        if not force and output_skill_path.exists():
            # Read existing hash from TTL file
            existing_graph = Graph()
            try:
                existing_graph.parse(output_skill_path, format="turtle")
                oc = get_oc_namespace()
                existing_hash = None
                for skill_uri in existing_graph.subjects(RDF.type, oc.Skill):
                    hash_val = existing_graph.value(skill_uri, oc.contentHash)
                    if hash_val:
                        existing_hash = str(hash_val)
                        break

                if existing_hash == skill_hash:
                    logger.info(f"Skill {skill_id} unchanged (hash match), skipping")
                    skill_output_paths.append(output_skill_path)
                    continue
            except Exception as e:
                logger.debug(f"Could not read existing skill: {e}")

        # Security check
        skill_file = skill_dir / "SKILL.md"
        if skill_file.exists():
            content = skill_file.read_text(encoding="utf-8")
            try:
                threats, passed = security_check(content, skip_llm=skip_security)
                if not passed:
                    console.print(f"[red]Security check failed for {skill_id}[/red]")
                    for threat in threats:
                        console.print(f"  - {threat.type}: {threat.match}")
                    continue
            except SecurityError as e:
                console.print(f"[red]Security error: {e}[/red]")
                continue

        # LLM extraction
        try:
            extracted = tool_use_loop(skill_dir, skill_hash, skill_id)
            compiled_skills.append(extracted)
            skill_output_paths.append(output_skill_path)

            logger.info(f"Successfully extracted: {skill_id}")
        except ExtractionError as e:
            console.print(f"[red]Extraction failed for {skill_id}: {e}[/red]")
            continue

    if not compiled_skills:
        console.print("[yellow]No skills compiled[/yellow]")
        return

    # Show preview
    console.print(Panel(f"[green]Compiled {len(compiled_skills)} skill(s)[/green]"))

    for skill in compiled_skills:
        console.print(f"\n[bold]{skill.id}[/bold]")
        console.print(f"  Nature: {skill.nature[:80]}...")
        console.print(f"  Genus: {skill.genus}")
        console.print(f"  Intents: {', '.join(skill.intents)}")
        if skill.state_transitions.requires_state:
            console.print(f"  Requires: {', '.join(skill.state_transitions.requires_state)}")
        if skill.state_transitions.yields_state:
            console.print(f"  Yields: {', '.join(skill.state_transitions.yields_state)}")

    if dry_run:
        console.print("\n[yellow]Dry run - no changes saved[/yellow]")
        return

    # Confirmation
    if not yes and skill_name:
        if not click.confirm("\nAdd this skill to the ontology?", default=True):
            console.print("[yellow]Cancelled[/yellow]")
            return

    # Serialize each skill module
    for skill, output_skill_path in zip(compiled_skills, skill_output_paths):
        serialize_skill_to_module(skill, output_skill_path, output_path)

    # Generate index manifest
    index_path = output_path / "index.ttl"
    generate_index_manifest(skill_output_paths, index_path, output_path)

    console.print(f"\n[green]Compiled {len(compiled_skills)} skill(s) to {output_path}[/green]")

    index_ttl = output_path / "index.ttl"
    if index_ttl.exists():
        snap = save_snapshot(index_ttl)
        console.print(f"[dim]Snapshot saved to {snap}[/dim]")


@cli.command('init-core')
@click.option('-o', '--output', 'output_dir', default=OUTPUT_DIR,
              type=click.Path(), help='Output directory for ontoskills')
@click.option('-f', '--force', is_flag=True, help='Overwrite existing core ontology')
@click.pass_context
def init_core(ctx, output_dir, force):
    """Initialize the core ontology (ontoclaw-core.ttl).

    Creates the foundational TBox with classes, properties, and predefined states.
    Safe to run multiple times - skips if file exists unless --force is used.
    """
    logger = logging.getLogger(__name__)
    output_path = Path(output_dir)
    core_path = output_path / "ontoclaw-core.ttl"

    if core_path.exists() and not force:
        console.print(f"[yellow]Core ontology already exists at {core_path}[/yellow]")
        console.print("Use --force to overwrite")
        return

    create_core_ontology(core_path)
    console.print(f"[green]Created core ontology at {core_path}[/green]")


@cli.command('query')
@click.argument('query_string')
@click.option('-o', '--ontology', 'ontology_file', default=OUTPUT_DIR + "/index.ttl",
              type=click.Path(exists=False), help='Ontology file or directory')
@click.option('-f', '--format', 'output_format',
              type=click.Choice(['table', 'json', 'turtle']), default='table',
              help='Output format')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def query_cmd(ctx, query_string, ontology_file, output_format, verbose, quiet):
    """Execute SPARQL query against ontology.

    Example:
        ontoclaw query "SELECT ?s ?n WHERE { ?s oc:nature ?n }" -f json
    """
    setup_logging(verbose or ctx.obj.get('verbose', False), quiet or ctx.obj.get('quiet', False))

    ontology_path = Path(ontology_file)
    if not ontology_path.exists():
        console.print(f"[red]Ontology not found: {ontology_path}[/red]")
        raise SPARQLError(f"Ontology not found: {ontology_path}")

    try:
        results, vars = execute_sparql(ontology_path, query_string)

        if not results:
            console.print("[yellow]No results[/yellow]")
            return

        output = format_results(results, output_format, vars)
        console.print(output)

    except SPARQLError as e:
        console.print(f"[red]Query error: {e}[/red]")
        raise


@cli.command('list-skills')
@click.option('-o', '--ontology', 'ontology_file', default=OUTPUT_DIR + "/index.ttl",
              type=click.Path(exists=False), help='Ontology file or directory')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def list_skills(ctx, ontology_file, verbose, quiet):
    """List all skills in the ontology."""
    setup_logging(verbose or ctx.obj.get('verbose', False), quiet or ctx.obj.get('quiet', False))

    ontology_path = Path(ontology_file)
    if not ontology_path.exists():
        console.print(f"[red]Ontology not found: {ontology_path}[/red]")
        return

    oc = get_oc_namespace()

    try:
        results, _ = execute_sparql(
            ontology_path,
            f"""PREFIX oc: <{str(oc)}>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            SELECT ?id ?nature WHERE {{
                ?skill a oc:Skill ;
                       dcterms:identifier ?id ;
                       oc:nature ?nature .
            }}"""
        )

        if not results:
            console.print("[yellow]No skills found in ontology[/yellow]")
            return

        console.print(f"\n[bold]Skills in ontology ({len(results)}):[/bold]\n")
        for row in results:
            id_val = row.get('id', 'unknown')
            nature = row.get('nature', '')[:60]
            console.print(f"  • {id_val}: {nature}...")

    except SPARQLError as e:
        console.print(f"[red]Query error: {e}[/red]")


@cli.command('security-audit')
@click.option('-i', '--input', 'input_dir', default=SKILLS_DIR,
              type=click.Path(exists=False), help='Input skills directory')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def security_audit(ctx, input_dir, verbose, quiet):
    """Re-validate all skills against current security patterns."""
    setup_logging(verbose or ctx.obj.get('verbose', False), quiet or ctx.obj.get('quiet', False))

    input_path = Path(input_dir)
    if not input_path.exists():
        console.print(f"[red]Skills directory not found: {input_path}[/red]")
        return

    skill_dirs = [
        d for d in input_path.rglob("*")
        if d.is_dir() and (d / "SKILL.md").exists()
    ]

    if not skill_dirs:
        console.print("[yellow]No skills found[/yellow]")
        return

    console.print(f"\n[bold]Security audit of {len(skill_dirs)} skill(s):[/bold]\n")

    issues_found = 0
    for skill_dir in skill_dirs:
        skill_file = skill_dir / "SKILL.md"
        content = skill_file.read_text(encoding="utf-8")

        threats, passed = security_check(content, skip_llm=True)

        if passed:
            console.print(f"  [green]✓[/green] {skill_dir.name}")
        else:
            console.print(f"  [red]✗[/red] {skill_dir.name}")
            for threat in threats:
                console.print(f"      - {threat.type}: {threat.match[:50]}")
            issues_found += 1

    console.print(f"\n[bold]Audit complete:[/bold] {issues_found} issue(s) found")


@cli.command('lint')
@click.option(
    '-o', '--ontology', 'ontology_file',
    default=OUTPUT_DIR + '/index.ttl',
    type=click.Path(exists=False),
    help='Ontology file to lint (default: ./ontoskills/index.ttl)',
)
@click.option(
    '--format', 'fmt',
    default='rich',
    type=click.Choice(['rich', 'json']),
    help='Output format',
)
@click.option('--errors-only', is_flag=True, help='Show only errors, suppress warnings and info')
@click.pass_context
def lint_cmd(ctx, ontology_file, fmt, errors_only):
    """Run static analysis on the compiled ontology.

    Checks for four categories of structural issues without calling the LLM:

    \b
    dead-state       A skill requiresState X but no skill yieldsState X
    circular-dep     A dependsOn B dependsOn ... dependsOn A  [error]
    duplicate-intent Two skills resolve the same intent string  [error]
    orphan-skill     Skill has no dependents and unreachable required states
    """
    import json as json_mod

    ontology_path = Path(ontology_file)
    if not ontology_path.exists():
        console.print(f"[red]Ontology not found: {ontology_path}[/red]")
        raise SystemExit(1)

    result = lint_ontology(ontology_path)

    if errors_only:
        result.issues = result.errors

    if fmt == 'json':
        data = [
            {
                'severity': i.severity,
                'code': i.code,
                'skill_id': i.skill_id,
                'message': i.message,
                'detail': i.detail,
            }
            for i in result.issues
        ]
        console.print(json_mod.dumps(data, indent=2))
    else:
        _ICONS = {'error': '🔴', 'warning': '⚠️ ', 'info': '🔵'}
        if result.is_clean:
            from rich.panel import Panel
            from rich import box
            console.print(Panel('[bold green]✓ No issues found — ontology is clean[/]', box=box.ROUNDED))
        else:
            from rich.table import Table
            from rich import box
            t = Table(title='Lint Results', box=box.SIMPLE_HEAVY)
            t.add_column('Severity', width=10)
            t.add_column('Code', width=18)
            t.add_column('Skill', width=22)
            t.add_column('Message')
            for issue in result.issues:
                icon = _ICONS.get(issue.severity, '⚪')
                t.add_row(f'{icon} {issue.severity}', issue.code, issue.skill_id, issue.message)
            console.print(t)
            console.print(
                f'\nSummary: [red]{len(result.errors)} error(s)[/] | '
                f'[yellow]{len(result.warnings)} warning(s)[/] | '
                f'[blue]{len([i for i in result.issues if i.severity == "info"])} info[/]'
            )

    if result.has_errors:
        raise SystemExit(1)


@cli.command('graph')
@click.option(
    '-o', '--ontology', 'ontology_file',
    default=OUTPUT_DIR + '/index.ttl',
    type=click.Path(exists=False),
    help='Ontology file to visualise (default: ./ontoskills/index.ttl)',
)
@click.option(
    '--format', 'fmt',
    default='mermaid',
    type=click.Choice(['mermaid', 'dot']),
    help='Output format (default: mermaid)',
)
@click.option('--skill', default=None, help='Show only this skill and its direct neighbours')
@click.option('--output', default=None, help='Write output to file instead of stdout')
@click.pass_context
def graph_cmd(ctx, ontology_file, fmt, skill, output):
    """Visualise the skill dependency graph.

    Exports oc:dependsOn, oc:extends, and oc:contradicts relationships as a
    Mermaid flowchart or Graphviz DOT digraph.

    \b
    Examples:
      ontoclaw graph                          # Mermaid to stdout
      ontoclaw graph --format dot             # DOT to stdout
      ontoclaw graph --skill create-pdf       # 1-hop subgraph
      ontoclaw graph --output graph.mmd       # save to file
    """
    ontology_path = Path(ontology_file)
    if not ontology_path.exists():
        console.print(f"[red]Ontology not found: {ontology_path}[/red]")
        raise SystemExit(1)

    src = build_graph(ontology_path, fmt=fmt, skill_filter=skill)

    if output:
        Path(output).write_text(src)
        console.print(f"[green]Graph saved to {output}[/green]")
    else:
        console.print(src)


@cli.command('diff')
@click.option('--skill', default=None, help='Analyse only this specific skill')
@click.option('--from', 'from_path', default=None, help='Previous .ttl snapshot path')
@click.option('--to', 'to_path', default=None, help='Current .ttl ontology path')
@click.option('--breaking-only', is_flag=True, help='Show only breaking changes (exit code 9 if found)')
@click.option(
    '--format', 'fmt',
    default='rich',
    type=click.Choice(['rich', 'json', 'md']),
    help='Output format',
)
@click.option('--output', default=None, help='Output file path for JSON/MD format')
def diff_cmd(skill, from_path, to_path, breaking_only, fmt, output):
    """Detect semantic drift between ontology versions.

    Compares the current ontology against a previous snapshot and reports
    changes classified by impact: breaking, additive, or cosmetic.

    Exit code 9 if breaking changes are detected (useful for CI/CD pipelines).
    """
    if not to_path:
        to_path = './ontoskills/index.ttl'
    if not from_path:
        snap = get_latest_snapshot()
        if not snap:
            raise click.ClickException(
                'No snapshot found. Run compile first to create a snapshot.'
            )
        from_path = str(snap)

    report = compute_diff(from_path, to_path)

    if fmt == 'json':
        out = output or 'drift-report.json'
        export_json(report, out)
    else:
        print_report(report, breaking_only=breaking_only)

    if report.has_breaking:
        raise SystemExit(9)


def main():
    """Entry point with proper error handling."""
    try:
        cli()
    except SkillETLError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(e.exit_code)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted[/yellow]")
        sys.exit(130)


if __name__ == '__main__':
    main()
