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
    ground = spacex['segments']['ground_compute'].get('capacity_ramp')
    network, ramp = orbit['launch_network'], taxi['production_ramp']
    def v(spec, year=None): return parameter(spec, base if year is None else year, base)
    upgrade = network.get('capacity_upgrade')
    initial_mw = v(network['payload_tonnes'])*v(network['it_kw_per_tonne'])*v(network['payload_efficiency'])/1000
    mw_text = f"基準{initial_mw:g}MW/次"
    if upgrade:
        mw_text += f"；{upgrade['year']}/{upgrade['month']}起淨{upgrade['net_it_mw_per_flight']:g}MW/次（使用者假設，不再折減）"
    dates = '；'.join(f"{site['id']}:"+', '.join(f"{p['id']} {p['online_year']}/{p['online_month']}" for p in site['pads']) for site in network['sites'])
    first_pad = network['sites'][0]['pads'][0]
    ramp_text = '；'.join(f"{y}年{v(first_pad['flights_per_year_start'],y):g}→{v(first_pad['flights_per_year_end'],y):g}" for y in config['years'])
    permits = '；'.join(site['id']+': '+site.get('regulatory_reference','未列資訊') for site in network['sites'])
    rows = [
        ['FSD（增量服務成本）',f"每戶每月{v(fsd['monthly_cost_usd']):g}美元；保留分部費用、折舊與公司費用。美國費率錨點{v(fsd['monthly_price_usd']):g}美元；未來全球實收價格曲線仍是假設"],
        ['FSD（付費車隊）',f"2026年底{fsd['opening_subscribers']/10000:g}萬；新車加入率{v(fsd['new_vehicle_attach_rate']):.0%}、退訂率{v(fsd['annual_churn_rate']):.0%}；均勻加入，按全年平均計費（假設）" + ('；'+config['metadata']['user_assumptions']['fsd_opening_fleet_basis'] if config['metadata']['user_assumptions'].get('fsd_opening_fleet_basis') else '')],
        ['Optimus（全年製造）','；'.join(f"{y}年{v(robot['production_units'],y)/10000:,.0f}萬台" for y in config['years'])+'；非公司年度指引'],
        ['Optimus（內用與出租）',f"平均內用需求{v(robot['internal_demand_robots'])/10000:g}萬台，內用優先；餘量出租率{v(robot['rental_utilization']):.0%}，年租：{'；'.join(f"{y}年{v(robot['monthly_rent_usd'],y)*12:,.0f}美元" for y in config['years'])}"],
        ['Optimus（降租規則）','2029全年產量達1,000萬台後，2030起每年複利降10%；全部付費租賃採當年費率，非僅新機器人；製造、維護、折舊與內用節省不隨租金同比調降（使用者假設）'],
        ['Optimus（租賃需求）',f"需求上限{v(robot['rental_demand_robots']):,.0f}台" if 'rental_demand_robots' in robot else '未另設需求上限，足量付費需求是使用者假設'],
        ['Robotaxi（量產／投運）',f"{ramp['full_rate_year']}/{ramp['full_rate_month']}全速，基準年化{v(ramp['annual_capacity_units']):,.0f}台；年初{ramp['initial_rate_fraction']:.0%}、部署延遲{ramp['deployment_delay_months']}月；均為條件假設"],
        ['Robotaxi（獲利口徑）','未套入每車年淨利3萬美元；2019 Musk約3萬美元是年毛利展望，非淨利實績。車資、里程與成本待校準'],
        ['星艦（單次容量）',mw_text+f"；AI發射分配{v(network['ai_flight_share']):.0%}（假設）"],
        ['星艦（每台年化頻率假設）',ramp_text+'；每架按啟用月份及月中頻率相乘後加總，不另套場址或全機隊上限。每架曲線仍為模型假設，非Musk逐架指引'],
        ['發射場（模型啟用月份）',dates+'；日期與許可均含未驗證條件'],
        ['發射容量算法','Σ每架啟用後每月年化頻率÷12；全部架累計後向下取整一次，不逐場截斷小數；90%分配AI，未依許可封頂'],
        ['許可／環評（獨立資訊）',permits],
        ['衛星製造／投運',('供應充足、隨AI發射能力備貨（使用者假設）' if orbit.get('manufacture_to_launch_capacity') else '受明列年度製造量限制')+f"；2027從{v(orbit['commissioning_start_month']):g}月起投運，製造及部署成本照計"],
        ['太空成本（模型假設）',f"硬體{v(orbit['hardware_cost_usd_per_mw'])/1e6:g}M美元/MW、部署{v(orbit['deployment_cost_usd_per_mw'])/1e6:g}M美元/MW；不代表已驗證成本"],
        ['資產服務壽命',f"Optimus {robot['service_life_years']}年、Robotaxi {taxi['service_life_years']}年、太空設備{orbit['service_life_years']}年；製造投入及退役按批次計算"],
        ['股票交換資源','；'.join(f"{co['name']}接受度{v(co['stock_payment']['acceptance_ratio']):.0%}、協議價{v(co['stock_payment']['reference_price_usd']):g}美元/股" for co in config['companies'].values())+'；有缺口才發股，保留成本與稀釋，非已簽約條件'],
        ['可改善現金成本',f"乘用車合格成本占比{v(tesla['segments']['passenger_vehicles']['automation_eligible_cash_cost_ratio']):.0%}，節省仍受公司上限{v(tesla['robotics_max_cogs_share']):.0%}限制；不抵銷折舊"],
    ]
    if ground:
        rows += [
            ['地面算力（名目IT容量）', f"2027年初{v(ground['opening_it_mw'])/1000:g}GW→年底{v(ground['year_end_it_mw'])/1000:g}GW，均勻月度投運、平均{(v(ground['opening_it_mw'])+v(ground['year_end_it_mw']))/2000:g}GW；依Musk第三方逐字稿目標，非已確認實績；20GW以上未納入主預測"],
            ['地面算力（後續擴張）',f"2028起年底容量每年成長{ground['year_end_it_mw'].get('growth',0):.0%}，沿用模型假設，非公司多年指引"],
            ['地面算力（資本成本）',f"硬體{v(ground['hardware_cost_usd_per_mw'])/1e6:g}M、基建{v(ground['infrastructure_cost_usd_per_mw'])/1e6:g}M美元/MW；JLL產業代理與預備額，非SpaceX報價；硬體{ground['hardware_life_years']}年／基建{ground['infrastructure_life_years']}年折舊並到期替換；期初視為零齡，年初資產不重複購置"],
            ['地面算力（計費與資金）', f"對外份額{v(spacex['segments']['ground_compute']['external_share']):.0%}、利用率{v(spacex['segments']['ground_compute']['external_utilization']):.0%}仍為模型假設；2027地面以完整投資12個月稅前分部簡單回收反推租價，非公司報價；後續仍每年降價6%。Apollo40B條件式租賃、5B有限信用及本金利息按月遞推，剩餘才增發"]
        ]
    rows += [['融資時點與限制', spacex.get('monthly_finance',{}).get('notes','採年度融資設定')]]
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
            pad_rate_start=min(p['rate_start'] for site in d['launch_sites'] for p in site['pads'] if p['active_months']),
            pad_rate_end=max(p['rate_end'] for site in d['launch_sites'] for p in site['pads'] if p['active_months']),
            raw_pad_capacity=d['raw_pad_capacity_flights'],
            active_pad_months=sum(site['active_pad_months'] for site in d['launch_sites']),
            site_details=d['launch_sites'],
            available_flights=d['available_starship_flights'],ai_slots=d['allocated_ai_flights'],
            used_ai_slots=sum(math.ceil(q/p-1e-9) for q,p in zip(d['deployed_monthly_mw'],d['monthly_mw_per_ai_flight']) if q>0 and p>0),
            manufactured_gw=d['manufactured_it_mw']/1000,new_gw=d['commissioned_new_it_mw']/1000,
            retired_gw=d['retired_it_mw']/1000,end_gw=d['year_end_it_mw']/1000,
            average_gw=d['average_it_mw']/1000,capex_usd=row['capex_usd']))
    return rows


