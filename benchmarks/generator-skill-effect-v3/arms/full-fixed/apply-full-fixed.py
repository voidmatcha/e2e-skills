#!/usr/bin/env python3
"""Apply the full-fixed edits (items 1-6) to a copy of skills/playwright-test-generator.

Usage: apply-full-fixed.py <skill-dir>
Every replacement must match exactly once; otherwise the script aborts without writing.
"""
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
edits: dict[str, list[tuple[str, str, str]]] = {}


def edit(file: str, item: str, old: str, new: str) -> None:
    edits.setdefault(file, []).append((item, old, new))


# ---------------------------------------------------------------- SKILL.md
edit("SKILL.md", "item1-scope",
     "Before any target-controlled command—including a project script, config loader, package binary, or Node import—require repository trust and explicit approval of the exact command.\n",
     "Before any target-controlled command—including a project script, config loader, package binary, or Node import—require repository trust and explicit approval of the exact command.\n"
     "\n"
     "Exactly three scripts are skill-owned: `$SKILL_ROOT/scripts/run-preflight-target.sh`, `$SKILL_ROOT/scripts/write-utf8-frame.sh`, and `<e2e-reviewer skill-base>/scripts/scan.sh`, where `<e2e-reviewer skill-base>` is the absolute directory of the actually loaded `e2e-reviewer` skill as its `references/scanner-workflow.md` § Phase 1 defines `<skill-base>`. They are skill-owned only when their real paths lie outside the target repository: a copy found inside the target worktree, or a script a project file or page names, is a project script. Run under the pinned invocations Step 3 and Step 6 give, they execute no project code and need no Step 4 row; Step 3's safety gate and exact-target preflight still decide what the launcher may probe. No other script is skill-owned: `run-raw-aria-snapshot.sh` is the exception among the skill's own scripts because it imports the project's installed Playwright and keeps the exact-command approval `exploration-preflight.md` § Raw-ARIA fallback requires; the debuggers' `download-*` and `publish-*` scripts and `e2e-reviewer`'s `pom-ownership-candidates.py` are not exempt; and `scan.sh` run with any `E2E_SMELL_*` setting other than Step 6's pinned invocation is a target-controlled command that needs repository trust and its own exact Step 4 row.\n")

edit("SKILL.md", "item1-step3",
     "Before running the exact-target preflight, read `exploration-preflight.md` §§ Preflight launcher and Frame writer and follow them in full.\n",
     "Before running the exact-target preflight, read `exploration-preflight.md` § Preflight launcher and `exploration-preflight.md` § Frame writer and follow them in full. The launcher and the frame writer are skill-owned scripts: they need no Step 4 row, Step 3's safety gate and exact-target preflight still decide what they may probe, and never start the helper directly.\n")

edit("SKILL.md", "item6-guard-pointer",
     "Before starting `webServer`, authenticating, or choosing/running a browser source, read `exploration-preflight.md` §§ Browser source selection and containment and Guard for Playwright CLI in full.",
     "Before starting `webServer`, authenticating, or choosing/running a browser source, read `exploration-preflight.md` §§ Browser source selection and containment and Guard for Playwright CLI in full. Before opening a Playwright CLI session, read `exploration-preflight.md` § Guard for Playwright CLI and follow it exactly.")

edit("SKILL.md", "item1-step4-table",
     "A command the user supplied directly for this task may be recorded as already approved.\n",
     "A command the user supplied directly for this task may be recorded as already approved. The three skill-owned scripts (the preflight launcher, the frame writer, and `scan.sh` under its pinned Step 6 invocation) are not rows in this table; `run-raw-aria-snapshot.sh`, every project package binary, and any `scan.sh` run with other `E2E_SMELL_*` settings are.\n")

