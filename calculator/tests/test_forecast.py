"""Economic identities and failure cases; no network or external packages."""
import copy
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("forecast", ROOT / "forecast.py")
model = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(model)


def fixture(years=(2027,)):
    return {
        "schema_version": 1, "years": list(years), "scenarios": {"base": {}},
        "companies": {"a": {
            "name": "A", "opening_cash_usd": 100, "opening_debt_usd": 20,
            "opening_shares": 10, "corporate_opex_usd": 5, "interest_rate": .1,
            "tax_rate": .2, "pe_multiple": 10, "corporate_ev_cost_multiple": 2,
            "nwc_revenue_ratio": .05, "opening_nwc_usd": 0,
            "segments": {"product": {
                "name": "Product", "kind": "unit", "units": 10, "price_usd": 10,
                "unit_cost_usd": 5, "opex_usd": 10, "capex_revenue_ratio": .2,
                "ev_sales_multiple": 2,
            }},
        }},
    }


def row(config):
    return model.forecast(config)["companies"]["a"][0]


class FinancialIdentities(unittest.TestCase):
    def test_profit_cash_and_valuation_have_distinct_bridges(self):
        r = row(fixture())
        expected = {"revenue_usd": 100, "gross_profit_usd": 50,
                    "operating_profit_usd": 35, "interest_usd": 2, "tax_usd": 6.6,
                    "net_income_usd": 26.4, "economic_fcf_usd": 1.4,
                    "cash_usd": 101.4, "price_pe_usd": 26.4, "price_sotp_usd": 27.14}
        for key, value in expected.items():
            self.assertAlmostEqual(r[key], value, msg=key)

    def test_equity_financing_adds_cash_and_dilutes_not_income(self):
        config = fixture()
        config["companies"]["a"].update(equity_raised_usd=50, equity_issue_price_usd=5)
        r = row(config)
        self.assertAlmostEqual(r["net_income_usd"], 26.4)
        self.assertEqual(r["shares"], 20)
        self.assertAlmostEqual(r["cash_usd"], 151.4)
        self.assertAlmostEqual(r["eps_usd"], 26.4 / 15)
        self.assertAlmostEqual(r["price_pe_usd"], 13.2)

    def test_sbc_expense_addback_and_dilution_are_separate(self):
        config = fixture()
        config["companies"]["a"].update(tax_rate=0, sbc_expense_usd=10, sbc_dilution_rate=.1)
        r = row(config)
        self.assertAlmostEqual(r["net_income_usd"], 23)
        self.assertAlmostEqual(r["cash_fcf_usd"] - r["economic_fcf_usd"], 10)
        self.assertEqual(r["shares"], 11)

    def test_annual_split_reduces_price_not_equity_value(self):
        original = row(fixture())
        config = fixture()
        config["companies"]["a"]["stock_split"] = 3
        split = row(config)
        self.assertEqual(split["shares"], 30)
        self.assertAlmostEqual(split["price_sotp_usd"] * 3, original["price_sotp_usd"])

    def test_depreciation_is_expensed_and_added_back_once(self):
        config = fixture()
        config["companies"]["a"]["tax_rate"] = 0
        config["companies"]["a"]["segments"]["product"]["da_usd"] = 10
        r = row(config)
        self.assertEqual(r["cogs_usd"], 60)
        self.assertEqual(r["da_usd"], 10)
        self.assertAlmostEqual(r["cash_fcf_usd"], 8)

    def test_working_capital_releases_on_revenue_decline(self):
        config = fixture((2027, 2028))
        config["companies"]["a"]["segments"]["product"]["units"] = {"value": 10, "growth": -.5}
        rows = model.forecast(config)["companies"]["a"]
        self.assertEqual(rows[1]["delta_nwc_usd"], -2.5)

    def test_funding_gap_is_separate_from_pe_and_is_not_auto_financed(self):
        config = fixture((2027, 2028))
        config["companies"]["a"]["segments"]["product"]["capex_usd"] = 1000
        rows = model.forecast(config)["companies"]["a"]
        self.assertGreater(rows[0]["funding_gap_usd"], 0)
        self.assertIsNone(rows[0]["price_sotp_usd"])
        self.assertEqual(rows[0]["price_sotp_unavailable_reason"], "non_positive_equity_value")
        self.assertGreater(rows[1]["price_pe_usd"], 0)
        self.assertEqual(rows[1]["valuation_status"], "conditional_unfunded")
        self.assertEqual(rows[0]["debt_usd"], 20)

    def test_positive_pe_and_sotp_remain_visible_with_funding_gap(self):
        config = fixture()
        config["companies"]["a"].update(opening_cash_usd=0)
        config["companies"]["a"]["segments"]["product"]["capex_usd"] = 100
        r = row(config)
        self.assertGreater(r["funding_gap_usd"], 0)
        self.assertAlmostEqual(r["price_pe_usd"], r["year_end_share_earnings_usd"] * r["pe_multiple"])
        self.assertGreater(r["price_sotp_usd"], 0)
        self.assertIsNone(r["price_pe_unavailable_reason"])
        self.assertIsNone(r["price_sotp_unavailable_reason"])

    def test_prior_gap_does_not_permanently_blank_future_prices(self):
        config = fixture((2027, 2028))
        config["companies"]["a"].update(opening_cash_usd=0)
        config["companies"]["a"]["segments"]["product"]["capex_revenue_ratio"] = 0
        config["companies"]["a"]["segments"]["product"]["capex_usd"] = {"value": 30, "annual": {"2028": 0}}
        rows = model.forecast(config)["companies"]["a"]
        self.assertGreater(rows[0]["funding_gap_usd"], 0)
        self.assertGreater(rows[1]["cash_usd"], 0)
        self.assertTrue(rows[1]["funding_failed"])
        self.assertGreater(rows[1]["price_pe_usd"], 0)

    def test_loss_making_company_has_no_pe_price_or_tax_benefit(self):
        config = fixture()
        config["companies"]["a"]["corporate_opex_usd"] = 100
        r = row(config)
        self.assertLess(r["net_income_usd"], 0)
        self.assertEqual(r["tax_usd"], 0)
        self.assertIsNone(r["price_pe_usd"])
        self.assertEqual(r["price_pe_unavailable_reason"], "non_positive_net_income")


