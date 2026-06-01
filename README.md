# Codex Research MCP

Local-first research pipeline and MCP server for Codex maintainer workflows.

It is built for work where "search the web" is not enough: triaging OSS issues, checking API changes before a patch, validating release/security claims, comparing sources, and producing a small evidence trail that another maintainer can audit.

## What It Does

- Searches with Exa and XMLstock Google XML, with Google CSE JSON as an optional fallback.
- Expands one maintainer question into a multi-query research plan.
- Dedupes sources across providers.
- Classifies sources as official docs, GitHub, forum, Reddit, or web.
- Scores freshness and source quality.
- Flags thin snippets, hype language, deprecated/security wording, and missing URLs.
- Writes reproducible `report.md`, `sources.jsonl`, and `summary.json` artifacts.
- Exposes the workflow as a stdio MCP server for Codex and other MCP clients.

## Install

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Optional provider config:

```bash
cp .env.example ~/.config/xmlstock/.env
```

Environment variables are also supported:

- `EXA_SEARCH_BIN`
- `EXA_FETCH_BIN`
- `EXA_API_KEY`
- `XMLSTOCK_USER`
- `XMLSTOCK_KEY`
- `XMLSTOCK_YANDEX_XML_USER`
- `XMLSTOCK_YANDEX_XML_KEY`
- `GOOGLE_CSE_API_KEY`
- `GOOGLE_CSE_CX`
- `SEARCH_LOCAL_CACHE_ROOT`

Google support defaults to XMLstock Google XML so it can reuse the same XMLstock account/key class as the old XML search path. The default config file is `~/.config/xmlstock/.env`; existing `~/.config/yandex-xmlstock/.env` files are also read through the legacy aliases above. Google CSE JSON remains available with `--backend cse`.

## CLI

```bash
codex-research quick "OpenAI Codex MCP docs" --json
codex-research docs "OpenAI Responses API file search"
codex-research google "MCP server examples" --num 5
codex-research google "MCP server examples" --backend cse --num 5
codex-research pipeline "Should this OSS project migrate to the latest OpenAI Responses API?" --max-sources 120
codex-research fetch "https://developers.openai.com/"
codex-research doctor
```

`search-local` is kept as a compatibility alias.

## MCP

Run the stdio server:

```bash
codex-research-mcp
```

Tools:

- `exa_quick`
- `exa_research`
- `exa_docs`
- `exa_fetch`
- `google_search`
- `research_pipeline`
- `search_doctor`

Example MCP client config:

```json
{
  "mcpServers": {
    "codex-research": {
      "command": "codex-research-mcp"
    }
  }
}
```

## Research Pipeline

`research_pipeline` is the main tool for Codex:

1. Build subqueries from the user's research question.
2. Query Exa and XMLstock Google XML.
3. Deduplicate by URL.
4. Annotate each source with `quality_score`, `freshness`, and flags.
5. Summarize cross-reference signals by domain and source type.
6. Write artifacts for review.

It is intentionally conservative: it does not claim truth from one result page. It gives Codex a structured evidence set and tells it where the weak spots are.

## Artifacts And Cache

Each run writes:

- `report.md`
- `sources.jsonl`
- `summary.json`

Default run directory:

```text
~/.cache/codex-research-mcp/runs/<profile>-<timestamp>-<slug>/
```

Dedup cache lives next to the run cache. Result summaries include `summary.cache_hit`.

| profile | TTL |
|---|---:|
| `quick`, `docs`, `research` | 24h |
| `google`, `research-pipeline` | 12h |
| `fetch` | 7d |
| `doctor` | never cached |

Bypass cache:

```bash
SEARCH_LOCAL_NO_CACHE=1 codex-research pipeline "..."
```

## Development

```bash
python3 -m pytest -q -p no:cacheprovider
python3 -m py_compile $(find src -name '*.py')
printf '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}\n' | PYTHONPATH=src python3 -m search_local.mcp_server
```

## Security

Secrets are redacted from stdout and artifacts. Do not commit provider credentials. See [SECURITY.md](SECURITY.md).
