<!-- SPDX-License-Identifier: Apache-2.0 -->
# Installation and generator setup

## Recommended setup

For reviewing and debugging in any agent, [install the skills with skills.sh](../README.md#review-and-debug-install-the-skills-recommended). For test generation in Claude Code or Codex, use the [e2e-skills installer](../README.md#test-generation-claude-code-and-codex) with your existing Playwright project, directly or through the paste-in prompt there. The installer prepares the four skills, the two dedicated subagents for the selected host, and the official Playwright agents and project MCP configuration when a project is supplied.

After installation, run the printed diagnostic command when authorized for that exact command. If needed, restart the host yourself, complete project trust and MCP approval, then ask the agent to resume verification in the new session. It reports installation, server tools, session tools and approval separately. It must see `generator_write_test` in the active session before proceeding with generation. Installation does not create your application, its API or database, install project dependencies or browsers, or run tests.

The installer requires Node.js 22.20+ with npm and npx at standard system or Homebrew locations. Node.js 24 LTS is recommended. Project setup also requires Playwright already installed in the project or workspace, plus an existing playwright.config.* file. It stops on conflicting configuration instead of overwriting it. Review the checkout and proposed project command before execution.

The reviewer includes its Node scanner and pinned TypeScript parser. Scanning, including the check after generation, requires Node.js 22+ at a standard system or Homebrew location; it does not require ripgrep, ast-grep or Python. See the [scanner prerequisites](../skills/e2e-reviewer/references/scanner-workflow.md#phase-1-mechanical-scan).

The installer and portable probe runner also use Node.js. Debugger artifact helpers and the source-checkout registered-adapter pilot still use Python; their references describe the required interpreter.

After this setup, do not repeat the manual steps below. They are alternatives for users who want to run the commands themselves or troubleshoot configuration.

## Direct installer commands

```bash
git clone https://github.com/voidmatcha/e2e-skills.git
cd e2e-skills
bash install.sh --host codex --project /path/to/playwright-project
```

Use `--host claude` for Claude Code. `--project` names the directory containing playwright.config.*. Omit it to install only the four skills and two dedicated agents. Add `--dry-run` to preview changes without executing installers or project code.

## CLI installer

The npm CLI installs the same skills and agents without a repository clone. Preview the changes, then install and diagnose the selected host:

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.3.0 e2e-skills install --host codex --project /path/to/playwright-project --dry-run
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.3.0 e2e-skills install --host codex --project /path/to/playwright-project
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.3.0 e2e-skills doctor --host codex --project /path/to/playwright-project
```

Use `--host claude` for Claude Code. Installation reuses the host installer described above; it does not create a project or install its dependencies or browsers. The default `doctor` returns structured file checks, missing requirements and next steps without executing project code. Active-session tools and approvals remain unknown.

Existing skill copies must match the package exactly. Older versions and local edits are preserved and stop installation; review the reported paths before retrying.

For a trusted project, explicitly add `--check-server` to `doctor` to start the configured MCP server and check `initialize` and `tools/list`. That check executes project code; it does not invoke MCP tools, launch a browser or run tests. A successful server check does not prove active-session readiness. Complete host restart, project trust and tool approval yourself where needed.

The same entry point forwards `scan PATH` to the existing scanner and `check ...` to the existing discovery, binding and probe CLI. These commands do not install skills or configure MCP. The existing `e2e-skills-scan` and `e2e-skills-check` commands remain available.

## Optional memo and failure policy

The [test-authoring memo](test-authoring-memo.md) and the [test-failure policy](test-failure-policy.md) are not installed by `install` and not checked by `doctor`. To write them into a project's `CLAUDE.md` or `AGENTS.md` without pasting by hand, ask for them explicitly:

```bash
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.3.0 e2e-skills guidance --host claude --project /path/to/project --memo --policy --dry-run
npx --yes --package=@voidmatcha/e2e-skills-scanner@3.3.0 e2e-skills guidance --host claude --project /path/to/project --memo --policy
```

`--memo`, `--policy` or both are required. `--host claude` writes `CLAUDE.md` and `--host codex` writes `AGENTS.md` in the `--project` directory, creating the file if it is missing. Each text is inserted unchanged between two HTML comments, such as `<!-- e2e-skills:test-authoring-memo sha256=... -->` and `<!-- /e2e-skills:test-authoring-memo -->`. A rerun leaves a matching block alone (`CURRENT`), replaces only the text between the markers when it differs (`UPDATED`), and otherwise appends the block after one blank line (`ADDED`); bytes outside the markers are never changed. The command refuses a symlinked, hard-linked or non-regular instruction file and malformed markers, and writes nothing in that case. `--dry-run` prints the JSON report, including the text it would insert, and writes nothing.

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

If you installed only the skills or plugin, you can use the [e2e-skills installer](../README.md#test-generation-claude-code-and-codex) to prepare the remaining setup. The generator skill itself installs nothing and changes no agent or MCP configuration.

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
