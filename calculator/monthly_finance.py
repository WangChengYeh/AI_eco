"""Monthly liquidity, conditional equipment lease and a bounded revolver.

Lease additions offset asset cash purchases once; principal, interest and prepaid
quarterly interest remain visible. Uncommitted future facilities are not invented.
"""
import copy
import math


def finance_year(company, year, base, rows, state, cash, debt, operating,
                 da, sbc, corporate_opex, robot_da, capex, delta_nwc, parameter, settle):
    cfg=company['monthly_finance']
    allowed={'enabled','credit_limit_usd','credit_interest_rate','cash_buffer_usd',
             'lease_commitment_usd','lease_start_month','lease_delivery_months',
             'lease_term_months','lease_interest_rate','credit_expiry_year','credit_expiry_month','notes'}
    if set(cfg)-allowed:raise ValueError('unknown monthly_finance field')
    def p(k,default=0):return parameter(company.get(k,default),year,base,k,0,1 if k in ('interest_rate','tax_rate') else None)
    def f(k,default=0):return parameter(cfg.get(k,default),year,base,k,0,1 if k.endswith('interest_rate') else None)
    if not state:
        state.update(legacy_debt=debt,revolver=0.,leases=[],prepaid_interest=0.)
    initial_prepaid=state['prepaid_interest']
    limit=f('credit_limit_usd');buffer=f('cash_buffer_usd')
    term=f('lease_term_months',60);start=f('lease_start_month',1);deliveries=f('lease_delivery_months',6)
    if term<3 or term%3 or start<1 or start>12 or not start.is_integer() or not deliveries.is_integer() or deliveries<1 or start+deliveries>13:
        raise ValueError('lease term must be whole quarters and delivery window valid months')
    lease_budget=f('lease_commitment_usd');remaining_lease=lease_budget
    schedules=[];cash_op=[0.]*12;monthly_da=[robot_da/12]*12;monthly_capex=[0.]*12
    eligible_hardware=[0.]*12;cash_cost=[0.]*12
    for sid,row in rows.items():
        d=row['drivers'];exposure=d.get('monthly_average_it_mw')
        if exposure is not None and (len(exposure)!=12 or any(not math.isfinite(v) or v<0 for v in exposure)):
            raise ValueError('monthly exposure must contain 12 nonnegative finite values')
        if exposure is not None and sum(exposure)>0:
            weights=[v/sum(exposure) for v in exposure]
        else:weights=[1/12]*12
        capital=d.get('monthly_capex_usd',[row['capex_usd']/12]*12)
        if len(capital)!=12 or any(not math.isfinite(v) or v<0 for v in capital):
            raise ValueError('monthly capex must contain 12 nonnegative finite values')
        if not math.isclose(sum(capital),row['capex_usd'],rel_tol=1e-10,abs_tol=.01):
            raise ValueError('monthly capex does not reconcile: '+sid)
        for i,w in enumerate(weights):
            expense=(row['cogs_usd']-row['da_usd'])*w+row['opex_usd']/12
            cash_op[i]+=row['revenue_usd']*w-expense
            cash_cost[i]+=expense
            monthly_da[i]+=row['da_usd']*w
            monthly_capex[i]+=capital[i]
            eligible_hardware[i]+=d.get('monthly_hardware_capex_usd',[0.]*12)[i]
    other_capex=capex-sum(monthly_capex)
    for i in range(12):
        monthly_capex[i]+=other_capex/12
        corporate_cash=(corporate_opex-robot_da-sbc)/12
        cash_op[i]-=corporate_cash;cash_cost[i]+=corporate_cash
    stock_total=dict(stock_payment_usd=0.,stock_paid_capex_usd=0.,stock_paid_opex_usd=0.,resource_shares_issued=0.,stock_payment_price_usd=None)
    totals=dict(interest_usd=0.,interest_paid_usd=0.,tax_usd=0.,cash_debt_draws_usd=0.,debt_principal_repaid_usd=0.,finance_lease_additions_usd=0.,lease_principal_paid_usd=0.,revolver_draws_usd=0.,revolver_repaid_usd=0.)
    cumulative_profit=tax_paid=0.;peak_credit=state['revolver'];peak_gap=0.
    opening_cash=cash
    for i in range(12):
        month=i+1;clock=(year-base)*12+i
        active_limit=limit if (year,month)<(f('credit_expiry_year',9999),f('credit_expiry_month',12)) else 0.
        mandatory_credit_repayment=max(state['revolver']-active_limit,0.)
        legacy_open=state['legacy_debt'];explicit_draw=p('debt_issued_usd')/12
        legacy_repaid=p('debt_repaid_usd')/12
        if legacy_repaid>legacy_open+explicit_draw+1e-6:raise ValueError('monthly legacy debt repayment exceeds debt')
        state['legacy_debt']+=explicit_draw-legacy_repaid
        legacy_interest=(legacy_open+state['legacy_debt'])/2*p('interest_rate')/12
        lease_add=0.
        if start<=month<start+deliveries:
            desired=lease_budget/deliveries
            lease_add=min(remaining_lease,eligible_hardware[i],desired)
            remaining_lease-=lease_add
            if lease_add:
                state['leases'].append(dict(original=lease_add,balance=lease_add,born=clock,
                    quarter_principal=lease_add/(term/3),rate=f('lease_interest_rate'),monthly_coupon=0.))
        lease_principal=lease_cash_interest=lease_expense=0.
        for lot in state['leases']:
            age=clock-lot['born']
            if age>=0 and age%3==0:
                lot['monthly_coupon']=lot['balance']*lot['rate']/12
                lease_cash_interest+=lot['monthly_coupon']*3
                principal=min(lot['balance'],lot['quarter_principal'])
                lot['balance']-=principal;lease_principal+=principal
            lease_expense+=lot['monthly_coupon']
        state['prepaid_interest']+=lease_cash_interest-lease_expense
        revolver_open=state['revolver'];rev_rate=f('credit_interest_rate')/12
        fixed_interest=legacy_interest+lease_expense+revolver_open*rev_rate
        fixed_cash_interest=legacy_interest+lease_cash_interest+revolver_open*rev_rate
        profit_before_new_draw=cash_op[i]-monthly_da[i]-sbc/12-fixed_interest
        def cash_at(draw):
            profit=profit_before_new_draw-draw*rev_rate
            tax=max(cumulative_profit+profit,0)*p('tax_rate',.21)-tax_paid
            value=(cash+cash_op[i]-fixed_cash_interest-draw*rev_rate-tax-monthly_capex[i]-delta_nwc/12+
                   lease_add+explicit_draw-legacy_repaid-lease_principal-mandatory_credit_repayment+
                   (p('equity_raised_usd')-p('buybacks_usd')-p('dividends_usd'))/12+draw)
            return value,tax,profit
        draw=0.
        for _ in range(40):
            no_extra,_,_=cash_at(draw)
            next_draw=min(max(draw+buffer-no_extra,0),max(active_limit-(revolver_open-mandatory_credit_repayment),0))
            if abs(next_draw-draw)<1e-7:break
            draw=next_draw
        cash_before_stock,tax,profit=cash_at(draw)
        state['revolver']+=draw-mandatory_credit_repayment;peak_credit=max(peak_credit,state['revolver'])
        cumulative_profit+=profit;tax_paid+=tax
        peak_gap=max(peak_gap,buffer-cash_before_stock)
        stock_cfg=copy.deepcopy(company.get('stock_payment',{}))
        if 'max_new_shares' in stock_cfg:
            stock_cfg['max_new_shares']=max(parameter(stock_cfg['max_new_shares'],year,base)-stock_total['resource_shares_issued'],0)
        stock=settle(stock_cfg,year,base,cash_before_stock,max(monthly_capex[i]-lease_add,0),max(cash_cost[i],0))
        cash=cash_before_stock+stock['stock_payment_usd']
        sweep=min(max(cash-buffer,0),state['revolver']);state['revolver']-=sweep;cash-=sweep
        for k in stock_total:
            if k=='stock_payment_price_usd':
                if stock[k] is not None:stock_total[k]=stock[k]
            else:stock_total[k]+=stock[k]
        interest=fixed_interest+draw*rev_rate
        totals['interest_usd']+=interest;totals['interest_paid_usd']+=fixed_cash_interest+draw*rev_rate
        totals['tax_usd']+=tax;totals['cash_debt_draws_usd']+=explicit_draw+draw
        totals['debt_principal_repaid_usd']+=legacy_repaid+lease_principal+sweep+mandatory_credit_repayment
        totals['finance_lease_additions_usd']+=lease_add;totals['lease_principal_paid_usd']+=lease_principal
        totals['revolver_draws_usd']+=draw;totals['revolver_repaid_usd']+=sweep+mandatory_credit_repayment
        closing_debt=state['legacy_debt']+state['revolver']+sum(x['balance'] for x in state['leases'])
        schedules.append(dict(month=month,cash_operating_before_interest_tax_usd=cash_op[i],
            capex_usd=monthly_capex[i],interest_usd=interest,interest_paid_usd=fixed_cash_interest+draw*rev_rate,
            tax_usd=tax,working_capital_change_usd=delta_nwc/12,
            lease_additions_usd=lease_add,lease_principal_usd=lease_principal,
            legacy_debt_draw_usd=explicit_draw,legacy_debt_repaid_usd=legacy_repaid,
            credit_draw_usd=draw,credit_repaid_usd=sweep+mandatory_credit_repayment,credit_limit_usd=active_limit,stock_payment_usd=stock['stock_payment_usd'],
            stock_paid_capex_usd=stock['stock_paid_capex_usd'],resource_shares_issued=stock['resource_shares_issued'],
            cash_before_stock_usd=cash_before_stock,closing_cash_usd=cash,
            closing_credit_usd=state['revolver'],closing_debt_usd=closing_debt))
    prepaid_delta=state['prepaid_interest']-initial_prepaid
    net=operating-totals['interest_usd']-totals['tax_usd']
    total_nwc=delta_nwc+prepaid_delta
    economic_fcf=net+da-capex-total_nwc
    cash_fcf=economic_fcf+sbc+stock_total['stock_payment_usd']+totals['finance_lease_additions_usd']
    expected=opening_cash+cash_fcf+totals['cash_debt_draws_usd']-totals['debt_principal_repaid_usd']+p('equity_raised_usd')-p('buybacks_usd')-p('dividends_usd')
    if not math.isclose(expected,cash,rel_tol=1e-10,abs_tol=.02):raise ValueError('monthly cash reconciliation failed')
    return dict(**totals,**stock_total,monthly_financing=schedules,
        cash_usd=cash,debt_usd=closing_debt,net_income_usd=net,economic_fcf_usd=economic_fcf,
        cash_fcf_usd=cash_fcf,delta_nwc_usd=total_nwc,delta_operating_nwc_usd=delta_nwc,
        delta_financing_prepaid_usd=prepaid_delta,finance_prepaid_interest_usd=state['prepaid_interest'],
        finance_lease_balance_usd=sum(x['balance'] for x in state['leases']),
        revolving_credit_balance_usd=state['revolver'],peak_credit_usd=peak_credit,
        peak_monthly_gap_before_stock_usd=max(peak_gap,0),
        cash_before_stock_payment_usd=cash-stock_total['stock_payment_usd'],
        funding_gap_before_stock_usd=stock_total['stock_payment_usd']+max(-cash,0))
