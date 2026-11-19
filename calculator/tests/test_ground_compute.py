"""Capacity timing and capital renewal must agree with billed output and funding."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from forecast import forecast, segment_forecast, ModelError

class GroundCompute(unittest.TestCase):
    def spec(self):
        return dict(kind='compute',capacity_ramp=dict(opening_it_mw=100,
            year_end_it_mw={'value':200,'annual':{'2028':200,'2029':200}},
            hardware_cost_usd_per_mw={'value':20,'annual':{'2029':10}},
            infrastructure_cost_usd_per_mw=10,hardware_life_years=2,
            infrastructure_life_years=20),price_usd_per_billable_mw_hour=1)

    def test_uniform_ramp_bills_average_and_funds_new_capacity(self):
        row=segment_forecast(self.spec(),2027,2027,{})
        self.assertAlmostEqual(row['drivers']['average_it_mw'],150)
        self.assertAlmostEqual(row['revenue_usd'],150*8760)
        self.assertAlmostEqual(row['capex_usd'],3000)
        # No repurchase of opening assets; both opening and new assets depreciate.
        self.assertAlmostEqual(row['da_usd'],150*20/2+150*10/20)

    def test_late_commissioning_preserves_year_end_but_reduces_revenue(self):
        spec=self.spec();spec['capacity_ramp']['monthly_addition_weights']={'2027':[0]*11+[1]}
        row=segment_forecast(spec,2027,2027,{})
        self.assertAlmostEqual(row['drivers']['year_end_it_mw'],200)
        self.assertAlmostEqual(row['drivers']['average_it_mw'],100+100/24)
        self.assertAlmostEqual(row['capex_usd'],3000)

    def test_renewal_costs_cash_without_growing_capacity_or_rebuilding_facility(self):
        state={};rows=[segment_forecast(self.spec(),y,2027,state) for y in range(2027,2030)]
        row=rows[-1];d=row['drivers']
        self.assertAlmostEqual(d['average_it_mw'],200)
        self.assertAlmostEqual(d['replacement_hardware_mw'],200)
        self.assertAlmostEqual(d['replacement_infrastructure_mw'],0)
        self.assertAlmostEqual(row['capex_usd'],2000)
        # Old cohort keeps its original cost until expiry; replacements use new price.
        self.assertAlmostEqual(row['da_usd'],1250+100)

    def test_invalid_timing_and_double_capacity_inputs_fail(self):
        spec=self.spec();spec['capacity_ramp']['monthly_addition_weights']={'2027':[0]*12}
        with self.assertRaisesRegex(ModelError,'sum to 1'):segment_forecast(spec,2027,2027,{})
        spec=self.spec();spec['average_it_mw']=100
        with self.assertRaisesRegex(ModelError,'cannot also set'):segment_forecast(spec,2027,2027,{})

    def test_new_primary_preserves_tesla_and_orbit_but_increases_funding_need(self):
        root=Path(__file__).resolve().parents[1]
        config=json.loads((root/'configs/current.json').read_text())
        old=copy.deepcopy(config);g=old['companies']['spacex']['segments']['ground_compute']
        g.pop('capacity_ramp');g['average_it_mw']={'value':1800,'growth':.18};g['hardware_da_usd_per_mw_year']={'value':6e6,'growth':-.03};g['capex_usd']={'value':12e9,'growth':.12}
        before,after=forecast(old),forecast(config)
        self.assertEqual(before['companies']['tesla'],after['companies']['tesla'])
        for r in after['segments']:
            if r['segment']=='orbital_compute':
                self.assertEqual(r,next(x for x in before['segments'] if x['year']==r['year'] and x['company_id']==r['company_id'] and x['segment']==r['segment']))
        row=next(r for r in after['segments'] if r['year']==2027 and r['segment']=='ground_compute')
        self.assertAlmostEqual(row['drivers']['average_it_mw'],8000)
        self.assertAlmostEqual(row['drivers']['year_end_it_mw'],13000)
        self.assertAlmostEqual(row['capex_usd'],400e9)
        self.assertGreater(after['companies']['spacex'][0]['resource_shares_issued'],before['companies']['spacex'][0]['resource_shares_issued'])

if __name__=='__main__':unittest.main()
