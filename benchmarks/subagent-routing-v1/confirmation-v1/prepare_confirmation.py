#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Materialize the preregistered confirmation protocol and fresh cases."""

from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PARENT = HERE.parent


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, value: object) -> None:
    write_text(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def find_line(files: dict[str, str], path: str, marker: str) -> int:
    hits = [i for i, line in enumerate(files[path].splitlines(), 1) if marker in line]
    if len(hits) != 1:
        raise ValueError(f"{path}: marker {marker!r} matched lines {hits}")
    return hits[0]


def make_case(spec: dict[str, object]) -> tuple[dict[str, object], dict[str, str]]:
    files = spec.pop("files")
    assert isinstance(files, dict)
    case_id = str(spec["case_id"])
    files = {
        path: (
            f"/* confirmation-case: {case_id}/{path} */\n{content}"
            if path.endswith(".css")
            else f"// confirmation-case: {case_id}/{path}\n{content}"
        )
        for path, content in files.items()
    }
    candidate = spec.pop("candidate")
    assert isinstance(candidate, dict)
    marker = candidate.pop("marker")
    candidate["line"] = find_line(files, candidate["file"], marker)
    decisive = []
    for item in spec.pop("decisive"):
        if isinstance(item, str):
            decisive.append(item)
        else:
            decisive.append(f"{item[0]}:{find_line(files, item[0], item[1])}")
    case = {
        "case_id": case_id,
        "task": spec["task"],
        "stratum": spec["stratum"],
        "framework": spec["framework"],
        "repository_root": f"{case_id}/repo",
        "files": [],
        "candidate": candidate,
        "report_excerpt": spec.get("report_excerpt"),
        "oracle": {
            "accepted_verdict": spec["verdict"],
            "decisive_evidence": decisive,
            "allowed_confidence": spec.get("confidence", ["high", "medium"]),
            "required_limitation": spec.get("limitation"),
            "forbidden_weakened_fix": spec.get("forbidden", []),
            "concrete_fix_legal": spec["fix_legal"],
        },
    }
    return case, files


def fv_specs() -> list[dict[str, object]]:
    return [
        {
            "case_id": "CFV-01", "task": "finding_verification", "stratum": "clear", "framework": "playwright",
            "files": {
                "playwright.config.ts": "import { defineConfig } from '@playwright/test';\n// CFV-01 publishes the matinee segment.\nexport default defineConfig({ testDir: './tests' });\n",
                "tests/live-segment.spec.ts": "import { test } from '@playwright/test';\n\ntest('publishes the matinee segment', async ({ page }) => {\n  await page.goto('/box-office/matinee');\n  await page.getByRole('button', { name: 'Publish segment' }).click();\n  await page.getByTestId('segment-live').isVisible();\n});\n",
            },
            "candidate": {"pattern_id": "#8", "file": "tests/live-segment.spec.ts", "marker": "segment-live", "snippet": "await page.getByTestId('segment-live').isVisible();"},
            "verdict": "CONFIRMED", "decisive": [("tests/live-segment.spec.ts", "segment-live")], "confidence": ["high"],
            "forbidden": ["remove the test", "mark the test skipped"], "fix_legal": True,
        },
        {
            "case_id": "CFV-02", "task": "finding_verification", "stratum": "clear", "framework": "cypress",
            "files": {
                "cypress.config.ts": "import { defineConfig } from 'cypress';\n// CFV-02 uses a harmless placeholder card fixture.\nexport default defineConfig({ e2e: { baseUrl: 'http://127.0.0.1:4310' } });\n",
                "cypress/e2e/placeholder-card.cy.ts": "const OBVIOUS_BOX_OFFICE_PLACEHOLDER = '0000-TEST-ONLY';\n\ndescribe('box office fixture', () => {\n  it('renders a harmless placeholder', () => {\n    cy.visit(`/box-office/demo?card=${OBVIOUS_BOX_OFFICE_PLACEHOLDER}`);\n    cy.get('[data-cy=demo-card]').should('contain', 'TEST-ONLY');\n  });\n});\n",
            },
            "candidate": {"pattern_id": "#14", "file": "cypress/e2e/placeholder-card.cy.ts", "marker": "OBVIOUS_BOX_OFFICE_PLACEHOLDER =", "snippet": "const OBVIOUS_BOX_OFFICE_PLACEHOLDER = '0000-TEST-ONLY';"},
            "verdict": "FALSE-POSITIVE", "decisive": [("cypress/e2e/placeholder-card.cy.ts", "OBVIOUS_BOX_OFFICE_PLACEHOLDER =")], "confidence": ["high"], "fix_legal": False,
        },
        {
            "case_id": "CFV-03", "task": "finding_verification", "stratum": "same_file", "framework": "playwright",
            "files": {
                "playwright.config.ts": "import { defineConfig } from '@playwright/test';\n// CFV-03 keeps helper context in the same spec file.\nexport default defineConfig({ testDir: './tests' });\n",
                "tests/cue-panel.spec.ts": "import { test, type Page } from '@playwright/test';\n\nasync function cuePanelIsReady(page: Page): Promise<boolean> {\n  return page.getByTestId('cue-panel-ready').isVisible();\n}\n\ntest('opens the stage cue panel', async ({ page }) => {\n  await page.goto('/stage/cues');\n  await cuePanelIsReady(page);\n});\n",
            },
            "candidate": {"pattern_id": "#8", "file": "tests/cue-panel.spec.ts", "marker": "await cuePanelIsReady", "snippet": "await cuePanelIsReady(page);"},
            "verdict": "CONFIRMED", "decisive": [("tests/cue-panel.spec.ts", "return page.getByTestId"), ("tests/cue-panel.spec.ts", "await cuePanelIsReady")],
            "forbidden": ["delete cuePanelIsReady", "mark the test skipped"], "fix_legal": True,
        },
        {
            "case_id": "CFV-04", "task": "finding_verification", "stratum": "same_file", "framework": "cypress",
            "files": {
                "cypress.config.ts": "import { defineConfig } from 'cypress';\nexport default defineConfig({ e2e: { supportFile: 'cypress/support/e2e.ts' } });\n",
                "cypress/support/e2e.ts": "Cypress.on('uncaught:exception', (error) => {\n  if (error.message === 'Known costume-preview WebGL fallback') {\n    return false;\n  }\n  throw error;\n});\n",
                "cypress/e2e/costume-preview.cy.ts": "describe('costume preview', () => {\n  it('shows the costume name', () => {\n    cy.visit('/costumes/preview');\n    cy.get('[data-cy=costume-name]').should('contain', 'Moon Chorus');\n  });\n});\n",
            },
            "candidate": {"pattern_id": "#3b", "file": "cypress/support/e2e.ts", "marker": "Cypress.on", "snippet": "Cypress.on('uncaught:exception', (error) => {"},
            "verdict": "FALSE-POSITIVE", "decisive": [("cypress/support/e2e.ts", "Known costume-preview"), ("cypress/support/e2e.ts", "throw error")], "fix_legal": False,
        },
        {
            "case_id": "CFV-05", "task": "finding_verification", "stratum": "cross_file_or_config", "framework": "playwright",
            "files": {
                "playwright.config.ts": "import { defineConfig } from '@playwright/test';\nexport default defineConfig({ testDir: './tests', projects: [{ name: 'chromium' }] });\n",
                "src/routes.ts": "export const routes = {\n  '/production/transmitter': { requiredRole: 'technical-director' },\n};\n",
                "tests/transmitter.spec.ts": "import { expect, test } from '@playwright/test';\n\ntest('shows transmitter status', async ({ page }) => {\n  await page.goto('/production/transmitter');\n  await expect(page.getByTestId('transmitter-status')).toContainText('On air');\n});\n",
            },
            "candidate": {"pattern_id": "#12", "file": "tests/transmitter.spec.ts", "marker": "page.goto", "snippet": "await page.goto('/production/transmitter');"},
            "verdict": "FALSE-POSITIVE", "decisive": [("tests/transmitter.spec.ts", "transmitter-status"), ("src/routes.ts", "requiredRole"), ("playwright.config.ts", "projects:")],
            "fix_legal": False,
        },
        {
            "case_id": "CFV-06", "task": "finding_verification", "stratum": "cross_file_or_config", "framework": "cypress",
            "files": {
                "cypress.config.ts": "import { defineConfig } from 'cypress';\nexport default defineConfig({ e2e: { baseUrl: 'https://shared-theatre.invalid' }, env: { backendBoundary: 'shared-staging-database' } });\n",
                "src/audition-booking.ts": "export async function reserveAuditionSlot(slotId: string) {\n  return fetch(`/api/auditions/${slotId}/reservations`, { method: 'POST' });\n}\n",
                "cypress/e2e/audition-booking.cy.ts": "describe('audition booking', () => {\n  it('reserves the evening slot', () => {\n    cy.visit('/auditions');\n    cy.get('[data-cy=reserve-evening]').click();\n    cy.get('[data-cy=reservation-state]').should('contain', 'Reserved');\n  });\n});\n",
            },
            "candidate": {"pattern_id": "#20", "file": "cypress/e2e/audition-booking.cy.ts", "marker": "reserve-evening", "snippet": "cy.get('[data-cy=reserve-evening]').click();"},
            "verdict": "CONFIRMED", "decisive": [("cypress/e2e/audition-booking.cy.ts", "reserve-evening"), ("src/audition-booking.ts", "method: 'POST'"), ("cypress.config.ts", "shared-staging-database")],
            "forbidden": ["disable the test", "ignore the request"], "fix_legal": True,
        },
        {
            "case_id": "CFV-07", "task": "finding_verification", "stratum": "cross_file_or_config", "framework": "playwright",
            "files": {
                "playwright.config.ts": "import { defineConfig } from '@playwright/test';\nexport default defineConfig({ testDir: './tests', projects: [\n  { name: 'auth-setup', testMatch: /director\\.setup\\.ts/ },\n  { name: 'chromium', dependencies: ['auth-setup'], use: { storageState: '.auth/director.json' } },\n] });\n",
                "src/routes.ts": "export const protectedRoutes = ['/production/light-board'];\n",
                "tests/director.setup.ts": "import { expect, test as setup } from '@playwright/test';\nsetup('director auth', async ({ page }) => {\n  await page.goto('/login');\n  await page.getByRole('button', { name: 'Sign in' }).click();\n  await expect(page.getByTestId('role')).toHaveText('technical-director');\n  await page.context().storageState({ path: '.auth/director.json' });\n});\n",
                "tests/light-board.spec.ts": "import { expect, test } from '@playwright/test';\ntest('shows channels', async ({ page }) => {\n  await page.goto('/production/light-board');\n  await expect(page.getByTestId('channel-count')).toHaveText('24');\n});\n",
            },
            "candidate": {"pattern_id": "#12", "file": "tests/light-board.spec.ts", "marker": "page.goto", "snippet": "await page.goto('/production/light-board');"},
            "verdict": "FALSE-POSITIVE", "decisive": [("playwright.config.ts", "dependencies: ['auth-setup']"), ("playwright.config.ts", "storageState:"), ("tests/director.setup.ts", "context().storageState")], "fix_legal": False,
        },
        {
            "case_id": "CFV-08", "task": "finding_verification", "stratum": "cross_file_or_config", "framework": "cypress",
            "files": {
                "cypress.config.ts": "import { defineConfig } from 'cypress';\nexport default defineConfig({ e2e: { baseUrl: 'http://127.0.0.1:4310', supportFile: 'cypress/support/e2e.ts' }, env: { backendBoundary: 'ephemeral-container-reset-per-spec' } });\n",
                "src/prop-checkout.ts": "export async function checkOutProp(propId: string) {\n  return fetch(`/api/props/${propId}/checkout`, { method: 'POST' });\n}\n",
                "cypress/support/e2e.ts": "beforeEach(() => { cy.task('resetEphemeralTheatreDatabase'); });\n",
                "cypress/e2e/prop-checkout.cy.ts": "describe('prop checkout', () => {\n  it('checks out the lantern', () => {\n    cy.visit('/props');\n    cy.get('[data-cy=checkout-brass-lantern]').click();\n    cy.get('[data-cy=prop-state]').should('contain', 'Checked out');\n  });\n});\n",
            },
            "candidate": {"pattern_id": "#20", "file": "cypress/e2e/prop-checkout.cy.ts", "marker": "checkout-brass-lantern", "snippet": "cy.get('[data-cy=checkout-brass-lantern]').click();"},
            "verdict": "FALSE-POSITIVE", "decisive": [("cypress.config.ts", "ephemeral-container-reset-per-spec"), ("cypress/support/e2e.ts", "resetEphemeralTheatreDatabase"), ("src/prop-checkout.ts", "method: 'POST'")], "fix_legal": False,
        },
    ]


def fc_specs() -> list[dict[str, object]]:
    return [
        {
            "case_id": "CFC-01", "task": "failure_classification", "stratum": "uncertainty_trigger", "framework": "playwright",
            "files": {
                "playwright.config.ts": "import { defineConfig } from '@playwright/test';\nexport default defineConfig({ testDir: './tests', retries: 0 });\n",
                "src/cast-banner.tsx": "export function CastBanner({ understudy }: { understudy: boolean }) {\n  if (!understudy) return null;\n  return <aside data-testid=\"understudy-banner\">Understudy tonight</aside>;\n}\n",
                "tests/cast-banner.spec.ts": "import { expect, test } from '@playwright/test';\ntest('shows the understudy notice', async ({ page }) => {\n  await page.goto('/cast?understudy=false');\n  await expect(page.getByTestId('understudy-banner')).toBeVisible();\n});\n",
            },
            "candidate": {"failing_test": "shows the understudy notice", "file": "tests/cast-banner.spec.ts", "marker": "understudy-banner", "snippet": "understudy-banner resolved to no element"},
            "report_excerpt": {"error": {"message": "expect.toBeVisible failed: understudy-banner resolved to no element", "stack": "tests/cast-banner.spec.ts:4:60"}, "dom_snapshot": {"understudy": False, "banner_present": False}, "attempt_summary": "one failure; retries disabled"},
            "verdict": "F6", "decisive": [("tests/cast-banner.spec.ts", "page.goto"), ("src/cast-banner.tsx", "if (!understudy)"), "report_excerpt#error.message"],
            "forbidden": ["remove the assertion", "waitForTimeout"], "fix_legal": True,
        },
        {
            "case_id": "CFC-02", "task": "failure_classification", "stratum": "uncertainty_trigger", "framework": "cypress",
            "files": {
                "cypress.config.ts": "import { defineConfig } from 'cypress';\n// CFC-02 classifies a swallowed reservation request.\nexport default defineConfig({ e2e: { baseUrl: 'http://127.0.0.1:4310' } });\n",
                "cypress/support/commands.ts": "Cypress.Commands.add('reserveRehearsalRoom', () => {\n  return cy.request('POST', '/api/rehearsals/reservations').then(undefined, () => undefined);\n});\n",
                "cypress/e2e/rehearsal-room.cy.ts": "describe('rehearsal room', () => {\n  it('shows the reserved state', () => {\n    cy.reserveRehearsalRoom();\n    cy.get('[data-cy=room-state]').should('have.text', 'Reserved');\n  });\n});\n",
            },
            "candidate": {"failing_test": "shows the reserved state", "file": "cypress/e2e/rehearsal-room.cy.ts", "marker": "room-state", "snippet": "room-state was Available rather than Reserved"},
            "report_excerpt": {"error": {"message": "expected room-state to have text 'Reserved', but it was 'Available'", "stack": "cypress/e2e/rehearsal-room.cy.ts:4:40"}, "network": {"request": "POST /api/rehearsals/reservations", "result": "rejected before response"}, "attempt_summary": "custom command completed and assertion failed"},
            "verdict": "F13", "decisive": [("cypress/support/commands.ts", "then(undefined"), "report_excerpt#network.result", ("cypress/e2e/rehearsal-room.cy.ts", "room-state")],
            "forbidden": ["remove the assertion", "return false"], "fix_legal": True,
        },
        {
            "case_id": "CFC-03", "task": "failure_classification", "stratum": "uncertainty_trigger", "framework": "playwright",
            "files": {
                "playwright.config.ts": "import { defineConfig } from '@playwright/test';\nexport default defineConfig({ testDir: './tests', retries: 1 });\n",
                "tests/cue-sequence.spec.ts": "import { expect, test } from '@playwright/test';\nlet previousCue = '';\ntest.beforeEach(async ({ page }) => {\n  if (previousCue) await page.evaluate((cue) => localStorage.setItem('previousCue', cue), previousCue);\n});\ntest('records opening cue', async ({ page }) => { previousCue = 'opening'; await page.goto('/stage/cues'); });\ntest('shows closing cue independently', async ({ page }) => {\n  await page.goto('/stage/cues');\n  await expect(page.getByTestId('closing-cue')).toBeVisible();\n});\n",
            },
            "candidate": {"failing_test": "shows closing cue independently", "file": "tests/cue-sequence.spec.ts", "marker": "closing-cue", "snippet": "timeout waiting for closing-cue"},
            "report_excerpt": {"error": {"message": "Timeout 5000ms exceeded while waiting for closing-cue", "stack": "tests/cue-sequence.spec.ts:9:55"}, "isolation_probe": {"alone": "10/10 passed", "full_suite": "failed after opening cue test"}, "attempt_summary": "failure only in complete file"},
            "verdict": "F7", "decisive": ["report_excerpt#isolation_probe.alone", "report_excerpt#isolation_probe.full_suite", ("tests/cue-sequence.spec.ts", "let previousCue")], "confidence": ["high"],
            "forbidden": ["reorder the tests", "workers: 1"], "fix_legal": True,
        },
        {
            "case_id": "CFC-04", "task": "failure_classification", "stratum": "uncertainty_trigger", "framework": "cypress",
            "files": {
                "cypress.config.ts": "import { defineConfig } from 'cypress';\nexport default defineConfig({ e2e: { retries: 1 } });\n",
                "cypress/e2e/costume-rack.cy.ts": "describe('costume rack', () => {\n  it('shows moon-chorus costume', () => {\n    cy.visit('/costumes');\n    cy.get('[data-cy=moon-chorus]').should('be.visible');\n  });\n});\n",
            },
            "candidate": {"failing_test": "shows moon-chorus costume", "file": "cypress/e2e/costume-rack.cy.ts", "marker": "cy.get('[data-cy=moon-chorus]')", "snippet": "timed out waiting for moon-chorus"},
            "report_excerpt": {"error": {"message": "Timed out retrying: expected moon-chorus to be visible", "stack": "cypress/e2e/costume-rack.cy.ts:4:38"}, "attempt_summary": "initial attempt failed and retry passed", "isolation_probe": {"performed": False, "missing_evidence": "spec-alone repetitions and full-suite run"}},
            "verdict": "CANNOT_VERIFY", "decisive": ["report_excerpt#isolation_probe.performed", ("cypress.config.ts", "retries: 1")],
            "limitation": "full-suite run", "fix_legal": False,
        },
        {
            "case_id": "CFC-05", "task": "failure_classification", "stratum": "disagreement_reconciliation", "framework": "playwright",
            "files": {
                "playwright.config.ts": "import { defineConfig } from '@playwright/test';\n// CFC-05 classifies a beforeAll setup hook failure.\nexport default defineConfig({ testDir: './tests' });\n",
                "tests/box-office-suite.spec.ts": "import { expect, test } from '@playwright/test';\ntest.beforeAll(async ({ request }) => {\n  const response = await request.post('/api/fixtures/box-office-seed');\n  const payload = await response.json();\n  expect(payload.seededProductions).toContain('matinee');\n});\ntest('lists matinee tickets', async ({ page }) => { await page.goto('/box-office/matinee'); });\ntest('lists evening tickets', async ({ page }) => { await page.goto('/box-office/evening'); });\n",
            },
            "candidate": {"failing_test": "box office suite (two affected tests)", "file": "tests/box-office-suite.spec.ts", "marker": "test.beforeAll", "snippet": "beforeAll seed payload omitted the required matinee production"},
            "report_excerpt": {"error": {"message": "beforeAll hook failed: expected seededProductions [] to contain matinee", "stack": "tests/box-office-suite.spec.ts:6:37"}, "seed_payload": {"http_status": 200, "seeded_productions": []}, "suite_summary": {"failed": 2, "identical_hook_failures": 2, "test_body_failures": 0}, "attempt_summary": "both tests failed from the same missing seed fixture"},
            "verdict": "F9", "decisive": ["report_excerpt#seed_payload", "report_excerpt#suite_summary", ("tests/box-office-suite.spec.ts", "seededProductions")],
            "forbidden": ["skip both tests", "increase retries"], "fix_legal": True,
        },
        {
            "case_id": "CFC-06", "task": "failure_classification", "stratum": "disagreement_reconciliation", "framework": "cypress",
            "files": {
                "cypress.config.ts": "import { defineConfig } from 'cypress';\nexport default defineConfig({ viewportWidth: process.env.CI ? 620 : 1280, viewportHeight: 800 });\n",
                "src/matinee-layout.css": "[data-cy='desktop-matinee-grid'] { display: grid; }\n@media (max-width: 700px) {\n  [data-cy='desktop-matinee-grid'] { display: none; }\n  [data-cy='mobile-matinee-list'] { display: block; }\n}\n",
                "cypress/e2e/matinee-grid.cy.ts": "describe('matinee grid', () => {\n  it('opens noon performance', () => {\n    cy.visit('/performances');\n    cy.get('[data-cy=desktop-matinee-grid] [data-cy=noon]').click();\n  });\n});\n",
            },
            "candidate": {"failing_test": "opens noon performance", "file": "cypress/e2e/matinee-grid.cy.ts", "marker": "desktop-matinee-grid", "snippet": "desktop grid not visible in CI"},
            "report_excerpt": {"error": {"message": "desktop-matinee-grid noon element is not visible", "stack": "cypress/e2e/matinee-grid.cy.ts:4:65"}, "environment": {"local": "passed at 1280x800", "ci": "failed at 620x800"}, "attempt_summary": "only CI viewport reproduces"},
            "verdict": "F8", "decisive": [("cypress.config.ts", "process.env.CI"), ("cypress/e2e/matinee-grid.cy.ts", "desktop-matinee-grid"), "report_excerpt#environment"],
            "forbidden": ["force: true", "cy.wait("], "fix_legal": True,
        },
        {
            "case_id": "CFC-07", "task": "failure_classification", "stratum": "disagreement_reconciliation", "framework": "playwright",
            "files": {
                "playwright.config.ts": "import { defineConfig } from '@playwright/test';\n// CFC-07 classifies an expired director storage state.\nexport default defineConfig({ testDir: './tests' });\n",
                "tests/director-console.spec.ts": "import { expect, test } from '@playwright/test';\ntest.use({ storageState: '.auth/expired-director.json' });\ntest('shows director console', async ({ page }) => {\n  await page.goto('/production/director-console');\n  await expect(page.getByTestId('director-controls')).toBeVisible();\n});\n",
            },
            "candidate": {"failing_test": "shows director console", "file": "tests/director-console.spec.ts", "marker": "director-controls", "snippet": "director-controls resolved to no element"},
            "report_excerpt": {"error": {"message": "director-controls resolved to no element; current URL /login?expired=1", "stack": "tests/director-console.spec.ts:5:58"}, "session": {"storage_state": ".auth/expired-director.json", "redirect": "/login?expired=1"}, "attempt_summary": "failed on both attempts"},
            "verdict": "F10", "decisive": ["report_excerpt#session.redirect", ("tests/director-console.spec.ts", "expired-director.json")],
            "forbidden": ["remove the assertion", "waitForTimeout"], "fix_legal": True,
        },
        {
            "case_id": "CFC-08", "task": "failure_classification", "stratum": "disagreement_reconciliation", "framework": "cypress",
            "files": {
                "cypress.config.ts": "import { defineConfig } from 'cypress';\n// CFC-08 classifies intercept registration order.\nexport default defineConfig({ e2e: { baseUrl: 'http://127.0.0.1:4310' } });\n",
                "cypress/e2e/prop-return.cy.ts": "describe('prop return', () => {\n  it('records lantern return', () => {\n    cy.visit('/props/lantern');\n    cy.get('[data-cy=return-prop]').click();\n    cy.intercept('POST', '/api/props/lantern/return').as('returnProp');\n    cy.wait('@returnProp');\n  });\n});\n",
            },
            "candidate": {"failing_test": "records lantern return", "file": "cypress/e2e/prop-return.cy.ts", "marker": "cy.wait", "snippet": "cy.wait found no aliased request"},
            "report_excerpt": {"error": {"message": "cy.wait timed out for route returnProp; no request occurred", "stack": "cypress/e2e/prop-return.cy.ts:6:8"}, "network": {"observed": "POST completed after click before intercept registration"}, "attempt_summary": "same ordering on both attempts"},
            "verdict": "F11", "decisive": [("cypress/e2e/prop-return.cy.ts", "return-prop]').click"), ("cypress/e2e/prop-return.cy.ts", "cy.intercept"), "report_excerpt#network.observed"],
            "forbidden": ["increase the timeout", "cy.wait(5000"], "fix_legal": True,
        },
    ]


def main() -> None:
    if (HERE / "freeze-record.json").exists():
        raise SystemExit("confirmation is frozen; preparation cannot run again")
    for path in (HERE / "protocol.json", HERE / "cases", HERE / "smoke", HERE / "evaluated-snapshot"):
        if path.exists():
            raise SystemExit(f"refusing to overwrite preparation output: {path}")

    sources = [
        "skills/e2e-reviewer/SKILL.md",
        "skills/e2e-reviewer/references/pattern-reference.md",
        "skills/playwright-debugger/SKILL.md",
        "skills/cypress-debugger/SKILL.md",
        "agents/e2e-finding-verifier.md",
        "agents/e2e-failure-classifier.md",
    ]
    snapshot: dict[str, str] = {}
    for relative in sources:
        destination = HERE / "evaluated-snapshot" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / relative, destination, follow_symlinks=False)
        snapshot[destination.relative_to(ROOT).as_posix()] = digest(destination)
    snapshot["benchmarks/subagent-routing-v1/run_routing.py"] = digest(PARENT / "run_routing.py")

    materialized = [make_case(spec) for spec in fv_specs() + fc_specs()]
    manifest_cases = []
    for case, files in materialized:
        repo = HERE / "cases" / str(case["repository_root"])
        for relative, content in files.items():
            write_text(repo / relative, content)
        case["files"] = [{"path": rel, "sha256": digest(repo / rel)} for rel in sorted(files)]
        manifest_cases.append(case)
    write_json(HERE / "cases/manifest.json", {"schema_version": 1, "protocol_id": "subagent-routing-v1", "kind": "measured", "cases": manifest_cases})

    smoke_spec = {
        "case_id": "SMOKE-CFV-01", "task": "finding_verification", "stratum": "sacrificial_clear", "framework": "playwright",
        "files": {
            "playwright.config.ts": "import { defineConfig } from '@playwright/test';\nexport default defineConfig({ testDir: './tests' });\n",
            "tests/orchestra-call.spec.ts": "import { test } from '@playwright/test';\ntest('records orchestra call', async ({ page }) => {\n  await page.goto('/rehearsals/orchestra-call');\n  await page.getByTestId('call-recorded').isVisible();\n});\n",
        },
        "candidate": {"pattern_id": "#8", "file": "tests/orchestra-call.spec.ts", "marker": "call-recorded", "snippet": "await page.getByTestId('call-recorded').isVisible();"},
        "verdict": "CONFIRMED", "decisive": [("tests/orchestra-call.spec.ts", "call-recorded")], "confidence": ["high"], "forbidden": ["remove the test"], "fix_legal": True,
    }
    smoke_case, smoke_files = make_case(smoke_spec)
    smoke_repo = HERE / "smoke" / str(smoke_case["repository_root"])
    for relative, content in smoke_files.items():
        write_text(smoke_repo / relative, content)
    smoke_case["files"] = [{"path": rel, "sha256": digest(smoke_repo / rel)} for rel in sorted(smoke_files)]
    write_json(HERE / "smoke/manifest.json", {"schema_version": 1, "protocol_id": "subagent-routing-v1", "kind": "smoke", "cases": [smoke_case]})

    protocol = copy.deepcopy(json.loads((PARENT / "protocol.json").read_text(encoding="utf-8")))
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    protocol["protocol_revision"] = 1
    protocol["revision_history"] = []
    protocol["confirmation"] = {
        "confirmation_id": "subagent-routing-v1-confirmation-v1",
        "target": "uncommitted provisional v1.16.2 delegation wording",
        "evaluated_worktree_snapshot": True,
        "host_scope": ["claude"],
        "codex_out_of_scope_reason": "delegation arms remain structurally unavailable",
        "debugger_policy_test_method": "preregistered inline-vs-named A/B proxy",
    }
    protocol["objective"] = "Confirm reviewer clear/same-file/cross-file routing and debugger uncertainty-trigger/inline-wins reconciliation on fresh cases."
    protocol["evaluated_snapshot"] = {
        "policy": "Exact provisional working-tree bytes copied before any live call; copied bytes are immutable evaluated inputs.",
        "git_head_at_preparation": head,
        "git_tag_at_preparation": None,
        "sha256_at_preparation": snapshot,
        "freeze_record_file": "freeze-record.json",
        "freeze_record_exists": False,
    }
    slots = []
    for case in manifest_cases:
        slot = {key: case[key] for key in ("case_id", "task", "stratum", "framework")}
        if case["task"] == "finding_verification":
            slot["pattern_id"] = case["candidate"]["pattern_id"]
        slot["expected"] = case["oracle"]["accepted_verdict"]
        slot["sketch"] = f"fresh community-theatre {case['stratum']} case"
        slots.append(slot)
    protocol["case_set"] = {
        "count": 16, "status": "AUTHORED_PREREGISTERED_NOT_FROZEN", "domain": "community theatre operations",
        "disposable_repository_rule": "Self-contained UTF-8 text; no secrets, network execution, model instructions, or mutable state.",
        "per_case_predeclared": protocol["case_set"]["per_case_predeclared"], "slots": slots,
        "smoke_cases": {"count": 1, "definition": "one sacrificial community-theatre case outside measured slots", "proves": protocol["case_set"]["smoke_cases"]["proves"]},
    }
    protocol["hosts"]["claude"]["budget"].update({"strategy_executions_measured": 96, "strategy_executions_smoke": 2, "strategy_executions_total_max": 110, "judge_calls_max": 0})
    protocol["hosts"]["codex"]["status"] = "out_of_scope_confirmation"
    protocol["schedule"]["full_matrix"] = {"claude_strategy_executions": 96, "codex_strategy_executions": 0, "total_strategy_executions": 96, "smoke_strategy_executions": 2, "judge_calls_max": 0, "note": "Claude-only confirmation."}
    protocol["schedule"]["claude_only_phase"] = {"strategy_executions": 96, "smoke": 2, "judge_calls_max": 0, "total_max": 110}
    protocol["confirmation_decision_rule"] = {
        "analysis_unit": "unique majority-stable case: at least 2 of 3 identical verdicts",
        "reviewer_upheld": "No stable named-only advantage on clear or same_file; at least two stable named-only advantages on cross_file_or_config; no stable inline-only advantage there; no harmful fix or safety regression.",
        "reviewer_revise": "Any stable named-only advantage on clear or same_file, any stable inline-only advantage on cross_file_or_config, fewer than two named-only cross-file/config advantages, or any safety regression.",
        "debugger_upheld": "No stable named PASS paired with stable inline FAIL; every stable disagreement favors inline; no harmful fix or safety regression.",
        "debugger_revise": "Any stable named PASS paired with stable inline FAIL, or any safety regression.",
        "debugger_proxy_limitation": "Forced-route A/B tests the empirical premise, not whether a free-running model elects to delegate.",
        "overall": "FULLY_CONFIRMED only if reviewer_upheld and debugger_upheld; otherwise NEEDS_WORDING_REVISION",
    }
    protocol["freshness_exclusion_search"] = {
        "performed_on": dt.date.today().isoformat(), "domain": "community theatre operations",
        "command": "git grep -n -i -E 'community theatre|box office|matinee|audition slot|stage cue|rehearsal room|prop checkout|costume rack' -- . ':(exclude)benchmarks/subagent-routing-v1/confirmation-v1'",
        "result": "zero hits before case authoring; no exact-byte duplicate files within the measured case tree after authoring",
        "excluded_prior_domains": "All domains listed in ../README.md, plus public-library, jobs/reports, and garden/harvest pilots.",
    }
    protocol["limitations"] = [
        "One Claude host; no cross-host claim.",
        "Forced-route debugger A/B tests the policy premise, not autonomous route selection.",
        "The provisional source files are user-owned and remain untouched; immutable copies are evaluated.",
    ]
    write_json(HERE / "protocol.json", protocol)


if __name__ == "__main__":
    main()
