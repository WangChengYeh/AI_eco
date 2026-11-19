"""Recompute the canonical forecast and refresh the committed GitHub Pages page.

The standalone page includes its stylesheet/runtime and a sandboxed document.
Only result data and the input date are replaced; no browser-side Python server
or ChatGPT session is required. Run from anywhere with Python 3.10+.
"""
import html
import json
from pathlib import Path
import re

from forecast import forecast, parameter, summary_markdown
from review_assumptions import validate_research, report_markdown

ROOT = Path(__file__).resolve().parents[1]


def assumptions(config):
    base = config["years"][0]
    robot = config["companies"]["tesla"]["segments"]["optimus_owned"]
    fsd = config["companies"]["tesla"]["segments"]["fsd"]
    taxi = config["companies"]["tesla"]["segments"]["robotaxi"]
    orbit = config["companies"]["spacex"]["segments"]["orbital_compute"]
    ramp = taxi["production_ramp"]
    def val(spec, year=2027):
        return parameter(spec, year, base)
    return [
        ["FSD（增量服務成本）", f"每戶每月{val(fsd['monthly_cost_usd']):,.0f}美元（近零假設）；保留研發／營運費用、折舊及共同費用；月費以美國官方99美元為錨點"],
        ["FSD（車隊與付費戶）", f"2026年底可訂閱500萬輛為使用者基數，非付費戶；2027平均付費{val(fsd['average_subscribers']) / 10000:,.0f}萬戶仍為待校準假設"],
        ["Optimus（使用者全年產量假設）", "；".join(f"{y}年{val(robot['production_units'], y) / 10000:,.0f}萬台" for y in (2027, 2028, 2029)) + "；內用優先、餘量出租，非公司年度指引"],
        ["Optimus（延伸與內用假設）", f"2030–2031各年{val(robot['production_units'], 2030) / 10000:,.0f}萬台；平均內用需求{val(robot['internal_demand_robots']) / 10000:,.0f}萬台"],
        ["Optimus（使用者租賃條件）", f"可租餘量付費出租率{val(robot['rental_utilization']):.0%}；每台每年{val(robot['monthly_rent_usd']) * 12:,.0f}美元" + (f"；付費需求上限{val(robot['rental_demand_robots']) / 10000:,.0f}萬台" if 'rental_demand_robots' in robot else "；無額外出租需求上限")],
        ["Robotaxi（獲利數據狀態）", "每車實際年淨利尚未披露；未套入3萬美元淨利。2019 Musk約3萬美元指年毛利預估，非淨利實績；目前輸出仍是未校準成本／車資估算"],
        ["Robotaxi（使用者時程）", f"{ramp['full_rate_year']}年中達全速；以{ramp['full_rate_month']}月起穩定產速實作"],
        ["Robotaxi（產速假設）", f"年化{val(ramp['annual_capacity_units']):,.0f}台，取已披露裝置產能下限作錨點，非2027產量指引"],
        ["Robotaxi（爬坡／部署假設）", f"年初達全速{ramp['initial_rate_fraction']:.0%}，線性爬坡；全部自持、投運延遲{ramp['deployment_delay_months']}個月"],
        ["太空算力（使用者時程）", "2027年底大量量產"],
        ["太空算力（規模假設）", f"2027製造{val(orbit['manufactured_it_mw']) / 1000:,.2f}GW，{val(orbit['commissioning_start_month']):.0f}月起部署；2028製造{val(orbit['manufactured_it_mw'], 2028) / 1000:,.2f}GW"],
        ["太空成本（模型假設）", f"硬體及配套{val(orbit['hardware_cost_usd_per_mw']) / 1e6:,.0f}M美元/MW；發射部署{val(orbit['deployment_cost_usd_per_mw']) / 1e6:,.0f}M美元/MW"],
        ["股票交換資源（使用者假設）", "有資金缺口時用新股支付合格資源，保留完整成本並計入稀釋"],
        ["股票支付條件（模型假設）", "；".join(f"{co['name']}接受度{val(co['stock_payment']['acceptance_ratio']):.0%}，協議價{val(co['stock_payment']['reference_price_usd']):,.0f}美元/股" for co in config['companies'].values())],
        ["資產壽命（模型假設）", f"Optimus {robot['service_life_years']}年到期等量替換；Robotaxi {taxi['service_life_years']}年，年度產量含替換；太空設備{orbit['service_life_years']}年退役"],
        ["可改善現金成本（模型假設）", f"合格製造業務現金成本的{config['companies']['tesla']['segments']['passenger_vehicles']['automation_eligible_cash_cost_ratio']:.0%}；不含折舊"],
    ]


