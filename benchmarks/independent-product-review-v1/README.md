# Independent product-review evidence v1

This archive is a **fresh-context curated subset remediation gate** for
prompt-complete, zero-tool model reviews. It is not full-product coverage, not a skill-accuracy estimate, not human review, not sealed review, and not independent ground truth. Runner and model identity are caller-declared, with
no remote model attestation. UUIDv4 invocation IDs are local provenance only;
they cannot prove that separate remote calls occurred.

The archive is content-addressed, internally consistent, and version-controlled; it is not immutable. Its hashes detect unreviewed byte
drift inside a checkout but are not an external signature or attestation.

Cross-model completion: **pending**. The R1–R6 ledger uses the historical
pre-schedule protocol. Its Claude attempts were `INCONCLUSIVE`, and those
historical attempts cannot fill the current fixed nine-cell schedule. R5 passed
one historical Codex packet, while R6 found defects in a later packet. The
original v1 protocol's three Codex cells are complete and all failed; the six
Opus/Fable cells were not run and remain missing rather than fabricated as
`INCONCLUSIVE`.

The original v1 fixed protocol defines three round-robin repetitions across
Codex, Opus, and Fable. Completion requires all nine declared attempt IDs
exactly once on one packet and protocol. Every cell, including an
`INCONCLUSIVE` cell, is present evidence; only `PASS` or `FAIL` is complete.
The cross-model gate passes only when all nine cells are `PASS`. The three exact
Codex cells also have separate completion and passage fields, neither of which
measures skill accuracy.

Post-remediation Codex completion: **complete; gate failed**. Before product remediation, v2
predeclares exactly three Codex-only repetitions on `gpt-5.6-sol`:
`codex-postremediation-r1`, `codex-postremediation-r2`, and
`codex-postremediation-r3`. They must use one newly frozen packet, the same
ordered selection policy and rubric, the same six dimensions and thresholds,
and the predeclared 800000-byte cap. The cap preserves all 26 original required
surfaces and adds two required security-remediation implementation surfaces;
any missing surface fails closed.

The exact archive destinations are:

- `codex-postremediation-r1` → `attempts/r10/codex/{report,raw}.json`
- `codex-postremediation-r2` → `attempts/r11/codex/{report,raw}.json`
- `codex-postremediation-r3` → `attempts/r12/codex/{report,raw}.json`

The three cells ran on one frozen packet. R10 and R11 passed; R12 failed with
two high findings, so the Codex-only post-remediation robustness gate failed.
This permits descriptive comparison with the immutable r7–r9 baseline only. It
does not complete or pass the original cross-model schedule and is not a
skill-accuracy estimate, full-product claim, human or sealed review, independent
ground truth, or remote model attestation.

Final-remediation Codex completion: **complete; gate failed**. Protocol v3 was
frozen before the next product-fix pass and declared exactly three more Codex-only
repetitions on `gpt-5.6-sol`: `codex-final-r1`, `codex-final-r2`, and
`codex-final-r3`. After the declared fixes and local verification, all three
used one frozen packet with the same 28 required surfaces, 800000-byte cap,
six dimensions, and thresholds. Their exact archive destinations are:

- `codex-final-r1` → `attempts/r13/codex/{report,raw}.json`
- `codex-final-r2` → `attempts/r14/codex/{report,raw}.json`
- `codex-final-r3` → `attempts/r15/codex/{report,raw}.json`

R13, R14, and R15 all failed at 89.67, 89.00, and 87.67, respectively,
with at least one high finding in every repetition. The fixed v3 gate therefore
failed. This remains a curated-subset robustness check: it cannot complete the
original cross-model schedule, estimate skill accuracy, or establish
full-product, human-review, sealed-review, independent-ground-truth, or
remote-attestation claims.

Closure-remediation Codex completion: **complete; gate failed**. Protocol v4
was frozen before product edits for all seven independently confirmed v3
findings. It declared exactly three Codex-only repetitions on `gpt-5.6-sol`:
`codex-closure-r1`, `codex-closure-r2`, and `codex-closure-r3`. After the
declared fixes and local verification, all three used one newly frozen packet
with the same 28 required surfaces, 800000-byte cap, six dimensions, and fixed
thresholds. Their exact archive destinations are:

- `codex-closure-r1` → `attempts/r16/codex/{report,raw}.json`
- `codex-closure-r2` → `attempts/r17/codex/{report,raw}.json`
- `codex-closure-r3` → `attempts/r18/codex/{report,raw}.json`

