"""Build both Pages entrypoints from stable templates and one forecast dataset."""
import html
import json
import math
from pathlib import Path

from forecast import forecast, parameter, summary_markdown
from review_assumptions import validate_research, report_markdown

ROOT = Path(__file__).resolve().parents[1]


def assumptions(config):
    base = config['years'][0]
    tesla, spacex = config['companies']['tesla'], config['companies']['spacex']
    robot, fsd, taxi = (tesla['segments'][k] for k in ('optimus_owned','fsd','robotaxi'))
    orbit = spacex['segments']['orbital_compute']
    network, ramp = orbit['launch_network'], taxi['production_ramp']
    def v(spec, year=None): return parameter(spec, base if year is None else year, base)
    upgrade = network.get('capacity_upgrade')
    initial_mw = v(network['payload_tonnes'])*v(network['it_kw_per_tonne'])*v(network['payload_efficiency'])/1000
    mw_text = f"基準{initial_mw:g}MW/次"
    if upgrade:
        mw_text += f"；{upgrade['year']}/{upgrade['month']}起淨{upgrade['net_it_mw_per_flight']:g}MW/次（使用者假設，不再折減）"
    dates = '；'.join(f"{site['id']}:"+', '.join(f"{p['id']} {p['online_year']}/{p['online_month']}" for p in site['pads']) for site in network['sites'])
    ramp_text = '；'.join(f"{y}年{v(network['fleet_rate_start'],y):g}→{v(network['fleet_rate_end'],y):g}" for y in config['years'])
    limits = '；'.join(site['id']+':'+ '/'.join(f"{v(site['annual_site_limit'],y):g}" for y in config['years']) for site in network['sites'])
    rows = [
        ['FSD（增量服務成本）',f"每戶每月{v(fsd['monthly_cost_usd']):g}美元；保留分部費用、折舊與公司費用。美國費率錨點{v(fsd['monthly_price_usd']):g}美元；未來全球實收價格曲線仍是假設"],
        ['FSD（付費車隊）',f"2026年底{fsd['opening_subscribers']/10000:g}萬；新車加入率{v(fsd['new_vehicle_attach_rate']):.0%}、退訂率{v(fsd['annual_churn_rate']):.0%}；均勻加入，按全年平均計費（假設）"],
        ['Optimus（全年製造）','；'.join(f"{y}年{v(robot['production_units'],y)/10000:,.0f}萬台" for y in config['years'])+'；非公司年度指引'],
        ['Optimus（內用與出租）',f"平均內用需求{v(robot['internal_demand_robots'])/10000:g}萬台，內用優先；餘量出租率{v(robot['rental_utilization']):.0%}，每台年租{v(robot['monthly_rent_usd'])*12:,.0f}美元"],
        ['Optimus（租賃需求）',f"需求上限{v(robot['rental_demand_robots']):,.0f}台" if 'rental_demand_robots' in robot else '未另設需求上限，足量付費需求是使用者假設'],
        ['Robotaxi（量產／投運）',f"{ramp['full_rate_year']}/{ramp['full_rate_month']}全速，基準年化{v(ramp['annual_capacity_units']):,.0f}台；年初{ramp['initial_rate_fraction']:.0%}、部署延遲{ramp['deployment_delay_months']}月；均為條件假設"],
        ['Robotaxi（獲利口徑）','未套入每車年淨利3萬美元；2019 Musk約3萬美元是年毛利展望，非淨利實績。車資、里程與成本待校準'],
        ['星艦（單次容量）',mw_text+f"；AI發射分配{v(network['ai_flight_share']):.0%}（假設）"],
        ['星艦（全機隊年化爬坡）',ramp_text+'；2027錨定Musk近期說法，之後為模型延伸，不逐塔相乘'],
        ['發射場（模型啟用月份）',dates+'；日期與許可均含未驗證條件'],
        ['場址額度（模型曲線）',limits+'；依序為2027–2031，後續擴容並非已獲准'],
        ['衛星製造／投運',('供應充足、隨AI發射能力備貨（使用者假設）' if orbit.get('manufacture_to_launch_capacity') else '受明列年度製造量限制')+f"；2027從{v(orbit['commissioning_start_month']):g}月起投運，製造及部署成本照計"],
        ['太空成本（模型假設）',f"硬體{v(orbit['hardware_cost_usd_per_mw'])/1e6:g}M美元/MW、部署{v(orbit['deployment_cost_usd_per_mw'])/1e6:g}M美元/MW；不代表已驗證成本"],
        ['資產服務壽命',f"Optimus {robot['service_life_years']}年、Robotaxi {taxi['service_life_years']}年、太空設備{orbit['service_life_years']}年；製造投入及退役按批次計算"],
        ['股票交換資源','；'.join(f"{co['name']}接受度{v(co['stock_payment']['acceptance_ratio']):.0%}、協議價{v(co['stock_payment']['reference_price_usd']):g}美元/股" for co in config['companies'].values())+'；有缺口才發股，保留成本與稀釋，非已簽約條件'],
        ['可改善現金成本',f"乘用車合格成本占比{v(tesla['segments']['passenger_vehicles']['automation_eligible_cash_cost_ratio']):.0%}，節省仍受公司上限{v(tesla['robotics_max_cogs_share']):.0%}限制；不抵銷折舊"],
    ]
    return rows


