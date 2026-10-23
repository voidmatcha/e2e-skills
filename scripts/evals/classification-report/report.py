#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Offline classification measurements; no model calls or project execution."""

import argparse
import hashlib
from html import escape
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts/ci/lib"))
from strict_json import loads_strict


def fraction(numerator, denominator):
    return numerator / denominator if denominator else None


def metrics(tp, fp, fn, tn=None):
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": fraction(tp, tp + fp),
            "recall": fraction(tp, tp + fn),
            "f1": fraction(2 * tp, 2 * tp + fp + fn),
            "false_positive_rate": None if tn is None else fraction(fp, fp + tn)}


def text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be nonempty text")
    return value


def finite_measurement(data):
    """One preregistered binary decision per unit, per system, per run.

    Labels and evidence are supplied by the experiment owner, not attested here.
    Missing decisions remain unmeasured; abstentions are never true negatives.
    """
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("expected finite-unit schema_version 1")
    definitions = {key: text(data.get(key), key) for key in
                   ("study_id", "setting", "unit_definition", "positive_definition",
                    "negative_definition", "ground_truth_method")}
    units = data.get("units")
    systems = data.get("systems")
    if not isinstance(units, list) or not units or not isinstance(systems, list) or not systems:
        raise ValueError("units and systems must be nonempty lists")
    labels = {}
    for unit in units:
        key = text(unit.get("id"), "unit id")
        if key in labels or type(unit.get("positive")) is not bool:
            raise ValueError("duplicate unit or non-boolean ground truth")
        text(unit.get("evidence"), "ground-truth evidence")
        labels[key] = unit["positive"]
    rows = []
    identities = set()
    for system in systems:
        identity = text(system.get("id"), "system id")
        if identity in identities:
            raise ValueError("duplicate system id")
        identities.add(identity)
        metadata = {key: text(system.get(key), key) for key in
                    ("definition", "decision_rule", "execution_evidence")}
        decisions = system.get("decisions")
        if not isinstance(decisions, dict) or set(decisions) - labels.keys():
            raise ValueError("decisions must map known unit IDs")
        if any(value not in ("positive", "negative", "abstain", "error")
               for value in decisions.values()):
            raise ValueError("unknown decision")
        counts = {key: 0 for key in ("tp", "fp", "fn", "tn")}
        unresolved = {key: [] for key in ("abstain", "error", "missing")}
        for key, positive in labels.items():
            prediction = decisions.get(key, "missing")
            if prediction in unresolved:
                unresolved[prediction].append(key)
            else:
                cell = ("tp" if positive else "fp") if prediction == "positive" else (
                    "fn" if positive else "tn")
                counts[cell] += 1
        decided = sum(counts.values())
        rows.append({"system": identity, **metadata,
                     "aggregation_unit": "fixed-unit-single-run",
                     "status": "COMPLETE" if decided == len(labels) else "INCOMPLETE",
                     "matrix": metrics(**counts), "total_units": len(labels),
                     "decided_units": decided, "coverage": decided / len(labels),
                     "unresolved": unresolved,
                     "unresolved_positive_units": sum(
                         labels[key] for keys in unresolved.values() for key in keys),
                     "unresolved_negative_units": sum(
                         not labels[key] for keys in unresolved.values() for key in keys)})
    return {"schema_version": 1, "mode": "finite-units", **definitions,
            "ground_truth_verified_by_exporter": False,
            "execution_evidence_verified_by_exporter": False,
            "release_eligible": False, "rows": rows,
            "limitations": ["Metrics apply only to the supplied labeled units.",
                            "Rates use decided units; compare coverage before comparing rates.",
                            "System names do not prove that lint or other tools actually ran."]}


