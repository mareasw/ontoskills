import click


@click.group()
@click.version_option(version="0.1.0", prog_name="skill-ontology-etl")
def cli():
    """Skill Ontology ETL CLI"""
    pass


@cli.command()
@click.argument('skill_name', required=False)
def compile(skill_name):
    """Compile skills into ontology."""
    click.echo(f"Compiling {skill_name if skill_name else 'all skills'}")


@cli.command()
@click.argument('query_string')
def query(query_string):
    """Execute SPARQL query."""
    click.echo("Query executed")
