"""SOP steps 3–4 after theory and source review; stdlib only."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def validate_data(config, registry, facts):
    fact_ids = {f["id"] for f in facts["facts"]}
    if len(fact_ids) != len(facts["facts"]):
        raise ValueError("duplicate source fact IDs")
    facts_by_id = {f["id"]: f for f in facts["facts"]}
    seen = set()
    for record in registry["records"]:
        path = record["input_path"]
        if path in seen:
            raise ValueError(f"duplicate provenance mapping: {path}")
        seen.add(path)
        value = config
        for key in path.split("."):
            value = value[key]
        if value != record["value"]:
            raise ValueError(f"input/provenance mismatch: {path}; revise data classification and evidence first")
        if record["classification"] not in {"company_disclosed", "user_assumption", "model_assumption"}:
            raise ValueError(f"unknown data classification: {path}")
        if not record.get("unit") or not record.get("checked_at") or not record.get("basis"):
            raise ValueError(f"incomplete data provenance: {path}")
        if any(ref not in fact_ids for ref in record.get("fact_ids", [])):
            raise ValueError(f"missing source fact: {path}")
        if record.get("fact_value_rule") == "lower_bound_anchor":
            sources = [facts_by_id[ref] for ref in record.get("fact_ids", [])]
            if len(sources) != 1 or sources[0].get("comparison") not in {">", ">="} or value != sources[0]["value"]:
                raise ValueError(f"capacity anchor must match the documented source lower bound: {path}")
            if record["classification"] != "model_assumption":
                raise ValueError("using installed capacity as production rate is a model assumption")
    ramp_path = "companies.tesla.segments.robotaxi.production_ramp."
    required = {ramp_path + k for k in ("annual_capacity_units.value", "full_rate_year", "full_rate_month",
                                       "initial_rate_fraction", "deployment_delay_months")}
    if not required <= seen:
        raise ValueError("Robotaxi production/deployment inputs require complete provenance")
    print(f"Validated {len(seen)} input mappings; unmapped inputs remain uncalibrated.")


def main():
    config_dir = ROOT / "calculator/configs"
    def read(name):
        return json.loads((config_dir / name).read_text(encoding="utf-8"))
    validate_data(read("current.json"), read("input_provenance.json"), read("reference_facts.json"))
    from review_assumptions import validate_research
    validate_research(read("current.json"), read("user_assumption_research.json"), read("input_provenance.json"))
    subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "calculator/tests", "-q"], cwd=ROOT, check=True)
    subprocess.run([sys.executable, "calculator/forecast.py", "--out", "forecast_output"], cwd=ROOT, check=True)
    # Validate optional sensitivities before changing published HTML.
    sys.path.insert(0, str(ROOT / "calculator"))
    from forecast import forecast
    config = read("current.json")
    for name in config["scenarios"]:
        forecast(config, name)
    from build_site import build
    build()
    print("SOP complete: commit reviewed inputs, Python, summary and both HTML entrypoints together.")


if __name__ == "__main__":
    main()
