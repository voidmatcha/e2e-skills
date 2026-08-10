# Self-audit of the rules

An adversarial audit of this project's own contracts: the 24 anti-patterns, the
15 failure codes, and the operational rules that decide how a finding is
produced and whether it survives. Every finding below was reproduced against the
shipped scanner before being written down. Findings that did not survive
reproduction are recorded as refuted, at the end.

## How it was run

Six subject axes, each audited independently by two model families. Reviewers
were told to refute first, to cite `file:line` for every claim, to label each
finding CONFIRMED or SUSPECTED, and to report nothing about wording or style.

The two families disagreed usefully. Seven rules that one family cleared as
sound were shown defective by the other: `#3b`, `#4f`, `#7`, `#9b`, `#9c`,
`#10b`, `#10d`. Two of those are P0. A single-reviewer audit would have passed
all seven.

## Two causes account for most of it

**Regexes assume one physical line; formatters do not.** The scanner's
candidate patterns are built around a statement fitting on one line. Prettier
wraps at 80 columns, so the same construct written by a formatter is invisible.
This is the mechanism behind `#7`, `#4a`, `#10c`, `#18`, `#4i`, and `#4c`-`#4e`.

**The recovery path is closed.** Several contracts state that Phase 1 supplies
the candidates and Phase 2 resolves them. The mandatory opening-token sweep that
would let Phase 2 look independently is declared "exactly this list — no more,
no less", and the rules with the widest Phase 1 gaps are not on it. When Phase 1
misses, nothing is authorised to look again.

## Confirmed — suppression

**A `// JUSTIFIED:` comment above a `describe` block suppressed findings in
unrelated sibling tests, and flipped the exit code from 1 to 0.**

The callback-scope walk accumulated every line between the marker and the hit
and asked whether `.evaluate(` or `.waitForFunction(` appeared anywhere in that
span. An `evaluate` call in an earlier sibling test satisfied it. The code
comment already described the intended rule — the hit must stay inside the same
callback — but the implementation did not enforce it.

Reproduction, before the fix: a marker above `test.describe` whose rationale
concerned a canvas read in the first test suppressed a `#4f` P0 and a `#9` P1 in
the second test, and `scan.sh` exited 0. Deleting the marker produced `1 P0` and
exit 1. `scan.sh` ships as a standalone CI scanner, so on that path there is no
Phase 2 to recover the demotion, and the P1/P2 hits are dropped without
retaining a pattern ID.

Fixed: only the construct that opens the scope may carry the rationale.
Guarded by eval 31.

A four-line comment explaining the change broke the v10 prompt-size cap. The
fix shipped at plus seventeen bytes with no comment at all, and the reasoning
lives in the commit message. See "What the fix budget allows" below for why
`scan.sh` has almost no room left.

## Confirmed — rules that cannot detect what they name

| Rule | Defect |
| --- | --- |
| `#7` (P0) | A one-hop alias written `const {`⏎`  only: focused,`⏎`} = test;` produces no candidate. `focused(...)` then excludes every sibling test silently. The one-line spelling is caught. |
| `#4f` (P0) | Coverage of POM members depends on the member's name. `expect(this.submitButton).toBeTruthy()` is flagged; `expect(this.submit).toBeTruthy()` on an identically typed `Locator` is not. |
| `#4a` (P0) | The entire detection is the literal `toBeGreaterThanOrEqual(0)`. `toBeGreaterThan(-1)`, `not.toBeLessThan(0)`, and a space inside the parentheses all pass. Phase 2 is separately instructed not to generalise. |
| `#18` | The candidate regex cannot match `await expect.soft(`. The only form it matches is the unawaited one, which is already `#15`. Every correctly written soft assertion is invisible. |
| `#10c` | `exact: false` is treated as if it were `exact: true`. The regex keys on the presence of the token `exact:`, and `exact: false` explicitly requests the substring behaviour the rule exists to catch. Multi-line `getByRole` calls are also missed. |
| `#14` | Any `.fill(` or `.type(` with a string literal becomes a candidate, with no credential evidence required. On the project's own labelled corpus this is a 75% false-positive rate; `fill('Mina')` is reported as a credential candidate. Credentials passed through other methods are missed. |
| `#21` | Detection keys on `storageState:`, a Playwright-only token. A Cypress suite restoring a manually captured session has the named defect and is never examined. The block never mentions Cypress, and unlike `#3b` its heading carries no framework tag. |
| `F13` | Both debuggers' readers discard non-failing tests before classification (`status in {expected, skipped}` / `classification != failed`). `F13`'s criterion is a test that passes. It is the only P0 label in the debugger holdout and the pipeline cannot produce it. |

## Refuted

