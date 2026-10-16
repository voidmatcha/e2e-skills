# Changes: generator ablation v2

## 2026-10-15: owner decisions (pre-freeze, nothing frozen)

- Model choice: the owner delegated it to the stated rule. The default stays `gpt-6-sol` (no `gpt-6-luna` override, `model_selection.owner_choice` stays null). The v3 admission of the model remains a precondition of every model-calling command.
- Dollar rates (`cost_deliverable.dollars.rates_per_million_tokens`) stay unfilled; rates are never guessed.
- The 16 extra preflight cells are kept.

Recorded in `protocol.json` (`model_selection.owner_decisions`) and in the README "Selection before outcomes" section.
