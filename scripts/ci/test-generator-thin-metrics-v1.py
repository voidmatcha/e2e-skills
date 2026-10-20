#!/usr/bin/env python3
"""Offline regression tests for thin-layer diagnostic counters. Apache-2.0."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/evals"))
spec = importlib.util.spec_from_file_location("thin_metrics", ROOT / "scripts/evals/generator_thin_metrics_v1.py")
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


class HygieneTests(unittest.TestCase):
    def test_delivered_counts(self):
        result = metrics.analyze_spec_text('''
        const submit = page.getByRole('button', {name:'Submit'});
        test('Behavior 12', async () => {
          await page.locator('#save .primary').nth(0).click();
          await page.locator('[data-test="literal.#words"] .active').first().click();
          await page.getByText('Save').last().click();
          await expect(submit).toBeTruthy();
          await expect(page.getByLabel('Name')).not.toBeUndefined();
          expect(true).toBe(true);
          await expect(submit).toHaveClass('active');
        });
        test.only('  SCENARIO   02  ', async () => {});
        test('Test 7 opens settings', async () => {});
        ''')
        self.assertEqual(result["counts"], {"id_selectors": 1, "class_selectors": 2,
            "positional_locators": 3, "to_have_class_assertions": 1,
            "generic_numbered_titles": 2, "vacuous_assertions": 3, "tests": 3})

    def test_comments_quotes_regex_and_template_bodies_are_opaque(self):
        result = metrics.analyze_spec_text(r'''
        // page.locator('#bad .bad').nth(0); expect(true); test('Behavior 1',()=>{});
        /* await expect(page.locator('#x')).toHaveClass('bad'); */
        const text = "page.locator('#bad .bad').nth(0); expect(true)";
        const rx = /expect(true).*page.locator('#bad .bad').nth(0)/g;
        const nested = `ignored ${`page.locator('#bad .bad').first()`} expect(true)`;
        await expect(page.getByRole('button')).toBeVisible();
        test.describe('Scenario 1', () => {});
        /x/.test('Behavior 1');
        test('Changes the theme', async () => {});
        ''')
        expected = dict.fromkeys(metrics.COUNTERS, 0)
        expected["tests"] = 1
        self.assertEqual(result["counts"], expected)

    def test_dynamic_selectors_are_unresolved_not_zero_evidence(self):
        result = metrics.analyze_spec_text('''
        page.locator(`#${key}`); page.locator('.' + name); page.locator(selector);
        page.locator(`.literal`); page.locator('[href="https://x.y/#z"]');
        ''')
        self.assertEqual(result["unresolved_selector_calls"], 3)
        self.assertEqual(result["counts"]["id_selectors"], 0)
        self.assertEqual(result["counts"]["class_selectors"], 1)

    def test_attribute_selector_equivalents_and_values(self):
        result = metrics.analyze_spec_text('''
        page.locator('[id="x"] [ID^="y"] [id$=z] [id*=a] [id|=b] [id~=c] [id]');
        page.locator('[class="x"] [CLASS~="y"] [class^=z] [class$=a] [class*=b] [class|=c] [class]');
        page.locator('[data-id="x.#y"] [data-class=".x#y"] [href="https://x.y/#z"]');
        page.locator('[data-text="]#not-an-id.not-a-class"] .real#real');
        ''')
        self.assertEqual(result["counts"]["id_selectors"], 8)
        self.assertEqual(result["counts"]["class_selectors"], 8)

    def test_text_and_selector_engines_do_not_create_css_dependencies(self):
        cases = [
            ('button:has-text(".docs #help")', 0, 0),
            ('button:text(".docs #help"):text-is(".more #other")', 0, 0),
            ('text=Read .docs #help', 0, 0),
            ('text="Read .docs #help >> css=.fake#fake"', 0, 0),
            ('"Read .docs #help"', 0, 0),
            ('xpath=//button[contains(., ".docs #help")]', 0, 0),
            ('//button[contains(., ".docs #help")]', 0, 0),
            ('custom=.docs #help', 0, 0),
            ('css=#help .docs', 1, 1),
            ('css:light=#help .docs', 1, 1),
            ('#help.docs:has-text(".fake #fake")', 1, 1),
            ('button:has(#help.docs)', 1, 1),
            ('text=Read .fake #fake >> css=#help .docs', 1, 1),
            ('css=#help .docs >> text=Read .fake #fake', 1, 1),
            ('xpath=//button >> #help .docs >> text=".fake #fake"', 1, 1),
            ('css=button:has-text(".fake #fake >> css=.fake") >> css=.docs#help', 1, 1),
        ]
        for selector, ids, classes in cases:
            with self.subTest(selector=selector):
                # Use template quotes to preserve the selector's quoted text.
                result = metrics.analyze_spec_text(f'page.locator(`{selector}`);')
                self.assertEqual(result["counts"]["id_selectors"], ids)
                self.assertEqual(result["counts"]["class_selectors"], classes)
                self.assertEqual(result["unresolved_selector_calls"], 0)

    def test_native_css_calls_and_playwright_engine_calls(self):
        result = metrics.analyze_spec_text('''
        page.$('text=Read .docs #help'); page.$$('text=Read .docs #help');
        page.waitForSelector('text=Read .docs #help');
        document.querySelector('#help.docs[data-label=".fake #fake"]');
        document.querySelectorAll('#help.docs');
        ''')
        self.assertEqual(result["counts"]["id_selectors"], 2)
        self.assertEqual(result["counts"]["class_selectors"], 2)

    def test_truthiness_tracks_simple_alias_and_observable_assertions(self):
        result = metrics.analyze_spec_text('''
        const row = page.locator('tr'); const alias = row;
        expect(alias).toBeDefined();
        await expect(row).toBeVisible(); await expect(row).toHaveCount(2);
        expect(user.isActive).toBeTruthy(); expect(ready).toBeTruthy();
        ''')
        self.assertEqual(result["counts"]["vacuous_assertions"], 1)

    def test_computed_locator_values_are_not_locators(self):
        result = metrics.analyze_spec_text('''
        const row = page.getByRole('row', {name:'Name'});
        const count = await row.count(); const visible = await page.locator('tr').isVisible();
        await expect(await row.count()).toBeTruthy();
        await expect(await page.getByRole('button').count()).toBeTruthy();
        await expect(await page.locator('tr').isVisible()).toBeTruthy();
        expect(count).toBeTruthy(); expect(visible).toBeTruthy();
        expect(helper(page.locator('tr'))).toBeTruthy();
        expect(row).toBeTruthy(); expect(page.getByRole('row').first()).toBeDefined();
        ''')
        self.assertEqual(result["counts"]["vacuous_assertions"], 2)

    def test_identical_primitive_literal_assertions_are_bounded(self):
        result = metrics.analyze_spec_text('''
        expect(false).toBe(false); expect(1).toEqual(1); expect('x').toStrictEqual('x');
        expect(false).toBe(true); expect(1).toBe(2); expect('x').toBe('y');
        expect(value).toBe(value); expect(1 + 1).toBe(2);
        ''')
        self.assertEqual(result["counts"]["vacuous_assertions"], 3)

    def test_assertion_messages_and_nested_template_regex_stay_safe(self):
        result = metrics.analyze_spec_text(r'''
        const unused = `${ /}/.test('}') ? `expect(true); page.locator('#bad')` : '' }`;
        const button = page.getByRole('button', {name:'Save'});
        expect(true, 'message').toBe(true);
        expect(button, 'message').toBeTruthy();
        await expect(page.getByRole('button', {name:'Save'}), 'message').toBeVisible();
        ''')
        self.assertEqual(result["counts"]["vacuous_assertions"], 2)
        self.assertEqual(result["counts"]["id_selectors"], 0)

    def test_placeholder_titles_are_full_case_insensitive_titles(self):
        result = metrics.analyze_spec_text('''
        test('behavior 1', () => {}); test.skip('TEST 33', () => {});
        test('Scenario 0', () => {}); test('Test 1: signs in', () => {});
        test('Behavior 9 works', () => {}); test('scenario names', () => {});
        ''')
        self.assertEqual(result["counts"]["generic_numbered_titles"], 3)
        self.assertEqual(result["counts"]["tests"], 6)

    def test_missing_and_invalid_files_never_become_clean_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            good, bad, absent = (Path(tmp) / name for name in ("good.spec.ts", "bad.spec.ts", "missing.spec.ts"))
            good.write_text("test('Saves the form', () => {});", encoding="utf-8")
            bad.write_bytes(b"\xff")
            complete = metrics.analyze_delivered_specs([good])
            self.assertTrue(complete["available"])
            self.assertEqual(complete["tests_per_file"][str(good)], 1)
            self.assertEqual(complete["unresolved_selector_calls"], 0)
            partial = metrics.analyze_delivered_specs([good, bad, absent])
            self.assertFalse(partial["available"])
            self.assertIsNone(partial["counts"])
            self.assertIsNone(partial["unresolved_selector_calls"])
            self.assertIsNone(partial["tests_per_file"][str(absent)])
            self.assertFalse(metrics.analyze_delivered_specs([])["available"])


class DesignTests(unittest.TestCase):
    def test_simulation_is_deterministic_and_limits_inference(self):
        result = metrics.power_simulation(simulations=12)
        self.assertEqual(result, metrics.power_simulation(simulations=12))
        self.assertEqual(result["seed"], 20261016)
        self.assertEqual(result["models"], 3)
        self.assertEqual(result["sign_flip_min_p"], .25)
        self.assertIsNone(result["sign_flip_80_percent_mde"])
        self.assertEqual(result["comparisons"], ["D_minus_A", "E_minus_D", "E_minus_B", "C_minus_E", "F_minus_A", "F_minus_D",
                                                 "F_minus_E", "G_minus_F", "G_minus_E", "G_minus_A"])
        self.assertIn("indirect", result["comparison_basis"]["F_minus_E"])
        self.assertIn("scanner effect on the CLI surface", result["comparison_basis"]["G_minus_F"])
        self.assertIn("equal scanner gate", result["comparison_basis"]["G_minus_E"])
        self.assertIn("official agent as it is", result["comparison_basis"]["G_minus_A"])
        self.assertNotIn("optional arm G", json.dumps(result["comparison_basis"]))
        self.assertIn("only when optional arm B", result["comparison_basis"]["E_minus_B"])
        self.assertIn("cross-campaign descriptive", result["comparison_basis"]["C_minus_E"])
        self.assertEqual(set(result["arms"]), set("ABCDEFG"))
        self.assertEqual(result["cells_per_arm_model"], 24)
        self.assertEqual(result["cells_per_model_default_A_D_E_F_G"], 120)
        self.assertEqual(result["cells_per_model_all_seven_arms"], 168)
        self.assertEqual(result["default_scored_cells"], 360)
        self.assertEqual(result["maximum_scored_cells"], 504)
        self.assertEqual(result["quality_point_margin"], .10)
        self.assertEqual(result["maximum_processed_token_ratio"], .80)  # E versus B and C, unchanged
        self.assertEqual(result["maximum_cli_token_ratio"], 1.10)  # F and G versus A, D and E
        self.assertEqual(result["shipping_deficit"], .20)
        self.assertIn("not joint", result["scope"])
        self.assertIn("B reuses A", result["unmodeled"][0])
        self.assertTrue(any("cross-campaign arm C reference" in item for item in result["unmodeled"]))
        self.assertTrue(any("sufficiency" in item for item in result["unmodeled"]))
        self.assertTrue(any("cost thresholds" in item for item in result["unmodeled"]))
        self.assertEqual(len(result["scenarios"]), 6)
        for scenario in result["scenarios"]:
            self.assertIn(scenario["fidelity"], (.75, 1.0))
            self.assertTrue(all(0 <= r["trigger_probability"] <= 1 for r in scenario["rows"]))
            self.assertTrue(all(0 <= r["cheap_stack_within_margin_probability"] <= 1 for r in scenario["rows"]))
            # Both rules include equality at .10; they are not complements.
            self.assertTrue(all(r["trigger_probability"] + r["cheap_stack_within_margin_probability"] >= .9999 for r in scenario["rows"]))
            self.assertTrue(all(scenario["baseline"] + r["risk_difference"] <= 1.00000001 for r in scenario["rows"]))
        with self.assertRaises(ValueError):
            metrics.power_simulation(0)
        for bad in (0, 4):
            with self.assertRaises(ValueError):
                metrics.power_simulation(12, models=bad)

    def test_fewer_model_clusters_change_the_sign_flip_floor_not_the_three_model_stream(self):
        for models, floor in ((1, 1.0), (2, .5), (3, .25)):
            result = metrics.power_simulation(simulations=6, models=models)
            self.assertEqual((result["models"], result["sign_flip_min_p"], result["default_scored_cells"]), (models, floor, models * 120))
            self.assertIn(("1" if models == 1 else str(models)) + " model cluster", result["sign_flip_limitation"])
            self.assertIsNone(result["sign_flip_80_percent_mde"])
        # The three-model stream is the earlier artifact's stream: changing the model count only changes the draws consumed.
        self.assertEqual(metrics.power_simulation(simulations=6)["scenarios"], metrics.power_simulation(simulations=6, models=3)["scenarios"])
        self.assertNotEqual(metrics.power_simulation(simulations=6, models=2)["scenarios"],
                            metrics.power_simulation(simulations=6, models=3)["scenarios"])

    def test_bundle_has_all_roster_sizes_and_defaults_to_two_models(self):
        bundle = metrics.power_bundle(simulations=3)
        self.assertEqual(bundle["stage_1_default_models"], 2)
        self.assertEqual(sorted(bundle["designs"]), ["1", "2", "3"])
        self.assertEqual([bundle["designs"][k]["models"] for k in "123"], [1, 2, 3])
        self.assertIn("minimum p = 0.5", bundle["note"])

    def test_committed_sensitivity_retains_numerics_and_does_not_claim_joint_power(self):
        bundle = json.loads((ROOT / "benchmarks/generator-thin-eval-v1/power-simulation.json").read_text())
        self.assertEqual(bundle["simulations_per_scenario_effect"], 2000)
        self.assertEqual(bundle["stage_1_default_models"], 2)
        self.assertIn("not formal noninferiority power", bundle["label"])
        for key, models in (("1", 1), ("2", 2), ("3", 3)):
            result = bundle["designs"][key]
            self.assertEqual(result["simulations_per_scenario_effect"], 2000)
            self.assertEqual((result["models"], result["default_scored_cells"], result["maximum_scored_cells"]),
                             (models, models * 120, models * 7 * 24))
            self.assertEqual(result["comparisons"][:4], ["D_minus_A", "E_minus_D", "E_minus_B", "C_minus_E"])
            self.assertIn("F_minus_D", result["comparisons"])
            self.assertIsNone(result["sign_flip_80_percent_mde"])
            self.assertIn("one-metric point screen only", result["cheap_stack_margin_trigger"])
        # The three-model design reproduces the earlier five-arm artifact's numerics exactly.
        scenario = next(s for s in bundle["designs"]["3"]["scenarios"] if s["baseline"] == .7 and s["fidelity"] == 1)
        self.assertEqual([r["trigger_probability"] for r in scenario["rows"][:5]], [.0715, .222, .4705, .762, .918])
        self.assertEqual([r["cheap_stack_within_margin_probability"] for r in scenario["rows"][:5:2]], [.9285, .5295, .082])
        self.assertGreater(scenario["rows"][0]["cheap_stack_within_margin_probability"], .9)
        self.assertLess(scenario["rows"][4]["cheap_stack_within_margin_probability"], .15)
        # Fewer clusters make the point trigger fire more often by chance (null) at the same baseline.
        null = lambda key: next(s for s in bundle["designs"][key]["scenarios"]
                                if s["baseline"] == .7 and s["fidelity"] == 1)["null_false_trigger_probability"]
        self.assertGreaterEqual(null("1"), null("3"))

    def budget(self):
        return json.loads((ROOT / "benchmarks/generator-thin-eval-v1/protocol.json").read_text())["budget"]

    def test_budget_arithmetic_uses_only_protocol_constants(self):
        budget = self.budget()
        A, D, E = "official-generator", "official+thin-rules", "official+thin-rules+scanner"
        plan = metrics.budget_plan(budget, (A, D, E))
        per = budget["per_cell"]
        central = 24 * sum(per[a]["points"][1] for a in (A, D, E)) + per[A]["points"][1] * budget["entry"]["attempts_per_model"][1]
        self.assertAlmostEqual(plan["points_per_model_low_central_high"][1], round(central, 3), places=3)
        self.assertEqual((plan["cells_per_model"], plan["generation_calls_per_model"], plan["reviewer_calls_per_model"]), (72, 72, 0))
        self.assertEqual(plan["ceiling_hours_per_model_at_call_timeout"], 30.0)
        one, two = plan["rolls_up"]["1"], plan["rolls_up"]["2"]
        self.assertEqual((one["cells"], two["cells"]), (72, 144))
        self.assertEqual(two["calls_incl_harness_check_and_max_entries"], 2 * (72 + 2) + 1)
        for field in ("points_low_central_high", "hours_low_central_high"):
            self.assertEqual(sorted(two[field]), two[field])
        self.assertAlmostEqual(two["flat_points_at_mean_cell_rate"], 144 * .37, places=1)
        # B is a reviewer call; C is a generation call.
        with_b = metrics.budget_plan(budget, (A, "official+reviewer", D, E))
        self.assertEqual((with_b["generation_calls_per_model"], with_b["reviewer_calls_per_model"]), (72, 24))
        five = metrics.budget_plan(budget, (A, "official+reviewer", "ours-2.0.1", D, E))
        self.assertEqual(five["rolls_up"]["3"]["cells"], 360)
        self.assertFalse(five["rolls_up"]["3"]["fits_one_weekly_window_central"])

    def test_budget_measured_basis_is_internally_consistent(self):
        budget = self.budget()
        basis = budget["measured_basis"]
        # 9 arm-A + 10 arm-C cells at the central per-cell points reproduce the observed 7 points within the integer-rounding band.
        used = 9 * budget["per_cell"]["official-generator"]["points"][1] + 10 * budget["per_cell"]["ours-2.0.1"]["points"][1]
        self.assertTrue(6 <= used <= 8)
        self.assertAlmostEqual(used / 19, budget["mean_points_per_cell_measured"], delta=.01)
        self.assertEqual(basis["points_per_hour"], 7)
        for arm, value in budget["per_cell"].items():
            low, central, high = value["points"]
            self.assertTrue(low <= central <= high, arm)
            low, central, high = value["minutes"]
            self.assertTrue(low <= central <= high, arm)
            self.assertTrue(value["basis"].startswith(("measured", "assumption")), arm)
        # Owner decision 2026-10-15: no wait for a weekly-limit reset; the estimates are informational.
        self.assertNotIn("window_reset_kst", budget)
        self.assertNotIn("2026-10-20", json.dumps(budget))
        self.assertIn("INFORMATIONAL", budget["status"])
        self.assertIn("right after the v3 models", budget["earliest_start"]["rule"])


if __name__ == "__main__":
    unittest.main()
