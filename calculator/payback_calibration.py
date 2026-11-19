"""Required annual prices for a user payback target; no changes to capital cost.

Prices are fixed after calibration at primary utilization. Demand sensitivities
keep those prices, allowing payback to deteriorate rather than silently reprice.
"""
import copy
import math
from forecast import forecast


def calibrate(config):
    resolved=copy.deepcopy(config)
    policy=config['metadata']['additional_assumptions']['compute_payback_policy']
    if set(policy['segments'])!={'ground_compute','orbital_compute'} or policy['years']!=config['years']:
        raise ValueError('user policy must cover both compute segments and every forecast year')
    months=policy['target_months']
    if isinstance(months,bool) or not isinstance(months,(float,int)) or not math.isfinite(months) or months<=0:
        raise ValueError('payback target must be a positive finite number of months')
    result=forecast(config)
    for sid in policy['segments']:
        company=resolved['companies']['spacex'];spec=company['segments'][sid]
        if spec.get('capex_revenue_ratio',0) or spec.get('da_revenue_ratio',0):
            raise ValueError('payback calibration requires explicit non-revenue-linked compute capital costs')
        annual={}
        for row in result['segments']:
            if row['company_id']!='spacex' or row['segment']!=sid:continue
            d=row['drivers']
            if d.get('billable_mwh',0)<=0:raise ValueError('payback calibration needs positive billable compute output')
            cash_cost=row['cogs_usd']-row['da_usd']+row['opex_usd']
            required_revenue=d['full_capital_usd_per_mw']*d['average_it_mw']*12/months+cash_cost
            annual[str(row['year'])]=required_revenue/d['billable_mwh']
        spec['price_usd_per_billable_mw_hour']={'value':annual[str(config['years'][0])],'growth':0,'annual':annual}
    return resolved


def validate_policy(config):
    policy=config.get('metadata',{}).get('additional_assumptions',{}).get('compute_payback_policy')
    if not policy:return
    expected=calibrate(config)
    for sid in policy['segments']:
        actual=config['companies']['spacex']['segments'][sid]['price_usd_per_billable_mw_hour']
        required=expected['companies']['spacex']['segments'][sid]['price_usd_per_billable_mw_hour']
        if set(actual.get('annual',{}))!=set(required['annual']):raise ValueError('all primary payback years require calibrated prices')
        for year,price in required['annual'].items():
            if not math.isclose(actual['annual'][year],price,rel_tol=1e-10,abs_tol=1e-6):
                raise ValueError('payback target/required price mismatch: '+sid+'/'+year)
