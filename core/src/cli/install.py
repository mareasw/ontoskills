"""Install commands - package installation and skill management."""

from pathlib import Path

import click
from rich.console import Console

from compiler.registry import (
    enable_skills,
    disable_skills,
    enabled_index_path,
    import_source_repository,
    install_package_from_directory,
    install_package_from_sources,
    list_installed_packages,
)
from compiler.config import OUTPUT_DIR, resolve_ontology_root

console = Console()


@click.command('install-package')
@click.argument('package_path', type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option('--trust-tier', type=click.Choice(['official', 'verified', 'community']), default=None)
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def install_package_cmd(ctx, package_path, trust_tier, ontology_root_arg):
    """Install a package manifest from a local directory into the global ontology root."""
    from . import setup_logging
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    package = install_package_from_directory(package_path, root=root, trust_tier=trust_tier)
    console.print(f"[green]Installed package {package.package_id}@{package.version}[/green]")
    console.print(f"  Trust: {package.trust_tier}")
    console.print(f"  Skills: {', '.join(skill.skill_id for skill in package.skills)}")
    console.print(f"  Root: {package.install_root}")


@click.command('import-source-repo')
@click.argument('repo_ref')
@click.option('--package-id', default=None, help='Override the inferred package id')
@click.option('--trust-tier', type=click.Choice(['official', 'verified', 'community']), default='community')
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def import_source_repo_cmd(ctx, repo_ref, package_id, trust_tier, ontology_root_arg):
    """Clone/copy a source skill repository into skills/author and compile it into ontoskills/author."""
    from . import setup_logging
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    package = import_source_repository(repo_ref, root=root, trust_tier=trust_tier, package_id=package_id)
    console.print(f"[green]Imported source repository {package.package_id}[/green]")
    console.print(f"  Trust: {package.trust_tier}")
    console.print(f"  Source: {package.source}")
    console.print(f"  Skills: {', '.join(skill.skill_id for skill in package.skills)}")
    console.print("  Enabled skills: (none by default)")


@click.command('install')
@click.argument('package_ref')
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.option('--with-embeddings', is_flag=True, help='Download per-skill embedding files for semantic search')
@click.pass_context
def install_cmd(ctx, package_ref, ontology_root_arg, with_embeddings):
    """Install packages by reference.

    Supports author-level (anthropics), package-level (anthropics/financial-services-plugin),
    skill-level (anthropics/financial-services-plugin/budgeting), and short names (impeccable).
    """
    from . import setup_logging
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))

    from compiler.registry import (
        load_registry_index,
        load_registry_sources,
        resolve_install_ref,
        install_author,
        install_single_skill,
        install_package_from_sources,
        NotFoundError,
        AmbiguousRefError,
        AuthorTarget,
        PackageTarget,
    )
    from compiler.registry.models import RegistryIndex

    # Build index from remote registry sources only
    combined_packages = []
    sources = load_registry_sources(root)
    if not sources.sources:
        console.print("[red]No registry sources configured. Run 'ontoskills registry add-source' first.[/red]")
        raise SystemExit(1)
    for source in sources.sources:
        try:
            idx = load_registry_index(source.index_url)
            combined_packages.extend(idx.packages)
        except Exception as e:
            source_name = getattr(source, "name", None) or source.index_url
            console.print(
                f"[yellow]Warning:[/yellow] Failed to load registry source "
                f"'{source_name}' ({source.index_url}): {e}"
            )
            continue

    if not combined_packages:
        console.print("[red]No packages found in configured registries.[/red]")
        raise SystemExit(1)

    index = RegistryIndex(packages=combined_packages)

    # Skill-level refs (3+ segments): split into package_id + skill_id
    # and route to install_single_skill, which downloads the manifest
    # from the remote URL directly.
    ref_parts = [part for part in package_ref.split("/") if part]
    if len(ref_parts) >= 3:
        package_id = "/".join(ref_parts[:2])
        skill_id = "/".join(ref_parts[2:])
        matching = [p for p in index.packages if p.package_id == package_id]
        if not matching:
            console.print(f"[red]Package '{package_id}' not found in configured registries.[/red]")
            raise SystemExit(1)
        result = install_single_skill(matching[0], skill_id, root=root, with_embeddings=with_embeddings)
        console.print(f"[green]Installed skill {package_id}/{skill_id}[/green]")
        console.print(f"  Trust: {result.trust_tier}")
        return

    try:
        target = resolve_install_ref(package_ref, index)
    except AmbiguousRefError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)
    except NotFoundError as e:
        console.print(f"[red]{e}[/red]")
        raise SystemExit(1)

    if isinstance(target, AuthorTarget):
        results = install_author(target.author, target.packages, root=root, with_embeddings=with_embeddings)
        total_skills = sum(len(pkg.skills) for pkg in results)
        console.print(f"[green]Installed author {target.author}: {len(results)} package(s), {total_skills} skill(s)[/green]")

    elif isinstance(target, PackageTarget):
        package = install_package_from_sources(target.package.package_id, root=root, with_embeddings=with_embeddings)
        console.print(f"[green]Installed {package.package_id}: {len(package.skills)} skill(s)[/green]")


@click.command('enable')
@click.argument('package_id')
@click.argument('skill_ids', nargs=-1)
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def enable_cmd(ctx, package_id, skill_ids, ontology_root_arg):
    """Enable all skills in a package or selected skills only."""
    from . import setup_logging
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    package = enable_skills(package_id, list(skill_ids) or None, root=root)
    enabled = [skill.skill_id for skill in package.skills if skill.enabled]
    console.print(f"[green]Enabled package {package.package_id}[/green]")
    console.print(f"  Enabled skills: {', '.join(enabled) if enabled else '(none)'}")
    console.print(f"  Index: {enabled_index_path(root)}")


@click.command('disable')
@click.argument('package_id')
@click.argument('skill_ids', nargs=-1)
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def disable_cmd(ctx, package_id, skill_ids, ontology_root_arg):
    """Disable all skills in a package or selected skills only."""
    from . import setup_logging
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    package = disable_skills(package_id, list(skill_ids) or None, root=root)
    enabled = [skill.skill_id for skill in package.skills if skill.enabled]
    console.print(f"[green]Disabled package {package.package_id}[/green]")
    console.print(f"  Still enabled: {', '.join(enabled) if enabled else '(none)'}")
    console.print(f"  Index: {enabled_index_path(root)}")


@click.command('list-installed')
@click.option('-o', '--ontology-root', 'ontology_root_arg', default=None, type=click.Path(path_type=Path))
@click.pass_context
def list_installed_cmd(ctx, ontology_root_arg):
    """List installed ontology packages and enabled skills."""
    from . import setup_logging
    setup_logging(ctx.obj.get('verbose', False), ctx.obj.get('quiet', False))
    root = ontology_root_arg or Path(resolve_ontology_root(OUTPUT_DIR))
    lock = list_installed_packages(root=root)
    if not lock.packages:
        console.print("[yellow]No installed packages[/yellow]")
        return

    for package in lock.packages.values():
        console.print(f"\n[bold]{package.package_id}[/bold] {package.version} [{package.trust_tier}]")
        enabled = [skill.skill_id for skill in package.skills if skill.enabled]
        disabled = [skill.skill_id for skill in package.skills if not skill.enabled]
        console.print(f"  enabled: {', '.join(enabled) if enabled else '(none)'}")
        console.print(f"  disabled: {', '.join(disabled) if disabled else '(none)'}")
