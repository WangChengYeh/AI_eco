"""Paid subscription cohorts follow external car deliveries and service time."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('forecast', ROOT / 'forecast.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

class FsdSubscriptions(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / 'configs/current.json').read_text())

    def rows(self, config):
        return [s for s in m.forecast(config)['segments'] if s['segment'] == 'fsd']

    def test_opening_paid_cohort_and_new_sales_are_time_weighted(self):
        rows = self.rows(self.config)
        d = rows[0]['drivers']
        self.assertEqual(d['opening_subscribers'], 5000000)
        self.assertEqual(d['closing_subscribers'], 7000000)
        self.assertEqual(d['average_subscribers'], 6000000)
        self.assertEqual(rows[0]['revenue_usd'], 7128000000)
        self.assertEqual(rows[1]['drivers']['opening_subscribers'], 7000000)
        self.assertEqual(rows[1]['drivers']['average_subscribers'], 8120000)

    def test_delivery_change_updates_subscriptions_without_manual_recalibration(self):
        changed = copy.deepcopy(self.config)
        segments = changed['companies']['tesla']['segments']
        segments['passenger_vehicles']['units']['value'] = 1000000
        # Resolve the source even if FSD appears before vehicle sales in JSON.
        changed['companies']['tesla']['segments'] = dict(reversed(list(segments.items())))
        first = self.rows(changed)[0]
        self.assertEqual(first['drivers']['average_subscribers'], 5500000)
        self.assertEqual(first['drivers']['closing_subscribers'], 6000000)

    def test_dual_average_and_cohort_inputs_are_rejected(self):
        self.config['companies']['tesla']['segments']['fsd']['average_subscribers'] = 123
        with self.assertRaisesRegex(m.ModelError, 'cannot also set average_subscribers'):
            m.forecast(self.config)