class BusinessDrivers(unittest.TestCase):
    def test_subscription_uses_average_accounts_and_twelve_months(self):
        segment = {"kind": "subscription", "average_subscribers": 10,
                   "monthly_price_usd": 5, "monthly_cost_usd": 2}
        r = model.segment_forecast(segment, 2027, 2027, {})
        self.assertEqual(r["revenue_usd"], 600)
        self.assertEqual(r["gross_profit_usd"], 360)

    def test_owned_fleet_rollforward_and_purchases_are_capex(self):
        segment = {"kind": "robotaxi", "opening_fleet": 10, "additions": 10,
                   "vehicle_cost_usd": 100, "depreciation_usd_per_vehicle_year": 30,
                   "km_per_vehicle_day": 100, "operating_days": 1, "paid_km_share": .5,
                   "fare_usd_per_paid_km": 2, "cash_cost_usd_per_total_km": .2,
                   "fixed_cash_usd_per_vehicle_year": 10}
        state = {}
        r = model.segment_forecast(segment, 2027, 2027, state)
        self.assertEqual(r["drivers"]["average_fleet"], 15)
        self.assertEqual(r["revenue_usd"], 1500)
        self.assertEqual(r["cogs_usd"], 900)
        self.assertEqual(r["capex_usd"], 1000)
        self.assertEqual(r["da_usd"], 450)
        self.assertEqual(state["fleet"], 20)

    def test_unpaid_km_still_consumes_cash(self):
        segment = {"kind": "robotaxi", "opening_fleet": 1, "operating_days": 10,
                   "km_per_vehicle_day": 10, "paid_km_share": 0,
                   "cash_cost_usd_per_total_km": 2}
        r = model.segment_forecast(segment, 2027, 2027, {})
        self.assertEqual(r["revenue_usd"], 0)
        self.assertEqual(r["cogs_usd"], 200)

    def test_compute_mw_kwh_conversion_and_internal_capacity_not_sold(self):
        segment = {"kind": "compute", "average_it_mw": 1, "external_share": .5,
                   "internal_share": .5, "external_utilization": 1,
                   "internal_utilization": 1, "availability": 1,
                   "price_usd_per_billable_mw_hour": 10, "electricity_usd_per_kwh": .1,
                   "pue": 1, "idle_power_fraction": 0}
        r = model.segment_forecast(segment, 2027, 2027, {})
        self.assertEqual(r["revenue_usd"], 43800)
        self.assertEqual(r["drivers"]["electricity_kwh"], 8760000)
        self.assertEqual(r["cogs_usd"], 876000)

    def test_compute_cannot_sell_capacity_reserved_for_own_models(self):
        with self.assertRaises(model.ModelError):
            model.segment_forecast({"kind": "compute", "external_share": .8, "internal_share": .3}, 2027, 2027, {})

    def test_prelaunch_development_still_spends_cash(self):
        r = model.segment_forecast({"kind": "compute", "start_year": 2030,
                                    "opex_usd": 5, "capex_usd": 10}, 2027, 2027, {})
        self.assertEqual(r["revenue_usd"], 0)
        self.assertEqual(r["operating_profit_usd"], -5)
        self.assertEqual(r["capex_usd"], 10)

    def test_robot_savings_capped_and_no_artificial_revenue(self):
        config = fixture()
        c = config["companies"]["a"]
        c.update(robotics_savings_usd=1000, robotics_max_cogs_share=.2)
        c["segments"]["product"].update(robotics_eligible=True, cost_includes_robotics=False)
        r = row(config)
        self.assertEqual(r["revenue_usd"], 100)
        self.assertEqual(r["robotics_savings_usd"], 10)
        self.assertEqual(r["cogs_usd"], 40)
        c["segments"]["product"]["cost_includes_robotics"] = True
        with self.assertRaises(model.ModelError):
            model.forecast(config)

    def test_production_shared_between_sales_and_owned_fleet(self):
        config = fixture()
        c = config["companies"]["a"]
        c.update(passenger_production_capacity=10, passenger_segment_id="product", robotaxi_segment_id="fleet")
        c["segments"]["fleet"] = {"name": "Fleet", "kind": "robotaxi", "additions": 1}
        with self.assertRaisesRegex(model.ModelError, "production capacity"):
            model.forecast(config)


