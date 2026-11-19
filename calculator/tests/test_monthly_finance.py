"""Timing, bounded finance and full capital payback regression checks."""
import copy
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from forecast import forecast, parameter, settle_resources_with_stock
from monthly_finance import finance_year
from audit_model import reconcile

ROOT=Path(__file__).resolve().parents[1]

class MonthlyFinance(unittest.TestCase):
    def run_year(self,credit=100,lease=0,rate=0,expiry=None,state=None,year=2027,cash=10,debt=0,capex=120,revenue=120):
        cfg=dict(enabled=True,credit_limit_usd=credit,credit_interest_rate=rate,
            lease_commitment_usd=lease,lease_start_month=1,lease_delivery_months=1,
            lease_term_months=60,lease_interest_rate=rate)
        if expiry:cfg.update(credit_expiry_year=expiry[0],credit_expiry_month=expiry[1])
        company=dict(monthly_finance=cfg,interest_rate=0,tax_rate=0,
            stock_payment=dict(enabled=True,reference_price_usd=10,acceptance_ratio=1,capex_eligible_ratio=1,opex_eligible_ratio=1))
        rows={'ground':dict(revenue_usd=revenue,cogs_usd=0,da_usd=0,opex_usd=0,capex_usd=capex,
            drivers=dict(monthly_capex_usd=[capex]+[0]*11,monthly_hardware_capex_usd=[capex]+[0]*11))}
        return finance_year(company,year,2027,rows,{} if state is None else state,cash,debt,revenue,0,0,0,0,capex,0,parameter,settle_resources_with_stock)

    def test_monthly_bridge_needed_even_when_annual_cash_suffices(self):
        r=self.run_year()
        self.assertAlmostEqual(r['economic_fcf_usd'],0)
        self.assertAlmostEqual(r['peak_credit_usd'],100)
        self.assertAlmostEqual(r['stock_payment_usd'],0)
        self.assertAlmostEqual(r['cash_usd'],10)
        self.assertAlmostEqual(r['debt_usd'],0)

    def test_credit_is_capped_and_only_remaining_need_issues_shares(self):
        r=self.run_year(credit=40)
        self.assertAlmostEqual(r['peak_credit_usd'],40)
        self.assertAlmostEqual(r['stock_payment_usd'],60)
        self.assertAlmostEqual(r['resource_shares_issued'],6)
        self.assertAlmostEqual(r['cash_usd'],70)

    def test_lease_preserves_economic_cost_and_repays_principal(self):
        r=self.run_year(credit=0,lease=120,rate=.06,cash=1000)
        self.assertAlmostEqual(r['finance_lease_additions_usd'],120)
        self.assertAlmostEqual(r['lease_principal_paid_usd'],24)
        self.assertAlmostEqual(r['finance_lease_balance_usd'],96)
        self.assertAlmostEqual(r['economic_fcf_usd'],-r['interest_usd'])
        self.assertAlmostEqual(r['cash_usd'],1000+120-24-r['interest_paid_usd'])
        self.assertGreater(r['interest_usd'],0)

    def test_expired_credit_repaid_without_automatic_extension(self):
        state=dict(legacy_debt=0,revolver=50,leases=[],prepaid_interest=0)
        r=self.run_year(credit=100,expiry=(2027,1),state=state,cash=50,debt=50,capex=0,revenue=0)
        self.assertAlmostEqual(r['revolver_repaid_usd'],50)
        self.assertAlmostEqual(r['cash_usd'],0)
        self.assertAlmostEqual(r['debt_usd'],0)

    def test_draw_interest_and_lease_prepayment_reconcile(self):
        r=self.run_year(credit=100,rate=.12)
        self.assertGreater(r['interest_usd'],0)
        self.assertGreater(r['stock_payment_usd'],0)
        self.assertLessEqual(r['peak_credit_usd'],100)

    def test_primary_calibration_is_pretax_full_cost_and_not_forced_in_future(self):
        c=json.loads((ROOT/'configs/current.json').read_text());r=forecast(c)
        g=[s for s in r['segments'] if s['segment']=='ground_compute']
        self.assertAlmostEqual(g[0]['drivers']['simple_payback_months'],12)
        self.assertEqual(g[0]['drivers']['full_capital_usd_per_mw'],40e6)
        self.assertGreater(g[-1]['drivers']['simple_payback_months'],12)
        self.assertAlmostEqual(g[0]['drivers']['annual_cash_contribution_usd_per_mw'],40e6)
        orbital=[s for s in r['segments'] if s['segment']=='orbital_compute']
        self.assertEqual(orbital[0]['drivers']['effective_price_usd_per_billable_mw_hour'],3500)
        self.assertGreater(orbital[0]['drivers']['simple_payback_months'],12)
        self.assertEqual(r['companies']['spacex'][0]['finance_lease_additions_usd'],40e9)
        self.assertTrue(all(a['finance_lease_additions_usd']==0 for a in r['companies']['spacex'][1:]))
        self.assertGreater(reconcile(r),685)
        old=copy.deepcopy(c);old['companies']['spacex'].pop('monthly_finance')
        self.assertEqual(r['companies']['tesla'],forecast(old)['companies']['tesla'])

if __name__=='__main__':unittest.main()
