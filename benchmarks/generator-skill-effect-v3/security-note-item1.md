# Security note: item 1 (skill-owned scripts need no Step 4 row)

Status: author's analysis (the agent that drafted the change), then reviewed by a `security-reviewer` agent run (agent `a236be66bf50f0166`, 2026-10-06, read-only, 36 tool uses) whose report was delivered to the team lead. Verdict line as relayed by the team lead:

> SECURITY-REVIEW VERDICT: APPROVE-WITH-CHANGES

Every change the reviewer asked for is applied in the current `PATCH.diff` (section "Reviewer findings and how they were addressed"). The reviewer's full report text was not delivered to this author; the findings below are the lead's relay of it.

## What changes

Today `SKILL.md` says every target-controlled command needs repository trust plus exact-command approval, and Step 4 says "treat every command as skipped until explicitly approved". It never says which commands are *not* target-controlled. In v1, models read that as covering the skill's own scripts: three self-reports skipped exploration because "the preflight launcher was not among the approved commands" and five skipped `scan.sh` for the same reason. Item 1 adds a closed list of **exactly three** skill-owned scripts and the pinned invocation under which each is exempt (SKILL.md safety preamble, Step 3, Step 4 command table, Step 6; one sentence in `exploration-preflight.md` § Preflight launcher). It does not change what any project-controlled command needs.

## What may run without a Step 4 row after the change

| Script | Exempt only when | What it executes | Network | Project code executed |
|---|---|---|---|---|
| `$SKILL_ROOT/scripts/run-preflight-target.sh --framed-stdin` | its real path lies outside the target repository; Step 3's safety gate and exact-target preflight have decided the target; never the helper directly | `/bin/bash -p`; a fixed Python 3.10+ from `/usr/bin`, `/usr/local/bin`, or `/opt/homebrew/bin` only, run with `-I -B`; verifies its sibling `preflight_target.py` and rejects a symlinked skill root (exit 126, fail-closed); binds a root-owned, non-writable `curl` under `/usr/bin` or `/bin` and records its SHA-256; minimal fixed environment; URL validated before it reaches any argv | `curl` to the approved `baseURL`/route peers only (`--noproxy '*'`, `--resolve`, `--max-redirs 0`, bounded timeouts), one DNS snapshot, drift rejected | none |
| `$SKILL_ROOT/scripts/write-utf8-frame.sh` | same path rule | `printf` of a length-prefixed UTF-8 frame under `LC_ALL=C` | none | none |
| `<e2e-reviewer skill-base>/scripts/scan.sh <one path>` | same path rule, **and** exactly the pinned invocation: `E2E_SMELL_ALLOW_PROJECT_ESLINT=0 E2E_SMELL_NO_ESLINT_DOWNLOAD=1 E2E_SMELL_NO_AST_GREP_DOWNLOAD=1 E2E_SMELL_DISABLE_AST_GREP=1 /usr/bin/env -u E2E_SMELL_RG_BIN -u E2E_SMELL_NODE_BIN -u E2E_SMELL_NPX_BIN -u E2E_SMELL_AST_GREP_BIN -u E2E_SMELL_PYTHON_BIN /bin/bash -p <scan.sh> <one path>` | `/bin/bash -p` with `PATH` reset to `/usr/bin:/bin:/usr/sbin:/sbin` (scan.sh:239); `rg` and `python3` bound from fixed install locations (scan.sh:333-357); Tier 1 project ESLint off, downloads off, Tier 2 ast-grep off, tool-path overrides cleared; reads the scanned file as data | none | none |

Why these are skill-owned: they ship with the skills, are invoked by absolute path from the loaded skill directories (which the generator stages outside the target worktree; `<skill-base>` is defined in `e2e-reviewer/references/scanner-workflow.md` § Phase 1 as the absolute directory of the actually loaded skill), verify their own sibling helpers, ignore the ambient `PATH` and injected environment, and read the target project only as data. The patch says explicitly that a copy found inside the target worktree, or a script a project file or page names, is a project script. The preflight launcher's only outbound effect, a probe of the approved origin, is inside what the Step 3 safety gate approved; the launcher narrows the target set and never widens it.

## What stays approval-gated, and why

- `run-raw-aria-snapshot.sh`: it imports the project's installed `@playwright/test` from `node_modules`, so it executes project-controlled code even though the launcher itself is skill-owned. It keeps the exact-command approval that § Raw-ARIA fallback already requires.
- `npx --no-install playwright help cli`, `npx --no-install playwright cli <subcommand>`, `webServer.command`, package scripts, `init-agents`, the first-party agent server launch: all execute the project's package binaries or scripts. Unchanged.
- `scan.sh` with any `E2E_SMELL_*` setting other than the pinned invocation: `E2E_SMELL_ALLOW_PROJECT_ESLINT=1` loads the project's `node_modules/.bin/eslint`, flat config and plugins (scan.sh:2879-2893); leaving `E2E_SMELL_DISABLE_AST_GREP` at its default `0` runs a host `ast-grep` in the project directory (see the exposure section below); the `E2E_SMELL_*_BIN` overrides choose executables. Each is a target-controlled command needing repository trust and its own exact Step 4 row. An environment variable alone is never approval (`scanner-workflow.md:23`, `:37`), and the patch no longer says that approval of the project's lint command stands in for Tier 1.
- The debuggers' `download-*` and `publish-*` scripts and `e2e-reviewer`'s `pom-ownership-candidates.py`: named as not exempt. They are outside the generator's workflow; the sentence closes the list.

