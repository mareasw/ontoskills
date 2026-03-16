"""
Skill Ontology ETL CLI.

Click-based command-line interface for compiling skills
to OWL 2 RDF/Turtle ontology.
"""

import logging
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax

from extractor import generate_skill_id, compute_skill_hash
from transformer import tool_use_loop
from security import security_check, SecurityError
from loader import (
    create_ontology_graph,
    load_ontology,
    merge_skill,
    save_ontology_atomic,
    apply_reasoning,
    get_id_mapping,
)
from sparql import execute_sparql, format_results
from exceptions import (
    SkillETLError,
    ExtractionError,
    SPARQLError,
    SkillNotFoundError,
)

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
@click.version_option(version="0.1.0", prog_name="skill-ontology-etl")
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def cli(ctx, verbose, quiet):
    """Skill Ontology ETL - Compile markdown skills to OWL 2 ontology."""
    setup_logging(verbose, quiet)
    ctx.ensure_object(dict)
    ctx.obj['verbose'] = verbose
    ctx.obj['quiet'] = quiet


@cli.command()
@click.argument('skill_name', required=False)
@click.option('-i', '--input', 'input_dir', default='./skills/',
              type=click.Path(exists=False), help='Input skills directory')
@click.option('-o', '--output', 'output_file', default='./ontology/skills.ttl',
              type=click.Path(), help='Output ontology file')
@click.option('--dry-run', is_flag=True, help='Preview without saving')
@click.option('--skip-security', is_flag=True, help='Skip security checks (not recommended)')
@click.option('--reason/--no-reason', default=False, help='Apply OWL reasoning')
@click.option('-y', '--yes', is_flag=True, help='Skip confirmation prompt')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def compile(ctx, skill_name, input_dir, output_file, dry_run, skip_security,
            reason, yes, verbose, quiet):
    """Compile skills into ontology.

    Without SKILL_NAME: Compile all skills in input directory.
    With SKILL_NAME: Compile specific skill (shows preview, asks confirmation).
    """
    setup_logging(verbose or ctx.obj.get('verbose', False),
                  quiet or ctx.obj.get('quiet', False))
    logger = logging.getLogger(__name__)

    input_path = Path(input_dir)
    output_path = Path(output_file)

    # Find skills to compile
    if skill_name:
        # Single skill
        skill_dir = input_path / skill_name
        if not skill_dir.exists():
            raise SkillNotFoundError(f"Skill directory not found: {skill_dir}")
        skill_dirs = [skill_dir]
    else:
        # All skills
        if not input_path.exists():
            console.print(f"[yellow]No skills directory found at {input_path}[/yellow]")
            console.print("[yellow]No SKILL.md files found in input directory[/yellow]")
            return

        skill_dirs = [
            d for d in input_path.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        ]

        if not skill_dirs:
            console.print("[yellow]No SKILL.md files found in input directory[/yellow]")
            return

    logger.info(f"Found {len(skill_dirs)} skill(s) to compile")

    # Process each skill
    compiled_skills = []
    for skill_dir in skill_dirs:
        skill_id = generate_skill_id(skill_dir.name)
        skill_hash = compute_skill_hash(skill_dir)

        logger.info(f"Processing skill: {skill_id}")

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

    if dry_run:
        console.print("\n[yellow]Dry run - no changes saved[/yellow]")
        return

    # Confirmation
    if not yes and skill_name:
        if not click.confirm("\nAdd this skill to the ontology?", default=True):
            console.print("[yellow]Cancelled[/yellow]")
            return

    # Merge and save
    output_path.parent.mkdir(parents=True, exist_ok=True)

    graph = load_ontology(output_path)
    for skill in compiled_skills:
        graph = merge_skill(output_path, skill)

    # Apply reasoning if requested
    if reason:
        logger.info("Applying OWL reasoning...")
        graph = apply_reasoning(graph)

    save_ontology_atomic(output_path, graph)
    console.print(f"\n[green]Ontology saved to {output_path}[/green]")


@cli.command('query')
@click.argument('query_string')
@click.option('-o', '--ontology', 'ontology_file', default='./ontology/skills.ttl',
              type=click.Path(exists=False), help='Ontology file')
@click.option('-f', '--format', 'output_format',
              type=click.Choice(['table', 'json', 'turtle']), default='table',
              help='Output format')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def query_cmd(ctx, query_string, ontology_file, output_format, verbose, quiet):
    """Execute SPARQL query against ontology.

    Example:
        skill-etl query "SELECT ?s ?n WHERE { ?s ag:nature ?n }" -f json
    """
    setup_logging(verbose or ctx.obj.get('verbose', False),
                  quiet or ctx.obj.get('quiet', False))

    ontology_path = Path(ontology_file)
    if not ontology_path.exists():
        console.print(f"[red]Ontology file not found: {ontology_path}[/red]")
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
@click.option('-o', '--ontology', 'ontology_file', default='./ontology/skills.ttl',
              type=click.Path(exists=False), help='Ontology file')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def list_skills(ctx, ontology_file, verbose, quiet):
    """List all skills in the ontology."""
    setup_logging(verbose or ctx.obj.get('verbose', False),
                  quiet or ctx.obj.get('quiet', False))

    ontology_path = Path(ontology_file)
    if not ontology_path.exists():
        console.print(f"[red]Ontology file not found: {ontology_path}[/red]")
        return

    try:
        results, _ = execute_sparql(
            ontology_path,
            """PREFIX ag: <http://agentic.web/ontology#>
            PREFIX dcterms: <http://purl.org/dc/terms/>
            SELECT ?id ?nature WHERE {
                ?skill a ag:Skill ;
                       dcterms:identifier ?id ;
                       ag:nature ?nature .
            }"""
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
@click.option('-i', '--input', 'input_dir', default='./skills/',
              type=click.Path(exists=False), help='Input skills directory')
@click.option('-v', '--verbose', is_flag=True, help='Enable debug logging')
@click.option('-q', '--quiet', is_flag=True, help='Suppress progress output')
@click.pass_context
def security_audit(ctx, input_dir, verbose, quiet):
    """Re-validate all skills against current security patterns."""
    setup_logging(verbose or ctx.obj.get('verbose', False),
                  quiet or ctx.obj.get('quiet', False))

    input_path = Path(input_dir)
    if not input_path.exists():
        console.print(f"[red]Skills directory not found: {input_path}[/red]")
        return

    skill_dirs = [
        d for d in input_path.iterdir()
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
