#!/usr/bin/env python3
"""Copy the v2 pool tasks (except the two whose fixtures v2 found defective, replaced by v3-13 and v3-14) into the v3 work dir.

The refactor edit lists are normalized so that wrappers add no landmark role: aside/nav/header/footer/fieldset wrappers introduced by
the v2 refactors become div wrappers. Roles, labels and text are otherwise untouched; `validate` proves ARIA equality afterwards.
"""
import json, os, re, shutil, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "benchmarks" / "generator-skill-effect-v2"
DST = Path(os.environ.get("GSE3_WORK_DIR") or Path(__file__).resolve().parent)  # the v3 directory itself, or the pre-GO work dir
SKIP = {"v2-02", "v2-03"}
WRAPPERS = ("aside", "nav", "header", "footer", "fieldset")


def normalize(text: str) -> str:
    for tag in WRAPPERS:
        text = re.sub(rf"<{tag}( class=\"[^\"]*\")>", r"<div\1>", text)
        text = text.replace(f"</{tag}>", "</div>")
    return text


def main() -> int:
    copied = []
    for case_dir in sorted((SRC / "cases").iterdir()):
        case = case_dir.name
        if not case.startswith("v2-") or case in SKIP:
            continue
        dst_case = DST / "cases" / case
        if dst_case.exists():
            shutil.rmtree(dst_case)
        shutil.copytree(case_dir, dst_case)
        truth = json.loads((SRC / "truth" / f"{case}.json").read_text())
        for edit in truth["refactor"]:
            edit["replace"] = normalize(edit["replace"])
            edit["find"] = normalize(edit["find"]) if any(f"<{t}" in edit["find"] for t in WRAPPERS) else edit["find"]
        (DST / "truth" / f"{case}.json").write_text(json.dumps(truth, indent=2) + "\n")
        dst_truth = DST / "truth" / case
        if dst_truth.exists():
            shutil.rmtree(dst_truth)
        shutil.copytree(SRC / "truth" / case, dst_truth)
        copied.append(case)
    print(json.dumps({"copied": copied, "count": len(copied)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
