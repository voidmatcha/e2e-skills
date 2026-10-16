# Hypotheses (written before any call of v7)

Context: the 3.0.0 debuggers load one mandatory first reference (`artifact-extraction.md`) and read the classification and fix-verification references on demand; the safety text moved out of `SKILL.md` into `references/safety-procedures.md`. `SKILL.md` falls from about 21 KB to about 11 KB per framework. No accuracy run of the 3.0.0 text exists. Earlier runs (v2, v3, v5, v6) found no accuracy lift from the skill text over a taxonomy-free prompt, and a skill-arm advantage only in fewer unsupported claims.

H1 (primary, non-inferiority): on zero-tool diagnosis of the 28 v3 cases, the typical-path text (`new-lean`) is not worse than the 2.0.1 text (`old`) by more than 0.05 on strict root-cause match (95% case-cluster lower bound), by more than 0.10 on F-code exact match (labeled cases, 95% lower bound), by more than 0.05 on product/test attribution, or by more than 0.30 unsupported claims per answer, while using at most 0.80 of its input tokens.

H2 (secondary): the worst-case text (`new-full`) is not worse than `old` on the same four quality checks.

H3 (secondary): reading fewer references (`new-lean` versus `new-full`) does not lower quality on the same checks. This is the cleanest test of the lean path because both arms use the same classification tables.

Not hypothesised: superiority of any arm; that the conditional load of `safety-procedures.md` works; anything about tool use, redaction, the launcher or the acquisition workflow.

Expected, stated so a surprise is visible: `old` and both `new` arms within noise of each other and of `free` on strict match (as in v2/v3/v5/v6), `new` arms ahead of `free` on unsupported claims, and F-code agreement higher for the `new` arms than for `old` because the labels were agreed on the new tables (a label effect, not evidence of better text).
