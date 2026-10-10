#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build a feature-only #13 lead-collector ablation for a development pilot."""

import argparse
import difflib
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "skills/e2e-reviewer"


def digest(root: Path) -> str:
    value = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            value.update(path.relative_to(root).as_posix().encode())
            value.update(b"\0")
            value.update(path.read_bytes())
    return value.hexdigest()


def replace_once(path: Path, old: str, new: str) -> None:
    source = path.read_text()
    if source.count(old) != 1:
        raise ValueError(f"expected one ablation anchor in {path}: found {source.count(old)}")
    path.write_text(source.replace(old, new))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new directory for the control skill")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        parser.error("output must not exist")
    if (output.parent / "arm-diff.patch").exists() or (output.parent / "arm-manifest.json").exists():
        parser.error("arm diff or manifest already exists beside output")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SOURCE, output)

    replace_once(
        output / "SKILL.md",
        "**#13 ownership leads:** Phase 1 automatically emits exact-selector leads for named Cypress specs under `cypress/e2e/`, using regular sibling `cypress/support/` and `cypress/pageobjects/` directories when present. For other reviewed specs with raw selector-based UI actions, run the bundled collector when an in-scope POM/support directory exists; see `references/semantic-review.md` § #13 ownership discovery. Leads are never findings or a substitute for the LLM-only #13 check; zero or incomplete output does not clear #13.\n",
        "**#13 ownership review:** Compare raw UI actions with established same-page POM interactions under the LLM-only #13 contract; see `references/semantic-review.md` § #13 ownership discovery.\n",
    )
    replace_once(
        output / "references/semantic-review.md",
        "**#13 ownership discovery:** For #13 on every reviewed spec, compare raw UI workflows with POM/helper interactions already used by that spec, regardless of scanner hits. The Phase 1 scanner emits leads for named `cypress/e2e/` specs. For other specs with raw selector-based actions, run the read-only collector when a POM/support root exists:\n\n```bash\npython3 <skill-base>/scripts/pom-ownership-candidates.py --spec <spec-file> --context-root <pom-or-support-dir>\n```\n\nUse the loaded collector and nearest POM/support root; do not run target code. It covers literal `cy.get`, `cy.getByTestId`, `page.locator`, and `page.getByTestId` actions, plus simple Cypress options and chains; zero leads or `INCOMPLETE` never clears #13. Automatic Cypress roots are sibling `support`/`pageobjects` directories, not repository-wide. Trace POM calls and inspect methods. Resolve selector fields or aliases to their declarations; the method body alone does not prove equivalence. Compare action order, page context, and outcome. Inspect same-spec POM calls for computed selectors or a missing root. A lead is not a verdict: cite the first raw action and equivalent POM source only when confirmed. An intentional failure path need not reuse a success helper.\n",
        "**#13 ownership discovery:** For #13 on every reviewed spec, compare raw UI workflows with POM/helper interactions already used by that spec. Trace POM calls through imports or registries, resolve selector fields or aliases to their declarations, and compare action order, page context, and intended outcome under the #13 ownership test. Cite the first raw action and equivalent POM source only when confirmed. A success-path helper need not replace an intentional failure-path action.\n",
    )
    replace_once(
        output / "scripts/scan.sh",
        "# A named Cypress spec can have a source-established POM boundary even when no\n# single-file regex sees it. Surface exact-selector cross-file leads from the\n# sibling support/pageobjects directories in the\n# mandatory Phase 1 output; #13 remains LLM-only and these leads do not affect\n# the mechanical counts or exit gate. A failed lead pass is incomplete, not clean.\nif [[ \"$REQUESTED_ROOT_KIND\" == file && \"$ROOT\" == */cypress/e2e/* ]]; then\n  if ! \"$PYTHON3_BIN\" -I -B \"$SCANNER_DIR_REAL/pom-ownership-candidates.py\" \\\n      --spec \"$ROOT\" --auto-cypress-support --format scanner; then\n    printf 'INCOMPLETE: #13 ownership lead collection failed\\n' >&2\n    exit 2\n  fi\nfi\n\n",
        "",
    )
    (output / "scripts/pom-ownership-candidates.py").unlink()

    allowed = {
        "SKILL.md",
        "references/semantic-review.md",
        "scripts/scan.sh",
        "scripts/pom-ownership-candidates.py",
    }
    files = {p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*") if p.is_file()}
    files |= {p.relative_to(output).as_posix() for p in output.rglob("*") if p.is_file()}
    changed = []
    patch = []
    for relative in sorted(files):
        before = SOURCE / relative
        after = output / relative
        a = before.read_text().splitlines(keepends=True) if before.exists() else []
        b = after.read_text().splitlines(keepends=True) if after.exists() else []
        if a != b:
            changed.append(relative)
            patch.extend(difflib.unified_diff(a, b, fromfile=f"treatment/{relative}", tofile=f"control/{relative}"))
    if set(changed) != allowed:
        raise ValueError(f"unexpected arm differences: {changed}")
    manifest = {
        "status": "development-pilot-ablation",
        "treatment_sha256": digest(SOURCE),
        "control_sha256": digest(output),
        "changed_files": changed,
    }
    (output.parent / "arm-diff.patch").write_text("".join(patch))
    (output.parent / "arm-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