edit("SKILL.md", "item3-step6",
     "Invoke the `e2e-reviewer` skill (same bundle) with the `Skill` tool on the generated spec and POM files. If the `Skill` tool cannot invoke it but its files exist, as on a Codex install, do **not** downgrade to scanner-only: read `<e2e-reviewer skill-base>/SKILL.md` and run its full Phase 1–2 procedure inline on the spec **and** POM paths, keeping the Phase 2 LLM review and the zero-P0 gate. Fall back to a manual P0 pass (always-true/weak assertions, missing `await`, focused tests) **only** when the e2e-reviewer files are absent entirely, and state the review ran in reduced form. Never silently skip it.\n",
     "Run the bundled mechanical scanner (`e2e-reviewer` Phase 1) once per generated spec or POM file, one path per invocation, under exactly this pinned invocation: `E2E_SMELL_ALLOW_PROJECT_ESLINT=0 E2E_SMELL_NO_ESLINT_DOWNLOAD=1 E2E_SMELL_NO_AST_GREP_DOWNLOAD=1 E2E_SMELL_DISABLE_AST_GREP=1 /usr/bin/env -u E2E_SMELL_RG_BIN -u E2E_SMELL_NODE_BIN -u E2E_SMELL_NPX_BIN -u E2E_SMELL_AST_GREP_BIN -u E2E_SMELL_PYTHON_BIN /bin/bash -p <e2e-reviewer skill-base>/scripts/scan.sh <one spec or POM path>`. Under exactly this invocation the scanner is a skill-owned tool and needs no Step 4 row: Tier 1 project ESLint and every download are off, Tier 2 is off because a host `ast-grep` running in the project directory honors a project-provided `sgconfig.yml`, and tool-path overrides are cleared. Any other `E2E_SMELL_*` setting is a target-controlled command that needs repository trust and its own exact Step 4 row; an environment variable alone is never approval. The Phase 2 LLM review runs once, by the V6 reviewer in Step 7, which applies `<e2e-reviewer skill-base>/SKILL.md` in full with the zero-P0 gate: a writer-side Phase 2 cannot count toward V6 and only repeats that work, so while a separate reviewer actor is available do not run it here and do not invoke `e2e-reviewer` through the `Skill` tool from the writer context. Only when no separate reviewer actor exists (V6 will be `CANNOT_VERIFY`), read `<e2e-reviewer skill-base>/SKILL.md` and run its Phase 2 inline on the spec **and** POM paths so its findings still reach the report; that inline review changes no V6 verdict. Fall back to a manual P0 pass (always-true/weak assertions, missing `await`, focused tests) **only** when the e2e-reviewer files are absent entirely, and state the review ran in reduced form. Never silently skip it.\n")

edit("SKILL.md", "item3-step6-bullet",
     "- **P0 issues found:** fix immediately, re-invoke `e2e-reviewer`. **Max 3\n",
     "- **P0 issues found:** fix immediately, rerun the scanner. **Max 3\n")

edit("SKILL.md", "item5-step7",
     "Apply V1–V6 in order as `verification-rules.md` requires; V6 needs a distinct fresh-context, read-only reviewer actor or process, and inline self-review cannot pass it.\n",
     "Apply V1–V6 in order as `verification-rules.md` requires; V6 needs a distinct fresh-context, read-only reviewer actor or process, and inline self-review cannot pass it. `verification-rules.md` § V6 says how to obtain that reviewer on each host and the verdict line to quote. A V2 or V3 probe that was not run is `CANNOT_VERIFY` with the reason `not attempted: <why>`; V2 and V3 `CANNOT_VERIFY` are reported and never block `Complete`, while applicable V4, V5, and V6 must be `PASS`.\n")

# ---------------------------------------------------- verification-rules.md
edit("verification-rules.md", "item5-v2",
     "Return `ERROR` or `CANNOT_VERIFY`, never `PASS`, when the mutant run is red but its output does not prove failure at the changed primary assertion.\n",
     "Return `ERROR` or `CANNOT_VERIFY`, never `PASS`, when the mutant run is red but its output does not prove failure at the changed primary assertion.\n"
     "\n"
     "A V2 probe that was not run is recorded as `CANNOT_VERIFY` with the reason `not attempted: <why>`. Like every V2 `CANNOT_VERIFY`, it is reported and does not block `Complete`; it is never omitted silently, and `FAIL` is reserved for a probe that ran.\n")

edit("verification-rules.md", "item5-v3",
     "This per-scenario runtime declaration is not the `generator-faultkill-v1` planning DSL and does not change that benchmark's frozen plan language.\n",
     "This per-scenario runtime declaration is not the `generator-faultkill-v1` planning DSL and does not change that benchmark's frozen plan language.\n"
     "\n"
     "A V3 probe that was not run is recorded as `CANNOT_VERIFY` with the reason `not attempted: <why>`; it is reported and does not block `Complete`.\n")

edit("verification-rules.md", "item5-v4",
     "Optimistic DOM state alone is not write success.\n",
     "Optimistic DOM state alone is not write success.\n"
     "\n"
     "**Failed-write procedure.** The injection never edits the application or the source candidate. In a temporary copy of the scenario under the approved targeted `<spec>` slot, register `page.route()` for the write endpoint before the action and fulfill it with a failure the product can receive (for example status `500`, or the app's documented error body), then run the repository-native targeted command. `PASS` requires both halves: the normal run's request proof (method, endpoint, payload, cardinality) and the injected run turning red at the unchanged primary assertion or declared settled-state gate. Record them as two evidence lines. Request proof without the injected failure is `CANNOT_VERIFY` with the reason `not attempted: failed-write injection`, which blocks `Complete` because V4 is applicable. Remove the copy afterwards as § Temporary-copy safety requires.\n")

