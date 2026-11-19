"""Rent repricing affects all paid robots, without erasing their costs."""
import copy
import json
from pathlib import Path
import sys
import unittest
CALC=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(CALC))
from forecast import forecast, parameter
from run_pipeline import validate_data

class OptimusRent(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config=json.loads((CALC/'configs/current.json').read_text())

    def test_discount_starts_after_annual_production_threshold(self):
        robot=self.config['companies']['tesla']['segments']['optimus_owned']
        first=next(y for y in self.config['years'] if parameter(robot['production_units'],y,2027)>=10000000)
        self.assertEqual(first,2029)
        self.assertEqual([parameter(robot['monthly_rent_usd'],y,2027)*12 for y in self.config['years']], [30000,30000,30000,27000,24300])

    def test_all_rentals_reprice_while_fleet_and_costs_stay_the_same(self):
        old=copy.deepcopy(self.config)
        old['companies']['tesla']['segments']['optimus_owned']['monthly_rent_usd']=2500
        before,after=forecast(old),forecast(self.config)
        self.assertEqual(before['companies']['spacex'],after['companies']['spacex'])
        for b,a in zip(before['segments'],after['segments']):
            if a['company_id']!='tesla' or a['segment']!='optimus_owned':
                self.assertEqual(b,a);continue
            factor={2030:.9,2031:.81}.get(a['year'],1)
            self.assertAlmostEqual(a['revenue_usd'],b['revenue_usd']*factor,delta=.01)
            self.assertAlmostEqual(a['revenue_usd'],a['drivers']['average_rented_robots']*a['drivers']['monthly_rent_usd']*12,delta=.01)
            for key in ('cogs_usd','capex_usd','da_usd','opex_usd'):self.assertEqual(a[key],b[key])
            for key in ('average_rented_robots','average_internal_robots','closing_fleet','production_units'):self.assertEqual(a['drivers'][key],b['drivers'][key])
        self.assertEqual(before['companies']['tesla'][:3],after['companies']['tesla'][:3])

    def test_provenance_alone_cannot_override_compounding_rule(self):
        c=copy.deepcopy(self.config)
        c['companies']['tesla']['segments']['optimus_owned']['monthly_rent_usd']['growth']=.01
        registry=json.loads((CALC/'configs/input_provenance.json').read_text())
        mapping=next(r for r in registry['records'] if r['input_path']=='companies.tesla.segments.optimus_owned.monthly_rent_usd')
        mapping['value']=c['companies']['tesla']['segments']['optimus_owned']['monthly_rent_usd']
        with self.assertRaisesRegex(ValueError,'rent policy and yearly price curve'):
            validate_data(c,registry,json.loads((CALC/'configs/reference_facts.json').read_text()))

if __name__=='__main__':unittest.main()
