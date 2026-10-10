# Batch four: source-scope audit

## Review Scope and Evidence

- **Mode:** full mode, limited to two staged development cases; not a full upstream repository review.
- **Behavior under review:** validity of the fourth primary batch's #8, #11, #14 and #20 proposals.
- **Diff base/range:** N/A.
- **Changed E2E artifacts:** none; staged source bytes are immutable.
- **Context-only files consulted:** the staged Playwright example config, Uptime Kuma config and `test/e2e/util-test.js`; the local frozen pattern reference and original model report.
- **Static evidence:** installed reviewer scanner, Tier 2 + 3, run once per staged case root; Tier 1 disabled. Playwright: zero mechanical hits. Uptime Kuma: four triage candidates (#8b, #10c, two #14); zero mechanically confirmed P0. Inline semantic confirmation and the required opening-token checklist were applied to the five supplied source/config files.
- **Runtime evidence:** not executed. The API example writes to GitHub; no credentials, upstream test commands or third-party mutations were used. Any runtime verification must use an explicitly approved disposable environment, not the example's live endpoint.
- **Independent verification:** V1–V5 recommended/unexecuted where applicable; no V6 PASS claimed. The diagnostic actor also maintains the harness, and model agreement is not independent truth.
- **Limitations/exclusions:** sibling tests, reverse users, repository documentation, setup implementation and deployment isolation are not fully supplied. This audit cannot prove repository-wide unused exports or complete suite cleanliness. No original report is rewritten.

## Supported catalog findings

### P1 #20 — Playwright API example

- **Issue:** `examples/github-api/tests/test-api.spec.ts:28`, `:38`, `:43` and `:60` create/delete a fixed-name repository and create issues on the explicit public GitHub API using an ambient token. The supplied config has no alternative endpoint; these are evidenced external persistent/rate-limited writes. Cleanup does not isolate concurrent runs or remove dependence on the external service.
- **Attribution (diff mode):** N/A.
- **Fix:** run this example only behind a documented isolated disposable test-account/resource boundary.
- **Verification:** V3 + V4 recommended in a disposable local substitute; not executed.
- **Qualification:** this is an intentionally live API example, not proof of a defect in Playwright itself or evidence that production credentials were exposed. One original pass omitted the teardown finding; the disagreement is retained.

### P1 #14 — Uptime Kuma positive authentication literals

- **Issue:** `test/e2e/specs/basic-auth.spec.js:28` and `:37` supply literal credentials in positive authentication requests. `test/e2e/util-test.js:27` and `:29` also contain literal positive-login inputs. Values are deliberately not reproduced here. The invalid-password case at spec line 19 is exempt.
- **Attribution (diff mode):** N/A.
- **Fix:** source the positive authentication values from one explicit test credential fixture shared with setup.
- **Verification:** positive/negative authentication checks against the disposable test backend are recommended/unexecuted.
- **Qualification:** the helper findings are source-level catalog matches, not proof that the selected spec calls that helper; these public test literals are not evidence of leaked production secrets.

## Rejected inferences and unresolved context

| Original proposal | Audit disposition | Evidence |
| --- | --- | --- |
| #11 at helper lines 12, 24, 39, 48 | NEEDS-CONTEXT; exclude from confirmed findings | The selected spec imports only `restoreSqliteSnapshot`. A forward import slice does not contain all reverse users. The #11 contract requires searching all tests/helpers, so absence in this slice cannot prove unused exports. |
| #8/P0 at helper line 32 | Not confirmed for the selected scenario; NEEDS-CONTEXT for other callers | The spec never calls `login`; its tests assert response status/body. No evidenced executed scenario loses its only verification through that discarded read. Other callers and their postconditions were not supplied. |
| Scanner #10c at helper line 31 | Not confirmed | No evidence of user-controlled competing accessible names or execution by the selected spec. |

The staged config also declares a setup project matching `setup-process.once.js`, but that setup file is not supplied. Localhost, a dedicated test data directory and snapshot restoration are positive isolation evidence; they must not be replaced by an unsupported claim of uncontrolled production writes. Their presence does not prove every missing setup dependency resolved.

For #1/#2, the supplied test titles have status/body or API read-back assertions. No catch-based swallowing or missing-auth wrong-surface pass is established. #21 has no supplied session-file reference; #22 has no optimistic UI-only verification in either selected spec; #23 has no supplied conditional render fixture. The opening-token sweep adds no confirmed P0. **Real P0 = 0 in this bounded audit**, not a claim of full repository cleanliness.

## Review Summary

| Severity | Confirmed source lines | Files |
| --- | --- | --- |
| P0 | 0 | none |
| P1 | 8 | API spec, Basic-auth spec, auth helper |
| P2 | 0 | none |

Priorities: establish the API example's isolated execution boundary; centralize positive test credentials; never count missing reverse-user/caller evidence as an unused-export or silent-pass finding. No upstream files were changed.

## Harness correction and sampling consequence

The old prompt calls the input a complete candidate boundary while intake supplies only a bounded forward import/context slice. Four model calls agreed on non-clean verdicts, but both Uptime Kuma passes made the same unsupported negative inference. The new opt-in `bounded-v1` prompt distinguishes file completeness from repository completeness, requires the missing proof, preserves directly supported findings and uses `insufficient-context` rather than claiming clean when decisive context is absent. The frozen protocol and legacy default remain unchanged.

The diagnostic reruns the same two cases twice each under that new prompt, with fresh tool-free Codex calls. It cannot replace the original results or measure general accuracy. More intake alone cannot repair this evidence gap: whole-repository #11 decisions need a bounded reverse-user census, and scenario-level #8 decisions need proven caller/postcondition context. Until that evidence is available, a release corpus must keep those decisions unresolved rather than manufacturing clean labels.

## Diagnostic outcome

All four `bounded-v1` calls completed and passed schema/citation validation. Both Playwright calls retained #20 at lines 28, 43 and 60; neither included teardown line 38. Both Uptime Kuma calls omitted #8 and #11 and retained #14 at spec lines 28/37 and helper line 29; one additionally reported helper line 27. Thus the targeted unsupported inference disappeared in both observed passes, while supported finding families remained. Line-level completeness/agreement is still imperfect. There were zero clean candidates, no release admissions and no three-arm evaluation.

This is one post-outcome diagnostic on two known cases, not a held-out accuracy measurement. Offline regression tests verify opt-in prompt delivery, preservation of the legacy protocol object, identical blinded prompts and rejection of carried results when the prompt changes. They do not prove arbitrary future model behavior.

- Original model report: `ed4e456489ad3206476cf4beb3f8664dea174bf7d9ec9c44bd4800b5edb8edc4`.
- Diagnostic input manifest: `d123ec7723d50c52fe61be27d6d975be7895ab716c221861a1bcc122d04706d5`.
- Diagnostic model report: `f7e176c2cdc20d202f5a944e2bf2b6eafe64deeaae1a072d0e6bdff42547dda6`.
- Frozen v3 protocol remains `96acfaa9fe29d485079f5276dc1940727ab17288184b7e2ee7e9c9c2cf3eecfa`.
- Frozen v4 protocol remains `032ed21b48d18a98cb97b3cf9da51b8f5056464626e07c3a8378ff2139457c7f`.