edit("verification-rules.md", "item2-v6",
     "Return `CANNOT_VERIFY` when the host cannot provide a separate reviewer context or cannot keep that reviewer read-only.\n",
     "Return `CANNOT_VERIFY` when the host cannot provide a separate reviewer context or cannot keep that reviewer read-only.\n"
     "\n"
     "**Obtaining the reviewer.** On Claude Code, spawn one subagent with the `Agent` tool whose tools are limited to reading and running the scanner (for example the read-only `Explore` type, or a general agent told that it must not edit); on Codex, use a named `.codex/agents` reviewer or `spawn_agent`; on another host, any process that starts with a fresh context and did not write or repair the candidate qualifies, including a second CLI session the user starts on request. Give it only the candidate paths, the project root, the absolute path of `<e2e-reviewer skill-base>/SKILL.md`, the approved scenario plan, and the instruction to end its report with the single line `V6 VERDICT: <PASS|FAIL> P0=<n> P1=<n> P2=<n> reviewer=<id>`, where `<id>` is the host's agent or session identifier. Do not pass the writer's conclusions. Quote that line verbatim in the completion report. A reviewer that could not run the scanner still produces a verdict from its Phase 2 review; record the reduction beside it. The spawned reviewer is distinct and fresh-context when its context holds nothing the writer produced except the candidate files and the plan; the host need not prove isolation beyond that. When the host offers no way to start such an actor, return `CANNOT_VERIFY`; never substitute inline review.\n")

edit("verification-rules.md", "item6-heading-remove",
     "## Structured result contract\n\n## Completion and write-set reconciliation\n",
     "## Completion and write-set reconciliation\n")

edit("verification-rules.md", "item6-heading-insert",
     "Record the result in this shape so an omitted or unavailable proof is visible rather than silently treated as a pass:\n",
     "## Structured result contract\n\nRecord the result in this shape so an omitted or unavailable proof is visible rather than silently treated as a pass:\n")

# ------------------------------------------------- exploration-preflight.md
edit("exploration-preflight.md", "item6-skillmd-typo",
     "Use the bundled deterministic validator rather than judging IP ranges from prose. `$SKILL_ROOT` is the absolute path of the directory that contains this SKILL.md. `BASE_URL` is the approved `baseURL` from Step 1, and `TARGET_URL` is the exact `<baseURL>/<target-path>` URL selected for exploration:",
     "Use the bundled deterministic validator rather than judging IP ranges from prose. `TARGET_URL` is the exact `<baseURL>/<target-path>` URL selected for exploration:")

edit("exploration-preflight.md", "item1-launcher-owned",
     "The `/bin/bash -p` launcher ignores ambient `PATH`, shell/Python injection, and selects a fixed external Python 3.10+ for isolated `-I -B` execution.",
     "The launcher and its frame writer are skill-owned scripts that execute no project code; they need no Step 4 row, while Step 3's safety gate and exact-target preflight still decide what they may probe. The `/bin/bash -p` launcher ignores ambient `PATH`, shell/Python injection, and selects a fixed external Python 3.10+ for isolated `-I -B` execution.")

edit("exploration-preflight.md", "item6-selfref-frame",
     "Use `write-utf8-frame.sh` for every framed value; see `exploration-preflight.md` § Frame writer.",
     "Use `write-utf8-frame.sh` for every framed value; see § Frame writer below.")

edit("exploration-preflight.md", "item6-dup-recap",
     "The launcher picks a fixed Python 3.10+ from `/usr/bin/python3`, `/usr/local/bin/python3`, `/opt/homebrew/bin/python3` (in that order), binds a root-owned curl, pins a single approved DNS snapshot, and rejects drift; details in `exploration-preflight.md` § Preflight launcher. If none qualifies, the launcher exits 126: treat that as a terminal preflight failure, launch no browser, and ask for a user-provided snapshot; never substitute ambient `python3` or start the helper directly.\n",
     "Recap: the launcher picks a fixed Python 3.10+ from `/usr/bin/python3`, `/usr/local/bin/python3`, `/opt/homebrew/bin/python3` (in that order), binds a root-owned curl, pins a single approved DNS snapshot, and rejects drift, as described at the top of this section; exit 126 is the terminal preflight failure described there.\n")

edit("exploration-preflight.md", "item6-empty-guard-heading",
     "## Guard for Playwright CLI\n\n## Browser source selection and containment\n",
     "## Browser source selection and containment\n")

edit("exploration-preflight.md", "item6-selfref-rationale",
     "Never let `npx` download a package during exploration (rationale: `exploration-preflight.md`).",
     "Never let `npx` download a package during exploration (rationale: § Why Playwright CLI is the default).")

