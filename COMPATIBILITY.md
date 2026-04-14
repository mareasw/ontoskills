# Version Compatibility

## Ontology Format

Current format version: `0.11`

Both OntoCore and OntoMCP must support the same ontology format version to work together.

## Tested Combinations

| OntoCore | OntoMCP | Ontology Format | Status   |
|----------|---------|-----------------|----------|
| 0.11.0   | 0.11.0  | 0.11            | Current  |
| 0.10.0   | 0.9.1   | 0.10            | Compatible |
| 0.9.1    | 0.9.1   | 0.9             | Compatible |
| 0.9.0    | 0.9.0   | 0.9             | Compatible |

> **Note:** OntoMCP 0.11.0 requires ontology format 0.11. The `oc:dependsOnSkill` predicate is used for dependency edges (replacing `oc:dependsOn`), and per-skill embeddings are required for semantic search. Older ontologies using `oc:dependsOn` will have missing dependency edges. Upgrade both packages together.

## Breaking Changes

When the ontology format changes, both packages must be updated together. Check this table before upgrading if you use both.