**`#20` burden-of-proof drift.** Reported as a contract conflict between
`SKILL.md` and `pattern-reference.md`. The `SKILL.md` row ends with "Flag only
shared, persistent, or otherwise uncontrolled writes", matching
`pattern-reference.md` exactly. The reviewer had read a truncated line.

## What the fix budget allows

The scanner cannot absorb these repairs. `scan.sh` is one of seven surfaces in
the v10 independent-review packet, and the packet currently measures 122,981 of
a preregistered 123,000 reference tokens — nineteen tokens of headroom, roughly
one line of code. Broadening a candidate regex is not affordable, and the cap is
frozen evidence rather than a tunable.

The reviewer's `SKILL.md` and `pattern-reference.md` are not in that packet, so
the LLM procedure is free to change. That is also the better place: the audit's
second cause is that the recovery path is closed, and opening it fixes the
family rather than one spelling.

So `#4a`, `#4f`, `#4i`, `#10c`, and `#18` now have rows in the mandatory sweep,
each naming the scanner's specific blind spot so Phase 2 knows what it is
covering for. `#7` already had a row listing the destructured alias forms — its
gap was scanner-only and the fallback already reached it. `#21` now sweeps the
Cypress session-file equivalents its `storageState:` key could never see.

The scanner keeps its narrow regexes. They remain correct where they fire; they
are simply no longer the only place a family can be found.

## Not pursued here

Still open: `#5a` guard-return bodies, `#5b` and `#10f` Cypress action
coverage, `#4g` Cypress query commands, `#19` `var` and mutated `const`, `#17`
renamed `page` fixtures, `#11` excluding POM files from its own usage grep
(which can recommend deleting live code), and the F1/F7 isolation probe being
unexecutable on the read-only verifier path.

`F13` is open and harder than the rest. Its fix belongs in the artifact readers
or the debugger `SKILL.md`, and all three of those files are inside the v10
packet, so the nineteen-token budget applies to them as well.

One finding stays SUSPECTED: under disk exhaustion the scanner appeared to emit
a clean zero-hit summary without printing `INCOMPLETE`. The condition was real —
a reviewer process died of `ENOSPC` during this audit — but reproducing it
requires filling the disk, so it is unproven.

## Our own CI is flaky under load

Four gate stages failed during this audit and passed on rerun with no change in
between. Each one measures wall-clock time, so each one fails when something
else on the machine takes the CPU.

| Stage | How it failed | Reruns |
| --- | --- | --- |
| `test-debugger-contracts.py` | `extract-junit-failures.py` hit its 20-second timeout | 2/2 passed |
| `test-reviewer-scanner.py` | the two checks that create 1500 files | failed only at load 20-40 |
| `test-residual-redos-budget.py` | growth measured 10.1x where linear is 4x | 3/3 passed |
| `test-playwright-debugger-report-publish.py` | a timeout marker file was not written | 3/3 passed |

This is the inverse of what the project exists to catch. A false-green test
passes when the product is broken; these fail when the product is fine. Both
destroy the signal, and the second kind is the more expensive to debug, because
a red gate demands an explanation and the obvious explanation is whatever
changed last.

It produced exactly that error here. `test-debugger-contracts.py` failed on a
branch whose only changes were three Markdown files, and passed at `HEAD`. One
comparison in each direction pointed at a documentation edit breaking a Cypress
JUnit extractor. Three more runs showed the failure was unrelated to the branch
at all.

The margins are not tight, so widening them is not the answer either. The JUnit
extractor that "timed out after 20 seconds" processes the test's own two
8&nbsp;MB fixtures in 0.4 to 0.8 seconds — a twenty-five to fifty times margin,
and it holds no lock that could block. A half-second job hitting a twenty-second
wall was starved of CPU, not slow.

Part of the starvation was self-inflicted, and calling it "machine load" would
have hidden that. The scanner suite had just been parallelised at one worker per
core, but each worker spawns `scan.sh`, so a worker costs more than a core and
filling every core oversubscribes the box. At ten workers the check that builds
1500 files lost the CPU long enough to fail; at five it passes in 362 seconds,
at four in 286. The default is now half the cores with an `E2E_SCANNER_WORKERS`
override, which keeps the speedup — serial is over ten minutes — without the
oversubscription. Only measuring across worker counts separated our own
regression from the ambient load that was also real.

The fix is to stop asserting on elapsed time where a result would do: whether
the reporter terminated, not whether it terminated within twenty seconds;
whether the regex is linear in shape, not whether one timing sample stayed under
4x. A deadline that is 50x the real cost still fails when the scheduler takes
the process away, and raising it to 100x only makes a genuine hang take longer
to surface.
