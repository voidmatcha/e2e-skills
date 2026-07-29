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

## Network behavior

The skills, plugin manifests, and documentation perform no network calls. The only component that can reach the network is the standalone scanner (`skills/e2e-reviewer/scripts/scan.sh`), and its behavior is intentionally narrow:

- It reads only the test files under the path you point it at. It never uploads test code, source, scan results, or any other data — there is no telemetry and no outbound reporting.
- For its highest-precision lint tier it prefers tools already installed in the target project. Package auto-downloads through `npx` are disabled by default, so the scanner falls back to its built-in deterministic regex/AST checks when those tools are missing. A legacy `npx` download path remains available only when both `E2E_SMELL_NO_ESLINT_DOWNLOAD` and `E2E_SMELL_NO_AST_GREP_DOWNLOAD` are explicitly cleared; in that mode it fetches only the pinned public packages documented by the scanner.
- The default execution is fully offline: it uses only locally installed tools plus its built-in deterministic tiers and attempts no network download. Set both `E2E_SMELL_NO_ESLINT_DOWNLOAD=1` and `E2E_SMELL_NO_AST_GREP_DOWNLOAD=1` explicitly when making the offline policy visible in CI or air-gapped environments.
