# Subagent routing confirmation v1

This directory is the separately frozen confirmation case set required by the
parent benchmark's change boundary. It evaluates the provisional, uncommitted
v1.16.2 routing wording without modifying the shared working-tree files.

The confirmation uses a fresh community-theatre domain and the parent harness's
strict two-arm Claude comparison. Sixteen cases run three times per arm: 96
measured strategy executions after a two-execution smoke gate. Reviewer cases
cover `clear`, `same_file`, and `cross_file_or_config`; debugger cases cover
`uncertainty_trigger` and `disagreement_reconciliation`.

The debugger cases are a preregistered A/B proxy. The frozen arms force inline
or named routing and therefore test the empirical premise for the provisional
bounded trigger and inline-wins reconciliation rule; they do not claim to test
whether an unconstrained parent independently elects to delegate.

Codex is out of scope because its two delegation arms remain structurally
unavailable under the parent benchmark's preserved feasibility evidence.

No live execution is authorized by `protocol.json`. The operator's instruction
in the coordinating session authorizes the Claude smoke and measured cells; the
measured authorization is separately bound to the frozen protocol and freeze
digests in `execution-authorization-claude.json`.
