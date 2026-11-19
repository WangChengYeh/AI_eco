"""Independent output reconciliations for each primary/sensitivity forecast."""
import calendar
import html
import json
import math
import re
from pathlib import Path
from forecast import parameter


def reconcile(result):
    config=result['resolved_assumptions']
    base=config['years'][0]
    checks=0
    def eq(a,b,label):
        nonlocal checks
        checks+=1
        if not math.isclose(a,b,rel_tol=1e-9,abs_tol=.01):
            raise ValueError(f'{label}: {a} != {b}')
    for cid,annual in result['companies'].items():
        spec=config['companies'][cid]
        prior_cash,prior_debt,prior_shares=spec['opening_cash_usd'],spec['opening_debt_usd'],spec['opening_shares']
        for row in annual:
            year=row['year']
            def p(key,default=0):return parameter(spec.get(key,default),year,base)
            segments=[s for s in result['segments'] if s['company_id']==cid and s['year']==year]
            eq(row['revenue_usd'],sum(s['revenue_usd'] for s in segments),f'{cid}/{year} revenue sum')
            eq(row['cogs_usd'],sum(s['cogs_usd'] for s in segments),f'{cid}/{year} cost sum')
            eq(row['gross_profit_usd'],row['revenue_usd']-row['cogs_usd'],'gross profit')
            eq(row['operating_profit_usd'],sum(s['operating_profit_usd'] for s in segments)-row['corporate_opex_usd'],'operating profit')
            pretax=row['operating_profit_usd']-row['interest_usd']
            eq(row['net_income_usd'],pretax-row['tax_usd'],'net profit')
            eq(row['economic_fcf_usd'],row['net_income_usd']+row['da_usd']-row['capex_usd']-row['delta_nwc_usd'],'economic FCF')
            eq(row['cash_fcf_usd'],row['economic_fcf_usd']+row['sbc_expense_usd']+row['stock_payment_usd'],'cash FCF')
            eq(row['cash_usd'],prior_cash+row['cash_fcf_usd']+p('debt_issued_usd')-p('debt_repaid_usd')+p('equity_raised_usd')-p('buybacks_usd')-p('dividends_usd'),'liquidity rollforward')
            eq(row['debt_usd'],prior_debt+p('debt_issued_usd')-p('debt_repaid_usd'),'debt rollforward')
            eq(row['shares'],prior_shares*p('stock_split',1)*(1+p('sbc_dilution_rate'))+row['cash_equity_shares_issued']+row['resource_shares_issued']-(p('buybacks_usd')/p('buyback_price_usd') if p('buybacks_usd') else 0),'share rollforward')
            eq(row['stock_payment_usd'],row['resource_shares_issued']*(row['stock_payment_price_usd'] or 0),'resource equity consideration')
            eq(row['capex_usd'],row['cash_capex_usd']+row['stock_paid_capex_usd'],'cash/noncash capex')
            if row['price_pe_usd'] is not None: eq(row['price_pe_usd']*row['shares'],row['net_income_usd']*row['pe_multiple'],'P/E price share basis')
            if row['price_sotp_usd'] is not None:eq(row['price_sotp_usd']*row['shares'],row['sotp_equity_value_usd'],'SOTP price share basis')
            prior_cash,prior_debt,prior_shares=row['cash_usd'],row['debt_usd'],row['shares']
    inventory={}
    for row in result['segments']:
        year,cid,sid=row['year'],row['company_id'],row['segment']
        spec=config['companies'][cid]['segments'][sid]
        def p(key,default=0):return parameter(spec.get(key,default),year,base)
        d=row['drivers']
        eq(row['gross_profit_usd'],row['revenue_usd']-row['cogs_usd'],'segment gross')
        eq(row['operating_profit_usd'],row['gross_profit_usd']-row['opex_usd'],'segment operating')
        if spec['kind']=='subscription' and row['active']:
            eq(row['revenue_usd'],d['average_subscribers']*d['monthly_price_usd']*12,'subscription revenue')
            if 'closing_subscribers' in d:
                eq(d['closing_subscribers'],d['opening_subscribers']+d['new_subscribers']-d['cancellations'],'subscription cohort')
                eq(d['average_subscribers'],(d['opening_subscribers']+d['closing_subscribers'])/2,'subscription average')
        if spec['kind'] in ('compute','orbital_compute') and row['active']:
            hours=24*(366 if calendar.isleap(year) else 365)
            eq(d['calendar_hours'],hours,'calendar hours')
            eq(row['revenue_usd'],d['average_it_mw']*p('external_share',1)*p('external_utilization',1)*p('availability',1)*hours*p('price_usd_per_billable_mw_hour'),'compute billed revenue')
        if spec['kind']=='orbital_compute' and row['active']:
            eq(d['year_end_it_mw'],d['opening_it_mw']+d['commissioned_new_it_mw']-d['retired_it_mw'],'orbital live capacity rollforward')
            previous=inventory.get((cid,sid),p('opening_inventory_mw'))
            eq(d['closing_inventory_mw'],previous+d['manufactured_it_mw']-d['deployment_attempted_mw'],'orbital inventory rollforward')
            inventory[cid,sid]=d['closing_inventory_mw']
            if 'launch_network' in spec:
                eq(sum(d['deployed_monthly_mw']),d['deployment_attempted_mw'],'monthly deployment sum')
                for deployed,limit in zip(d['deployed_monthly_mw'],d['monthly_launch_capacity_mw']):
                    checks+=1
                    if deployed>limit+1e-8:raise ValueError('monthly deployment exceeds launch capacity')
                checks+=1
                if d['available_starship_flights']>d['infrastructure_site_slots']:raise ValueError('fleet exceeds site slots')
                if spec.get('manufacture_to_launch_capacity'):
                    eq(sum(d['manufactured_monthly_mw']),d['manufactured_it_mw'],'monthly manufacturing sum')
            expected_capex=d['manufactured_it_mw']*p('hardware_cost_usd_per_mw')+d['deployment_attempted_mw']*p('deployment_cost_usd_per_mw')+p('capex_usd')+row['revenue_usd']*p('capex_revenue_ratio')
            eq(row['capex_usd'],expected_capex,'orbital fully paid hardware/deployment capex')
    return checks


def validate_html(document,result):
    frame=re.search(r'data-srcdoc="([^"]*)"',document)
    if not frame:raise ValueError('missing iframe document')
    source=html.unescape(frame[1])
    data=json.loads(re.search(r'<script type="application/json" id="ts-data">(.*?)</script>',source,re.S)[1])[0]
    if data['companies']!=result['companies']:raise ValueError('HTML company results differ from Python')
    fields={'year','company_id','segment','segment_name','revenue_usd','operating_profit_usd','capex_usd','drivers'}
    expected=[{k:v for k,v in row.items() if k in fields} for row in result['segments']]
    if data['segments']!=expected:raise ValueError('HTML segment results differ from Python')
    if len(data['orbital_audit'])!=len(result['companies']['spacex']):raise ValueError('missing annual launch audit rows')
    return True


if __name__=='__main__':
    from forecast import forecast
    root=Path(__file__).resolve().parents[1]
    config=json.loads((root/'calculator/configs/current.json').read_text())
    result=forecast(config)
    print('Primary output reconciliations:',reconcile(result))
    document=(root/'index.html').read_text()
    validate_html(document,result)
    if document!=(root/'docs/index.html').read_text():raise ValueError('Pages entrypoints differ')
    print('Both HTML entrypoints match the current Python result.')
