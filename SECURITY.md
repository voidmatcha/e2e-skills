# Security Policy

## Supported versions

Security fixes are handled on the `main` branch and included in the next released plugin version.

## Reporting a vulnerability

Please do not publish exploit details in a public issue. If GitHub private vulnerability reporting is available for this repository, use that channel. Otherwise, open a minimal public issue asking for a private security contact and omit sensitive details until a private channel is established.

Include enough context to reproduce and assess the issue, such as affected skill, manifest file, scanner output, and whether the issue can expose secrets, execute commands, or make tests silently pass.

## Scope

This repository ships agent skills, plugin manifests, documentation, and local/CI scanners. Security reports are most useful when they concern:

- hardcoded secrets or credential leakage,
- unsafe shell or MCP command patterns,
- plugin manifest paths that expose unintended files,
- scanner bypasses that allow P0 E2E smells to pass undetected,
- supply-chain risk in GitHub Actions or dependency installation.
