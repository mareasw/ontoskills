# OntoStore Registry Blueprint

This directory is the local blueprint for the future official OntoStore mono-repo.

It defines:
- the registry index format
- the package manifest format
- the folder layout for official verified packages
- the separation between ontology packages and source packages

The current compiler/runtime can already consume this model through:
- `ontoclaw registry add-source`
- `ontoclaw install`
- `ontoclaw import-source`
- `ontoclaw import-source-repo`

## Layout

```text
registry/
  README.md
  index.json
  packages/
    marea.office/
      package.json
    skillssh.office/
      package.json
```

## Package Kinds

### Ontology package

Contains already compiled `.ttl` artifacts.

Required fields:
- `package_id`
- `version`
- `trust_tier`
- `modules`
- `skills`

### Source package

Contains raw source skills to compile locally.

Required fields:
- `package_id`
- `version`
- `trust_tier`
- `source_root`
- `source_files`
- `skills`

Runtime rule:
- source packages are compiled locally and installed as `source_kind = "source"`
- their skills remain disabled by default

### Direct source repository import

OntoClaw also supports importing a raw source repository directly from a local path or GitHub URL.

Example:

```bash
ontoclaw import-source-repo https://github.com/nextlevelbuilder/ui-ux-pro-max-skill
```

The importer:
- clones or copies the repository
- discovers every `SKILL.md`
- compiles the discovered skills locally
- registers the result as a community source package

## Registry Index

The registry index is a JSON document listing installable packages.

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

## Trust Tiers

- `verified`
- `trusted`
- `community`
- `local`

## Resolution Rules

- Canonical runtime identity is `package_id/skill_id`
- Short ids are accepted only as lookup convenience
- Ambiguous short ids resolve with precedence:
  - `verified > local > trusted > community`

## Activation Rules

- install unit: package
- activation unit: skill
- enabling a skill auto-enables required `extends` / `dependsOn`
- source/community skills stay disabled until explicitly enabled
