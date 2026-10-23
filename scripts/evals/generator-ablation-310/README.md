<!-- SPDX-License-Identifier: Apache-2.0 -->
# Generator 3.1.0 preparation canary

Prepare a fresh external fixture using an existing exact Playwright 1.62.0
installation. This does not run a model, browser, test or app server, and does
not change user Codex configuration or authentication.

```bash
python3 scripts/evals/generator-ablation-310/prepare.py \
  --output /absolute/fresh/external/preflight \
  --modules /absolute/existing/node_modules \
  --node /absolute/node --codex /absolute/codex
```

The script runs official `init-agents --loop codex`, then sends real stdio MCP
`initialize`, `notifications/initialized` and `tools/list` requests. It preserves
runtime tool schemas, generated agents, commands, versions and source hashes.
`preflight.json` PASS means preparation and MCP transport discovery passed. It does not prove session
approval, delegation, browser operation, test quality or a benchmark advantage.

`next-model-command.json` is an unexecuted command proposal with invocation-local
MCP overrides. Its tool allowlist is the installed official planner/generator
union plus `test_run`; the raw server listing can contain more tools. Keep
sessions persistent to capture child defining calls. Before execution, freeze
one scenario, select a free loopback port, start the owned fixture, and resolve
tool approval policy. No model invocation or approval bypass is automatic.

Dependencies are reused through an external project symlink. Preparation pins
package versions and hashes metadata and official source; a mutable shared
dependency tree is not isolation. Historical comparison scripts are not imported.
The official source contract is [Playwright Test Agents](https://playwright.dev/docs/test-agents).

## One measured canary

After a model-free outgoing-request capture proves the runtime advertises the
named official generator, run exactly one fresh prepared directory:

```bash
python3 scripts/evals/generator-ablation-310/canary.py \
  --directory /absolute/fresh/external/preflight \
  --registry-proof /absolute/private/catalog-receipt.json --allow-live
```

This starts one owned loopback app, invokes Codex with a project-specific trust
table and scoped MCP approvals, then runs the generated spec against the same
app. Codex 0.159.3 requires project trust to discover these local agent files;
`--ignore-user-config` removes stored trust. The whole-table invocation override
avoids global writes. A dotted quoted project override fails strict validation.
The probe preserves attempts and stops on timeout or missing tools.

Retain root and child persistent rollouts in `persistent-rollouts/`, then run:

```bash
python3 scripts/evals/generator-ablation-310/report.py \
  --directory /absolute/external/preflight
```

The receipt requires actual delegation, completed generator setup/read/write
calls, unchanged frozen inputs and native test success. Setup alone and a model
summary cannot prove those claims. This is a transport canary, not an ablation or
quality benchmark. Keep raw captured requests private until reviewed.

## Fixed-scenario comparison

`compare.py --directory /fresh/external/path --machine-config /external/machine.json --prepare-only` freezes one authored
two-counter ownership and reload-persistence scenario, three independent arms
(official only, current twelve rules, candidate four groups), fixed arm order,
source bytes and rule hashes. Host paths come only from an explicit external machine JSON, with exactly these
absolute paths: `setup_template` (a reviewed successful canary freeze), `modules`
(the pinned existing dependency directory), `node`, `codex`, and
`sessions_directory` (the bounded native rollout directory). Preparation resolves
and validates them and freezes their provenance in the protocol. It rewrites
invocation-local MCP paths for the selected host; no embedded account or host
paths are used. Run with `--allow-live` only after reviewing the fresh protocol
and registry proof.

Each cell must show a linked official child and all three defining calls before
the next cell. The harness runs normal, omitted-write, wrong-item-write and
restored conditions and records server-side POST/state witnesses independently
of test assertions. Scanner output is recorded separately, without repairs.
Unexpected setup/control/reach/integrity failures stop later cells. One authored
scenario cannot establish general superiority or justify changing the skill.

The native selector is an escaped relative filename: Playwright treats CLI file
arguments as regular expressions, so absolute paths containing `+` can silently
select no tests. Require exactly one executed test. Preserve failed selection
reports and freeze a runner-only amendment before replaying existing generated
specs; do not regenerate models to fix a selector bug.

The portable harness uses protocol schema 2. Earlier measured schema-1 protocols,
frozen runner bytes and receipts remain unchanged in external evidence. Use their
frozen runner for exact historical replay; do not pass an old protocol to the new
runner. The portability check prepares schema 2 without calling a model/browser;
it does not repeat the comparison or extend its result.
