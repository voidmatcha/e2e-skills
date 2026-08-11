# React optimistic-write proof

This disposable example makes one false-green E2E pattern executable: React
updates a like button optimistically, so a UI-only assertion can pass even when
the POST is removed.

The example separates five outcomes:

| Run | Product mode | Expected result | What it proves |
|---|---|---|---|
| Strong default suite | Normal write | Green | The request fires, rejected writes roll back, and confirmed state survives reload |
| Weak mutant | `omit-post` | Green | Pixels alone can hide the missing write |
| Strong request proof | `omit-post` | Red at `await request` | The test is causally coupled to the write |
| Strong request proof via default fault | `omit-post` | Red at `await request` | The environment-driven fault seam works without changing the candidate URL |
| Strong suite repeated 3× | Normal write | Green | The reset seam makes bounded replay deterministic |

## Run the proof

From this directory:

```bash
npm ci
npm test
npm run verify:demo
```

`verify:demo` exits zero only when it observes the complete expected split,
including the deliberately red strong test under the missing-write fault.

If Playwright reports that Chromium is missing, install the browser once with
the project-local CLI:

```bash
npm exec -- playwright install chromium
```

## Read the mechanism

- [`src/LikeButton.jsx`](src/LikeButton.jsx) sets local state before the POST.
- [`server.mjs`](server.mjs) holds disposable in-memory server truth and a
  reset endpoint. It binds only to `127.0.0.1`.
- [`tests/optimistic-write.spec.mjs`](tests/optimistic-write.spec.mjs) contains
  the strong request, rollback, and reload proofs.
- [`mutants/ui-only.spec.mjs`](mutants/ui-only.spec.mjs) is the intentionally
  weak #22 counterexample. It is excluded from the default suite.
- [`scripts/verify-demo.mjs`](scripts/verify-demo.mjs) checks the expected
  green/green/red/repeat matrix without installing another verifier.

Use `/?fault=omit-post` to omit the POST while retaining optimistic UI, or
`/?fault=reject-post` to return 503 and exercise rollback.

## Actual-generation observation

[`evidence/b-lite-20260811/`](evidence/b-lite-20260811/) preserves one clean
baseline and one clean skill-guided Codex generation plus a sequential
normal/omit/reject matrix. Both candidates passed normal behavior and detected
both faults. The guided prompt explicitly required exact request count and
payload proof, and its candidate complied; that is treatment compliance rather
than an independently discovered advantage. Because this is one public
development generation per arm, its comparative status is `INCONCLUSIVE` and
it supports no accuracy claim.

## Evidence boundary

This is an educational React reproduction of pattern #22, not a second
benchmark operator and not evidence of framework-wide detection accuracy. The
repository's canonical 12-operator/36-cell fixture-fault matrix remains
unchanged.
