"""Lifecycle economics and the canonical, continuously revised forecast."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("forecast", ROOT / "forecast.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class LifecycleEconomics(unittest.TestCase):
    def robots(self, replace, cost=100):
        return dict(kind="robot_fleet", production_units={"value": 0, "annual": {"2027": 120}},
                    unit_manufacturing_cost_usd=cost, service_life_years=2,
                    depreciation_life_years=2, replace_retired=replace,
                    monthly_rent_usd=10, rental_utilization=1,
                    cash_cost_usd_per_robot_year=2)

    def run_segment(self, spec, years):
        state = {}
        return [m.segment_forecast(spec, y, 2027, state) for y in years]

    def test_retirement_ends_output_without_replacement(self):
        r = self.run_segment(self.robots(False), range(2027, 2031))
        self.assertAlmostEqual(r[0]["drivers"]["average_fleet"], 60)
        self.assertAlmostEqual(r[2]["drivers"]["average_fleet"], 60)
        self.assertAlmostEqual(r[2]["drivers"]["closing_fleet"], 0)
        self.assertEqual(r[3]["revenue_usd"], 0)
        self.assertAlmostEqual(sum(x["da_usd"] for x in r), 12000)

    def test_replacement_preserves_output_but_requires_new_capex(self):
        r = self.run_segment(self.robots(True), range(2027, 2030))
        self.assertAlmostEqual(r[2]["drivers"]["average_fleet"], 120)
        self.assertAlmostEqual(r[2]["drivers"]["replacement_units"], 120)
        self.assertAlmostEqual(r[2]["capex_usd"], 12000)
        self.assertAlmostEqual(r[2]["da_usd"], 6000)
        self.assertAlmostEqual(r[2]["drivers"]["closing_net_book_value_usd"], 9000)

    def test_cost_decline_does_not_reprice_old_assets(self):
        r = self.run_segment(self.robots(True, {"value": 100, "annual": {"2029": 50}}), range(2027, 2030))
        self.assertAlmostEqual(r[2]["capex_usd"], 6000)
        self.assertAlmostEqual(r[2]["da_usd"], 4500)

    def test_short_service_life_writes_off_remaining_book(self):
        s = self.robots(False); s["depreciation_life_years"] = 4
        r = self.run_segment(s, range(2027, 2030))
        self.assertAlmostEqual(r[2]["drivers"]["retirement_writeoff_usd"], 6000)
        self.assertAlmostEqual(sum(x["da_usd"] for x in r), 12000)

    def test_backloaded_robot_production_reduces_average_available_fleet(self):
        s = self.robots(False)
        s["production_quarter_units"] = {"2027": [0, 0, 0, 120]}
        r = self.run_segment(s, (2027,))[0]
        self.assertAlmostEqual(r["drivers"]["average_fleet"], 15)
        self.assertAlmostEqual(r["drivers"]["closing_fleet"], 120)
        self.assertAlmostEqual(r["capex_usd"], 12000)

    def test_quarterly_and_annual_production_must_reconcile(self):
        s = self.robots(False)
        s["production_quarter_units"] = {"2027": [10, 10, 10, 10]}
        with self.assertRaisesRegex(m.ModelError, "sum to annual"):
            self.run_segment(s, (2027,))

    def test_late_orbital_capacity_expires_on_its_actual_vintage(self):
        s = dict(kind="orbital_compute", manufactured_it_mw={"value": 0, "annual": {"2027": 1000}},
                 commissioning_start_month=10, hardware_cost_usd_per_mw=20e6,
                 deployment_cost_usd_per_mw=5e6, service_life_years=4,
                 depreciation_life_years=4, price_usd_per_billable_mw_hour=1)
        r = self.run_segment(s, range(2027, 2033))
        self.assertAlmostEqual(r[0]["drivers"]["average_it_mw"], 125)
        self.assertAlmostEqual(r[4]["drivers"]["average_it_mw"], 875)
        self.assertAlmostEqual(r[4]["drivers"]["year_end_it_mw"], 0)
        self.assertAlmostEqual(r[4]["drivers"]["retired_it_mw"], 1000)
        self.assertEqual(r[5]["revenue_usd"], 0)
        self.assertAlmostEqual(sum(x["da_usd"] for x in r), 25e9, delta=.01)

    def test_inventory_keeps_historical_cost_until_commissioning(self):
        s = dict(kind="orbital_compute", manufactured_it_mw=100,
                 deployment_limit_mw={"value": 100, "annual": {"2027": 0}},
                 hardware_cost_usd_per_mw={"value": 10, "annual": {"2028": 20}},
                 deployment_cost_usd_per_mw=1, commissioning_start_month=1,
                 service_life_years=4, depreciation_life_years=4)
        r = self.run_segment(s, (2027, 2028))
        self.assertEqual(r[0]["da_usd"], 0)
        self.assertAlmostEqual(r[1]["da_usd"], 137.5)
        self.assertAlmostEqual(r[1]["drivers"]["closing_net_book_value_usd"], 2962.5)

    def test_robotaxi_replacements_are_real_production(self):
        s = dict(kind="robotaxi", opening_fleet=100, service_life_years=1,
                 depreciation_life_years=1, replace_retired=True, vehicle_cost_usd=10)
        r = self.run_segment(s, (2027, 2028))
        self.assertEqual(r[1]["drivers"]["additions"], 100)
        self.assertEqual(r[1]["capex_usd"], 1000)
        self.assertEqual(r[1]["drivers"]["average_fleet"], 100)

    def test_primary_forecast_preserves_user_assumptions_and_resource_balance(self):
        c = json.loads((ROOT / "configs/current.json").read_text())
        r = m.forecast(c)
        robots = next(s for s in r["segments"] if s["segment"] == "optimus_owned" and s["year"] == 2027)
        orbit = next(s for s in r["segments"] if s["segment"] == "orbital_compute" and s["year"] == 2027)
        self.assertEqual(robots["drivers"]["production_units"], 1000000)
        self.assertAlmostEqual(robots["drivers"]["average_fleet"], 285000)
        self.assertEqual(robots["revenue_usd"], 0)
        production = [s["drivers"]["production_units"] for s in r["segments"] if s["segment"] == "optimus_owned"]
        self.assertEqual(production, [1000000, 5000000, 10000000, 10000000, 10000000])
        rental = {s["year"]: s for s in r["segments"] if s["segment"] == "optimus_owned"}
        self.assertAlmostEqual(rental[2028]["drivers"]["average_rented_robots"], 1950000)
        self.assertAlmostEqual(rental[2028]["revenue_usd"], 58.5e9, delta=.1)
        self.assertAlmostEqual(rental[2030]["drivers"]["average_rented_robots"], 20000000)
        self.assertAlmostEqual(rental[2030]["revenue_usd"], 600e9, delta=.1)
        self.assertAlmostEqual(orbit["drivers"]["average_it_mw"], 9.25)
        self.assertEqual(c["years"], list(range(2027, 2032)))
        late = next(s for s in r["segments"] if s["segment"] == "orbital_compute" and s["year"] == 2031)
        self.assertAlmostEqual(late["drivers"]["year_end_it_mw"], 12192)
        for rows in r["companies"].values():
            for a in rows:
                self.assertAlmostEqual(a["resource_shares_issued"] * (a["stock_payment_price_usd"] or 0), a["stock_payment_usd"], delta=.01)
                self.assertAlmostEqual(a["cash_capex_usd"] + a["stock_paid_capex_usd"], a["capex_usd"], delta=.01)
                self.assertGreaterEqual(a["cash_usd"], -.01)
        old = {}
        for s in r["segments"]:
            if s["segment"] not in ("optimus_owned", "orbital_compute"):
                continue
            book = s["drivers"]["closing_net_book_value_usd"]
            prior = old.get(s["segment"], 0)
            # Optimus also has separately expensed infrastructure capex of $100M.
            asset_capex = s["capex_usd"] - (1e8 if s["segment"] == "optimus_owned" else 0)
            self.assertAlmostEqual(prior + asset_capex - s["da_usd"], book, delta=.1)
            old[s["segment"]] = book

    def test_default_cli_emits_only_primary_forecast(self):
        with tempfile.TemporaryDirectory() as d:
            p = subprocess.run([sys.executable, str(ROOT / "forecast.py"), "--out", d], capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            results = json.loads((Path(d) / "results.json").read_text())["results"]
            self.assertEqual([r["scenario"] for r in results], ["base"])

    def test_automation_cannot_save_depreciation_or_ineligible_cash_cost(self):
        company = dict(name="A", opening_cash_usd=1000, opening_debt_usd=0,
                       opening_shares=10, robotics_savings_usd=1000, robotics_max_cogs_share=1,
                       segments={"factory": dict(name="Factory", kind="unit", units=1, price_usd=200,
                           unit_cost_usd=100, da_usd=20, robotics_eligible=True,
                           cost_includes_robotics=False, automation_eligible_cash_cost_ratio=.3)})
        r = m.company_forecast(company, [2027])[1][0]
        self.assertAlmostEqual(r["robotics_savings_usd"], 30)
        self.assertAlmostEqual(r["cogs_usd"], 90)


if __name__ == "__main__":
    unittest.main()
