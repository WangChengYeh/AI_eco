"""Require a recorded web/Musk evidence search for every user assumption."""
from datetime import date
from urllib.parse import urlsplit


def validate_research(config, research, registry=None):
    sources = research["sources"]
    for key, source in sources.items():
        if urlsplit(source["url"]).scheme != "https" or not source.get("access"):
            raise ValueError(f"invalid research source: {key}")
    covered, ids = {}, set()
    statuses = {"direct_support", "partial_support", "not_supported_as_stated", "not_established"}
    for claim in research["claims"]:
        if claim["id"] in ids:
            raise ValueError("duplicate research claim")
        ids.add(claim["id"])
        date.fromisoformat(claim["searched_at"])
        if not claim.get("search_queries") or not claim.get("musk_search"):
            raise ValueError("every user assumption needs recorded web and Musk searches")
        if claim["verdict"] not in statuses or not claim.get("limits") or not claim.get("finding"):
            raise ValueError("research needs a supported verdict and evidence limits")
        if not claim.get("source_ids") or any(s not in sources for s in claim["source_ids"]):
            raise ValueError("missing research sources")
        if claim["verdict"] == "direct_support" and not any(
            sources[s]["access"] == "primary_text_read" for s in claim["source_ids"]):
            raise ValueError("direct support requires readable primary evidence")
        for key, value in claim.get("user_values", {}).items():
            if key in covered:
                raise ValueError("duplicate user-assumption research mapping")
            covered[key] = value
    assumptions = config["metadata"]["user_assumptions"]
    if set(assumptions) - set(covered):
        raise ValueError("user assumption has no web/Musk research record: " + str(sorted(set(assumptions) - set(covered))))
    for key, value in assumptions.items():
        if covered[key] != value:
            raise ValueError("user assumption changed; redo its web/Musk evidence review: " + key)
    if registry:
        for record in registry["records"]:
            if record["classification"] == "user_assumption" and record.get("research_claim_id") not in ids:
                raise ValueError("user input provenance requires a researched claim: " + record["input_path"])
    print(f"Reviewed search coverage: {len(assumptions)} user inputs; {len(ids)} claims. Search coverage is not factual verification.")


def report_markdown(research):
    lines = ["# 使用者假設網路與 Musk 訊息查核", "", "查核日：" + research["checked_at"], "",
             "範圍：現行主預測全部使用者假設，加上原始理論的重要強版本。查核包含支持、反向及限縮證據；沒有找到支持不等於已證偽。公司目標、Musk預測、第三方逐字稿及已發生實績分開。", "",
             "本輪未以未驗證的新聞數字自動覆寫營運輸入。2027 Optimus產量、太空GW規模、Robotaxi滿產月份與股票普遍接受度仍保留為待驗證假設；2027–2031輸出不因此升格為實證預測。", ""]
    for claim in research["claims"]:
        lines += ["## " + claim["title"], "", "- 原命題：" + claim["claim"],
                  "- 判定：**" + claim["verdict_label"] + "**", "- 支持／相關證據：" + claim["finding"],
                  "- 限縮／相反證據：" + claim["limits"], "- Musk查核：" + claim["musk_search"],
                  "- 計算處理：" + claim["forecast_action"], "", "搜尋紀錄：", ""]
        lines += ["- `" + q + "`" for q in claim["search_queries"]]
        lines += ["", "來源：", ""]
        for key in claim["source_ids"]:
            s = research["sources"][key]
            lines.append(f"- [{s['title']}]({s['url']})：{s['access_note']}")
        lines.append("")
    lines += ["## 更新規則", "", "新增或修改任何使用者假設，必須同步重新搜尋並更新查核記錄，才能通過run_pipeline。不能把多年後的年化產能寫成當年產量、把Musk目標當已發生實績、把媒體轉述標為已直接看過原片，或把供應商投資當成股票抵付採購帳款。", "",
              "X貼文原頁若403或無法讀取，保留原始URL與讀取失敗狀態，轉述另列。影片已定位但未取得可核對的原片字幕時，不編造時間碼、直接引文或完成收看紀錄。", ""]
    return "\n".join(lines)
