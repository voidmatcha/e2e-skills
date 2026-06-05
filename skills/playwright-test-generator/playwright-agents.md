# Playwright Agents Interop (Playwright ≥ 1.56)

Playwright v1.56+ ships three first-party AI agents — **planner** (explores the app, writes a Markdown test plan to `specs/`), **generator** (turns plans into specs), **healer** (re-runs failures, re-resolves locators by semantic intent, patches). Docs: https://playwright.dev/docs/test-agents

## When to prefer which

| Situation | Use |
|-----------|-----|
| Playwright < 1.56, upgrade is risky (e.g. pixel-perfect visual baselines would need full re-capture) | This skill's pipeline as-is — do not upgrade just for agents |
| Playwright ≥ 1.56, interactive session, few targeted specs | This skill's pipeline (tighter approval gates, project-convention awareness) |
| Playwright ≥ 1.56, bulk generation (10+ scenarios from a written plan) | `init-agents` loop; feed it the conventions doc + seed spec this skill produced in Step 5b |

## Setup

```bash
npx playwright init-agents --loop=claude   # also: --loop=vscode, --loop=opencode
```

Produces agent definitions, a `specs/` directory for Markdown test plans, and a `seed.spec.ts`. The seed test is the context bootstrap — point it at the project's existing fixtures/auth setup rather than letting it invent one.

## Division of labor with this skill

- The conventions doc + seed spec from Step 5b are exactly what the planner/generator consume best — generate them first, then hand off.
- The healer's intent-based locator re-resolution is the same approach as this skill's Step 7 failure handling; on < 1.56 projects, this skill's loop is the fallback.
- Cost expectations (practitioner-reported, 2025–2026): a full plan→generate→heal loop runs roughly $0.30–0.60 of tokens per medium flow; expect 5–15 specs per session before the context window fills.
