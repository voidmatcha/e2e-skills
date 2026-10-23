<!-- SPDX-License-Identifier: Apache-2.0 -->
# Classification measurements

An offline scorer and presentation export. It never calls a model, runs lint,
executes a reviewed project, or changes a frozen benchmark. JSON preserves the
measurement contract; Markdown and standalone HTML include counts, rates and a
confusion matrix. HTML uses only Python's standard library to produce an escaped
document with inline styling, no JavaScript, dependencies or external assets.

## Define the decision before measuring

The classifier is the whole system producing a final issue report. A model name
alone does not describe it. Record the input snapshot, model/settings, available
rules/tools, actual execution evidence and the rule mapping its final output to
a positive decision. For example, a lint warning that the final reviewer rejects
is not automatically a positive reviewer prediction.

Define the evaluation unit and ground truth independently of predictions. A unit
could be one fixed code location and pattern, with a rubric explaining whether
it warrants a finding. Legitimate cleanup and justified code belong among the
negative examples. Repetitions of a case are not new independent defects.

| Ground truth | System reports an issue | System reports no issue |
|---|---|---|
| Reportable issue | TP: found it | FN: missed it |
| Legitimate code | FP: reported it incorrectly | TN: correctly left it alone |

Precision = TP / (TP + FP); recall = TP / (TP + FN). F1 combines both.
False-positive rate = FP / (FP + TN), **not** FP / all reported issues.
Undefined ratios are `null` / `N/A`, not zero.

## Fixed binary decision units

For a new study, freeze the unit list and labeling method before running systems.
Give every system the same units. Record separate files for separate repetitions;
this scorer does not silently pool repeated runs. Input example (synthetic only):

```json
{
  "schema_version": 1,
  "study_id": "synthetic-example-not-benchmark-evidence",
  "setting": "Same source snapshot and output schema for each system",
  "unit_definition": "One fixed source location and pattern",
  "positive_definition": "A reportable issue under the frozen rubric",
  "negative_definition": "Legitimate code under that rubric",
  "ground_truth_method": "Independent adjudication before predictions",
  "units": [
    {"id": "broken-assertion", "positive": true, "evidence": "Source and adjudication reference"},
    {"id": "intentional-cleanup", "positive": false, "evidence": "Source and justification reference"}
  ],
  "systems": [{
    "id": "example-system",
    "definition": "Describe model, prompt, tools and versions here",
    "decision_rule": "Positive iff the final report includes this unit",
    "execution_evidence": "Reference logs; a name alone proves no tool use",
    "decisions": {"broken-assertion": "positive", "intentional-cleanup": "negative"}
  }]
}
```

Add systems to compare LLM-only, LLM with lint, or a complete reviewer workflow.
Use those names only when logs establish the actual treatment. Ground-truth and
execution evidence strings are recorded, not independently verified by this tool.

```bash
python3 scripts/evals/classification-report/report.py \
  --decisions /absolute/decisions.json --output /absolute/new-measurement.json
python3 scripts/evals/classification-report/report.py \
  --decisions /absolute/decisions.json --format markdown --output /absolute/new-measurement.md
python3 scripts/evals/classification-report/report.py \
  --decisions /absolute/decisions.json --format html --output /absolute/new-measurement.html
```

The HTML page shows definitions, setting, labeling method, each system's decision
rule and recorded execution evidence, a 2×2 matrix, rate formulas and denominators,
decision coverage and unresolved counts. Metadata remains readable without opening
the optional raw JSON disclosure. `N/A` distinguishes unavailable or undefined
values from measured zero. The same `--format html` option applies to holdout
exports below; open-ended TN and inconclusive metric cells stay unavailable.
The page does not infer a winner or release approval.

Decisions are `positive`, `negative`, `abstain` or `error`. Missing decisions,
abstentions and execution errors stay outside the four cells, with their IDs,
positive/negative counts and decision coverage recorded. Conditional rates from
an incomplete run cannot be compared as if coverage were complete. There is no
automatic accuracy threshold or release approval.

## Existing reviewer holdout reports

```bash
python3 scripts/evals/classification-report/report.py \
  --report /absolute/holdout.json \
  --cases scripts/evals/reviewer-holdout.json \
  --protocol scripts/evals/reviewer-validation-protocol.json \
  --format markdown --output /absolute/new-holdout-measurement.md
```

Select the exact corpus/protocol and evaluated skill checkout used by the report.
The exporter reuses the canonical comparator to reparse outputs and rescore
findings; it rejects inconsistent saved metrics or provenance. It currently
supports ordinary full-schedule finding holdouts, not specificity-only,
revision-comparison, superseded or known-invalid studies. Partial schedules are
rejected. Inconclusive sources retain reasons and unscored counts, with metric
cells unavailable. A complete `FAIL` report remains a measured failure.

The matching unit is a required finding label, matched by pattern, severity,
file and line, including protocol-declared alternatives. Optional labels do not
become required TP/FN. Exports separate unique stable findings from repeated-run
totals and retain the protocol's stability rule. These open-ended findings have
**no finite TN universe**: TN and false-positive rate remain unavailable. Clean
case specificity is a different metric. Do not invent TN from unreported lines.
The historical `full` prompt profile does not mean lint or scanner execution;
retain its recorded model tool surface instead of relabeling it “LLM + lint”.

The 69-shape scanner migration comparison is not an adjudicated defect corpus.
Matching a legacy candidate there is not automatically a TP. Do not feed its
candidate-match counts into a confusion matrix as accuracy evidence.

## Promptfoo display

Use the separately installed `promptfoo@0.124.1`, as described in
[the existing adapter](../promptfoo/README.md). First generate JSON above, then:

```bash
python3 scripts/evals/classification-report/promptfoo.py \
  --report /absolute/new-measurement.json --output /absolute/new-view.json
PROMPTFOO_DISABLE_TELEMETRY=1 /absolute/path/to/promptfoo eval \
  -c /absolute/new-view.json --no-cache -o /absolute/new-results.html
```

Each row is a display case, not a new independent sample. The provider reads a
SHA-256-pinned measurement file; every row keeps the full definitions, source
status and limitations. A Promptfoo assertion passes when transport matches,
even if the measured system performed badly or its source is incomplete.
No LLM grader is used. Zero provider tokens/cost describes this replay only.
Hashes detect changes; they do not attest ground-truth correctness or tool use.
All output commands refuse to overwrite existing files. Store reports outside Git.

```bash
python3 scripts/evals/classification-report/test_report.py
```
