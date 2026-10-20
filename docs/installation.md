<!-- SPDX-License-Identifier: Apache-2.0 -->
# Installation and generator setup

## Recommended setup

Use the [all-in-one installation prompt](../README.md#install-with-your-coding-agent-recommended) in Claude Code or Codex and identify your existing Playwright project. The installer prepares the four skills, the two dedicated agents for the selected host, and the official Playwright agents and project MCP configuration when a project is supplied.

After installation, restart the host, approve the project MCP tools, and ask the agent to generate tests for your local project. The agent checks readiness and reports anything missing. Installation does not create your application, its API or database, install project dependencies or browsers, or run tests.

The installer requires Python 3.11+ and Node.js 22.20+ with npm and npx at standard system or Homebrew locations. Node.js 24 LTS is recommended. Project setup also requires Playwright already installed in the project or workspace, plus an existing playwright.config.* file. It stops on conflicting configuration instead of overwriting it. Review the checkout and proposed project command before execution.

After this setup, do not repeat the manual steps below. They are alternatives for users who want to run the commands themselves or troubleshoot configuration.

## Direct installer commands

```bash
git clone https://github.com/voidmatcha/e2e-skills.git
cd e2e-skills
bash install.sh --host codex --project /path/to/playwright-project
```

Use `--host claude` for Claude Code. `--project` names the directory containing playwright.config.*. Omit it to install only the four skills and two dedicated agents. Add `--dry-run` to preview changes without executing installers or project code.

## Manual generator setup

If you installed only the skills or plugin, you can use the all-in-one installer to prepare the remaining setup. The generator skill itself installs nothing and changes no agent or MCP configuration.

### Claude Code

In your trusted existing Playwright project, follow the [official Playwright Test Agents setup](https://playwright.dev/docs/test-agents#getting-started): run `npx --no-install playwright init-agents --loop=claude`, review its generated agents and `.mcp.json`, then approve the MCP tools and restart the host. Unlike our installer, `init-agents` also writes a seed spec and `specs/README.md`.

### Codex

`playwright-test-generator` works only with a session-wide `playwright-test` MCP server. Follow the [official Playwright Test Agents setup](https://playwright.dev/docs/test-agents#getting-started) for Codex and configure a session-wide `playwright-test` MCP entry in trusted-project `.codex/config.toml` or user `~/.codex/config.toml`; `init-agents` alone does not add it. The installer with `--project` prepares the project entry.

The required server exposes `generator_write_test`. The general-purpose [Playwright MCP](https://github.com/microsoft/playwright-mcp) browser server is not a substitute. See the [generator setup steps](../skills/playwright-test-generator/SKILL.md#4-not-set-up) for exact requirements. Missing setup makes the generator show the guide and stop.

## Ready to generate

The `playwright-test` MCP server must expose `generator_write_test` in the active session. Ask the agent to generate coverage for a local project. It checks the project, test command, and disposable local application environment before browser work. Approve the exact project command before it runs; credentials and shared or production environments are not used. If configuration or safe execution cannot be established, it reports the missing requirement and stops. The full behavior is defined by the [generator contract](../skills/playwright-test-generator/SKILL.md).

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