class MergerAndValidation(unittest.TestCase):
    def test_merger_uses_exchange_ratio_instead_of_adding_prices(self):
        config = fixture()
        config["companies"]["b"] = copy.deepcopy(config["companies"]["a"])
        config["companies"]["b"].update(name="B", opening_shares=20)
        config["merger"] = {"enabled": True, "acquirer": "a", "target": "b",
                            "target_exchange_ratio": .5, "pe_multiple": 10}
        result = model.forecast(config)
        combined = result["merger"][0]
        self.assertEqual(combined["shares"], 20)
        self.assertEqual(combined["revenue_usd"], 200)
        self.assertAlmostEqual(combined["price_pe_usd"], 26.4)
        self.assertNotAlmostEqual(combined["price_pe_usd"], sum(rows[0]["price_pe_usd"] for rows in result["companies"].values()))

    def test_merger_elimination_removes_revenue_and_seller_ev(self):
        config = fixture()
        config["companies"]["b"] = copy.deepcopy(config["companies"]["a"])
        config["merger"] = {"enabled": True, "acquirer": "a", "target": "b",
                            "intercompany_revenue_usd": 10, "intercompany_ev_elimination_usd": 20}
        merged = model.forecast(config)["merger"][0]
        self.assertEqual(merged["revenue_usd"], 190)
        self.assertAlmostEqual(merged["net_income_usd"], 52.8)
        self.assertAlmostEqual(merged["sotp_equity_value_usd"], 522.8)

    def test_merger_funding_gap_does_not_hide_conditional_pe(self):
        config = fixture()
        config["companies"]["a"].update(opening_cash_usd=0)
        config["companies"]["a"]["segments"]["product"]["capex_usd"] = 1000
        config["companies"]["b"] = copy.deepcopy(config["companies"]["a"])
        config["merger"] = {"enabled": True, "acquirer": "a", "target": "b", "pe_multiple": 10}
        r = model.forecast(config)["merger"][0]
        self.assertTrue(r["funding_failed"])
        self.assertGreater(r["price_pe_usd"], 0)
        self.assertEqual(r["valuation_status"], "conditional_unfunded")

    def test_curves_absolute_override_and_cap(self):
        spec = {"value": 100, "growth": .1, "annual": {"2029": 140}, "cap": 135}
        self.assertAlmostEqual(model.parameter(spec, 2028, 2027), 110)
        self.assertEqual(model.parameter(spec, 2029, 2027), 135)
        self.assertAlmostEqual(model.parameter(spec, 2030, 2027), 133.1)
        self.assertEqual(model.parameter({"value": 100, "growth": -.5, "floor": 40}, 2029, 2027), 40)
        with self.assertRaises(model.ModelError):
            model.parameter({"value": 100, "floor": 50, "cap": 40}, 2027, 2027)

    def test_reject_invalid_numbers_years_and_override_typos(self):
        for value in [-1, float("nan"), float("inf"), True]:
            with self.subTest(value=value), self.assertRaises(model.ModelError):
                model.parameter(value, 2027, 2027)
        config = fixture((2027, 2029))
        with self.assertRaises(model.ModelError):
            model.forecast(config)
        with self.assertRaises(model.ModelError):
            model.patch(fixture(), "companies.a.typo", 1)

    def test_no_silent_missing_financing_price_or_impossible_retirements(self):
        config = fixture()
        config["companies"]["a"]["equity_raised_usd"] = 10
        with self.assertRaises(model.ModelError):
            model.forecast(config)
        with self.assertRaises(model.ModelError):
            model.segment_forecast({"kind": "robotaxi", "opening_fleet": 1, "retirements": 2}, 2027, 2027, {})

    def test_example_scenarios_reconcile_and_keep_original_input(self):
        config = json.loads((ROOT / "configs" / "example.json").read_text())
        before = copy.deepcopy(config)
        for scenario in config["scenarios"]:
            result = model.forecast(config, scenario)
            json.dumps(result, allow_nan=False)
            for rows in result["companies"].values():
                for r in rows:
                    segments = [s for s in result["segments"] if s["company"] == r["company"] and s["year"] == r["year"]]
                    self.assertAlmostEqual(sum(s["revenue_usd"] for s in segments), r["revenue_usd"], places=3)
                    self.assertAlmostEqual(sum(s["gross_profit_usd"] for s in segments), r["gross_profit_usd"], places=3)
                    self.assertAlmostEqual(r["net_income_usd"] + r["da_usd"] - r["capex_usd"] - r["delta_nwc_usd"], r["economic_fcf_usd"], places=3)
        self.assertEqual(config, before)

    def test_cli_override_after_scenario_and_csv_exports(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "out"
            run = subprocess.run([sys.executable, str(ROOT / "forecast.py"), "--scenario", "bear",
                                  "--set", "companies.tesla.pe_multiple=12", "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads((out / "results.json").read_text())["results"][0]
            self.assertEqual(result["companies"]["tesla"][0]["pe_multiple"], 12)
            self.assertTrue((out / "segments.csv").exists())
            self.assertTrue((out / "companies.csv").read_bytes().startswith(b"\xef\xbb\xbf"))
            self.assertFalse((out / "merger.csv").exists())

    def test_cli_invalid_override_returns_two_and_no_partial_files(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / "out"
            run = subprocess.run([sys.executable, str(ROOT / "forecast.py"), "--set", "companies.tesla.bad=1", "--out", str(out)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 2)
            self.assertFalse(out.exists())


class OrbitalRamp(unittest.TestCase):
    def segment(self, **overrides):
        segment = {"kind": "orbital_compute", "opening_it_mw": 0,
                   "manufactured_it_mw": 1000, "deployment_limit_mw": 1000,
                   "commissioning_yield": 1, "commissioning_start_month": 10,
                   "external_share": 1, "internal_share": 0, "availability": 1,
                   "external_utilization": 1, "price_usd_per_billable_mw_hour": 1,
                   "hardware_cost_usd_per_mw": 10, "deployment_cost_usd_per_mw": 2,
                   "asset_life_years": 4}
        segment.update(overrides)
        return segment

    def test_q4_linear_ramp_is_one_eighth_of_end_year_capacity(self):
        r = model.segment_forecast(self.segment(), 2027, 2027, {})
        self.assertEqual(r["drivers"]["year_end_it_mw"], 1000)
        self.assertEqual(r["drivers"]["average_it_mw"], 125)
        self.assertEqual(r["revenue_usd"], 125 * 8760)
        self.assertEqual(r["capex_usd"], 12000)

    def test_december_ramp_does_not_bill_a_full_year(self):
        r = model.segment_forecast(self.segment(commissioning_start_month=12), 2027, 2027, {})
        self.assertAlmostEqual(r["drivers"]["average_it_mw"], 1000 / 24)

    def test_commissioned_capacity_contributes_next_full_year(self):
        state = {}
        model.segment_forecast(self.segment(), 2027, 2027, state)
        r = model.segment_forecast(self.segment(manufactured_it_mw=0, commissioning_start_month=1), 2028, 2027, state)
        self.assertEqual(r["drivers"]["average_it_mw"], 1000)
        self.assertEqual(r["capex_usd"], 0)

    def test_manufactured_backlog_is_not_commissioned_revenue(self):
        state = {}
        r = model.segment_forecast(self.segment(deployment_limit_mw=0), 2027, 2027, state)
        self.assertEqual(r["revenue_usd"], 0)
        self.assertEqual(r["capex_usd"], 10000)
        self.assertEqual(r["drivers"]["closing_inventory_mw"], 1000)
        r = model.segment_forecast(self.segment(manufactured_it_mw=0, commissioning_start_month=1), 2028, 2027, state)
        self.assertEqual(r["drivers"]["year_end_it_mw"], 1000)
        self.assertEqual(r["capex_usd"], 2000)

    def test_commissioning_failure_reduces_capacity_and_writes_off_assets(self):
        r = model.segment_forecast(self.segment(commissioning_yield=.5), 2027, 2027, {})
        self.assertEqual(r["drivers"]["year_end_it_mw"], 500)
        self.assertEqual(r["drivers"]["deployment_writeoff_usd"], 6000)
        self.assertGreaterEqual(r["drivers"]["closing_net_book_value_usd"], 0)
        self.assertLessEqual(r["da_usd"], r["capex_usd"])

    def test_invalid_month_or_average_capacity_conflict_rejected(self):
        for extra in [{"commissioning_start_month": 13}, {"commissioning_start_month": 10.5}, {"average_it_mw": 1000}]:
            with self.assertRaises(model.ModelError):
                model.segment_forecast(self.segment(**extra), 2027, 2027, {})

    def test_combined_user_assumptions_keep_optimus_and_add_2028_orbital(self):
        config = json.loads((ROOT / "configs" / "current.json").read_text())
        result = model.forecast(config, "base")
        robots = [s for s in result["segments"] if s["segment"] == "optimus_owned"]
        orbital = [s for s in result["segments"] if s["segment"] == "orbital_compute"]
        self.assertEqual(robots[0]["drivers"]["production_units"], 10000000)
        self.assertEqual(robots[1]["drivers"]["production_units"], 0)
        self.assertEqual(orbital[0]["drivers"]["average_it_mw"], 125)
        self.assertEqual(orbital[1]["drivers"]["average_it_mw"], 2500)
        self.assertEqual(orbital[1]["drivers"]["year_end_it_mw"], 4000)
        self.assertEqual(len(result["companies"]["tesla"]), 9)


class OptimusOwnedFleet(unittest.TestCase):
    def robot(self, **overrides):
        segment = {"kind": "robot_fleet", "opening_fleet": 10, "production_units": 10,
                   "unit_manufacturing_cost_usd": 100, "opening_net_book_value_usd": 1000,
                   "internal_demand_robots": 12, "internal_avoided_cost_usd_per_robot_year": 50,
                   "rental_utilization": .5, "monthly_rent_usd": 100,
                   "cash_cost_usd_per_robot_year": 2, "depreciation_usd_per_robot_year": 20}
        segment.update(overrides)
        return segment

    def test_internal_priority_and_only_paid_external_rent_is_revenue(self):
        r = model.segment_forecast(self.robot(), 2027, 2027, {})
        self.assertEqual(r["drivers"]["average_fleet"], 15)
        self.assertEqual(r["drivers"]["average_internal_robots"], 12)
        self.assertEqual(r["drivers"]["average_rented_robots"], 1.5)
        self.assertEqual(r["drivers"]["internal_savings_requested_usd"], 600)
        self.assertEqual(r["revenue_usd"], 1800)
        self.assertEqual(r["capex_usd"], 1000)
        self.assertEqual(r["cogs_usd"], 330)

    def test_internal_demand_consumes_capacity_before_rent(self):
        r = model.segment_forecast(self.robot(internal_demand_robots=100), 2027, 2027, {})
        self.assertEqual(r["revenue_usd"], 0)
        self.assertEqual(r["drivers"]["average_internal_robots"], 15)

    def test_unused_supply_is_not_automatically_rented(self):
        r = model.segment_forecast(self.robot(rental_utilization=0), 2027, 2027, {})
        self.assertEqual(r["revenue_usd"], 0)
        self.assertEqual(r["drivers"]["average_idle_robots"], 3)
        self.assertGreater(r["cogs_usd"], 0)
        r = model.segment_forecast(self.robot(rental_demand_robots=.2), 2027, 2027, {})
        self.assertEqual(r["drivers"]["average_rented_robots"], .2)

    def test_depreciation_cannot_exceed_remaining_book_value(self):
        state = {}
        segment = self.robot(opening_fleet=1, production_units=0, opening_net_book_value_usd=50,
                             depreciation_usd_per_robot_year=100)
        first = model.segment_forecast(segment, 2027, 2027, state)
        second = model.segment_forecast(segment, 2028, 2027, state)
        self.assertEqual(first["da_usd"], 50)
        self.assertEqual(second["da_usd"], 0)
        self.assertEqual(second["drivers"]["closing_net_book_value_usd"], 0)

    def test_existing_robot_savings_cannot_be_counted_twice(self):
        c = fixture()
        company = c["companies"]["a"]
        company["segments"]["robots"] = {"name": "Robots", **self.robot()}
        company["robotics_savings_usd"] = 1
        with self.assertRaisesRegex(model.ModelError, "cannot both"):
            model.forecast(c)

    def test_ten_million_produced_are_half_year_average_and_need_financing(self):
        config = json.loads((ROOT / "configs" / "optimus_10m.json").read_text())
        result = model.forecast(config, "optimus_10m")
        fleet = next(s for s in result["segments"] if s["segment"] == "optimus_owned")
        self.assertEqual(fleet["drivers"]["closing_fleet"], 10000000)
        self.assertEqual(fleet["drivers"]["average_fleet"], 5000000)
        self.assertEqual(fleet["drivers"]["average_rented_robots"], 2000000)
        self.assertEqual(fleet["revenue_usd"], 48e9)
        self.assertAlmostEqual(result["companies"]["tesla"][0]["revenue_usd"], sum(s["revenue_usd"] for s in result["segments"] if s["company_id"] == "tesla"))
        self.assertGreater(result["companies"]["tesla"][0]["funding_gap_usd"], 0)
        self.assertGreater(result["companies"]["tesla"][0]["price_pe_usd"], 0)
        self.assertEqual(result["companies"]["tesla"][0]["valuation_status"], "conditional_unfunded")


if __name__ == "__main__":
    unittest.main()
