#!/usr/bin/env python3
"""Apache-2.0. Bounded public-source development intake, not frozen collection."""

import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("fresh_followup", ROOT / "scripts/evals/pilot-specificity-context-followup.py")
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
C = F.P.C
ast_spec = importlib.util.spec_from_file_location("fresh_ast", ROOT / "scripts/evals/replay-specificity-context-ast.py")
AST = importlib.util.module_from_spec(ast_spec)
ast_spec.loader.exec_module(AST)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--calibration", type=Path)
    parser.add_argument("--primary-batch", action="store_true", help="ordered development intake without semantic discovery; one case per repository")
    parser.add_argument("--usage-context", action="store_true", help="collect up to twenty source files under the literal test root; never infer whole-repository coverage")
    parser.add_argument("--typescript", type=Path, help="optional trusted TypeScript 6.0.3 lib/typescript.js; diagnostic only")
    parser.add_argument("--node", type=Path, help="trusted Node executable; required with --typescript")
    parser.add_argument("--spec-scope", choices=("e2e", "all"), default="e2e", help="all removes only the path-name restriction; framework proof and scan limits still apply")
    parser.add_argument("--continue-primary-from", type=Path, help="new output: retain prepared prefix and consumed budgets; never retry a visited repository")
    parser.add_argument("--after-primary", type=Path, help="new development batch after an exhausted registered repository segment")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache-source", type=Path, action="append", default=[], help="reuse prior public API responses without changing them")
    parser.add_argument("--raw-blobs", action="store_true", help="read pinned public source bytes through raw URLs instead of the blob API")
    args = parser.parse_args()
    if bool(args.typescript) != bool(args.node):
        raise ValueError("--typescript and --node must be provided together")
    ast_identity = None
    if args.typescript:
        probe = AST.analyze({}, args.typescript, args.node)
        ast_identity = {"parser_version": probe["parser_version"], "parser_sha256": probe["parser_sha256"],
                        "node_sha256": probe["node_sha256"], "node_version": probe["node_version"],
                        "implementation_sha256": probe["implementation_sha256"],
                        "wrapper_sha256": C.digest(Path(AST.__file__).read_bytes())}
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(ROOT):
        raise ValueError("use new external output")
    if not args.primary_batch:
        if args.calibration is None:
            raise ValueError("discovery intake requires calibration")
        calibration = C.read_json(args.calibration)
        if calibration.get("status") != "complete" or calibration.get("v2_gate") is not True:
            raise ValueError("calibration gate not passed")
    inventory = C.read_json(args.inventory)
    excluded = C.prior_use(C.load_protocol(ROOT / "scripts/evals/reviewer-specificity-protocol-v4.json"), None)
    excluded.add("freecodecamp/freecodecamp")
    if args.primary_batch:
        excluded.update({"react/react", "facebook/react"})
    eligible = [r for r in inventory["repositories"] if r["framework"] == "playwright"
                and r["repository_identity"].casefold() not in excluded]
    offset = 0
    previous_batch = None
    if args.after_primary:
        if not args.primary_batch:
            raise ValueError("new segment requires primary mode")
        prior_source = args.after_primary.resolve()
        prior = C.read_json(prior_source / "context-report.json")
        prior_registration = C.read_json(prior_source / "intake-registration.json")
        prior_offset = prior_registration.get("inventory_offset", 0)
        prior_rows = prior_registration["ordered_repositories"]
        if (prior.get("mode") != "primary-development" or prior.get("status") not in {"complete", "incomplete", "no-prepared-cases"}
                or prior.get("registration_sha256") != C.digest((prior_source / "intake-registration.json").read_bytes())
                or prior_registration["inventory_sha256"] != C.digest(args.inventory.read_bytes())
                or prior_registration["excluded"] != sorted(excluded)
                or type(prior_offset) is not int or prior_offset < 0 or not prior_rows
                or prior_rows != eligible[prior_offset:prior_offset + len(prior_rows)]
                or [r["repository"] for r in prior["walk"]] != [r["repository_identity"] for r in prior_rows]):
            raise ValueError("prior segment is not an exhausted matching inventory prefix")
        offset = prior_offset + len(prior_rows)
        previous_batch = {"report_sha256": C.digest((prior_source / "context-report.json").read_bytes()),
                          "registration_sha256": prior["registration_sha256"]}
    rows = eligible[offset:offset + 10]
    report = {"status": "preparing", "evaluation_allowed": False, "cases": [], "walk": [], "api_requests": 0,
              "inventory_sha256": C.digest(args.inventory.read_bytes()),
              "calibration_sha256": C.digest(args.calibration.read_bytes()) if args.calibration else None,
              "limits": {"repositories": 10, "api_requests": 60, "specs_per_repository": 20, "cases": 3},
              "selection": "snapshot rank; ancestor manifest dependency; e2e-named path; direct test import; POSIX spec order",
              "excluded": sorted(excluded)}
    registration = {"mode": "primary-development" if args.primary_batch else "discovery-development",
                    "ordered_repositories": rows, "inventory_sha256": report["inventory_sha256"],
                    "excluded": sorted(excluded), "limits": {**report["limits"], "raw_requests": 60,
                    "cases_per_repository": 1 if args.primary_batch else 3},
                    "selection": report["selection"], "raw_blobs": args.raw_blobs,
                    "evaluation_allowed": False,
                    "implementation_sha256": {p.name: C.digest(p.read_bytes()) for p in
                        [Path(__file__), Path(F.Q.__file__), Path(C.__file__)]}}
    if args.spec_scope == "all":
        report["selection"] = registration["selection"] = "snapshot rank; ancestor manifest dependency; any spec-named path; direct test import; POSIX spec order"
    if args.usage_context:
        registration["selection"] += "; bounded usage context v1 (20 files, existing byte/request caps)"
        report["selection"] = registration["selection"]
    if ast_identity:
        registration["ast_diagnostic"] = ast_identity
    if args.after_primary:
        registration.update(inventory_offset=offset, previous_batch=previous_batch)
    if args.continue_primary_from:
        previous = args.continue_primary_from.resolve()
        if not args.primary_batch or output.is_relative_to(previous) or previous.is_relative_to(output):
            raise ValueError("continuation requires separate primary output")
        prior = C.read_json(previous / "context-report.json")
        old_registration = C.read_json(previous / "intake-registration.json")
        if (prior.get("status") != "incomplete" or prior.get("mode") != "primary-development"
                or prior.get("registration_sha256") != C.digest((previous / "intake-registration.json").read_bytes())
                or any(old_registration.get(k) != registration[k] for k in
                       ("mode", "ordered_repositories", "inventory_sha256", "excluded", "limits", "selection", "raw_blobs"))
                or old_registration.get("inventory_offset", 0) != offset
                or old_registration.get("ast_diagnostic") != ast_identity):
            raise ValueError("continuation contract changed")
        visited = prior["walk"]
        if [r["repository"] for r in visited] != [r["repository_identity"] for r in rows[:len(visited)]]:
            raise ValueError("continuation is not an ordered prefix")
        # Zero cases is valid for intake recovery, but never for a model run.
        prepared = [] if prior["cases"] == [] else F.inputs(previous, allow_prepared_prefix=True)
        for item in prepared:
            for name, text in item["files"].items():
                C.write(output / "sources" / item["id"] / name, text.encode())
        report.update(cases=prior["cases"], walk=visited, api_requests=prior["api_requests"],
                      raw_requests=prior.get("raw_requests", 0),
                      reused_response_sha256=prior.get("reused_response_sha256", {}))
        for row in visited:
            if row["status"] == "checking":
                row["status"] = "incomplete-not-retried"
                row["error_type"] = prior.get("error_type", "unknown")
        registration["continuation"] = {"report_sha256": C.digest((previous / "context-report.json").read_bytes()),
                                         "policy": "retain consumed budgets and prepared prefix; skip every visited repository including failed rows"}
        rows = rows[len(visited):] if len(prepared) < 3 else []
    C.write_json(output / "intake-registration.json", registration)
    report["registration_sha256"] = C.digest((output / "intake-registration.json").read_bytes())
    report["mode"] = registration["mode"]
    github = C.GitHub(output, None, None)
    def save():
        C.write_json(output / "context-report.json", report)
    save()
    def api(path, params=None):
        for cache_source in args.cache_source:
            key = C.digest(("shared\0" + C.GitHub.request_key(path, params)).encode())
            cached = cache_source / "cache/api" / (key + ".body")
            meta = cache_source / "cache/api" / (key + ".json")
            if cached.is_file() and meta.is_file() and C.read_json(meta).get("request") == C.GitHub.request_key(path, params):
                data = cached.read_bytes()
                report.setdefault("reused_response_sha256", {})[key] = C.digest(data)
                return json.loads(data)
        if report["api_requests"] >= 60:
            raise RuntimeError("api-budget-exhausted")
        report["api_requests"] += 1
        save()
        data, _ = github.get(path, params)
        return json.loads(data)
    try:
        for row in rows:
            identity = row["repository_identity"]
            walk = {"repository": identity, "rank": row["repository_rank"], "status": "checking", "specs": []}
            report["walk"].append(walk)
            save()
            metadata = api(f"/repos/{identity}")
            if metadata.get("private") or metadata.get("fork") or metadata.get("archived") or metadata.get("visibility") != "public":
                walk["status"] = "ineligible"
                continue
            branch = urllib.parse.quote(row["default_branch_at_snapshot"], safe="")
            sha = api(f"/repos/{identity}/commits/{branch}")["sha"]
            tree = api(f"/repos/{identity}/git/trees/{sha}", {"recursive": "1"})
            if tree.get("truncated"):
                walk["status"] = "truncated-tree"
                continue
            entries = {e["path"]: e for e in tree["tree"] if e["type"] == "blob" and e.get("mode") in {"100644", "100755"}}
            fetched = {}
            def load(name):
                F.P.R.validate_workspace_path(name, "fresh source")
                if name not in fetched:
                    entry = entries[name]
                    if entry.get("size", 0) > 250_000:
                        raise ValueError("source-budget-exceeded")
                    if args.raw_blobs:
                        if report.get("raw_requests", 0) >= 60:
                            raise RuntimeError("raw-request-budget-exhausted")
                        report["raw_requests"] = report.get("raw_requests", 0) + 1
                        url = f"https://raw.githubusercontent.com/{identity}/{sha}/{urllib.parse.quote(name)}"
                        with urllib.request.urlopen(url, timeout=20) as response:
                            data = response.read(250_001)
                        if len(data) > 250_000:
                            raise ValueError("source-budget-exceeded")
                    else:
                        blob = api(f"/repos/{identity}/git/blobs/{entry['sha']}")
                        if blob.get("encoding") != "base64":
                            raise ValueError("invalid-blob")
                        data = base64.b64decode(blob["content"], validate=False)
                    if hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != entry["sha"]:
                        raise ValueError("blob-hash-mismatch")
                    fetched[name] = data
                return fetched[name]
            matching = sorted(p for p in entries if C.is_spec(p, "playwright")
                              and (args.spec_scope == "all" or "e2e" in p.lower()))
            specs = matching[:20]
            walk.update(matching_spec_paths=len(matching), selected_spec_paths=len(specs))
            if not specs:
                walk["status"] = "no-matching-spec-paths"
                continue
            manifest_paths = sorted({(parent / "package.json").as_posix() for name in specs
                                     for parent in Path(name).parents if (parent / "package.json").as_posix() in entries})[:20]
            packages = {p: json.loads(load(p)) for p in manifest_paths}
            external = {k for package in packages.values() for field in C.PACKAGE_FIELDS for k in package.get(field, {})}
            if "@playwright/test" not in external:
                walk["status"] = "no-owner-playwright-dependency"
                continue
            licence = api(f"/repos/{identity}/license", {"ref": sha})
            spdx = (licence.get("license") or {}).get("spdx_id")
            if not spdx or spdx in {"NOASSERTION", "OTHER", "NONE"}:
                walk["status"] = "unverified-licence"
                continue
            for name in specs:
                attempt = {"path": name, "status": "checking"}
                walk["specs"].append(attempt)
                try:
                    owners = [p for p, package in packages.items() if Path(name).is_relative_to(Path(p).parent)
                              and any("@playwright/test" in package.get(field, {}) for field in C.PACKAGE_FIELDS)]
                    if not owners:
                        attempt["status"] = "no-owner-playwright-dependency"
                        continue
                    if not F.P.DIRECT_TEST.search(C.without_comments(load(name).decode())):
                        attempt["status"] = "no-direct-test-import"
                        continue
                    def closure(path):
                        try:
                            return C.closure(path, "playwright", set(entries), load, external, {})[0]
                        except C.UnresolvableSpec as exc:
                            raise ValueError("unresolved-import") from exc
                    initial = closure(name)
                    expanded = F.Q.expand_context(initial, set(entries), load, closure, C.without_comments)
                    if args.usage_context:
                        expanded = F.Q.collect_usage_context(expanded, name, set(entries), load, C.without_comments)
                    if sum(len(data) for data in expanded["files"].values()) > 500_000:
                        raise ValueError("case-budget-exceeded")
                    if ast_identity:
                        diagnostic = AST.analyze({p: b.decode('utf-8') for p, b in expanded["files"].items()}, args.typescript, args.node)
                        if any(diagnostic[k] != ast_identity[k] for k in ("parser_version", "parser_sha256", "implementation_sha256", "node_sha256", "node_version")):
                            raise RuntimeError("registered AST parser changed")
                        expanded["ast_context"] = diagnostic
                    case_id = f"fresh-{len(report['cases']) + 1:03d}"
                    for path, data in expanded.pop("files").items():
                        C.write(output / "sources" / case_id / path, data)
                    report["cases"].append({"id": case_id, "spec": name, "repository": identity,
                                            "commit": sha, "licence_spdx": spdx, "framework_manifests": owners, **expanded})
                    attempt["status"] = "prepared"
                except (ValueError, KeyError, UnicodeDecodeError) as exc:
                    attempt["status"] = "incomplete-context"
                    attempt["error_type"] = type(exc).__name__
                save()
                if len(report["cases"]) == 3 or (args.primary_batch and attempt["status"] == "prepared"):
                    break
            walk["status"] = "visited"
            save()
            if len(report["cases"]) == 3:
                break
        report["status"] = ("incomplete" if any(r["status"] == "incomplete-not-retried" for r in report["walk"])
                            else "complete" if report["cases"] else "no-prepared-cases")
    except Exception as exc:
        report["status"] = "incomplete"
        report["error_type"] = type(exc).__name__
        if str(exc) in {"source-budget-exceeded", "case-budget-exceeded", "blob-hash-mismatch",
                        "api-budget-exhausted", "raw-request-budget-exhausted", "invalid-blob"}:
            report["error_reason"] = str(exc)
        if hasattr(exc, "code"):
            report["http_status"] = exc.code
    save()
    print(json.dumps({"status": report["status"], "cases": len(report["cases"]), "api_requests": report["api_requests"]}))


if __name__ == "__main__":
    main()
