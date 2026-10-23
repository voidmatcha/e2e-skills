#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Opt-in, source-checkout-only fixed E2E fault pilot. No arbitrary commands."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[3]
PILOT = REPO / "scripts/evals/hybrid-check-pilot/check-docker-matrix"
ADAPTERS = {
    "notepad-playwright-v2": PILOT.parent / "reviewer-evidence-v2/notepad_adapter_v2.py",
    "passport-cypress-v1": PILOT / "passport_adapter_v1.py",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_hash(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def load_adapter(name: str):
    path = ADAPTERS[name]
    if not path.is_file():
        raise ValueError("fixed adapter unavailable in this source checkout")
    spec = importlib.util.spec_from_file_location("fixed_e2e_check_adapter", path)
    if spec is None or spec.loader is None:
        raise ValueError("fixed adapter cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if module.ADAPTER_ID != name:
        raise ValueError("adapter identity mismatch")
    return module, path


def validate_promise(path: Path, adapter) -> dict:
    promise = json.loads(path.read_text())
    if set(promise) != {"id", "text", "source", "source_sha256"}:
        raise ValueError("promise must contain exactly id, text, source, source_sha256")
    source = Path(promise["source"]).resolve(strict=True)
    if not source.is_file() or source.is_relative_to(REPO) or source == path.resolve():
        raise ValueError("promise requires an external source file")
    if promise["id"] != adapter.PROMISE_ID or promise["text"] != adapter.PROMISE_TEXT:
        raise ValueError("promise identity or text mismatch")
    if sha256(source) != promise["source_sha256"] or promise["text"] not in source.read_text():
        raise ValueError("promise source digest or quotation mismatch")
    return {"id": promise["id"], "text": promise["text"], "source": str(source),
            "source_sha256": promise["source_sha256"]}


def preview(adapter, adapter_path: Path, promise: dict, test: str) -> dict:
    if test not in adapter.TEST_SELECTORS:
        raise ValueError("test selector is not registered")
    definition = adapter.descriptor()
    if (definition.get("adapter", definition.get("adapter_id")) != adapter.ADAPTER_ID
            or definition.get("promise_id") != adapter.PROMISE_ID):
        raise ValueError("adapter descriptor mismatch")
    record = {"adapter": adapter.ADAPTER_ID, "adapter_sha256": sha256(adapter_path),
              "check_sha256": sha256(Path(__file__)),
              "test": test, "promise": promise, "definition": definition}
    return {"status": "PREVIEW", "approval_sha256": canonical_hash(record), **record}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, epilog=
        "Internal trusted-checkout pilot only; public execution remains NO-GO.")
    parser.add_argument("--adapter", choices=sorted(ADAPTERS), required=True)
    parser.add_argument("--promise-file", type=Path, required=True)
    parser.add_argument("--test", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--trust-checkout", action="store_true")
    parser.add_argument("--approve-adapter-sha256")
    args = parser.parse_args(argv)
    try:
        if not args.trust_checkout:
            raise ValueError("explicit checkout trust is required before loading a registered Python adapter")
        adapter, path = load_adapter(args.adapter)
        promise = validate_promise(args.promise_file, adapter)
        report = preview(adapter, path, promise, args.test)
        output = args.output_dir.resolve()
        if output.is_relative_to(REPO) or output.exists() or not output.parent.is_dir():
            raise ValueError("output must be a fresh directory outside the checkout")
        sidecar = output.with_name(output.name + ".invocation.json")
        if sidecar.exists():
            raise ValueError("invocation evidence sidecar already exists")
        report["output_dir"] = str(output)
        if not args.execute:
            print(json.dumps(report, indent=2))
            return 0
        if args.approve_adapter_sha256 != report["approval_sha256"]:
            raise ValueError("execution requires trusted checkout and exact preview approval digest")
        result = adapter.run(output, args.test)
        verdict = result.get("status", result.get("verdict"))
        if verdict not in {"DETECTED", "SURVIVED", "CANNOT_VERIFY"}:
            raise ValueError("adapter returned invalid verdict")
        envelope = {"preview": report, "result": result, "status": verdict}
        sidecar.write_text(json.dumps(envelope, indent=2) + "\n")
        print(json.dumps({"status": verdict, "adapter": args.adapter, "test": args.test,
                          "approval_sha256": report["approval_sha256"],
                          "artifacts": str(output), "invocation_evidence": str(sidecar),
                          "reason": result.get("reason")}, indent=2))
        return 0 if verdict != "CANNOT_VERIFY" else 2
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        print(json.dumps({"status": "CANNOT_VERIFY", "reason": str(error)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
