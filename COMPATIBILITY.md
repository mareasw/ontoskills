# Version Compatibility

## Ontology Format

Current format version: `1.0`

Both OntoCore and OntoMCP must support the same ontology format version to work together.

## Tested Combinations

| OntoCore | OntoMCP | Ontology Format | Status   |
|----------|---------|-----------------|----------|
| 1.0.0    | 1.0.0   | 1.0             | Current  |
| 0.11.0   | 0.11.0  | 0.11            | Compatible |
| 0.10.0   | 0.9.1   | 0.10            | Compatible |
| 0.9.1    | 0.9.1   | 0.9             | Compatible |
| 0.9.0    | 0.9.0   | 0.9             | Compatible |

> **Note:** OntoMCP 1.0.0 introduces compact response format (88% token reduction) and `prefetch_knowledge` tool. The `format` parameter on all tools supports `"compact"` (default) and `"raw"` for backward compatibility. Ontology format 1.0 is backward-compatible with 0.11 compiled TTLs.

## Breaking Changes

When the ontology format changes, both packages must be updated together. Check this table before upgrading if you use both.
