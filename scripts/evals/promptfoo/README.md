<!-- SPDX-License-Identifier: Apache-2.0 -->
# Optional Promptfoo CLI-report canary

This adapter keeps the existing holdout runner, login, model settings, isolation
checks and scoring. It runs one public development cell through Codex CLI, then
lets Promptfoo display the hash-pinned result without calling a model or an LLM
grader. It does not evaluate browser probes, MCP workflows or overall skill
quality. Promptfoo assertion success means report transport matched, not that
the source benchmark passed. The original verdict and its reasons stay visible.

Install `promptfoo@0.124.1` in a separate tooling directory. It is not a product
dependency. From the source checkout, with a working Codex login:

```bash
python3 scripts/evals/promptfoo/canary.py \
  --runner-path /absolute/path/to/codex \
  --output /absolute/new/external/canary-directory --allow-live
```

Run the separately installed `promptfoo` executable against the generated
`promptfooconfig.json`, with telemetry disabled:

```bash
PROMPTFOO_DISABLE_TELEMETRY=1 /absolute/path/to/promptfoo eval \
  -c /absolute/canary-directory/promptfooconfig.json --no-cache \
  -o /absolute/canary-directory/results.json \
  -o /absolute/canary-directory/results.html
```

Only rerun the Promptfoo command to view/recheck existing results. It never
starts Codex. A changed report hash is rejected. The live canary refuses an
existing output directory and does not retry automatically. Native runner logs,
the complete source report and the projected cell remain in that directory;
keep these together. No hosted sharing is needed.

Promptfoo's zero token/cost display describes the report-reading provider only,
not the original Codex call. Missing source usage stays unknown. This canary does
not add tool-call capture: it preserves the existing runner's recorded surface.
To create another view config without a live call, use `config.py --report
/absolute/holdout.json --case playwright-split-context --output /absolute/new.json`.

The current cell uses the built-in public development protocol with one case
and one repetition, retaining its declared `gpt-5.6-sol` model. A different model
must be declared by a separate protocol, not substituted into frozen evidence.
It is an integration check, not a new frozen benchmark or
evidence of general accuracy. The holdout's tool-disabled model surface also
does not establish official-agent or MCP compatibility.

Run the dependency-free adapter checks with:

```bash
python3 scripts/evals/promptfoo/test_provider.py
```

## Portable local evidence bundles

Export only the frozen report, the selected raw logs (`command.json`,
`harness.stdout.txt`, `harness.stderr.txt`), the original view config, and the
adapter source. Credentials and runtime configuration directories are not
selected. Review raw logs for sensitive content before publishing anything.
The export does not upload to Hugging Face or call a model.

```bash
python3 scripts/evals/promptfoo/bundle.py export \
  --source /absolute/canary-directory \
  --config /absolute/canary-directory/promptfooconfig.json \
  --case playwright-split-context --output /absolute/new/bundle
python3 scripts/evals/promptfoo/bundle.py verify --bundle /absolute/new/bundle
python3 scripts/evals/promptfoo/bundle.py restore \
  --bundle /absolute/new/bundle --output /another/root/restored-bundle
python3 scripts/evals/promptfoo/test_bundle.py
```

Exporting the same frozen inputs with the same adapter produces the same
manifest bytes. The manifest pins every selected file's SHA-256 and byte size;
provenance records the original paths and the relationship between the report,
adapter and derived config. Keep the printed manifest digest in an independently
trusted receipt when transferring the directory. These hashes detect changes;
they do not establish authorship or protect against replacing the whole bundle
and its manifest.

Restore verifies all listed files, rejects extra files, path traversal and
symlinks, and refuses existing destinations. It uses the trusted local adapter
only when its source matches the frozen adapter; bundled Python is never run.
Use stable local directories without concurrent writers. This is an integrity
check, not an OS sandbox for hostile writers.

The restored bundle preserves the report, logs and original config byte for byte.
It generates a sibling `<destination>-view.json` using the restored report path,
and a `<destination>-receipt.json` with the manifest/config digests and source
verdict. Run Promptfoo with that new config; the archived config still records
its original machine's paths. Restoration preserves the exact cell, including
errors and partial-run reasons. A local restore verifies portability only; it
is not a Hugging Face upload/download check or a benchmark accuracy result.
