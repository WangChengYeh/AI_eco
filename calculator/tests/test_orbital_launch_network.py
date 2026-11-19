"""Launch infrastructure limits commissioning, not factory purchases."""
import copy
import importlib.util
import json
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('forecast', ROOT / 'forecast.py')
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)

class LaunchNetwork(unittest.TestCase):
    def network(self):
        return dict(payload_tonnes=100, it_kw_per_tonne=75, payload_efficiency=.8,
                    ai_flight_share=.5, sites=[dict(id='test', annual_site_limit=24,
                    pads=[dict(id='a',online_year=2027,online_month=1,flights_per_year=52)])])

    def test_two_pads_share_one_site_limit(self):
        n = self.network()
        n['sites'][0]['pads'].append(dict(id='b',online_year=2027,online_month=1,flights_per_year=52))
        d = m.orbital_launch_capacity(n,2027,2027)
        self.assertEqual(d['available_starship_flights'],24)
        self.assertEqual(d['allocated_ai_flights'],12)
        self.assertEqual(d['annual_launch_capacity_mw'],72)

    def test_july_activation_gives_no_first_half_capacity(self):
        n=self.network();n['sites'][0]['pads'][0]['online_month']=7
        d=m.orbital_launch_capacity(n,2027,2027)
        self.assertEqual(d['available_starship_flights'],12)
        self.assertEqual(d['monthly_launch_capacity_mw'][:6],[0]*6)

    def test_zero_ai_allocation_prevents_output_but_preserves_paid_inventory(self):
        c=json.loads((ROOT/'configs/current.json').read_text())
        o=c['companies']['spacex']['segments']['orbital_compute']
        o['launch_network']['ai_flight_share']=0
        rows=[s for s in m.forecast(c)['segments'] if s['segment']=='orbital_compute']
        self.assertEqual(rows[0]['revenue_usd'],0)
        self.assertEqual(rows[0]['da_usd'],0)
        self.assertEqual(rows[0]['drivers']['closing_inventory_mw'],1000)
        self.assertGreaterEqual(rows[0]['capex_usd'],1000*o['hardware_cost_usd_per_mw'])
        self.assertEqual(rows[1]['drivers']['closing_inventory_mw'],4000)

    def test_live_model_never_deploys_more_than_monthly_launch_slots(self):
        c=json.loads((ROOT/'configs/current.json').read_text())
        rows=[s for s in m.forecast(c)['segments'] if s['segment']=='orbital_compute']
        for row in rows:
            d=row['drivers']
            self.assertLessEqual(d['commissioned_new_it_mw'],d['annual_launch_capacity_mw'])
            for used,cap in zip(d['deployed_monthly_mw'],d['monthly_launch_capacity_mw']):
                self.assertLessEqual(used,cap+1e-8)
        self.assertEqual(rows[0]['drivers']['deployed_monthly_mw'][:9],[0]*9)
        self.assertEqual(rows[1]['drivers']['year_end_it_mw'],414)

    def test_uncommissioned_inventory_does_not_retire_as_operating_assets(self):
        c=json.loads((ROOT/'configs/current.json').read_text())
        rows=[s for s in m.forecast(c)['segments'] if s['segment']=='orbital_compute']
        self.assertEqual(rows[-1]['drivers']['retired_it_mw'],54)

    def test_invalid_ai_share_is_rejected(self):
        n=self.network();n['ai_flight_share']=1.1
        with self.assertRaises(m.ModelError):m.orbital_launch_capacity(n,2027,2027)
