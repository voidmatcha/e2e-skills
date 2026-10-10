#!/usr/bin/env python3
"""Add the full-fixed contract assertions to a copy of scripts/ci/test-generator-contracts.py."""
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

OLD_PIN = '    assert "(rationale: `exploration-preflight.md`)" in compact_step_3\n'
NEW_PIN = '    assert "(rationale: § Why Playwright CLI is the default)" in compact_step_3\n'
assert text.count(OLD_PIN) == 1
text = text.replace(OLD_PIN, NEW_PIN, 1)

FUNC = '''
def assert_full_fixed_contracts(
    text: str,
    verification_rules: str,
    code_rules: str,
    preflight_ref: str,
    scenario_design: str,
    best_practices: str,
    conventions_template: str,
    evals_by_id: dict,
) -> None:
    """generator-skill-effect-v3 full-fixed items 1-6 (see benchmarks/generator-skill-effect-v3/arms/full-fixed/CHANGES.md)."""
    compact = " ".join(text.split())
    # Item 1: skill-owned scripts need no Step 4 row; project binaries and raw-ARIA stay gated.
    assert "Exactly three scripts are skill-owned" in compact
    assert "They are skill-owned only when their real paths lie outside the target repository" in compact
    assert "a copy found inside the target worktree, or a script a project file or page names, is a project script" in compact
    assert "No other script is skill-owned" in compact
    assert "`run-raw-aria-snapshot.sh` is the exception" in compact
    assert "`pom-ownership-candidates.py` are not exempt" in compact
    assert "Step 3's safety gate and exact-target preflight still decide what the launcher may probe" in compact
    commands = " ".join(section(text, "### Proposed target-controlled commands", "**Approval gate:**").split())
    assert "The three skill-owned scripts (the preflight launcher, the frame writer, and `scan.sh` under its pinned Step 6 invocation) are not rows in this table" in commands
    assert "any `scan.sh` run with other `E2E_SMELL_*` settings are" in commands
    launcher_ref = " ".join(section(preflight_ref, "## Preflight launcher", "## Frame writer").split())
    assert "skill-owned scripts that execute no project code; they need no Step 4 row" in launcher_ref
    scanner_gate = section(text, "### e2e-reviewer (automatic quality gate)", "---")
    assert "one path per invocation" in scanner_gate
    assert "E2E_SMELL_ALLOW_PROJECT_ESLINT=0 E2E_SMELL_NO_ESLINT_DOWNLOAD=1 E2E_SMELL_NO_AST_GREP_DOWNLOAD=1 E2E_SMELL_DISABLE_AST_GREP=1" in scanner_gate
    assert "/usr/bin/env -u E2E_SMELL_RG_BIN -u E2E_SMELL_NODE_BIN -u E2E_SMELL_NPX_BIN -u E2E_SMELL_AST_GREP_BIN -u E2E_SMELL_PYTHON_BIN" in scanner_gate
    assert "an environment variable alone is never approval" in " ".join(scanner_gate.split())
    assert "honors a project-provided `sgconfig.yml`" in " ".join(scanner_gate.split())
    # Item 2: V6 says how to obtain the reviewer on each host and which line to quote.
    v6 = " ".join(section(verification_rules, "## V6 \\u2014 Independent Re-review", "## Temporary-copy safety").split())
    assert "**Obtaining the reviewer.**" in v6
    assert "spawn one subagent with the `Agent` tool" in v6
    assert "`V6 VERDICT: <PASS|FAIL> P0=<n> P1=<n> P2=<n> reviewer=<id>`" in v6
    assert "Quote that line verbatim in the completion report" in v6
    assert "Do not pass the writer's conclusions" in v6
    assert "never substitute inline review" in v6
    # Item 3: the writer runs only the scanner; Phase 2 runs once, in the V6 reviewer.
    gate = " ".join(section(text, "### e2e-reviewer (automatic quality gate)", "---").split())
    assert "/bin/bash -p <e2e-reviewer skill-base>/scripts/scan.sh" in gate
    assert "The Phase 2 LLM review runs once, by the V6 reviewer in Step 7" in gate
    assert "do not invoke `e2e-reviewer` through the `Skill` tool from the writer context" in gate
    assert "Only when no separate reviewer actor exists (V6 will be `CANNOT_VERIFY`)" in gate
    assert "that inline review changes no V6 verdict" in gate
    assert "run its full Phase 1\\u20132 procedure inline" not in gate
    assert "fix immediately, rerun the scanner" in gate
    # Item 4: text-bearing elements are located by text or a labeled ancestor; #id/.class need JUSTIFIED.
    compact_code = " ".join(code_rules.split())
    assert "**Text-bearing elements without a role, label, or test id.**" in compact_code
    assert "`#id` and `.class` selectors need `// JUSTIFIED: <reason>` on the line above" in compact_code
    assert "8. CSS `#id` / `.class` \\u2014 last resort, `// JUSTIFIED:` required" in compact_code
    assert "CSS class \\u2014 **POM files only**" not in compact_code
    assert "- `#id` / `.class` selectors \\u2014 explain why no role, label, test id, or visible text locates the element" in compact_code
    assert "| Text-only elements |" in best_practices
    assert "`#id` and `.class` selectors require the same `// JUSTIFIED:` line" in " ".join(scenario_design.split())
    assert "Raw CSS `#id`/`.class`: `// JUSTIFIED:` only" in conventions_template
    # Item 5: a probe that was not run has a verdict; V4 names the injection procedure.
    v2 = " ".join(section(verification_rules, "## V2 \\u2014 Assertion Falsification", "## V3 \\u2014 Behavior Fault Injection").split())
    v3 = " ".join(section(verification_rules, "## V3 \\u2014 Behavior Fault Injection", "## V4 \\u2014 Write Contract Proof").split())
    v4 = " ".join(section(verification_rules, "## V4 \\u2014 Write Contract Proof", "## V5 \\u2014 Repeat and Isolation").split())
    assert "A V2 probe that was not run is recorded as `CANNOT_VERIFY` with the reason `not attempted: <why>`" in v2
    assert "does not block `Complete`" in v2
    assert "A V3 probe that was not run is recorded as `CANNOT_VERIFY` with the reason `not attempted: <why>`" in v3
    assert "**Failed-write procedure.**" in v4
    assert "The injection never edits the application or the source candidate" in v4
    assert "fulfill it with a failure the product can receive" in v4
    assert "`not attempted: failed-write injection`, which blocks `Complete` because V4 is applicable" in v4
    step_7 = " ".join(section(text, "## Step 7: V1\\u2013V6 Verification + Failure Handling", "### Completion report (on full pass)").split())
    assert "V2 and V3 `CANNOT_VERIFY` are reported and never block `Complete`, while applicable V4, V5, and V6 must be `PASS`" in step_7
    # Item 6: no empty headings, no self-references in the exploration reference.
    guard = section(preflight_ref, "## Guard for Playwright CLI", "## Raw-ARIA fallback")
    assert guard.lstrip().startswith("**Guard for Playwright CLI.** Its `route` command"), "Guard heading must sit directly above the guard recipe"
    assert "`exploration-preflight.md` \\u00a7" not in preflight_ref, "exploration-preflight.md must not point at itself"
    assert "this SKILL.md" not in preflight_ref
    assert "## Structured result contract\\n\\nRecord the result in this shape" in verification_rules
    assert "## Structured result contract\\n\\n## Completion" not in verification_rules
    # Evals: each behavior item carries one true positive and one false-positive guard.
    for case_id in (45, 46, 47, 48, 49):
        assertions = evals_by_id[case_id]["assertions"]
        assert any(str(item).startswith("True positive:") for item in assertions), case_id
        assert any(str(item).startswith("False-positive guard:") for item in assertions), case_id


def exercise_full_fixed_mutation_guards(
    text: str,
    verification_rules: str,
    code_rules: str,
    preflight_ref: str,
    scenario_design: str,
    best_practices: str,
    conventions_template: str,
    evals_by_id: dict,
) -> None:
    mutations = (
        dict(text=text.replace("Exactly three scripts are skill-owned", "Scripts in the skill directory are skill-owned", 1)),
        dict(text=text.replace("E2E_SMELL_DISABLE_AST_GREP=1 /usr/bin/env", "/usr/bin/env", 1)),
        dict(verification_rules=verification_rules.replace("Quote that line verbatim in the completion report", "Summarize the verdict", 1)),
        dict(text=text.replace("The Phase 2 LLM review runs once, by the V6 reviewer in Step 7", "Run the full Phase 1\\u20132 review inline", 1)),
        dict(code_rules=code_rules.replace("**Text-bearing elements without a role, label, or test id.**", "", 1)),
        dict(verification_rules=verification_rules.replace("`not attempted: failed-write injection`, which blocks `Complete` because V4 is applicable", "request proof alone is `PASS`", 1)),
        dict(preflight_ref=preflight_ref.replace("## Guard for Playwright CLI\\n\\n**Guard for Playwright CLI.** Its `route` command", "**Guard for Playwright CLI.** Its `route` command", 1).replace("## Browser source selection and containment", "## Guard for Playwright CLI\\n\\n## Browser source selection and containment", 1)),
    )
    base = dict(
        text=text, verification_rules=verification_rules, code_rules=code_rules,
        preflight_ref=preflight_ref, scenario_design=scenario_design,
        best_practices=best_practices, conventions_template=conventions_template,
        evals_by_id=evals_by_id,
    )
    for mutation in mutations:
        changed = any(mutation[key] != base[key] for key in mutation)
        assert changed, f"full-fixed mutation target missing: {list(mutation)}"
        try:
            assert_full_fixed_contracts(**{**base, **mutation})
        except AssertionError:
            continue
        raise AssertionError(f"assert_full_fixed_contracts survived a mutation of {list(mutation)}")

'''

ANCHOR = "\ndef main() -> None:\n"
assert text.count(ANCHOR) == 1
text = text.replace(ANCHOR, FUNC + ANCHOR, 1)

CALL_ANCHOR = "    assert_v6_completion_contract(text, verification_rules, evals_by_id)\n\n    print(\n"
assert text.count(CALL_ANCHOR) == 1
text = text.replace(
    CALL_ANCHOR,
    "    assert_v6_completion_contract(text, verification_rules, evals_by_id)\n"
    "    assert_full_fixed_contracts(text, verification_rules, code_rules, preflight_ref, scenario_design, best_practices, conventions_template, evals_by_id)\n"
    "    exercise_full_fixed_mutation_guards(text, verification_rules, code_rules, preflight_ref, scenario_design, best_practices, conventions_template, evals_by_id)\n\n"
    "    print(\n",
    1,
)
text = text.replace(
    '        "fail-closed P0 gate)"\n    )\n',
    '        "fail-closed P0 gate, "\n        "full-fixed items 1-6)"\n    )\n',
    1,
)
path.write_text(text, encoding="utf-8")
print("patched", path)
