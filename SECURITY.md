# Security

## Supported Versions

Security fixes target the latest `main` branch until tagged releases exist.

## Reporting

Open a private security advisory on GitHub when available, or email the maintainer listed in the repository profile.

## Secret Handling

- Do not commit `.env` files or provider credentials.
- `EXA_API_KEY`, `XMLSTOCK_KEY`, `GOOGLE_CSE_API_KEY`, tokens, passwords, and credential-bearing URLs are redacted from stdout and artifacts.
- Raw provider payloads are parsed in memory and are not written as artifacts.

## Threat Model

This tool runs locally and can call configured search providers. Treat provider results as untrusted text. Do not execute code copied from research output without separate review.
