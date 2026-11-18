"""Manufacturing, deployment and paid service are distinct quantities."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("forecast", Path(__file__).resolve().parents[1] / "forecast.py")
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


def segment(delay=1):
    return dict(kind="robotaxi", opening_fleet=0, service_life_years=6,
                depreciation_life_years=6, replace_retired=False, vehicle_cost_usd=120,
                production_ramp=dict(annual_capacity_units=1200, full_rate_year=2027,
                    full_rate_month=7, initial_rate_fraction=.2, deployment_delay_months=delay))


class RobotaxiRamp(unittest.TestCase):
    def test_full_rate_from_july_not_full_year_at_year_end_rate(self):
        monthly, capacity = m.robotaxi_production(segment()["production_ramp"], 2027, 2027)
        self.assertEqual(capacity, 1200)
        self.assertAlmostEqual(sum(q for q, month in monthly), 960)
        self.assertLess(monthly[5][0], 100)
        self.assertTrue(all(q == 100 for q, month in monthly[6:]))

    def test_inventory_costs_cash_but_earns_nothing_before_deployment(self):
        state = {}
        r = m.segment_forecast(segment(12), 2027, 2027, state)
        self.assertAlmostEqual(r["capex_usd"], 960 * 120)
        self.assertEqual(r["drivers"]["average_fleet"], 0)
        self.assertEqual(r["revenue_usd"], 0)
        self.assertEqual(r["da_usd"], 0)
        self.assertAlmostEqual(r["drivers"]["pending_deployment_units"], 960)
        self.assertAlmostEqual(r["drivers"]["closing_net_book_value_usd"], r["capex_usd"])

    def test_pending_cars_enter_service_next_year_without_new_purchase(self):
        state = {}; s = segment()
        a = m.segment_forecast(s, 2027, 2027, state)
        b = m.segment_forecast(s, 2028, 2027, state)
        self.assertAlmostEqual(a["drivers"]["additions"], 860)
        self.assertAlmostEqual(a["drivers"]["pending_deployment_units"], 100)
        self.assertAlmostEqual(b["drivers"]["manufactured_units"], 1200)
        self.assertAlmostEqual(b["drivers"]["additions"], 1200)
        self.assertAlmostEqual(b["drivers"]["closing_fleet"], 2060)
        self.assertAlmostEqual(a["drivers"]["closing_net_book_value_usd"] + b["capex_usd"] - b["da_usd"], b["drivers"]["closing_net_book_value_usd"])

    def test_average_service_uses_monthly_ramp_not_half_of_year_end(self):
        r = m.segment_forecast(segment(0), 2027, 2027, {})
        self.assertLess(r["drivers"]["average_fleet"], r["drivers"]["closing_fleet"] / 2)

    def test_replacement_cannot_be_manufactured_again_outside_gross_output(self):
        s = segment();s["replace_retired"] = True
        with self.assertRaises(m.ModelError):
            m.segment_forecast(s, 2027, 2027, {})

    def test_dates_and_delays_reject_fractional_months(self):
        s = segment();s["production_ramp"]["full_rate_month"] = 6.5
        with self.assertRaises(m.ModelError):
            m.segment_forecast(s, 2027, 2027, {})


if __name__ == "__main__":
    unittest.main()