R16 failed at 90.50 because one high finding violated the fixed zero-high
threshold. R17 and R18 passed individually at 92.50 and 91.50, but the
predeclared aggregate requires all three attempts to pass, so the v4 gate
failed. This third Codex-only phase cannot complete the original cross-model
schedule and remains descriptive curated-subset robustness evidence, not a
skill-accuracy estimate or a full-product, human, sealed,
independent-ground-truth, or remotely attested review.

## Attempt ledger

| Round | Label | Status | Score | C/H/M | Packet | Evidence |
| --- | --- | --- | ---: | --- | --- | --- |
| r1 | codex | FAIL | 83.17 | 0/3/0 | [`86e95c…`](packets/86e95c845a72c020fee66b654045c104db62967d6d30edb5656e4e1e33ed7f26.json) | [report](attempts/r1/codex/report.json), [raw](attempts/r1/codex/raw.json) |
| r1 | fable | INCONCLUSIVE | — | — | [`86e95c…`](packets/86e95c845a72c020fee66b654045c104db62967d6d30edb5656e4e1e33ed7f26.json) | [report](attempts/r1/fable/report.json), [raw](attempts/r1/fable/raw.json) |
| r1 | opus | INCONCLUSIVE | — | — | [`86e95c…`](packets/86e95c845a72c020fee66b654045c104db62967d6d30edb5656e4e1e33ed7f26.json) | [report](attempts/r1/opus/report.json), [raw](attempts/r1/opus/raw.json) |
| r2 | codex | FAIL | 85.50 | 0/2/5 | [`5dfd5c…`](packets/5dfd5cd7e37898c7e123a0094766d83521e561ca1e5965a20b3d5b9909da61f3.json) | [report](attempts/r2/codex/report.json), [raw](attempts/r2/codex/raw.json) |
| r2 | fable | INCONCLUSIVE | — | — | [`5dfd5c…`](packets/5dfd5cd7e37898c7e123a0094766d83521e561ca1e5965a20b3d5b9909da61f3.json) | [report](attempts/r2/fable/report.json), [raw](attempts/r2/fable/raw.json) |
| r2 | opus | INCONCLUSIVE | — | — | [`5dfd5c…`](packets/5dfd5cd7e37898c7e123a0094766d83521e561ca1e5965a20b3d5b9909da61f3.json) | [report](attempts/r2/opus/report.json), [raw](attempts/r2/opus/raw.json) |
| r3 | codex | FAIL | 89.17 | 0/1/3 | [`51cfd3…`](packets/51cfd3b67af9b1b6b1eb82b1747c49a8b6b641d5d9a481235d5f4fdb109a3a44.json) | [report](attempts/r3/codex/report.json), [raw](attempts/r3/codex/raw.json) |
| r3b | codex | FAIL | 83.67 | 0/2/1 | [`51cfd3…`](packets/51cfd3b67af9b1b6b1eb82b1747c49a8b6b641d5d9a481235d5f4fdb109a3a44.json) | [report](attempts/r3b/codex/report.json), [raw](attempts/r3b/codex/raw.json) |
| r4 | codex | FAIL | 82.83 | 0/2/3 | [`bccc53…`](packets/bccc53c93a59aa1cd463db91ac740962aca7c89a1db65bb8368b7f81bf3f5a10.json) | [report](attempts/r4/codex/report.json), [raw](attempts/r4/codex/raw.json) |
| r5 | codex | PASS | 93.17 | 0/0/2 | [`cbd0ab…`](packets/cbd0ab13d8faf539f1e6e0610a302270478a04a61ee867f27371e469b4b835a6.json) | [report](attempts/r5/codex/report.json), [raw](attempts/r5/codex/raw.json) |
| r6 | codex | FAIL | 88.00 | 0/1/1 | [`5b3495…`](packets/5b349530c3153c11c7abe0d30dc2073b16091bc82c7d071a6518b4bc4ef53a72.json) | [report](attempts/r6/codex/report.json), [raw](attempts/r6/codex/raw.json) |
| r7 | codex | FAIL | 87.00 | 0/2/2 | [`da4b31…`](packets/da4b317623ed9cd460fc4decdbfcb55fe6ed0af3dd67ce8b189fa67c739aa41d.json) | [report](attempts/r7/codex/report.json), [raw](attempts/r7/codex/raw.json) |
| r8 | codex | FAIL | 86.33 | 0/3/0 | [`da4b31…`](packets/da4b317623ed9cd460fc4decdbfcb55fe6ed0af3dd67ce8b189fa67c739aa41d.json) | [report](attempts/r8/codex/report.json), [raw](attempts/r8/codex/raw.json) |
| r9 | codex | FAIL | 87.00 | 0/1/3 | [`da4b31…`](packets/da4b317623ed9cd460fc4decdbfcb55fe6ed0af3dd67ce8b189fa67c739aa41d.json) | [report](attempts/r9/codex/report.json), [raw](attempts/r9/codex/raw.json) |
| r10 | codex | PASS | 93.00 | 0/0/2 | [`278fed…`](packets/278fed9d19efa7d16bbea241bac956824cda2c7699b5b88756157f3c52212a04.json) | [report](attempts/r10/codex/report.json), [raw](attempts/r10/codex/raw.json) |
| r11 | codex | PASS | 91.17 | 0/0/5 | [`278fed…`](packets/278fed9d19efa7d16bbea241bac956824cda2c7699b5b88756157f3c52212a04.json) | [report](attempts/r11/codex/report.json), [raw](attempts/r11/codex/raw.json) |
| r12 | codex | FAIL | 87.67 | 0/2/1 | [`278fed…`](packets/278fed9d19efa7d16bbea241bac956824cda2c7699b5b88756157f3c52212a04.json) | [report](attempts/r12/codex/report.json), [raw](attempts/r12/codex/raw.json) |
| r13 | codex | FAIL | 89.67 | 0/1/1 | [`68f130…`](packets/68f130d7b4a3e4a33956e2bc47c417bba9d8d46ee8a7501a8317772e3bbdb334.json) | [report](attempts/r13/codex/report.json), [raw](attempts/r13/codex/raw.json) |
| r14 | codex | FAIL | 89.00 | 0/1/2 | [`68f130…`](packets/68f130d7b4a3e4a33956e2bc47c417bba9d8d46ee8a7501a8317772e3bbdb334.json) | [report](attempts/r14/codex/report.json), [raw](attempts/r14/codex/raw.json) |
| r15 | codex | FAIL | 87.67 | 0/2/0 | [`68f130…`](packets/68f130d7b4a3e4a33956e2bc47c417bba9d8d46ee8a7501a8317772e3bbdb334.json) | [report](attempts/r15/codex/report.json), [raw](attempts/r15/codex/raw.json) |
| r16 | codex | FAIL | 90.50 | 0/1/2 | [`fb19f5…`](packets/fb19f5846a7bd5a8cb7e5bb3c49287f136761b91e12481025e1f3040245c03b3.json) | [report](attempts/r16/codex/report.json), [raw](attempts/r16/codex/raw.json) |
| r17 | codex | PASS | 92.50 | 0/0/3 | [`fb19f5…`](packets/fb19f5846a7bd5a8cb7e5bb3c49287f136761b91e12481025e1f3040245c03b3.json) | [report](attempts/r17/codex/report.json), [raw](attempts/r17/codex/raw.json) |
| r18 | codex | PASS | 91.50 | 0/0/3 | [`fb19f5…`](packets/fb19f5846a7bd5a8cb7e5bb3c49287f136761b91e12481025e1f3040245c03b3.json) | [report](attempts/r18/codex/report.json), [raw](attempts/r18/codex/raw.json) |

