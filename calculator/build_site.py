"""Recompute the canonical forecast and refresh the committed GitHub Pages page.

The standalone page includes its stylesheet/runtime and a sandboxed document.
Only result data and the input date are replaced; no browser-side Python server
or ChatGPT session is required. Run from anywhere with Python 3.10+.
"""
import html
import json
from pathlib import Path
import re

from forecast import forecast, summary_markdown

ROOT = Path(__file__).resolve().parents[1]


def build():
    config = json.loads((ROOT / "calculator/configs/current.json").read_text(encoding="utf-8"))
    result = forecast(config)
    data = [{"scenario": "base", "companies": result["companies"], "segments": [
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
    payload = json.dumps(data, ensure_ascii=False, allow_nan=False, separators=(",", ":")).replace("<", "\\u003c")
    source, count = re.subn(r'(<script type="application/json" id="ts-data">).*?(</script>)',
                           lambda m: m[1] + payload + m[2], source, flags=re.S)
    if count != 1:
        raise ValueError("standalone page must contain exactly one primary forecast dataset")
    source = re.sub(r"更新日 \d{4}-\d{2}-\d{2}", "更新日 " + config["metadata"]["as_of"], source)
    document = document[:frame.start(1)] + html.escape(source, quote=True) + document[frame.end(1):]
    path.write_text(document, encoding="utf-8")
    (ROOT / "calculator/forecast_summary.md").write_text(summary_markdown([result]), encoding="utf-8")
    print("Updated docs/index.html and calculator/forecast_summary.md from configs/current.json")


if __name__ == "__main__":
    build()
