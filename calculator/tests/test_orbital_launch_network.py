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
        o.pop('manufacture_to_launch_capacity',None)
        o['manufactured_it_mw']={'value':3000,'annual':{'2027':1000}}
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
        self.assertEqual(rows[1]['drivers']['year_end_it_mw'],3495)

    def test_uncommissioned_inventory_does_not_retire_as_operating_assets(self):
        c=json.loads((ROOT/'configs/current.json').read_text())
        rows=[s for s in m.forecast(c)['segments'] if s['segment']=='orbital_compute']
        self.assertEqual(rows[-1]['drivers']['retired_it_mw'],345)

    def test_invalid_ai_share_is_rejected(self):
        n=self.network();n['ai_flight_share']=1.1
        with self.assertRaises(m.ModelError):m.orbital_launch_capacity(n,2027,2027)

    def test_more_pads_do_not_multiply_the_fleet_wide_target(self):
        n=self.network();n.update(fleet_rate_start=12,fleet_rate_end=24)
        one=m.orbital_launch_capacity(n,2027,2027)
        n['sites'].append(copy.deepcopy(n['sites'][0]));n['sites'][1]['id']='another_site'
        two=m.orbital_launch_capacity(n,2027,2027)
        self.assertEqual(one['available_starship_flights'],18)
        self.assertEqual(two['available_starship_flights'],18)
        self.assertEqual(two['infrastructure_site_slots'],48)

    def test_fleet_target_cannot_override_site_limit(self):
        n=self.network();n.update(fleet_rate_start=365,fleet_rate_end=365)
        self.assertEqual(m.orbital_launch_capacity(n,2027,2027)['available_starship_flights'],24)

    def test_unpaired_fleet_ramp_is_rejected(self):
        n=self.network();n['fleet_rate_start']=52
        with self.assertRaises(m.ModelError):m.orbital_launch_capacity(n,2027,2027)

    def test_net_15mw_applies_from_july_without_another_efficiency_discount(self):
        n=self.network()
        n['capacity_upgrade']={'year':2027,'month':7,'net_it_mw_per_flight':15}
        d=m.orbital_launch_capacity(n,2027,2027)
        self.assertEqual(d['monthly_mw_per_ai_flight'],[6]*6+[15]*6)
        self.assertEqual(d['monthly_launch_capacity_mw'],[6]*6+[15]*6)
        self.assertEqual(d['annual_launch_capacity_mw'],126)
        self.assertEqual(m.orbital_launch_capacity(n,2028,2027)['annual_launch_capacity_mw'],180)

    def test_invalid_capacity_upgrade_month_is_rejected(self):
        n=self.network()
        n['capacity_upgrade']={'year':2027,'month':13,'net_it_mw_per_flight':15}
        with self.assertRaises(m.ModelError):m.orbital_launch_capacity(n,2027,2027)

    def test_unconstrained_manufacturing_matches_flights_and_keeps_full_capex(self):
        c=json.loads((ROOT/'configs/current.json').read_text())
        spec=c['companies']['spacex']['segments']['orbital_compute']
        rows=[s for s in m.forecast(c)['segments'] if s['segment']=='orbital_compute']
        for row in rows:
            d=row['drivers']
            self.assertAlmostEqual(d['manufactured_it_mw'],d['commissioned_new_it_mw'])
            self.assertAlmostEqual(d['closing_inventory_mw'],0)
            expected=d['manufactured_it_mw']*spec['hardware_cost_usd_per_mw']+d['deployment_attempted_mw']*spec['deployment_cost_usd_per_mw']
            self.assertAlmostEqual(row['capex_usd'],expected,delta=.1)
        self.assertEqual(rows[-1]['drivers']['commissioned_new_it_mw'],29565)
        self.assertEqual(rows[-1]['drivers']['year_end_it_mw'],54870)

    def test_no_ai_slots_means_no_unnecessary_matched_manufacture(self):
        c=json.loads((ROOT/'configs/current.json').read_text())
        c['companies']['spacex']['segments']['orbital_compute']['launch_network']['ai_flight_share']=0
        rows=[s for s in m.forecast(c)['segments'] if s['segment']=='orbital_compute']
        self.assertEqual(rows[0]['drivers']['manufactured_it_mw'],0)
        self.assertEqual(rows[0]['capex_usd'],0)

    def test_fixed_and_unconstrained_manufacturing_inputs_conflict(self):
        c=json.loads((ROOT/'configs/current.json').read_text())
        c['companies']['spacex']['segments']['orbital_compute']['manufactured_it_mw']=3000
        with self.assertRaisesRegex(m.ModelError,'no manufactured_it_mw'):m.forecast(c)

    def test_ninety_percent_reallocates_slots_without_creating_flights(self):
        c=json.loads((ROOT/'configs/current.json').read_text())
        self.assertEqual(c['companies']['spacex']['segments']['orbital_compute']['launch_network']['ai_flight_share'],.9)
        ninety=m.forecast(c)
        c['companies']['spacex']['segments']['orbital_compute']['launch_network']['ai_flight_share']=.5
        fifty=m.forecast(c)
        ai90=[s for s in ninety['segments'] if s['segment']=='orbital_compute']
        ai50=[s for s in fifty['segments'] if s['segment']=='orbital_compute']
        for high,low in zip(ai90,ai50):
            h,l=high['drivers'],low['drivers']
            self.assertEqual(h['available_starship_flights'],l['available_starship_flights'])
            self.assertEqual(h['allocated_ai_flights'],int(h['available_starship_flights']*.9+1e-9))
            self.assertLessEqual(h['allocated_ai_flights'],h['available_starship_flights'])
            self.assertGreater(high['capex_usd'],low['capex_usd'])
        self.assertEqual(ai90[0]['drivers']['deployed_monthly_mw'][:9],[0]*9)
        self.assertEqual(ninety['companies']['tesla'],fifty['companies']['tesla'])
        self.assertGreater(ninety['companies']['spacex'][-1]['resource_shares_issued'],fifty['companies']['spacex'][-1]['resource_shares_issued'])
