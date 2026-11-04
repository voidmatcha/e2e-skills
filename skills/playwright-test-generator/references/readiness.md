<!-- SPDX-License-Identifier: Apache-2.0 -->
# Official-agent readiness

Read before deciding whether the current session is ready. Registration, user approval and the visible defining tool are separate requirements; a file or doctor result alone is insufficient.

Before declaring official agents missing, check host metadata and the project and user agent directories. Codex: `.codex/agents/` in the project and `$CODEX_HOME/agents/` (or `~/.codex/agents/` when unset). Claude Code: `.claude/agents/` in the project and `$CLAUDE_CONFIG_DIR/agents/` (or `~/.claude/agents/` when unset). Identify the official planner/generator by the loaded definition or registration name, not a guessed filename; inspect only relevant definitions, not unrelated home files. A file's presence does not establish approval or active host registration. Reuse current `e2e-skills doctor` registration/configuration evidence when supplied; its session tools and approval remain unknown until checked in this session. Do not require a project-local duplicate of a verified user registration.

`browser_get_config` reports browser MCP settings, not the Playwright Test project's effective configuration. Do not call it for this readiness check or use it as project/origin evidence. Use reviewed project configuration, effective non-secret environment and verified launch evidence; unresolved configuration or scope remains BLOCKED. A listed tool may be unavailable in a test-server session, and a child's setup does not initialize its parent. Do not repeat an unchanged setup/unavailable error or initialize a browser/test merely to obtain configuration evidence. Carry this distinction into the delegated context.

Missing prerequisites: show the relevant path in `../setup-guide.md` and stop; do not run setup commands or change host configuration.
