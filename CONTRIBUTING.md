# Contributing

Thanks for considering a contribution.

## Local Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
python3 -m pytest -q -p no:cacheprovider
```

## Patch Rules

- Keep providers isolated behind adapter modules.
- Do not print or store raw secrets.
- Add parser tests for every new provider response shape.
- Add MCP contract tests when adding or renaming tools.
- Prefer deterministic fixtures over live network tests.

## Live Provider Tests

Live Google/Exa checks should be opt-in and skipped when credentials are absent. Unit tests must pass without network access.