`r3b` is a second Codex review of the same frozen R3 packet. It is retained
because the disagreement is useful robustness evidence; it is not treated as
another independent defect corpus or averaged into a quality score.

## What the rounds changed

- R1–R2 exposed assertion-semantics, scope, artifact-publication, scanner, and
  installation-contract defects.
- R3 and R3b added scanner provenance/race hardening, JUnit read-integrity
  checks, safe Playwright artifact download, and documentation corrections.
- R4 drove equivalent Cypress artifact-download safety, trusted executable
  resolution, suppression wording, and host-install/fallback corrections.
- R5 passed the fixed gate while retaining two medium findings.
- R6 tested a later packet and found a high-severity screenshot-read boundary
  plus a medium taxonomy error. Its `FAIL` supersedes R5 as the latest archived
  historical Codex status.
- R7–R9 completed the fixed protocol's Codex-only slice on one frozen packet.
  All three failed, with scores from 86.33 to 87.00. Confirmed findings are
  remediated only under a separately frozen post-remediation protocol; these
  baseline failures remain unchanged.
- R10–R12 completed the predeclared v2 Codex-only post-remediation slice on one
  frozen packet. R10 and R11 passed at 93.00 and 91.17; R12 failed at 87.67
  with two high findings. The v2 repetition gate therefore failed, and the
  reports remain unchanged while findings are independently adjudicated.
