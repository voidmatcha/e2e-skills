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

`playwright-test-generator` is a router. It delegates browsing to the official Playwright agents only on loopback targets, because their browser has no origin allowlist; it refuses production, shared, unnamed and remote targets, installs nothing, writes no agent or MCP configuration, and runs only the reviewer scanner and the project's own test command. When the official agents are not set up it shows the setup guide and stops.

Loading the skills, plugin manifests, and documentation does not itself initiate network activity. Agents and explicitly enabled runtime paths may execute tools with network capability, so the applicable boundary depends on the operation. The standalone scanner (`skills/e2e-reviewer/scripts/scan.sh`) has the following explicit trust boundary:

- By default it executes no code, plugin, parser, or ESLint configuration from the target project. The Node scanner uses its bundled TypeScript parser to inspect source beneath the requested root, and scanner findings remain scoped to that requested root. Provenance resolution may read relative fixture/support modules elsewhere within the containing project. It does not download tooling, upload source, or send telemetry. Analysis and source-integrity failures exit 2 rather than reporting a clean scan.
- `--project-eslint --trust-project` explicitly permits the scanner to execute the containing project's already installed ESLint, plugins, parser, and configuration. The child receives a restricted environment and temporary storage, but these controls are not an OS sandbox. Trusted project code retains ordinary host filesystem, process, and network access. Missing or incomplete ESLint evidence exits 2; the scanner does not install dependencies or apply fixes.
- `E2E_SMELL_FAIL_ON` selects the finding exit policy; `--fail-on` overrides it. All other `E2E_SMELL_*` settings are rejected with exit 2, including retired backend, executable, download, and limit controls.
- The installed `scan.sh` verifies the bundled runtime before launching it. The npm CLI runs the same scanner; invoking it through `npx` may download an uncached package before execution. This package acquisition is separate from scanning, which provides no tooling-download path.

The opt-in live benchmark runner uses a separate environment boundary. Each call receives a fresh temporary `HOME`, no inherited XDG configuration paths, and only basic process paths plus one narrowly staged authentication source. Codex receives a private, descriptor-opened copy of the parent `auth.json` in its temporary home. Claude receives one validated `CLAUDE_CODE_OAUTH_TOKEN` snapshot obtained before the call; it does not inherit `CLAUDE_CONFIG_DIR`, `ANTHROPIC_API_KEY`, or other parent settings. Custom runner executables receive neither host's authentication. Generic tokens, cloud credentials, proxy variables, `NODE_OPTIONS`, `BASH_ENV`, `ENV`, and arbitrary caller variables are removed. Empty and relative `PATH` entries are removed, and the selected runner is resolved to an absolute executable before the staged corpus workspace becomes the process working directory. This prevents a fixture from shadowing `codex`, `claude`, or a custom runner. The complete frozen skill/case payload travels in the prompt and both built-in hosts run with every model-callable tool disabled, so the model cannot use a filesystem or shell tool to read the staged authentication material. Corpus files cannot target runner-owned surfaces such as `.skill/`, `.git/`, `.codex/`, `.claude/`, `.agents/`, `.omx/`, `AGENTS.md`, or `CLAUDE.md`. The actual staged `.skill/e2e-reviewer` digest must equal the frozen evaluated-skill digest before and after every model call. This minimizes ambient credential exposure but is not a substitute for the external isolation wrapper required for non-public release evidence. Because the harness cannot attest an arbitrary wrapper, non-public reports remain `INCONCLUSIVE`; executable presence alone can never produce a release `PASS`.

The behavioral-eval runner applies the same credential separation: Codex and Claude receive the same minimal authentication snapshots plus a fresh temporary `HOME`; custom runner executables receive no model credentials. Built-in host prompts contain the exact task artifacts and, for the treatment arm, the skill instruction snapshot; model-callable tools remain disabled. The Playwright and Cypress semantic probes pass only process/runtime, temporary storage, locale, display/session, and explicit browser-cache variables, plus the probe variables they define. Shell startup hooks, language-runtime injection, proxies, cloud credentials, generic tokens, and arbitrary caller variables are not inherited. The browser probes retain the caller's `HOME` when needed to locate installed browser caches. These controls minimize ambient exposure but do not sandbox the locally pinned Node/browser processes, which retain ordinary filesystem and loopback-network capabilities.
