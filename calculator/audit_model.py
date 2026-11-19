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
            eq(row['cash_fcf_usd'],row['economic_fcf_usd']+row['sbc_expense_usd']+row['stock_payment_usd']+row.get('finance_lease_additions_usd',0),'cash FCF')
            eq(row['cash_usd'],prior_cash+row['cash_fcf_usd']+row.get('cash_debt_draws_usd',p('debt_issued_usd'))-row.get('debt_principal_repaid_usd',p('debt_repaid_usd'))+p('equity_raised_usd')-p('buybacks_usd')-p('dividends_usd'),'liquidity rollforward')
            eq(row['debt_usd'],prior_debt+row.get('cash_debt_draws_usd',p('debt_issued_usd'))+row.get('finance_lease_additions_usd',0)-row.get('debt_principal_repaid_usd',p('debt_repaid_usd')),'debt rollforward')
            eq(row['shares'],prior_shares*p('stock_split',1)*(1+p('sbc_dilution_rate'))+row['cash_equity_shares_issued']+row['resource_shares_issued']-(p('buybacks_usd')/p('buyback_price_usd') if p('buybacks_usd') else 0),'share rollforward')
            eq(row['stock_payment_usd'],row['resource_shares_issued']*(row['stock_payment_price_usd'] or 0),'resource equity consideration')
            eq(row['capex_usd'],row['cash_capex_usd']+row['stock_paid_capex_usd']+row.get('finance_lease_additions_usd',0),'cash/noncash capex')
            if row['price_pe_usd'] is not None: eq(row['price_pe_usd']*row['shares'],row['net_income_usd']*row['pe_multiple'],'P/E price share basis')
            if row['price_sotp_usd'] is not None:eq(row['price_sotp_usd']*row['shares'],row['sotp_equity_value_usd'],'SOTP price share basis')
            if 'monthly_financing' in row:
                months=row['monthly_financing']
                if len(months)!=12:raise ValueError('missing monthly finance rows')
                for key in ('capex_usd','interest_usd','interest_paid_usd','tax_usd','stock_payment_usd','resource_shares_issued'):
                    eq(sum(m[key] for m in months),row[key],'monthly annual sum '+key)
                eq(row['tax_usd'],max(pretax,0)*p('tax_rate',.21),'YTD monthly tax')
                mc,md=prior_cash,prior_debt
                for m in months:
                    eq(m['closing_cash_usd'],mc+m['cash_operating_before_interest_tax_usd']-m['interest_paid_usd']-m['tax_usd']-m['capex_usd']-m['working_capital_change_usd']+m['lease_additions_usd']+m['legacy_debt_draw_usd']-m['legacy_debt_repaid_usd']-m['lease_principal_usd']+m['credit_draw_usd']-m['credit_repaid_usd']+m['stock_payment_usd']+(p('equity_raised_usd')-p('buybacks_usd')-p('dividends_usd'))/12,'monthly cash bridge')
                    eq(m['closing_debt_usd'],md+m['lease_additions_usd']+m['legacy_debt_draw_usd']-m['legacy_debt_repaid_usd']-m['lease_principal_usd']+m['credit_draw_usd']-m['credit_repaid_usd'],'monthly debt bridge')
                    checks+=1
                    if m['closing_credit_usd']>m['credit_limit_usd']+.01:raise ValueError('credit exceeds available facility')
                    mc,md=m['closing_cash_usd'],m['closing_debt_usd']
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
        if spec['kind']=='robot_fleet' and row['active']:
            eq(row['revenue_usd'],d['average_rented_robots']*p('monthly_rent_usd')*12,'robot rental revenue at current year price')
        if spec['kind'] in ('compute','orbital_compute') and row['active']:
            hours=24*(366 if calendar.isleap(year) else 365)
            eq(d['calendar_hours'],hours,'calendar hours')
            if d.get('simple_payback_months') is not None:
                cash_unit=(row['revenue_usd']-row['cogs_usd']+row['da_usd']-row['opex_usd'])/d['average_it_mw']
                eq(d['annual_cash_contribution_usd_per_mw'],cash_unit,'unit pretax cash contribution')
                eq(d['simple_payback_months']*cash_unit/12,d['full_capital_usd_per_mw'],'full capital payback')
            eq(row['revenue_usd'],d['average_it_mw']*p('external_share',1)*p('external_utilization',1)*p('availability',1)*hours*p('price_usd_per_billable_mw_hour'),'compute billed revenue')
        if spec['kind']=='compute' and 'capacity_ramp' in spec and row['active']:
            ramp=spec['capacity_ramp']
            def rp(key):return parameter(ramp[key],year,base)
            eq(d['year_end_it_mw'],d['opening_it_mw']+d['commissioned_new_it_mw'],'ground net capacity target')
            eq(d['year_end_it_mw'],rp('year_end_it_mw'),'ground target reached')
            eq(sum(d['monthly_new_it_mw']),d['commissioned_new_it_mw'],'ground monthly additions')
            eq(sum(d['monthly_average_it_mw'])/12,d['average_it_mw'],'ground capacity exposure')
            eq(d['hardware_capex_usd'],(d['commissioned_new_it_mw']+d['replacement_hardware_mw'])*rp('hardware_cost_usd_per_mw'),'ground hardware funding')
            eq(d['infrastructure_capex_usd'],(d['commissioned_new_it_mw']+d['replacement_infrastructure_mw'])*rp('infrastructure_cost_usd_per_mw'),'ground infrastructure funding')
            eq(row['capex_usd'],d['hardware_capex_usd']+d['infrastructure_capex_usd']+p('capex_usd')+row['revenue_usd']*p('capex_revenue_ratio'),'ground capital cost sum')
            eq(row['da_usd'],d['hardware_da_usd']+d['infrastructure_da_usd']+p('da_usd')+row['revenue_usd']*p('da_revenue_ratio'),'ground depreciation sum')
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
                eq(d['raw_pad_capacity_flights'],sum(site['raw_annual_flights'] for site in d['launch_sites']),'sum of pad capacities')
                if 'fleet_rate_start' not in spec['launch_network']:
                    site_sum=sum(site['available_flights'] for site in d['launch_sites'])
                    if spec['launch_network'].get('capacity_method')=='pad_frequency':
                        site_sum=math.floor(site_sum+1e-9)
                        cumulative,previous=0.0,0
                        for i,actual in enumerate(d['monthly_available_starship_flights']):
                            cumulative+=sum(site['raw_monthly_flights'][i] for site in d['launch_sites'])
                            total=math.floor(cumulative+1e-9)
                            eq(actual,total-previous,'global pad sum integerized once per cumulative month')
                            previous=total
                    eq(d['available_starship_flights'],site_sum,'pad/site launch sum without fleet cap')
                    eq(d['allocated_ai_flights'],math.floor(d['available_starship_flights']*parameter(spec['launch_network'].get('ai_flight_share',1),year,base)+1e-9),'global AI allocation')
                for site in d['launch_sites']:
                    eq(site['raw_annual_flights'],sum(pad['raw_annual_flights'] for pad in site['pads']),'per-pad site sum')
                    expected=(sum(site['raw_monthly_flights']) if site['annual_site_limit'] is None else math.floor(sum(min(q,site['annual_site_limit']/12) for q in site['raw_monthly_flights'])+1e-9))
                    eq(site['available_flights'],expected,'site capacity matches selected calculation method')
                    eq(site['available_flights'],sum(site['monthly_available_flights']),'site monthly count')
                    for pad in site['pads']:
                        expected=sum((pad['rate_start']+(pad['rate_end']-pad['rate_start'])*(m-.5)/12)/12 for m in range(1,13) if (year,m)>=(pad['online_year'],pad['online_month']))
                        eq(pad['raw_annual_flights'],expected,'pad frequency times active months')
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
    share_rows=data['share_dilution']
    if len(share_rows)!=sum(len(rows) for rows in result['companies'].values()):raise ValueError('missing annual share rows')
    for row in share_rows:
        actual=next(r for r in result['companies'][row['company_id']] if r['year']==row['year'])
        if not math.isclose(row['opening_shares']+row['gross_new_shares']-row['buyback_shares'],actual['shares'],rel_tol=1e-10):
            raise ValueError('share report does not reconcile to forecast')
        if row['closing_shares']!=actual['shares'] or row['resource_shares']!=actual['resource_shares_issued']:
            raise ValueError('share report differs from forecast')
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