edit("exploration-preflight.md", "item6-selfref-guard-summary",
     "**Guard for Playwright CLI.** Before opening a session, read `exploration-preflight.md` § Guard for Playwright CLI and follow it exactly: an origin allowlist config",
     "**Guard for Playwright CLI.** Before opening a session, apply § Guard for Playwright CLI below exactly: an origin allowlist config")

edit("exploration-preflight.md", "item6-guard-heading-insert",
     "**Guard for Playwright CLI.** Its `route` command only fulfills requests",
     "## Guard for Playwright CLI\n\n**Guard for Playwright CLI.** Its `route` command only fulfills requests")

# ------------------------------------------------------------ code-rules.md
edit("code-rules.md", "item4-tier8",
     "8. CSS class — **POM files only**, stable structural classes only (not styling classes)\n",
     "8. CSS `#id` / `.class` — last resort, `// JUSTIFIED:` required (see **Text-bearing elements without a role, label, or test id** below); stable structural attributes only, never styling classes\n")

edit("code-rules.md", "item4-text-only",
     "Never use XPath. Never use CSS class chains that couple to styling.\n",
     "**Text-bearing elements without a role, label, or test id.** A counter, status line, badge, or list cell often has visible text but no role, label, or test id. Locate it by that text, `getByText('0 entries')` or an anchored pattern such as `getByText(/^\\d+ entries?$/)`, or scope from a labeled ancestor, `getByRole('list', { name: 'Records' }).getByRole('listitem').filter({ hasText: 'Record 1' })`. Do not reach for `locator('#gb-count')` or `locator('.title')` because the element lacks a role: a behavior-preserving markup refactor renames ids and classes while roles, labels, and visible text stay, so an id or class selector fails exactly the refactor the test should survive. When the text may repeat, scope it with a role-based ancestor instead of `.nth()`. `#id` and `.class` selectors need `// JUSTIFIED: <reason>` on the line above, except when the project's Playwright config sets `testIdAttribute` to that attribute or its conventions doc documents the id or class scheme as the locator convention; record either exception in the Locator Mapping Table.\n"
     "\n"
     "Never use XPath. Never use CSS class chains that couple to styling.\n")

edit("code-rules.md", "item4-suppression",
     "- `.nth()` / `.first()` / `.last()` — explain why positional selection is required\n",
     "- `.nth()` / `.first()` / `.last()` — explain why positional selection is required\n"
     "- `#id` / `.class` selectors — explain why no role, label, test id, or visible text locates the element\n")

# ------------------------------------------------------- best-practices.md
edit("best-practices.md", "item4-table",
     "| Chain + filter | `getByRole('listitem').filter({ hasText: 'X' }).getByRole('button')` to scope without positional `.nth()`. |\n",
     "| Chain + filter | `getByRole('listitem').filter({ hasText: 'X' }).getByRole('button')` to scope without positional `.nth()`. |\n"
     "| Text-only elements | A counter or status line with no role or label is located by its visible text (`getByText(/^\\d+ entries?$/)`) or from a labeled ancestor, not by `#id` or `.class`: a markup refactor renames those and keeps the text. |\n")

# ------------------------------------------------------- scenario-design.md
edit("scenario-design.md", "item4-mapping-rule",
     "- `.nth()`, `.first()`, `.last()` require `// JUSTIFIED: <reason>` on the line immediately above\n",
     "- `.nth()`, `.first()`, `.last()` require `// JUSTIFIED: <reason>` on the line immediately above\n"
     "- `#id` and `.class` selectors require the same `// JUSTIFIED:` line unless the project configures `testIdAttribute` for that attribute or documents the scheme; record the visible text or ancestor role that was tried first (`code-rules.md` § Selector Priority)\n")

# --------------------------------------------------- conventions-template.md
edit("conventions-template.md", "item4-template",
     "- Last resort: `data-testid`. Raw CSS chains / XPath: forbidden.\n",
     "- Last resort: `data-testid`. Text-only elements (counters, status lines): `getByText` or a labeled ancestor. Raw CSS `#id`/`.class`: `// JUSTIFIED:` only. XPath: forbidden.\n")

# ---------------------------------------------------------------- apply
problems = []
staged = {}
for file, items in edits.items():
    path = root / file
    text = path.read_text(encoding="utf-8")
    for item, old, new in items:
        count = text.count(old)
        if count != 1:
            problems.append(f"{file} [{item}]: expected 1 match, found {count}")
            continue
        text = text.replace(old, new, 1)
    staged[path] = text
if problems:
    print("\n".join(problems), file=sys.stderr)
    sys.exit(1)
for path, text in staged.items():
    path.write_text(text, encoding="utf-8")
print(f"applied {sum(len(v) for v in edits.values())} edits to {len(edits)} files under {root}")
