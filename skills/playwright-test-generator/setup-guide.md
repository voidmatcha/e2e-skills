<!-- SPDX-License-Identifier: Apache-2.0 -->
# Generator setup guidance

Read this when generation prerequisites are missing or the project has no E2E/lint setup. Explain the relevant path; do not execute setup commands, install packages, or write configuration under this skill. Report generation, scan and execution as not done when prerequisites are absent. A separately requested installation task can prepare the environment under its own authority.

## No E2E setup versus no tests

Inspect package metadata, Playwright config and existing scripts without executing them. No spec files alone is not missing setup: an installed Playwright Test runner, usable config, approved official agents/MCP and a prepared disposable loopback stack allow first-test generation.

No Playwright dependency or config: explain that the test runner must be initialized first. Link the [official installation guide](https://playwright.dev/docs/intro). Ask the user to initialize Playwright with the project's existing package manager in a separate setup task, reviewing dependency, config, script and browser changes. Do not assume npm in a pnpm/yarn workspace, overwrite existing files, or invent a baseURL. Request the owning package, intended local URL and start/test commands. Once the local runner, config, browser and disposable stack are prepared, recommend the e2e-skills installer with `--project` from its reviewed checkout. Then check official agents and session MCP below.

## Existing development server

Reuse an already running, approved loopback dev server and its existing real test backend or mocks. Confirm only services and data reached by the requested scenario. For writes, establish isolated test data and cleanup/reset; read-only scenarios need no reset method. A disposable test-data boundary does not require replacing the app, creating a mock server, using an in-memory database, or provisioning a new deployment. Mark services the scenario does not use as N/A.

Inspect non-sensitive existing configuration and reuse confirmed scope/approvals; ask only about an unresolved destination, data boundary or, for writes, cleanup/reset method. Do not propose mock infrastructure just because the project uses a real API/database. Production or shared non-test data remain ineligible, and a loopback frontend alone does not prove backend safety.

Mocking is an optional project/scenario choice, never a prerequisite imposed by this skill. Suggest a new mock only as an optional alternative when the scenario would write to a real backend and an isolated test-data boundary cannot be established. A real backend alone is not a reason to suggest mocks; existing mocks and read-only scenarios get no new-mock proposal.

## Official agents and session tools

1. In the project: `npx --no-install playwright init-agents --loop=<claude|codex>`. Writes repo files (agents, `specs/README.md`, seed spec); this skill never runs it.
2. Declare `playwright-test` (`npx --no-install playwright run-test-mcp-server`) in the host with tool approval. Claude Code: `init-agents` wrote `.mcp.json`; approve its prompt. Codex: `init-agents` declares it only inside the agent file; declare it in trusted-project `.codex/config.toml` or user `~/.codex/config.toml` yourself. Headless, existing config; expose `generator_write_test` and, for MCP execution, `test_run`. Missing tools: check server errors; `required = true`, `mcp_optional_startup_grace_ms = 0` wait for startup. Keep Codex sessions persistent.
3. Start a new session and ask again.

Tool absence alone is not approval evidence. Distinguish missing configuration, disabled server/tools, startup failure, and tools not exposed in the active session. The installer's `--check` verifies server discovery only, not host approval or session visibility; use it only as a separately authorized setup diagnostic. Never change host trust/approval or global settings to make this skill proceed.

## No project lint rules

Missing ESLint configuration or `eslint-plugin-playwright` does not block generation or the bundled scanner. Keep the section 5 pinned scanner invocation unchanged: it disables target-controlled ESLint and downloads. Report optional ESLint as skipped, not lint-clean; bundled scan results do not establish lint coverage. A missing scanner prerequisite or failed scan still follows section 5's blocked/incomplete handling.

Follow existing lint conventions when present. When Playwright lint rules are absent, recommend the [eslint-plugin-playwright recommended configuration](https://github.com/playwright-community/eslint-plugin-playwright) as optional follow-up, scoped to E2E files. Reuse an installed plugin; recommend enabling its preset rather than installing it again. Show proposed setup for a separately requested configuration task; do not install plugins, create lint files or replace existing rules during generation. Lint setup is not a prerequisite and cannot replace the scanner or native test execution, or a separately requested semantic review.
