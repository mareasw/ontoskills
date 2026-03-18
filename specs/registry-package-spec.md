# Registry Package Spec

This document defines the current package format consumed by the OntoClaw registry pipeline.

## Common Fields

All package manifests use `package.json`.

Required common fields:
- `package_id`
- `version`
- `trust_tier`
- `skills`

Optional common fields:
- `core_version`
- `source`
- `checksum`

## Skill Entry

Each exported skill is described as:

```json
{
  "id": "xlsx",
  "path": "office/public/xlsx/ontoskill.ttl",
  "default_enabled": false,
  "aliases": ["excel", "spreadsheet"]
}
```

Rules:
- `id` is the short skill id
- `path` is package-relative
- runtime canonical identity becomes `package_id/id`
- `default_enabled` controls initial install state
- `aliases` are lookup conveniences only

## Ontology Package

An ontology package distributes compiled TTL files.

Required additional field:
- `modules`

## Source Package

A source package distributes raw source skills to compile locally.

Required additional fields:
- `source_root`
- `source_files`

Rules:
- files in `source_files` are fetched/copied into the local source subtree
- compilation happens locally through `ontoclaw compile`
- installed package state is recorded as `source_kind = "source"`
- skills remain disabled by default after install

## Registry Index Spec

The registry index is a JSON file listing installable packages.

```json
{
  "packages": [
    {
      "package_id": "marea.office",
      "manifest_url": "https://example.invalid/packages/marea.office/package.json",
      "trust_tier": "verified",
      "source_kind": "ontology"
    }
  ]
}
```

## Runtime Semantics

- install unit: package
- enable unit: skill
- exact qualified id always wins
- short id lookup precedence is:
  - `verified > local > trusted > community`

## Direct Source Repository Import

Besides manifest-based source packages, OntoClaw supports direct raw repository import.

Expected behavior:
- accept a local path or GitHub URL
- clone/copy the repository
- discover all `SKILL.md` files
- compile them locally
- register the result as `source_kind = "source"`
- keep imported skills disabled by default