def load_comparator():
    path = ROOT / "scripts/evals/compare-reviewer-holdouts.py"
    spec = importlib.util.spec_from_file_location("classification_comparator", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def holdout_measurement(report_path, cases_path, protocol_path):
    comparator = load_comparator()
    runner = comparator.RUNNER
    # Reuse snapshotting and canonical parsing/scoring, never trust saved totals.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="classification-inputs-") as directory:
        root = Path(directory)
        report_hash, report_bytes = comparator.descriptor_sha256(
            report_path, comparator.MAX_REPORT_BYTES)
        protocol_hash, protocol_bytes = comparator.descriptor_sha256(
            protocol_path, comparator.MAX_REPORT_BYTES)
        frozen_report = root / "report.json"
        frozen_protocol = root / "protocol.json"
        comparator.write_snapshot_file(frozen_report, report_bytes)
        comparator.write_snapshot_file(frozen_protocol, protocol_bytes)
        frozen_cases, _ = comparator.snapshot_corpus_inputs(cases_path, root / "corpus")
        protocol = runner.load_protocol(frozen_protocol)
        protocol_id = protocol["protocol_id"]
        unsupported = (runner.SPECIFICITY_PROTOCOL_IDS | runner.REVISION_COMPARISON_PROTOCOL_IDS
                       | runner.SUPERSEDED_PROTOCOL_IDS | runner.HISTORICAL_DIAGNOSTIC_PROTOCOL_IDS)
        if protocol_id in unsupported:
            raise ValueError("use the protocol-specific comparator for this study")
        metadata, cases = runner.load_cases(frozen_cases)
        digest = runner.corpus_digest(frozen_cases, cases)
        runner.validate_corpus_protocol_pairing(metadata, protocol, digest)
        report = comparator.recompute_report(
            comparator.load_report(frozen_report), cases, digest, protocol, protocol_hash,
            metadata.get("corpus_visibility"), "development",
            runner.evaluator_digest())
    complete = report["execution_complete"] and report["complete"]
    rows = []
    for unit, source in (("unique-stable-finding", report["primary_metrics"]["unique"]),
                         ("repeated-run-finding", report["summary"])):
        rows.append({"system": report["prompt_profile"], "runner": report["runner"],
                     "model": report["model"], "aggregation_unit": unit,
                     "status": report["status"],
                     "matrix": metrics(source["tp"], source["fp"], source["fn"]) if complete else None})
    return {"schema_version": 1, "mode": "canonical-holdout", "rows": rows,
            "report_sha256": report_hash, "protocol_sha256": protocol_hash,
            "protocol_id": protocol_id,
            "corpus_sha256": digest, "release_eligible": False,
            "source_status": report["status"], "source_status_reasons": report["status_reasons"],
            "execution_complete": report["execution_complete"],
            "scheduled_runs": len(report["runs"]),
            "unscored_runs": sum(run["score"] is None for run in report["runs"]),
            "stability": report["primary_metrics"]["stability"],
            "model_tool_surface": report["model_tool_surface"],
            "unit_definition": "Finding label matched by pattern, severity, file and line, including declared alternatives.",
            "positive_definition": "A required reportable finding in the corpus oracle.",
            "negative_definition": "An unmatched reported finding is FP; no finite finding-level TN universe is defined.",
            "limitations": ["TN and false-positive rate are unavailable for open-ended findings.",
                            "Repeated runs are not independent defects.",
                            "Prompt profile full does not establish execution of lint or scanner tools.",
                            "Incomplete or inconclusive sources have no authoritative metric cells."]}


def markdown(data):
    lines = ["# Classification measurements", "", f"Mode: {data['mode']}", "",
             data["unit_definition"], "", f"Positive: {data['positive_definition']}",
             f"Negative: {data['negative_definition']}", "",
             "| System | Unit | Status | TP | FP | FN | TN | Precision | Recall | F1 | Coverage |",
             "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    def show(value):
        if value is None:
            return "N/A"
        return f"{value:.3f}" if isinstance(value, float) else str(value)
    def cell(value):
        return str(value).replace("|", "\\|").replace("\n", " ").replace("\r", " ")
    for row in data["rows"]:
        matrix = row["matrix"] or {}
        values = [row["system"], row["aggregation_unit"], row["status"],
                  *(show(matrix.get(key)) for key in ("tp", "fp", "fn", "tn", "precision", "recall", "f1")),
                  show(row.get("coverage"))]
        lines.append("| " + " | ".join(cell(value) for value in values) + " |")
    lines.extend(["", "Interpretation:", "", *[f"- {item}" for item in data["limitations"]]])
    for row in data["rows"]:
        matrix = row["matrix"] or {}
        lines.extend(["", f"## {cell(row['system'])}: {row['aggregation_unit']}", "",
                      "| Ground truth | Reported positive | Reported negative |",
                      "|---|---:|---:|",
                      f"| Positive | TP: {show(matrix.get('tp'))} | FN: {show(matrix.get('fn'))} |",
                      f"| Negative | FP: {show(matrix.get('fp'))} | TN: {show(matrix.get('tn'))} |"])
    # Keep definitions, unresolved counts and original status reasons beside the table.
    lines.extend(["", "## Measurement contract and details", "", "```json",
                  json.dumps(data, indent=2, ensure_ascii=False), "```", ""])
    return "\n".join(lines)


def html_report(data):
    """Render measurement facts without scripts, remote assets or inferred cells."""
    def escaped(value):
        return escape(str(value), quote=True)

    def show(value):
        if value is None:
            return "N/A (unavailable or undefined)"
        return f"{value:.3f}" if isinstance(value, float) else escaped(value)

    def details(value):
        if isinstance(value, dict):
            return "<dl>" + "".join(
                f"<dt>{escaped(key.replace('_', ' '))}</dt><dd>{details(item)}</dd>"
                for key, item in value.items()) + "</dl>"
        if isinstance(value, list):
            if not value:
                return "None recorded"
            return "<ul>" + "".join(f"<li>{details(item)}</li>" for item in value) + "</ul>"
        return show(value)

    parts = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width, initial-scale=1">',
             '<title>Classification measurements</title><style>',
             'body{font:16px/1.5 system-ui,sans-serif;max-width:70rem;margin:2rem auto;padding:0 1rem;color:#17202a;background:#fff}'
             'table{border-collapse:collapse;margin:1rem 0;width:100%}th,td{border:1px solid #aab4be;padding:.5rem;text-align:left}'
             'th{background:#eef2f6}dt{font-weight:bold}dd{margin:0 0 .6rem 1rem;overflow-wrap:anywhere}'
             'section{border-top:2px solid #aab4be;margin-top:2rem}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
             'caption{text-align:left;font-weight:bold}summary{cursor:pointer}',
             '</style></head><body><main><h1>Classification measurements</h1>',
             '<p>Offline presentation of supplied measurements. No winner or release approval is inferred.</p>',
             '<h2>Measurement definitions</h2>',
             details({key: data.get(key) for key in (
                 'mode', 'study_id', 'setting', 'unit_definition', 'positive_definition',
                 'negative_definition', 'ground_truth_method')}),
             '<p>Rates use decided units. Missing decisions, abstentions and errors are unresolved; '
             'they do not become TN. Compare coverage before comparing rates. '
             'N/A means unavailable or undefined, never zero. '
             'For open-ended findings there is no finite TN universe, so TN and FPR are N/A.</p>']
    for row in data['rows']:
        matrix = row['matrix']
        cells = matrix or {}
        parts.extend(['<section>', f"<h2>{escaped(row['system'])}</h2>",
                      details({key: row.get(key) for key in (
                          'aggregation_unit', 'status', 'definition', 'decision_rule', 'execution_evidence')}),
                      '<table><caption>Confusion matrix (decided units)</caption><thead><tr>'
                      '<th scope="col">Ground truth</th><th scope="col">Reported positive</th>'
                      '<th scope="col">Reported negative</th></tr></thead><tbody>',
                      f"<tr><th scope=\"row\">Positive</th><td>TP: {show(cells.get('tp'))}</td>"
                      f"<td>FN: {show(cells.get('fn'))}</td></tr>",
                      f"<tr><th scope=\"row\">Negative</th><td>FP: {show(cells.get('fp'))}</td>"
                      f"<td>TN: {show(cells.get('tn'))}</td></tr></tbody></table>"])
        if matrix is None:
            parts.append('<p>No authoritative metric cells: the source is incomplete or inconclusive.</p>')
        parts.append('<table><caption>Rates and their denominators</caption><thead><tr>'
                     '<th scope="col">Metric</th><th scope="col">Formula</th>'
                     '<th scope="col">Denominator</th><th scope="col">Value</th></tr></thead><tbody>')
        for name, key, formula, terms in (
            ('Precision', 'precision', 'TP / (TP + FP)', ('tp', 'fp')),
            ('Recall', 'recall', 'TP / (TP + FN)', ('tp', 'fn')),
            ('F1', 'f1', '2TP / (2TP + FP + FN)', ('tp', 'tp', 'fp', 'fn')),
            ('False-positive rate (FPR)', 'false_positive_rate', 'FP / (FP + TN)', ('fp', 'tn')),
        ):
            denominator = (sum(cells[key] for key in terms)
                           if all(cells.get(key) is not None for key in terms) else None)
            parts.append(f'<tr><th scope="row">{name}</th><td>{formula}</td>'
                         f'<td>{show(denominator)}</td><td>{show(cells.get(key))}</td></tr>')
        parts.extend(['</tbody></table>',
                      '<p>FP / (TP + FP) is the false-discovery share among reported positives '
                      '(1 − precision when defined). FPR uses actual negatives: FP / (FP + TN).</p>',
                      '<h3>Decision coverage and unresolved units</h3>',
                      details({key: row.get(key) for key in ('total_units', 'decided_units', 'coverage',
                               'unresolved_positive_units', 'unresolved_negative_units')}),
                      details({f'{key} count': len(row['unresolved'][key])
                               for key in ('abstain', 'error', 'missing')}
                              if 'unresolved' in row else {'unresolved counts': None}),
                      '<h3>Recorded arm metadata</h3>', details(row), '</section>'])
    parts.extend(['<h2>Measurement metadata and limitations</h2>',
                  details({key: value for key, value in data.items() if key != 'rows'}),
                  '<details><summary>Raw measurement JSON</summary><pre>',
                  escaped(json.dumps(data, indent=2, ensure_ascii=False)),
                  '</pre></details></main></body></html>\n'])
    return '\n'.join(parts)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--decisions", type=Path)
    inputs.add_argument("--report", type=Path)
    parser.add_argument("--cases", type=Path)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--format", choices=("json", "markdown", "html"), default="json")
    parser.add_argument("--output", type=Path, help="new file only; otherwise stdout")
    args = parser.parse_args()
    try:
        if args.decisions:
            if args.cases or args.protocol:
                raise ValueError("--cases/--protocol apply only to --report")
            raw = args.decisions.read_bytes()
            if len(raw) > 8_388_608:
                raise ValueError("decision input exceeds 8 MiB")
            result = finite_measurement(loads_strict(raw.decode(), context="decisions"))
            result["input_sha256"] = hashlib.sha256(raw).hexdigest()
        else:
            if not args.cases or not args.protocol:
                raise ValueError("--report requires --cases and --protocol")
            result = holdout_measurement(args.report.resolve(), args.cases.resolve(), args.protocol.resolve())
        output = (html_report(result) if args.format == "html" else markdown(result)
                  if args.format == "markdown" else json.dumps(result, indent=2) + "\n")
        if args.output:
            with args.output.open("x") as stream:
                stream.write(output)
        else:
            print(output, end="")
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print(f"classification report: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
