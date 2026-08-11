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

The two families disagreed usefully. `#4f` and `#7` — both P0 — were cleared as
sound by one family and shown defective by the other, and both defects are
documented below. A single-reviewer audit would have passed them.

Five more rules were reported defective by only one family, and reproducing
them kept all five: `#3b` misses the bracket form of the Cypress handler registration, `#9b` misses
`cy.wait(delays.render)`, `#9c` misses a `networkidle` constant reached through
a variable, `#10d` misses a formatter-wrapped `async` callback, and `#10b`
misses a serial policy supplied as a variable.

`#10b` is worth the detail, because it was briefly written up here as refuted
and it was not. The fixture put the variable form one line above the inline
form; the filter windows twelve lines forward from a hit, so the variable line
matched the *next* line's literal and both were reported. That read as "the
filter resolves variables". Isolated, the variable form scores zero and the
inline form scores one. A fixture artifact was mistaken for a behaviour, and no
sweep row was added on the strength of it — the third time in this audit that a
claim survived until someone re-ran it alone.

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

## Refuted

**`#20` burden-of-proof drift.** Reported as a contract conflict between
`SKILL.md` and `pattern-reference.md`. The `SKILL.md` row ends with "Flag only
shared, persistent, or otherwise uncontrolled writes", matching
`pattern-reference.md` exactly. The reviewer had read a truncated line.

**`F13` unreachable.** Reported, and written into an earlier version of this
document, as the taxonomy's worst defect: the readers drop passing tests
(`read-playwright-artifact.py:929-931`, `read-cypress-artifact.py:575-576`) and
`F13`'s criterion is a test that passes, so the only P0 label in the debugger
holdout looked unproducible. Both halves are true and the conclusion does not
follow. The debugger is entered on a failing suite; the reader drop removes
passing tests from the Phase 1 *records*, not from the review. Phase 2 reads the
spec source, and both eval suites pin exactly that: "Flags the PASSING test
'mark-all-read clears the badge' (340ms) as P0 F13"
(`skills/playwright-debugger/evals/evals.json`), with a matching Cypress case and
false-positive guards on both. The holdout is answerable for a further reason —
its runner is prompt-complete and zero-tool, so the artifact text reaches the
model directly and never passes through a reader at all.

This one is on the audit's method, not on a reviewer. Two verified premises were
carried to an unverified conclusion, and no one checked whether `F13` was
reachable by another route before the finding was written down.

## What the fix budget allows

The scanner cannot absorb these repairs. `scan.sh` is one of seven surfaces in
the v10 independent-review packet, and at the time of writing the packet measured 122,982 of a
preregistered 123,000 reference tokens — eighteen tokens of headroom, roughly
one line of code. Re-measure before relying on it; the figure moves with any
edit to a packet surface. Broadening a candidate regex is not affordable, and the cap is
frozen evidence rather than a tunable.

The reviewer's `SKILL.md` and `pattern-reference.md` are not in that packet, so
the LLM procedure is free to change. That is also the better place: the audit's
second cause is that the recovery path is closed, and opening it fixes the
family rather than one spelling.

So `#4a`, `#4f`, `#4i`, `#10c`, and `#18` now have rows in the mandatory sweep,
each naming the scanner's specific blind spot so Phase 2 knows what it is
covering for. `#7` already had a row listing the destructured alias forms, but only as
one-line literals, and its opening token `\.only\(` appears nowhere in the
formatter-wrapped spelling — so the row now carries a token for that shape too. `#21` now sweeps the
Cypress session-file equivalents its `storageState:` key could never see.

The scanner keeps its narrow regexes. They remain correct where they fire; they
are simply no longer the only place a family can be found.

Evals 32 and 33 pin the two rows most likely to rot. 32 gives the sweep a spec
where Phase 1 finds only a false positive, and asserts the guard-return,
`exact: false`, and awaited soft assertion are recovered while an intentional
`test.skip` is not. 33 gives `#11` a POM whose member is called only from
another POM, plus a genuinely dead one, so neither the spec-only glob nor the
self-hitting wide glob can pass it. Writing these first would have caught four
of the defects a later review found in this work.

## Fixed the same way, and what is left

`#5a` guard-return bodies, `#5b` and `#10f` Cypress action coverage, `#4g`
Cypress query commands, and `#17` renamed `page` fixtures now have sweep rows
for the same reason as the five above: the scanner cannot grow, and the
reviewer can.

`#19` deliberately does not. A row for `var` and mutated `const` module state
was written and then removed: `pattern-reference.md` defines `#19` as an
initialised top-level `let`, so a sweep row covering the other binding forms
would produce findings the finding-verifier — which resolves against
pattern-reference — is obliged to refute. The hazard is real and now has no
home on any path. Widening it is a taxonomy change to the contract itself, not
something the sweep can paper over, and it is recorded here as an open gap
rather than as covered. `#11` was a live-code hazard rather
than a coverage gap — its documented grep says "specs, POMs, and other utility
modules" while the glob beside it matched specs only, so a member called from
another POM returned zero hits and was classified UNUSED. The glob now covers
the E2E root.

The F1/F7 isolation probe is unexecutable on the read-only classifier path, so
that path could never reach the same verdict as one that ran the probe. The
repair was smaller than it looked: both debugger `SKILL.md` files already define
`CANNOT_VERIFY` between F1 and F7 for exactly the case where the probe was not
performed, and neither classifier copy carried it. Both now do, and both apply
the probe table when the caller's payload includes the probe outcomes — so the
three paths agree on a code given evidence, and agree on the same failure token
without it. `SP3b` in `review.sh` requires the term in both the procedure and
the output contract of every classifier copy, with mutation cases in
`test-parity.sh` for each.

Still open: nothing from the confirmed list. The remaining item is the packet
budget itself — `scan.sh`, both artifact readers, and
`playwright-debugger/SKILL.md` have under twenty tokens between them, and the next
defect found in any of those has nowhere to go.



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
at four in 286. The default is now half the cores, capped below the core count so a
two-core runner gets one worker rather than the whole box, with an
`E2E_SCANNER_WORKERS` override. That keeps the speedup — serial is over ten
minutes — without the oversubscription. The parity suite still defaults to a
flat six workers, each running `review.sh` over its own full-tree copy, so a
host with fewer cores than that should set `E2E_PARITY_WORKERS` down. Only measuring across worker counts separated our own
regression from the ambient load that was also real.

Two of the four assert on elapsed time where a result would do: whether the
reporter terminated, not whether it terminated within twenty seconds; whether
the regex is linear in shape, not whether one timing sample stayed under 4x.
Those need the assertion rewritten.

The debugger-contract timeouts are a different case and were fixed here. They
never claimed a runtime — they bound a hang around work that finishes in under a
second — so a twenty-second wall clock was only ever an arbitrary guard, and an
arbitrary guard should be generous. All fourteen now go through one helper at
six times their old value, raisable with `E2E_CONTRACT_TIMEOUT_SCALE`, and so do
the three elapsed-time assertions that guard against exponential blowup on
deeply nested XML — those were left unscaled at first, which would have kept the
suite flaky through a different door. A real hang still surfaces; a scheduler
delay no longer reads as one.