def share_dilution_audit(result):
    """Follow a fixed opening holding, adjusted only for stock splits."""
    config=result['resolved_assumptions']
    base=config['years'][0]
    rows=[]
    for cid, annual in result['companies'].items():
        spec=config['companies'][cid]
        previous=initial_block=spec['opening_shares']
        for row in annual:
            year=row['year']
            def p(key,default=0):return parameter(spec.get(key,default),year,base)
            split=p('stock_split',1)
            opening=previous*split
            initial_block*=split
            sbc=opening*p('sbc_dilution_rate')
            retired=p('buybacks_usd')/p('buyback_price_usd') if p('buybacks_usd') else 0
            gross=sbc+row['cash_equity_shares_issued']+row['resource_shares_issued']
            retained=initial_block/row['shares']
            rows.append(dict(company_id=cid,company=spec['name'],year=year,
                opening_shares=opening,sbc_shares=sbc,
                cash_equity_shares=row['cash_equity_shares_issued'],
                resource_shares=row['resource_shares_issued'],gross_new_shares=gross,
                buyback_shares=retired,net_new_shares=gross-retired,
                closing_shares=row['shares'],annual_dilution=1-opening/row['shares'],
                original_holding_retained=retained,cumulative_dilution=1-retained,
                stock_payment_usd=row['stock_payment_usd'],
                resource_price_usd=row['stock_payment_price_usd']))
            previous=row['shares']
    return rows