- R13–R15 completed the predeclared v3 Codex-only final-remediation slice on one
  frozen packet. All three failed at 89.67, 89.00, and 87.67. The reports remain
  unchanged; all seven findings were independently adjudicated as confirmed.
- R16–R18 completed the preregistered v4 Codex-only closure-remediation
  schedule on one frozen packet. R17 and R18 passed, while R16 failed at 90.50
  with one high finding. The all-three repetition gate therefore failed.

Finding locations are original one-based source lines embedded in each packet.
The validator checks every cited file/line against the archived packet instead
of the current working tree.

## Integrity and extension

[`status.json`](status.json) is derived from the reports. It deliberately keeps
full-product, skill-accuracy, human-review, sealed-review,
independent-ground-truth, and remote-attestation claims disabled.
[`evidence-manifest.json`](evidence-manifest.json) hashes every regular archive
file except itself.

The historical, original v1 scheduled, post-remediation v2,
final-remediation v3, and preregistered closure-remediation v4 protocol
revisions are stored under
[`protocols/`](protocols/) by SHA-256. The root `protocol.json` remains the
historical compatibility copy; each report binds to the protocol SHA in its
own integrity snapshot. V2 binds the baseline protocol
`6eba5bec52997da20ae621e50281ff7a3856afbc9dd9b08d9917e5ced3f6950d`,
packet `da4b317623ed9cd460fc4decdbfcb55fe6ed0af3dd67ce8b189fa67c739aa41d`,
and exact r7–r9 report/raw hashes. V3 binds v2 protocol
`018729aedd61c8013884fb803e5632cdb50f5130c46f6cd2074daca31d494abe`,
packet `278fed9d19efa7d16bbea241bac956824cda2c7699b5b88756157f3c52212a04`,
and exact r10–r12 report/raw hashes. V4 binds v3 protocol
`7d1223452a9df28c1daed5aeb419949b7dffead281a454a5990dd3cb6532e186`,
packet `68f130d7b4a3e4a33956e2bc47c417bba9d8d46ee8a7501a8317772e3bbdb334`,
and exact r13–r15 report/raw hashes.

To add the post-remediation evidence mechanically:

1. After remediation and before any model call, freeze the v2 packet once. Copy
   it to `packets/<packet-sha256>.json` and its manifest to
   `packet-manifests/<packet-sha256>.json`. All three v2 reports must bind to
   those same content-addressed bytes and the v2 protocol SHA.
2. Copy the three report/raw pairs to the exact r10–r12 destinations above.
3. Rename each copied pair to `report.json` and `raw.json`, append matching
   ledger rows above, and run:

```bash
python3 scripts/ci/test-independent-review-evidence.py --refresh
python3 scripts/ci/test-independent-review-evidence.py
```

For v3, keep the already archived protocol bytes unchanged, complete and verify
the declared fixes, then freeze one new 28-surface packet. Copy the three exact
report/raw pairs to r13–r15 and run the same refresh/read-only validation pair.
Do not substitute ad-hoc attempts or reuse a v2 invocation.

For v4, keep the archived protocol bytes unchanged, complete and verify all
seven confirmed v3 fixes, then freeze one new 28-surface packet before any
model call. Copy the three exact report/raw pairs to r16–r18 and run the same
refresh/read-only validation pair. Do not substitute ad-hoc attempts or reuse
an earlier invocation.

The validator preserves R1–R6 and the immutable r7–r9 Codex baseline, leaves the
six unrun Opus/Fable calls missing, and validates v2, v3, and v4 separately. It rejects
missing report/raw pairs, ad-hoc or reused IDs, reused invocation UUIDs,
wrong r10–r18 destinations, order/binding or schedule-digest drift, protocol
mismatch, mixed packets or protocols inside either remediation phase, and
invalid report decisions. `--refresh` only derives `status.json` and the hash manifest;
ordinary CI is read-only.
