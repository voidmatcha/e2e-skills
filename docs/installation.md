<!-- SPDX-License-Identifier: Apache-2.0 -->
# Installation and generator setup

## Recommended setup

Use the [all-in-one installation prompt](../README.md#install-with-your-coding-agent-recommended) in Claude Code or Codex and identify your existing Playwright project. The installer prepares the four skills, the two dedicated agents for the selected host, and the official Playwright agents and project MCP configuration when a project is supplied.

After installation, run the printed diagnostic command when authorized for that exact command. If needed, restart the host yourself, complete project trust and MCP approval, then ask the agent to resume verification in the new session. It reports installation, server tools, session tools and approval separately. It must see `generator_write_test` in the active session before proceeding with generation. Installation does not create your application, its API or database, install project dependencies or browsers, or run tests.

The installer requires Python 3.11+ and Node.js 22.20+ with npm and npx at standard system or Homebrew locations. Node.js 24 LTS is recommended. Project setup also requires Playwright already installed in the project or workspace, plus an existing playwright.config.* file. It stops on conflicting configuration instead of overwriting it. Review the checkout and proposed project command before execution.

The reviewer includes its Node scanner and pinned TypeScript parser. Scanning, including the check after generation, requires Node.js 22+ at a standard system or Homebrew location; it does not require ripgrep, ast-grep or Python. See the [scanner prerequisites](../skills/e2e-reviewer/references/scanner-workflow.md#phase-1-mechanical-scan).

After this setup, do not repeat the manual steps below. They are alternatives for users who want to run the commands themselves or troubleshoot configuration.

## Direct installer commands

```bash
git clone https://github.com/voidmatcha/e2e-skills.git
cd e2e-skills
bash install.sh --host codex --project /path/to/playwright-project
```

Use `--host claude` for Claude Code. `--project` names the directory containing playwright.config.*. Omit it to install only the four skills and two dedicated agents. Add `--dry-run` to preview changes without executing installers or project code.

## First Playwright project

If the project has no Playwright runner or configuration, follow the [official initial setup](https://playwright.dev/docs/intro) using its existing package manager. Review and authorize dependency installation, browser downloads and generated files separately; the generator skill does not perform this setup automatically. Confirm the project-native test command, Playwright configuration, required browsers and approved local development stack before rerunning `bash install.sh --host codex --project /path/to/playwright-project` (use `--host claude` for Claude Code).

A configured project with no spec files can generate its first tests; missing specs alone do not block generation. See the [generator setup guide](../skills/playwright-test-generator/setup-guide.md) for the separate runner, session-tool and execution requirements.

## Optional project lint

The bundled reviewer scanner does not require project ESLint configuration or rules. It uses its bundled checks and does not download ESLint. If compatible project lint is unavailable, report the optional ESLint stage as skipped, rather than claiming the generated tests are lint-clean; the scanner gate still applies.

For additional checks, consider [eslint-plugin-playwright](https://github.com/playwright-community/eslint-plugin-playwright) and its recommended configuration, scoped to your Playwright tests. Installing it or modifying existing lint configuration requires a separate setup decision; the generator does neither automatically. Preserve existing project lint rules.

## Diagnose the configured server

The normal installer prints this follow-up command when a project is supplied:

```bash
bash install.sh --host codex --project /path/to/playwright-project --check
```

Use `--host claude` for Claude Code. `--check` skips global installation and installer writes. It starts the installer-configured local Playwright MCP server and performs only `initialize` and `tools/list`: no tool calls, browser launch or tests. Starting the server executes project code and configuration, so use a trusted project and authorize the exact command before execution.

A successful check verifies the server's advertised tools, including `generator_write_test`; it does not prove the active host session exposes them or that host approval is complete. Treat session tools and approval as unknown until checked in that session. A missing tool alone does not identify an approval problem. Do not bypass trust or approval, edit global configuration, or restart the host automatically to resolve it.

## Manual generator setup

If you installed only the skills or plugin, you can use the all-in-one installer to prepare the remaining setup. The generator skill itself installs nothing and changes no agent or MCP configuration.

### Claude Code

In your trusted existing Playwright project, follow the [official Playwright Test Agents setup](https://playwright.dev/docs/test-agents#getting-started): run `npx --no-install playwright init-agents --loop=claude`, review its generated agents and `.mcp.json`, then approve the MCP tools and restart the host. Unlike our installer, `init-agents` also writes a seed spec and `specs/README.md`.

### Codex

`playwright-test-generator` works only with a session-wide `playwright-test` MCP server. Follow the [official Playwright Test Agents setup](https://playwright.dev/docs/test-agents#getting-started) for Codex and configure a session-wide `playwright-test` MCP entry in trusted-project `.codex/config.toml` or user `~/.codex/config.toml`; `init-agents` alone does not add it. The installer with `--project` prepares the project entry.

The required server exposes `generator_write_test`. The general-purpose [Playwright MCP](https://github.com/microsoft/playwright-mcp) browser server is not a substitute. See the [generator setup steps](../skills/playwright-test-generator/SKILL.md#4-not-set-up) for exact requirements. Missing setup makes the generator show the guide and stop.

## Ready to generate

The `playwright-test` MCP server must expose `generator_write_test` in the active session. Ask the agent to generate coverage for a local project. It checks the project, test command and scenario-used services in the approved local development environment before browser work. Approve the exact project command before it runs; credentials and shared or production environments are not used. If configuration or safe execution cannot be established, it reports the missing requirement and stops.

Reuse an existing approved local dev server and its real test backend or mocks; no new mock server or deployment is required. Check only scenario-used services. Read-only scenarios need no reset; writes require isolated test data and cleanup/reset. The full behavior is defined by the [generator contract](../skills/playwright-test-generator/SKILL.md).

## Manual Claude Code checkout

Keep the checkout outside `~/.claude/skills/`, then link each public skill directory:

```bash
(
git clone https://github.com/voidmatcha/e2e-skills.git "$HOME/.claude/e2e-skills" || exit 1
mkdir -p "$HOME/.claude/skills" || exit 1

skip_link=
for skill in playwright-test-generator e2e-reviewer playwright-debugger cypress-debugger; do
  if [ -e "$HOME/.claude/skills/$skill" ] || [ -L "$HOME/.claude/skills/$skill" ]; then
    echo "Already exists, nothing linked: $HOME/.claude/skills/$skill" >&2
    skip_link=1
  fi
done

if [ -z "$skip_link" ]; then
  for skill in playwright-test-generator e2e-reviewer playwright-debugger cypress-debugger; do
    ln -s "$HOME/.claude/e2e-skills/skills/$skill" "$HOME/.claude/skills/$skill" || exit 1
  done
else
  exit 1
fi
)
```

If any of the four names already exists under `~/.claude/skills/`, the commands print that path, return a nonzero status and link nothing, so an existing skill is never replaced and no link is nested inside it. Run `/skills` in Claude Code and confirm all four names appear.