def orbital_audit(config, result):
    network=config['companies']['spacex']['segments']['orbital_compute']['launch_network']
    rows=[]
    for row in result['segments']:
        if row['company_id']!='spacex' or row['segment']!='orbital_compute':continue
        y,d=row['year'],row['drivers']
        pads=[p for site in network['sites'] for p in site['pads']]
        rows.append(dict(year=y,
            pads_start=sum((y,1)>=(p['online_year'],p['online_month']) for p in pads),
            pads_end=sum((y,12)>=(p['online_year'],p['online_month']) for p in pads),
            mw_start=d['mw_per_ai_flight_start'],mw_end=d['mw_per_ai_flight'],
            fleet_rate_start=d['fleet_rate_start'],fleet_rate_end=d['fleet_rate_end'],
            available_flights=d['available_starship_flights'],ai_slots=d['allocated_ai_flights'],
            used_ai_slots=sum(math.ceil(q/p-1e-9) for q,p in zip(d['deployed_monthly_mw'],d['monthly_mw_per_ai_flight']) if q>0 and p>0),
            manufactured_gw=d['manufactured_it_mw']/1000,new_gw=d['commissioned_new_it_mw']/1000,
            retired_gw=d['retired_it_mw']/1000,end_gw=d['year_end_it_mw']/1000,
            average_gw=d['average_it_mw']/1000,capex_usd=row['capex_usd']))
    return rows


def payload(config,research,result):
    evidence=[dict(title=r['title'],verdict=r['verdict_label'],finding=r['finding'],limits=r['limits'],musk=r['musk_search']) for r in research['claims']]
    segment_keys={'year','company_id','segment','segment_name','revenue_usd','operating_profit_usd','capex_usd','drivers'}
    anchors=[dict(company=co['name'],shares=co['opening_shares'],liquid_funds_usd=co['opening_cash_usd'],debt_usd=co['opening_debt_usd']) for co in config['companies'].values()]
    return [dict(scenario='base',evidence=evidence,assumptions=assumptions(config),companies=result['companies'],
        segments=[{k:v for k,v in row.items() if k in segment_keys} for row in result['segments']],
        opening_anchors=anchors,orbital_audit=orbital_audit(config,result),
        model_notice='條件式預測：部分期初財務值採2026Q3／10月申報錨點，假設至2026年底淨變動為0；其餘營運、許可擴容、估值與股票支付條件仍待驗證。')]


def render_document(config,research,result):
    template=(ROOT/'calculator/site_template.html').read_text(encoding='utf-8')
    shell=(ROOT/'calculator/site_shell.html').read_text(encoding='utf-8')
    if template.count('__FORECAST_DATA__')!=1 or shell.count('__FRAME_DOCUMENT__')!=1:
        raise ValueError('site templates must have exactly one data and frame placeholder')
    data=json.dumps(payload(config,research,result),ensure_ascii=False,allow_nan=False,separators=(',',':')).replace('<','\\u003c')
    frame=template.replace('__FORECAST_DATA__',data).replace('__AS_OF__',config['metadata']['as_of']).replace('__YEAR_RANGE__',f"{config['years'][0]}–{config['years'][-1]}")
    return shell.replace('__FRAME_DOCUMENT__',html.escape(frame,quote=True))


def build():
    def read(name):return json.loads((ROOT/'calculator/configs'/name).read_text(encoding='utf-8'))
    config,research=read('current.json'),read('user_assumption_research.json')
    validate_research(config,research)
    result=forecast(config)
    document=render_document(config,research,result)
    for entry in ('index.html','docs/index.html'):(ROOT/entry).write_text(document,encoding='utf-8')
    (ROOT/'calculator/forecast_summary.md').write_text(summary_markdown([result]),encoding='utf-8')
    (ROOT/'research/user_assumption_review_2026-11-19.md').write_text(report_markdown(research),encoding='utf-8')
    print('Built both Pages entrypoints, summary and research report from one config and stable templates.')
    return result


if __name__=='__main__':build()