def dilution_report(result):
    config=result['resolved_assumptions']
    rows=share_dilution_audit(result)
    sx_price=parameter(config['companies']['spacex']['stock_payment']['reference_price_usd'],config['years'][0],config['years'][0])
    lines=['# Tesla／SpaceX：逐年股數與持股稀釋', '',
        '更新日：'+config['metadata']['as_of']+'（台北）。本報告由主預測Python結果自動生成；修改輸入後執行run_pipeline即可同步更新。不是公司已宣布增發計畫或股價預測。', '',
        '## 結論與比較', '',
        '股數為億股。保留比例以期初持股不買賣、未獲配新增股份的持有人衡量；例如原本持有1%，將剩下表列「保留比例」乘1%。不是直接把保留比例當成該人的公司持股百分比。', '',
        '| 年 | Tesla年底股數 | Tesla原持股保留 | SpaceX年底股數 | SpaceX原持股保留 |',
        '|---|---:|---:|---:|---:|']
    for year in config['years']:
        t=next(x for x in rows if x['company_id']=='tesla' and x['year']==year)
        x=next(x for x in rows if x['company_id']=='spacex' and x['year']==year)
        lines.append(f"| {year} | {t['closing_shares']/1e8:,.2f} | {t['original_holding_retained']:.2%} | {x['closing_shares']/1e8:,.2f} | {x['original_holding_retained']:.2%} |")
    for cid,spec in config['companies'].items():
        company_rows=[x for x in rows if x['company_id']==cid]
        final=company_rows[-1]
        rate=parameter(spec.get('sbc_dilution_rate',0),config['years'][0],config['years'][0])
        price=parameter(spec['stock_payment']['reference_price_usd'],config['years'][0],config['years'][0])
        lines+=['', '## '+spec['name'], '',
            f"期初普通股{spec['opening_shares']/1e8:,.4f}億股；員工／其他股權增發率在模型中為每年{rate:.1%}。資源支付每股基準協議價{price:g}美元，另依折價及年度設定處理；不是市場成交價。", '',
            '股數為億股；「本年新增」＝員工股權＋現金募資＋資源支付；年底股數另扣回購。', '',
            '| 年 | 年初股數 | 員工股權新增 | 資源支付新增 | 本年新增合計 | 年底股數 | 當年稀釋 | 累計稀釋 |',
            '|---|---:|---:|---:|---:|---:|---:|---:|---:|']
        for x in company_rows:
            vals=[f"{x[k]/1e8:,.2f}" for k in ('opening_shares','sbc_shares','resource_shares','gross_new_shares','closing_shares')]
            lines.append('| '+str(x['year'])+' | '+' | '.join(vals)+f" | {x['annual_dilution']:.2%} | {x['cumulative_dilution']:.2%} |")
        lines+=['',f"到{final['year']}年底，期初固定持股的比例保留{final['original_holding_retained']:.2%}，累計稀釋{final['cumulative_dilution']:.2%}；原持有公司1%者，在不增減持股的條件下剩{final['original_holding_retained']:.4f}%。", '',
            '股票直接支付資源，單位十億美元；沒有把它當作現金募資收入。', '',
            '| 年 | 股票資源對價 | 本年資源新股（億股） | 協議價美元／股 |',
            '|---|---:|---:|---:|']
        for x in company_rows:
            px=f"{x['resource_price_usd']:,.2f}" if x['resource_price_usd'] else '—（未發行）'
            lines.append(f"| {x['year']} | {x['stock_payment_usd']/1e9:,.2f} | {x['resource_shares']/1e8:,.2f} | {px} |")
    lines+=['', '## 公式、來源與解讀限制', '',
        '- 年底股數＝拆股調整後年初股數＋員工股權新增＋現金募資新股＋資源支付新股−回購註銷。拆股不改變所有權比例。',
        '- 資源支付新股＝本年股票支付資源價值÷實際模型協議價；當年稀釋＝1−拆股調整後年初股數÷年底股數。累計稀釋＝1−拆股調整後期初固定持股÷年底股數；每年稀釋率不能直接相加。',
        '- 本輪兩公司均未設定現金募資、回購或拆股。Tesla雖有部分年度經濟FCF為負，仍可動用模型期初流動資金，沒有觸發額外資源新股，因此主要為每年1%員工股權增發；不代表真實世界沒有融資需要。',
        f'- SpaceX已按月計入營運現金、40B條件式設備租賃及有限信用，再以股票支付剩餘合格資源。後段太空擴張仍產生資金缺口；供應商接受度、可交換資源範圍與每股{sx_price:g}美元基準協議價均為情境輸入，不是已簽約或能無限發股的證據。',
        '- 資源協議價保持獨立於同年度P/E及SOTP估值；公司估值上升不會自動提高發股價格。若以更高協議價換取相同資源，所需新股會減少；本輪沒有自行改價，也沒有以同年稀釋後估值回填發股價。',
        '- 所有權稀釋不等於持有資產價值必然同幅減少，還須檢查取得資源的收益、投入、負債及每股價值。此表為普通股數量口徑，未分A／B類投票權，也不是加權平均EPS股數、自由流通股或各類潛在權益工具完整fully-diluted口徑。',
        '- 期初股數取2026-10-15申報錨點，假設至2026年底淨變動為0；[Tesla 10-Q](https://www.sec.gov/Archives/edgar/data/1318605/000162828026066775/tsla-20260930.htm)、[SpaceX 10-Q](https://www.sec.gov/Archives/edgar/data/1181412/000162828026066880/spcx-20260930.htm)。本輪已校準地面必要收入並加入條件式租賃與有限信用；回收、融資來源及限制見[完整重算報告](spacex_payback_financing_2026-11-20.md)。來源分類見[reference_facts](../calculator/configs/reference_facts.json)，實際輸入見[current.json](../calculator/configs/current.json)。',
        '- 理論001的股份資源支付仍保留完整經濟成本；來源與假設查核見[使用者假設報告](user_assumption_review_2026-11-19.md)，產能與投入見[星艦報告](starship_launch_capacity_2026-11-20.md)。', '',
        '此報告、年度比較及網頁由同一份主預測結果生成；財務及股數公式由run_pipeline勾稽。', '']
    return '\n'.join(lines)


