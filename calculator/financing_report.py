"""Generate the payback and monthly financing report from the published forecast."""
from forecast import parameter

IR='https://ir.spacex.com/updates/releases-details/2026/SPACEX-SECURES-40-BILLION-IN-THE-LARGEST-GPU-FINANCING-EVER-2026-EnDqGhTAB3/'
LEASE='https://www.sec.gov/Archives/edgar/data/1181412/000110465926118614/tm2628247d1_8k.htm'
DEBT='https://www.sec.gov/Archives/edgar/data/1181412/000162828026066880/spcx-20260930.htm'

def report(result,baseline):
    c=result['resolved_assumptions'];sx=c['companies']['spacex'];years=c['years'];base=years[0]
    def num(v,scale=1):return 'N/A' if v is None else f'{v/scale:,.2f}'
    lines=['# SpaceX：回收期、月度融資與全模型重算','', '更新日：2026-11-20（台北）。依主預測自動生成。金額除單位成本與股價外，均為十億美元；股數為億股。','',
        '## 判讀與來源','',
        '客戶合約、微軟意願、建設速度及2029太空占比的最新查核見[算力證據集](../evidence/spacex_compute_contracts_and_build_speed_2026-11-20.md)。本輪只補證據，未調整預測數字；Anthropic最新協議不能在既有算力分部外另加一次收入。','',
        f'[公司10月26日公告]({IR})稱SI投資回收少於一年，沒有披露逐案成本範圍或公式。依使用者最新要求，2027–2031地面與太空各年度均設12個月稅前分部簡單回收；這是使用者情境，並非公司已證實太空及所有未來年度都達標。','',
        f'[8-K]({LEASE})披露約40B的條件式設備租賃，預計2027上半年分批起租，約5–5.25年，季度期初本金約為融資成本1/20，另加固定利息及費用；實際利率待定。主預測假設1–6月均分六批、60個月、6.5%利率，尚未估計未披露的額外交易費用。未把承諾寫成已交割，也未自動新增2028以後融資。','',
        f'[Q3申報]({DEBT})提供5B信用額度（含信用狀、契約條件），2031年5月到期；主預測假設符合條件且可提足，以6.5%代理，當月到期歸還，不自動續約。2027–2030舊債還款採披露到期表；2031首批債券暫估5B，並非披露的單年金額。舊債統一5.855%僅是債券票息代理，既有0.983B融資租賃的付款分配仍待校準。','',
        '## 1．完整投資與回收口徑','',
        '簡單回收月數＝（每MW當年新增硬體成本＋基建或部署成本）÷ 每MW全年稅前分部現金貢獻 ×12。現金貢獻扣電力、維護、閒置與自用容量成本及分部研發；加回折舊。未扣公司共同費用、稅、利息、營運資金及未來汰換，不是IRR、股東現金回收或逐批實際累計回款日。','',
        '地面保留2027硬體25M＋基建15M美元/MW，太空保留硬體20M＋部署5M美元/MW；按65%對外、75%利用率、95%可用率及平均8GW分攤研發，反推必要租價。自用35%不虛列租金；因此不能直接拿名目MW乘滿載租價。','',
        '| 年 | 分部 | 成本M美元/MW | 必要／模型租價美元/MWh | 現金貢獻M美元/MW年 | 簡單回收月 |','|---|---|---:|---:|---:|---:|']
    for r in result['segments']:
        if r['company_id']=='spacex' and r['segment'] in ('ground_compute','orbital_compute'):
            d=r['drivers'];lines.append('| '+' | '.join([str(r['year']),'地面' if r['segment']=='ground_compute' else '太空',num(d['full_capital_usd_per_mw'],1e6),num(d['effective_price_usd_per_billable_mw_hour']),num(d['annual_cash_contribution_usd_per_mw'],1e6),num(d['simple_payback_months'])])+' |')
    lines+=['','地面2027反推價格約10,506、太空約6,246美元/計費MWh；後續各年各自反推，以完整投資12個月回收取代原固定年降6%租價。硬體及基建／部署成本保持原曲線，未刪除研發、維修或折舊。價格與足量需求是此使用者情境成立的必要條件，不是已查到的客戶合約；敏感度保留主預測租價，利用率不足時回收會變長。單靠改成租賃不會縮短經濟回收。','',
        '## 2．年度現金、租賃與增發','',
        '按月以期初現金＋營運回款−現金費用／稅／利息−全額資產投入−營運資金−償債計缺口；設備租賃只抵同一設備的購置現金一次，增加對應負債；信用額度有上限、利息與到期日，仍不足才以股票支付合格資源。','',
        '現金FCF＝經濟FCF＋SBC＋股票支付資源＋新租賃資產；期末現金再加現金借款、減所有本金。新租賃不是現金流入；經濟FCF保留完整資本投入。預付季度利息列營運資金變動，確保利息費用與實付勾稽。','',
        '| 年 | 營收 | 淨利 | 完整capex | 經濟FCF | 新設備租賃 | 現金借款 | 全部本金償還 | 股票資源對價 | 年底現金 | 年底債務 |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
    for r in result['companies']['spacex']:
        keys=['revenue_usd','net_income_usd','capex_usd','economic_fcf_usd','finance_lease_additions_usd','cash_debt_draws_usd','debt_principal_repaid_usd','stock_payment_usd','cash_usd','debt_usd']
        lines.append('| '+str(r['year'])+' | '+' | '.join(num(r[k],1e9) for k in keys)+' |')
    lines+=['','地面及太空在模型中都一年回收後，2028–2031不再觸發資源增發；2027仍因集中建設與年內爬坡產生資金缺口。這是主預測租價及付費利用率均成立下的現金結果，並不保證真實資金充足，也未新增未承諾的租賃。Tesla既有營運、租金下降及年度融資假設不變。','',
        '## 3．改版前後股數與估值','',
        f"舊版基準：[{baseline['commit'][:7]}](https://github.com/WangChengYeh/AI_eco/commit/{baseline['commit']})；只作歷史比較，不是新增主情境。資源股份仍沿用每股100美元，沒有用同年預測股價回填。",'',
        '| 年 | 舊版股數 | 新版股數 | 舊版期初持股保留 | 新版期初持股保留 | 新P/E股價 | 新分部股價 |','|---|---:|---:|---:|---:|---:|---:|']
    for r,b in zip(result['companies']['spacex'],baseline['spacex']):
        lines.append('| '+' | '.join([str(r['year']),num(b['shares'],1e8),num(r['shares'],1e8),f"{sx['opening_shares']/b['shares']:.2%}",f"{sx['opening_shares']/r['shares']:.2%}",num(r['price_pe_usd']),num(r['price_sotp_usd'])])+' |')
    lines+=['','完整Tesla／SpaceX股數見[逐年稀釋報告](share_dilution_2026-11-20.md)。每股估值仍高度依賴反推租價、未校準需求、發射頻率、供應商收股及估值倍數，不能將數值上升當成已證實的投資報酬。','',
        '## 4．逐月資金明細','',
        '地面新增與替換、太空製造與部署按月計投入；算力收入按月平均有效容量分配。其餘分部、公司費用及年度營運資金暫均分12月。實際帳期、應收／應付、客戶預收、施工前置付款、信用契約測試、融資費及既有租賃還款明細仍待資料校準；這是月度流動性代理，並非完整GAAP三表或已知收款時程。當月期末有現金不證明月內最低現金充足。','']
    for r in result['companies']['spacex']:
        lines += [f"### {r['year']}",'','| 月 | 營運現金（稅息前） | capex | 利息實付 | 稅 | 租賃資產 | 租賃本金 | 信用提用 | 信用歸還 | 股票支付 | 月底現金 | 月底信用 |','|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|']
        for m in r['monthly_financing']:
            keys=['cash_operating_before_interest_tax_usd','capex_usd','interest_paid_usd','tax_usd','lease_additions_usd','lease_principal_usd','credit_draw_usd','credit_repaid_usd','stock_payment_usd','closing_cash_usd','closing_credit_usd']
            lines.append('| '+str(m['month'])+' | '+' | '.join(num(m[k],1e9) for k in keys)+' |')
    lines+=['','計算與來源映射：[current.json](../calculator/configs/current.json)、[input_provenance](../calculator/configs/input_provenance.json)、[research](../calculator/configs/user_assumption_research.json)。完整變更與驗證記錄見[SOP](../SOP.md)。','']
    return '\n'.join(lines)