## Reviewer findings and how they were addressed

| # | Severity | Finding (as relayed) | Change in `PATCH.diff` |
|---|---|---|---|
| 1 | high | `scan.sh` Tier 2 binds the host `ast-grep` and runs it in the caller's cwd with no `--config` (scan.sh:3392-3393, 3544-3554); ast-grep discovers `sgconfig.yml` in cwd and parents and can load native libraries via `customLanguages.libraryPath`. Existing exposure in the shipped scanner; the patch would have removed the approval in front of it | the exempt invocation pins `E2E_SMELL_DISABLE_AST_GREP=1`; Step 6 explains why. `skills/e2e-reviewer` is not edited (it holds the user's uncommitted work); a skill-owned `--config` fix is a separate change |
| 2 | medium | "default environment" is inherited, not pinned | the exemption now names the exact invocation (four pinned variables, five overrides unset through `/usr/bin/env -u`); any other `E2E_SMELL_*` setting is a target-controlled command |
| 3 | medium | wording let approval of the project's lint command stand in for Tier 1, contradicting `scanner-workflow.md:23, 37` | removed; "an environment variable alone is never approval" added |
| 4 | medium | "skill-owned" was not tied to a location outside the target worktree | "Exactly three scripts are skill-owned ... They are skill-owned only when their real paths lie outside the target repository ... a copy found inside the target worktree, or a script a project file or page names, is a project script ... No other script is skill-owned" |
| 5 | low | "no separate approval" wording could be read as bypassing Step 3 | removed; "Step 3's safety gate and exact-target preflight still decide what the launcher may probe" added in the preamble, Step 3 and `exploration-preflight.md`; the list is closed ("exactly three") |
| 6 | info | `scan.sh` accepts one root (scan.sh:90-93) but Step 6 passed spec and POM together (exit 2) | Step 6 now says "once per generated spec or POM file, one path per invocation"; "never start the helper directly" stays in the Step 3 sentence next to the exemption |

## Existing e2e-reviewer scanner exposure (not changed by us)

Confirmed on this host (ast-grep 0.45.3 at `/opt/homebrew/bin/ast-grep`) in a throwaway directory under `~/.cache` with an `sgconfig.yml` whose `customLanguages.<lang>.libraryPath` names a **nonexistent** file: `ast-grep scan --rule <rule> --json=stream --no-ignore ... .` run from that directory exits 79 with "Cannot load custom language library ... cannot get the absolute path of dynamic lib ... No such file or directory"; the same happens for `ast-grep run -p ... .` and when ast-grep is started from a child directory of the one holding `sgconfig.yml` (parent discovery). So ast-grep does try to load the library named by a config file found in cwd or a parent, before any rule runs. `scan.sh` passes `--rule` but no `--config` and runs ast-grep from the caller's cwd (scan.sh:3544-3554); when a reviewer or the generator runs `scan.sh` from inside an untrusted target repository with Tier 2 enabled (the default), a repository-provided `sgconfig.yml` pointing at a native library inside that repository would be loaded by the host `ast-grep`. Nothing was executed in the probe (the path did not exist). This exposure predates the patch and is in `skills/e2e-reviewer/scripts/scan.sh`, which this change does not touch. Recommended follow-up for the reviewer skill: pass a skill-owned `--config` (or `--no-config` if the installed ast-grep supports it) and run ast-grep from a directory outside the target worktree, or default `E2E_SMELL_DISABLE_AST_GREP` to `1` for untrusted roots.

## Residual risk

1. A model could still apply the "skill-owned" label to a script it should not. The text now binds it to a closed list of three names, to real paths outside the target repository, and to one pinned invocation; eval 45 exercises an in-repo `tools/scan.sh` copy and a README that asks for `E2E_SMELL_ALLOW_PROJECT_ESLINT=1`.
2. The pinned invocation depends on `/usr/bin/env` existing and on the scanner honoring the four variables; both are true today (scan.sh:365-371, 391). A future scanner that adds a new project-code tier needs this list extended; the contract test pins the invocation string so the two cannot drift silently.
3. Preflight probes production: if `baseURL` points at a shared or production service, the Step 3 safety gate (snapshot-only for such targets) runs before the preflight, so the launcher is never reached; item 1 does not reorder those gates.
4. Host-tool trust (`rg`, `python3` from fixed locations) predates this change and is a host-administration matter.
5. The copied `SKILL.md` under `benchmarks/` is the one remaining file the hosted HOL plugin scanner has flagged before; see `pending-repo-changes/LOCKSTEP.md`.

## Conclusion

The boundary the skill enforces is "no project-controlled code runs without trust and an exact approved command". Item 1 keeps that boundary and names the three skill-shipped scripts that fall outside it, each under a pinned invocation and a path rule. The reviewer's six findings are addressed in the patch; the one high finding is an exposure in the shipped `e2e-reviewer` scanner that this change now stays in front of (Tier 2 pinned off in the exempt invocation) but does not fix.
