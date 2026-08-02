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

Loading the skills, plugin manifests, and documentation does not itself initiate
network activity. Agents and explicitly enabled runtime paths may execute tools
with network capability, so the applicable boundary depends on the operation.
The standalone scanner (`skills/e2e-reviewer/scripts/scan.sh`) has the following
explicit trust boundary:

- By default it evaluates no executable, plugin, parser, or ESLint config from
  the target repository. Bundled checks inspect JavaScript/TypeScript source
  beneath the requested root, and scanner findings remain scoped to that
  requested root. Provenance resolution may read relative fixture/support
  modules elsewhere within the containing project. The checks contain no
  telemetry, upload path, or intentional network operation. A PATH-resolved
  `ast-grep`/`sg` is rejected
  when either its lexical or resolved path is inside the containing target
  project, even if the requested scan root is only a subdirectory. The
  load-bearing Tier 3 requires PCRE2-capable ripgrep and fails with exit 2 when
  PCRE2 or a source scan is unusable; scan errors are never converted to an
  empty clean result. Relative roots are resolved with `CDPATH` disabled.
  Tier 2 uses ast-grep JSON-stream output, validates every record before
  counting it, and applies the same generated/vendor/report/eval exclusions as
  Tiers 1 and 3. Malformed, oversized, or renderer-only output is an
  infrastructure failure, never zero findings. Tier 3 still completes so its
  evidence is retained, then the scan exits incomplete without a final
  Summary.
- `E2E_SMELL_ALLOW_PROJECT_ESLINT=1` is a positive trust capability. It permits
  the scanner to execute the containing project's local ESLint binary, plugins,
  parser, and flat config against E2E-proven files beneath the requested scan
  root. The child receives an environment
  allowlist with a temporary home/config/cache, but this is credential
  minimization—not a sandbox. Trusted target code can still read or write other
  accessible filesystem paths, spawn processes, and open network connections.
- Package download is a separate capability. Set
  `E2E_SMELL_NO_ESLINT_DOWNLOAD=0` or
  `E2E_SMELL_NO_AST_GREP_DOWNLOAD=0` to enable the corresponding legacy `npx`
  path. This downloads and executes public third-party packages. The ast-grep
  path is pinned to `@ast-grep/cli@0.39.7` and runs from scanner-owned private
  storage with a minimal environment, private home/cache/config, `/dev/null`
  user config, and the public npm registry fixed explicitly; target `.npmrc`
  files and inherited npm/proxy/Node settings do not configure it. The legacy
  ESLint path requests an exact, jointly reviewed set of direct package
  versions with install lifecycle scripts disabled, and it materializes them
  from scanner-owned private storage: a private working directory carrying its
  own `package.json` and empty `.npmrc`, a private home, cache, and prefix,
  distinct private user and global npm config files, and the public npm
  registry fixed explicitly. The audited project's `.npmrc` is therefore not
  read for that step, including scoped `@scope:registry` lines that no
  `npm_config_*` variable can override. ESLint is then executed directly from
  the resolved entry point, so no npm process runs from the audited project.
  Only the direct versions are pinned: npm still resolves the transitive
  closure from semver ranges at scan time and the scanner ships no lockfile, so
  transitive versions are not integrity-pinned. Disabled lifecycle scripts
  bound that residual exposure to code the linter actually loads.
- All three capability flags accept only `0` or `1` and fail closed on any
  other value. Default values are project ESLint disabled and both downloads
  disabled.

The opt-in live benchmark runner uses a separate environment boundary. Each
call receives a fresh temporary `HOME`, no inherited XDG configuration paths,
and only basic process paths plus one narrowly staged authentication source.
Codex receives a private, descriptor-opened copy of the parent `auth.json` in
its temporary home. Claude receives one validated
`CLAUDE_CODE_OAUTH_TOKEN` snapshot obtained before the call; it does not inherit
`CLAUDE_CONFIG_DIR`, `ANTHROPIC_API_KEY`, or other parent settings. Custom
runner executables receive neither host's authentication. Generic tokens, cloud
credentials, proxy variables, `NODE_OPTIONS`, `BASH_ENV`, `ENV`, and arbitrary
caller variables are removed.
Empty and relative `PATH` entries are removed, and the selected runner is
resolved to an absolute executable before the staged corpus workspace becomes
the process working directory. This prevents a fixture from shadowing
`codex`, `claude`, or a custom runner. The complete frozen skill/case payload
travels in the prompt and both built-in hosts run with every model-callable tool
disabled, so the model cannot use a filesystem or shell tool to read the staged
authentication material.
Corpus files cannot target runner-owned surfaces such as `.skill/`, `.git/`,
`.codex/`, `.claude/`, `.agents/`, `.omx/`, `AGENTS.md`, or `CLAUDE.md`. The
actual staged `.skill/e2e-reviewer` digest must equal the frozen evaluated-skill
digest before and after every model call.
This minimizes ambient credential exposure but is not a substitute for the
external isolation wrapper required for non-public release evidence. Because
the harness cannot attest an arbitrary wrapper, non-public reports remain
`INCONCLUSIVE`; executable presence alone can never produce a release `PASS`.

The behavioral-eval runner applies the same credential separation: Codex and
Claude receive the same minimal authentication snapshots plus a fresh temporary
`HOME`; custom runner executables receive no model credentials. Built-in host
prompts contain the exact task artifacts and, for the treatment arm, the skill
instruction snapshot; model-callable tools remain disabled.
The Playwright and Cypress semantic probes pass only process/runtime, temporary
storage, locale, display/session, and explicit browser-cache variables, plus
the probe variables they define. Shell startup hooks, language-runtime
injection, proxies, cloud credentials, generic tokens, and arbitrary caller
variables are not inherited. The browser probes retain the caller's `HOME`
when needed to locate installed browser caches. These controls minimize ambient
exposure but do not sandbox the locally pinned Node/browser processes, which
retain ordinary filesystem and loopback-network capabilities.