def build():
    config = json.loads((ROOT / "calculator/configs/current.json").read_text(encoding="utf-8"))
    research = json.loads((ROOT / "calculator/configs/user_assumption_research.json").read_text(encoding="utf-8"))
    validate_research(config, research)
    result = forecast(config)
    evidence = [{"title": r["title"], "verdict": r["verdict_label"], "finding": r["finding"],
                 "limits": r["limits"], "musk": r["musk_search"]} for r in research["claims"]]
    data = [{"scenario": "base", "evidence": evidence, "assumptions": assumptions(config), "companies": result["companies"], "segments": [
        {k: v for k, v in row.items() if k in {
            "year", "company_id", "segment", "segment_name", "revenue_usd",
            "operating_profit_usd", "capex_usd", "drivers"}}
        for row in result["segments"]]}]
    path = ROOT / "docs/index.html"
    document = path.read_text(encoding="utf-8")
    frame = re.search(r'data-srcdoc="([^"]*)"', document)
    if not frame:
        raise ValueError("standalone page template has no data-srcdoc document")
    source = html.unescape(frame[1])
    start, end = config["years"][0], config["years"][-1]
    source = re.sub(r"\d{4}–\d{4} · 更新日", f"{start}–{end} · 更新日", source)
    source = source.replace("+'，2027至2035年，單位'+def.unit",
                            "+'，'+rows[0].year+'至'+rows[rows.length-1].year+'年，單位'+def.unit")
    # Keep displayed assumptions tied to the same input that produced results.
    source = re.sub(r'(<table class="table table-sm"><tbody(?: id="ts-assumptions")?>).*?(</tbody></table>)',
                    lambda m: '<table class="table table-sm"><tbody id="ts-assumptions"></tbody></table>',
                    source, count=1, flags=re.S)
    marker = "const data=JSON.parse(el('ts-data').textContent);"
    render = """
el('ts-assumptions').replaceChildren(...data[0].assumptions.map(([label,value])=>{
 const tr=document.createElement('tr');for(const text of [label,value]){const td=document.createElement('td');td.textContent=text;tr.appendChild(td);}return tr;
}));"""
    if "replaceChildren(...data[0].assumptions" not in source:
        source = source.replace(marker, marker + render)
    if 'id="ts-robotaxi-detail"' not in source:
        source = source.replace('<div id="ts-current-detail" class="text-small" aria-live="polite"></div>',
                                '<div id="ts-current-detail" class="text-small" aria-live="polite"></div>\n<div id="ts-robotaxi-detail" class="text-small" aria-live="polite"></div>')
        source = source.replace("if(!r)return;", """if(!r)return;
 const taxi=selectedData.segments.find(s=>s.company_id===company.value&&s.year===r.year&&s.segment==='robotaxi');
 el('ts-robotaxi-detail').textContent=taxi?(()=>{const d=taxi.drivers;return r.year+' Robotaxi：製造 '+fmt(d.manufactured_units)+' 輛／新投運 '+fmt(d.additions)+' 輛／平均服役 '+fmt(d.average_fleet)+' 輛／年底待投運 '+fmt(d.pending_deployment_units)+' 輛；營收 '+fmt(taxi.revenue_usd,1e9)+' 十億美元。';})():'';""")
    if "四步驟 SOP" not in source:
        source = source.replace('<h2>Tesla／SpaceX 主預測</h2>', '<h2>Tesla／SpaceX 主預測</h2>\n<div class="text-small"><a href="https://github.com/WangChengYeh/AI_eco/blob/main/SOP.md" target="_blank" rel="noopener">四步驟 SOP：理論 → 數據 → Forecast Python → HTML</a></div>')
    if 'id="ts-evidence"' not in source:
        source = source.replace('<div class="viz-grid" aria-live="polite">',
            '<details><summary>使用者假設查核（含Musk訊息）</summary><div class="text-small">已搜尋支持與限縮證據；方向／目標不等於已實現產量，原始影片未核對及X原頁403均明列。</div><div class="table-responsive"><table class="table table-sm"><thead><tr><th>假設</th><th>判定</th><th>支持與限制</th></tr></thead><tbody id="ts-evidence"></tbody></table></div><a href="https://github.com/WangChengYeh/AI_eco/blob/main/research/user_assumption_review_2026-11-19.md" target="_blank" rel="noopener">來源、Musk原貼／原片入口與搜尋紀錄</a></details>\n<div class="viz-grid" aria-live="polite">')
        source = source.replace(marker, marker + """
el('ts-evidence').replaceChildren(...data[0].evidence.map(r=>{
 const tr=document.createElement('tr');for(const text of [r.title,r.verdict,r.finding+' '+r.limits+' Musk：'+r.musk]){const td=document.createElement('td');td.textContent=text;tr.appendChild(td);}return tr;
}));""")
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c")
    source, count = re.subn(r'(<script type="application/json" id="ts-data">).*?(</script>)',
                           lambda m: m[1] + payload + m[2], source, flags=re.S)
    if count != 1:
        raise ValueError("standalone page must contain exactly one primary forecast dataset")
    source = re.sub(r"更新日 \d{4}-\d{2}-\d{2}", "更新日 " + config["metadata"]["as_of"], source)
    document = document[:frame.start(1)] + html.escape(source, quote=True) + document[frame.end(1):]
    # User-activated source links open independently; the frame keeps an opaque
    # origin and cannot execute scripts in the containing document.
    document = document.replace('sandbox="allow-scripts"', 'sandbox="allow-scripts allow-popups allow-popups-to-escape-sandbox"')
    path.write_text(document, encoding="utf-8")
    (ROOT / "index.html").write_text(document, encoding="utf-8")
    (ROOT / "calculator/forecast_summary.md").write_text(summary_markdown([result]), encoding="utf-8")
    report = ROOT / "research/user_assumption_review_2026-11-19.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(report_markdown(research), encoding="utf-8")
    print("Updated index.html, docs/index.html and calculator/forecast_summary.md from configs/current.json")


if __name__ == "__main__":
    build()
