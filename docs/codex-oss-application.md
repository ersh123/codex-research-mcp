# Codex for OSS Application Draft

## Project

`codex-research-mcp`

## Short Description

Codex Research MCP is a local-first MCP server and CLI that turns a maintainer research question into a source-backed research artifact: multi-provider search, dedupe, freshness scoring, cross-reference summaries, and weak-source/BS flags.

## Repository URL

To fill after GitHub push:

`https://github.com/ersh123/codex-research-mcp`

## Maintainer Role

Owner and maintainer.

## Why This Helps Open Source

Maintainers waste a lot of time checking whether a dependency change, API behavior, security claim, or issue workaround is real. Existing web-search wrappers usually return a few links and leave the model to guess. This project gives Codex a structured research layer:

- official docs and GitHub sources are classified separately from forums and generic web pages;
- duplicate results are removed;
- freshness and source quality are exposed as fields;
- suspicious wording, deprecated/security terms, missing URLs, and thin snippets are flagged;
- every run writes `report.md`, `sources.jsonl`, and `summary.json` so a maintainer can audit the evidence.

## How Codex Will Use It

Codex can call `research_pipeline` before changing code when correctness depends on current external facts: SDK migrations, issue triage, CI failure research, security release checks, and dependency behavior changes.

## API Credit Use

API credits would be used to dogfood the MCP server against real OSS maintenance tasks, improve source validation heuristics, test deeper 200+ source research runs, and publish reproducible examples for Codex users.

## Current Status

- Local CLI and MCP server implemented.
- Unit tests pass without network access.
- Exa, XMLstock Google XML, and optional Google CSE provider paths are separated behind adapters.
- The Codex-facing Google backend uses XMLstock Google XML; Google CSE JSON remains a fallback.

## Notes

The project is new, so the application should not claim existing community traction. The honest angle is usefulness, maintainability, and direct fit for Codex-powered OSS workflows.