def payload(config,research,result):
    evidence=[dict(title=r['title'],verdict=r['verdict_label'],finding=r['finding'],limits=r['limits'],musk=r['musk_search']) for r in research['claims']]
    segment_keys={'year','company_id','segment','segment_name','revenue_usd','operating_profit_usd','capex_usd','drivers'}
    anchors=[dict(company=co['name'],shares=co['opening_shares'],liquid_funds_usd=co['opening_cash_usd'],debt_usd=co['opening_debt_usd']) for co in config['companies'].values()]
    return [dict(scenario='base',evidence=evidence,assumptions=assumptions(config),companies=result['companies'],
        segments=[{k:v for k,v in row.items() if k in segment_keys} for row in result['segments']],
        opening_anchors=anchors,orbital_audit=orbital_audit(config,result),share_dilution=share_dilution_audit(result),
        model_notice='條件式預測：部分期初財務值採2026Q3／10月申報錨點，假設至2026年底淨變動為0；其餘營運、估值與股票支付仍待驗證。2027地面租價為12個月稅前回收反推假設，非公司報價；設備租賃尚有條件。星艦為逐架技術容量情境，未依場址許可封頂，不代表已取得可執行任務額度。')]


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
    from financing_report import report as finance_report
    baseline=json.loads((ROOT/'calculator/configs/payback_revision_baseline.json').read_text())
    (ROOT/'research/spacex_payback_financing_2026-11-20.md').write_text(finance_report(result,baseline),encoding='utf-8')
    share_report=dilution_report(result)
    (ROOT/'research/share_dilution_2026-11-20.md').write_text(share_report,encoding='utf-8')
    (ROOT/'calculator/forecast_summary.md').write_text(summary_markdown([result])+'\n\n## 股數與稀釋\n\n'+share_report.split('## 結論與比較\n\n',1)[1].split('\n## Tesla',1)[0]+'\n\n[逐年增發、資源對價與累計稀釋](../research/share_dilution_2026-11-20.md)。\n',encoding='utf-8')
    (ROOT/'research/user_assumption_review_2026-11-19.md').write_text(report_markdown(research),encoding='utf-8')
    print('Built both Pages entrypoints, summary and research report from one config and stable templates.')
    return result


if __name__=='__main__':build()
