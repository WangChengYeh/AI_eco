#!/usr/bin/env python3
"""Driver-based Tesla/SpaceX scenario calculator. Python 3.10+, stdlib only.

USD throughout. Sample inputs are illustrative assumptions, not reported actuals.
Public API: forecast(config, scenario='base') -> JSON-serializable dictionary.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path


class ModelError(ValueError):
    """Invalid assumption or economically inconsistent input."""


def number(value, label, minimum=None, maximum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelError(f"{label}: expected a number, got {value!r}")
    value = float(value)
    if not math.isfinite(value):
        raise ModelError(f"{label}: must be finite")
    if minimum is not None and value < minimum:
        raise ModelError(f"{label}: must be >= {minimum}")
    if maximum is not None and value > maximum:
        raise ModelError(f"{label}: must be <= {maximum}")
    return value


def parameter(spec, year, base_year, label="parameter", minimum=0, maximum=None):
    """Absolute annual overrides win; growth always anchors to base_year.

    {value: 100, growth: .1, cap: 150, annual: {'2029': 140}}
    gives 100, 110, 140, 133.1...; override is NOT a new growth anchor.
    """
    if isinstance(spec, dict):
        allowed = {"value", "growth", "cap", "floor", "annual"}
        if set(spec) - allowed or "value" not in spec:
            raise ModelError(f"{label}: allowed curve fields are {sorted(allowed)}")
        value = number(spec["value"], label + ".value")
        growth = number(spec.get("growth", 0), label + ".growth", -1)
        annual = spec.get("annual", {})
        if not isinstance(annual, dict):
            raise ModelError(f"{label}.annual: expected object")
        for key, entry in annual.items():
            if not isinstance(key, str) or not key.isdigit():
                raise ModelError(f"{label}.annual: year keys must be integer strings")
            number(entry, label + ".annual." + key)
        try:
            result = number(annual[str(year)], label) if str(year) in annual else value * (1 + growth) ** (year - base_year)
        except OverflowError as exc:
            raise ModelError(f"{label}: growth overflow") from exc
        if "cap" in spec:
            result = min(result, number(spec["cap"], label + ".cap", 0))
        if "floor" in spec:
            floor = number(spec["floor"], label + ".floor", 0)
            if "cap" in spec and floor > spec["cap"]:
                raise ModelError(f"{label}: floor cannot exceed cap")
            result = max(result, floor)
    else:
        result = spec
    return number(result, label, minimum, maximum)


def patch(config, path, value):
    """Replace an existing dotted path; reject typos rather than invent keys."""
    keys = path.split(".")
    node = config
    for key in keys[:-1]:
        if not isinstance(node, dict) or key not in node:
            raise ModelError(f"unknown override path: {path}")
        node = node[key]
    if not isinstance(node, dict) or keys[-1] not in node:
        raise ModelError(f"unknown override path: {path}")
    node[keys[-1]] = value


def resolve(config, scenario):
    if not isinstance(config, dict):
        raise ModelError("config must be an object")
    result = copy.deepcopy(config)
    scenarios = result.get("scenarios", {})
    if not isinstance(scenarios, dict):
        raise ModelError("scenarios must be an object")
    if scenario not in scenarios:
        raise ModelError(f"unknown scenario {scenario!r}; choose from {list(scenarios)}")
    if not isinstance(scenarios[scenario], dict):
        raise ModelError("scenario overrides must be an object")
    for path, value in scenarios[scenario].items():
        if path.startswith(("scenarios.", "metadata.")):
            raise ModelError("scenario patches may not alter metadata or scenario definitions")
        patch(result, path, value)
    return result


COMMON_SEGMENT_FIELDS = {
    "name", "kind", "start_year", "end_year", "notes", "opex_usd",
    "capex_usd", "capex_revenue_ratio", "da_usd", "da_revenue_ratio",
    "ev_sales_multiple", "robotics_eligible", "cost_includes_robotics", "volume_unit",
}
KIND_FIELDS = {
    "unit": {"units", "capacity_units", "price_usd", "unit_cost_usd"},
    "subscription": {"average_subscribers", "monthly_price_usd", "monthly_cost_usd"},
    "robotaxi": {"opening_fleet", "additions", "retirements", "vehicle_cost_usd",
                 "depreciation_usd_per_vehicle_year", "km_per_vehicle_day", "operating_days",
                 "paid_km_share", "fare_usd_per_paid_km", "cash_cost_usd_per_total_km",
                 "fixed_cash_usd_per_vehicle_year", "fleet_capacity"},
    "compute": {"average_it_mw", "external_share", "internal_share", "external_utilization",
                "internal_utilization", "availability", "price_usd_per_billable_mw_hour",
                "electricity_usd_per_kwh", "pue", "idle_power_fraction",
                "cash_overhead_usd_per_mw_year", "hardware_da_usd_per_mw_year"},
}


def segment_forecast(segment, year, base_year, state):
    kind = segment.get("kind")
    if kind not in KIND_FIELDS:
        raise ModelError(f"unknown segment kind: {kind}")
    unknown = set(segment) - COMMON_SEGMENT_FIELDS - KIND_FIELDS[kind]
    if unknown:
        raise ModelError(f"unknown segment fields: {sorted(unknown)}")
    start = number(segment.get("start_year", base_year), "start_year", base_year)
    end = number(segment.get("end_year", 9999), "end_year", start)
    if not start.is_integer() or not end.is_integer():
        raise ModelError("segment start/end years must be integers")
    def p(key, default=0, minimum=0, maximum=None):
        return parameter(segment.get(key, default), year, base_year, key, minimum, maximum)
    active = start <= year <= end
    inputs = {}
    revenue = cogs = extra_capex = extra_da = 0.0
    if active:
        if kind == "unit":
            desired = p("units")
            volume = min(desired, p("capacity_units", desired))
            price, cost = p("price_usd"), p("unit_cost_usd")
            revenue, cogs = volume * price, volume * cost
            inputs = {"external_units": volume, "requested_units": desired,
                      "capacity_limited": volume < desired, "price_usd": price, "unit_cost_usd": cost}
        elif kind == "subscription":
            subscribers, price, cost = p("average_subscribers"), p("monthly_price_usd"), p("monthly_cost_usd")
            revenue, cogs = subscribers * price * 12, subscribers * cost * 12
            inputs = {"average_subscribers": subscribers, "monthly_price_usd": price, "monthly_cost_usd": cost}
        elif kind == "robotaxi":
            opening = state.setdefault("fleet", number(segment.get("opening_fleet", 0), "opening_fleet", 0))
            adds, retirements = p("additions"), p("retirements")
            if retirements > opening:
                raise ModelError("robotaxi retirements cannot exceed opening fleet")
            closing = opening + adds - retirements
            if closing > p("fleet_capacity", closing):
                raise ModelError("robotaxi closing fleet exceeds fleet_capacity")
            average = (opening + closing) / 2
            total_km = average * p("km_per_vehicle_day") * p("operating_days", 365, 0, 366)
            paid_km = total_km * p("paid_km_share", 0.6, 0, 1)
            revenue = paid_km * p("fare_usd_per_paid_km")
            extra_da = average * p("depreciation_usd_per_vehicle_year")
            cogs = total_km * p("cash_cost_usd_per_total_km") + average * p("fixed_cash_usd_per_vehicle_year") + extra_da
            extra_capex = adds * p("vehicle_cost_usd")
            state["fleet"] = closing
            inputs = {"opening_fleet": opening, "additions": adds, "retirements": retirements,
                      "closing_fleet": closing, "average_fleet": average, "total_km": total_km,
                      "paid_km": paid_km, "vehicle_cost_usd": p("vehicle_cost_usd")}
        elif kind == "compute":
            mw = p("average_it_mw")
            external, internal = p("external_share", 1, 0, 1), p("internal_share", 0, 0, 1)
            if external + internal > 1 + 1e-12:
                raise ModelError("compute external_share + internal_share must be <= 1")
            available = p("availability", 1, 0, 1)
            ext_util, own_util = p("external_utilization", 1, 0, 1), p("internal_utilization", 1, 0, 1)
            billable_mwh = mw * external * ext_util * available * 8760
            busy = available * (external * ext_util + internal * own_util)
            energy_kwh = mw * 1000 * 8760 * p("pue", 1, 1) * (busy + (1 - busy) * p("idle_power_fraction", 0.15, 0, 1))
            revenue = billable_mwh * p("price_usd_per_billable_mw_hour")
            extra_da = mw * p("hardware_da_usd_per_mw_year")
            cogs = energy_kwh * p("electricity_usd_per_kwh") + mw * p("cash_overhead_usd_per_mw_year") + extra_da
            inputs = {"average_it_mw": mw, "external_share": external, "internal_share": internal,
                      "billable_mwh": billable_mwh, "electricity_kwh": energy_kwh}
    # Pre-launch R&D, capex and depreciation are intentionally NOT suppressed.
    opex, capex = p("opex_usd"), p("capex_usd") + revenue * p("capex_revenue_ratio") + extra_capex
    da = p("da_usd") + revenue * p("da_revenue_ratio") + extra_da
    # Explicit/revenue-based DA is part of COGS; special-kind DA already included.
    cogs += da - extra_da
    return {"active": active, "volume_unit": segment.get("volume_unit", "see config notes"),
            "revenue_usd": revenue, "cogs_usd": cogs,
            "gross_profit_usd": revenue - cogs, "opex_usd": opex,
            "operating_profit_usd": revenue - cogs - opex,
            "capex_usd": capex, "da_usd": da,
            "ev_sales_multiple": p("ev_sales_multiple"), "robotics_savings_usd": 0.0,
            "drivers": inputs}


COMPANY_FIELDS = {
    "name", "notes", "opening_cash_usd", "opening_debt_usd", "opening_shares",
    "segments", "corporate_opex_usd", "interest_rate", "tax_rate", "pe_multiple",
    "corporate_ev_cost_multiple", "nwc_revenue_ratio", "opening_nwc_usd",
    "debt_issued_usd", "debt_repaid_usd", "equity_raised_usd", "equity_issue_price_usd",
    "sbc_dilution_rate", "sbc_expense_usd", "stock_split", "dividends_usd", "buybacks_usd", "buyback_price_usd",
    "robotics_savings_usd", "robotics_max_cogs_share", "robotics_capex_usd", "robotics_da_usd",
    "passenger_production_capacity", "robotaxi_segment_id", "passenger_segment_id",
}


def company_forecast(company, years):
    unknown = set(company) - COMPANY_FIELDS
    if unknown:
        raise ModelError(f"unknown company fields: {sorted(unknown)}")
    if not isinstance(company.get("segments"), dict) or not company["segments"]:
        raise ModelError("company must have nonempty segments")
    base = years[0]
    cash = number(company["opening_cash_usd"], "opening_cash_usd", 0)
    debt = number(company["opening_debt_usd"], "opening_debt_usd", 0)
    shares = number(company["opening_shares"], "opening_shares", 1e-9)
    nwc = number(company.get("opening_nwc_usd", 0), "opening_nwc_usd", 0)
    states, summaries, details = {}, [], []
    funding_failed = False
    for year in years:
        def p(key, default=0, minimum=0, maximum=None):
            return parameter(company.get(key, default), year, base, key, minimum, maximum)
        rows = {}
        for key, segment in company["segments"].items():
            try:
                rows[key] = segment_forecast(segment, year, base, states.setdefault(key, {}))
            except ModelError as exc:
                raise ModelError(f"{year} / {key}: {exc}") from exc
        # One production constraint for external passenger cars plus owned fleet additions.
        if "passenger_production_capacity" in company:
            passenger_id, fleet_id = company["passenger_segment_id"], company["robotaxi_segment_id"]
            try:
                used = rows[passenger_id]["drivers"].get("external_units", 0) + rows[fleet_id]["drivers"].get("additions", 0)
            except KeyError as exc:
                raise ModelError("production constraint references unknown segment") from exc
            if used > p("passenger_production_capacity") + 1e-6:
                raise ModelError(f"{year}: passenger sales + owned fleet additions exceed production capacity")
        eligible = [key for key in rows if company["segments"][key].get("robotics_eligible", False)]
        requested_savings = p("robotics_savings_usd")
        if requested_savings and any(company["segments"][key].get("cost_includes_robotics", True) for key in eligible):
            raise ModelError("robotics savings require cost_includes_robotics=false on eligible segments")
        pool = sum(rows[key]["cogs_usd"] for key in eligible)
        savings = min(requested_savings, pool * p("robotics_max_cogs_share", 0, 0, 1))
        robot_da = p("robotics_da_usd")
        for key in eligible:
            allocated = savings * rows[key]["cogs_usd"] / pool if pool else 0
            rows[key]["cogs_usd"] -= allocated
            rows[key]["gross_profit_usd"] += allocated
            rows[key]["operating_profit_usd"] += allocated
            rows[key]["robotics_savings_usd"] = allocated
        revenue = sum(row["revenue_usd"] for row in rows.values())
        cogs = sum(row["cogs_usd"] for row in rows.values())
        gross = revenue - cogs
        sbc = p("sbc_expense_usd")
        corporate_opex = p("corporate_opex_usd") + robot_da + sbc
        operating = sum(row["operating_profit_usd"] for row in rows.values()) - corporate_opex
        new_debt, repaid = p("debt_issued_usd"), p("debt_repaid_usd")
        if repaid > debt + new_debt:
            raise ModelError(f"{year}: debt repayment exceeds available debt")
        closing_debt = debt + new_debt - repaid
        interest = (debt + closing_debt) / 2 * p("interest_rate")
        pretax = operating - interest
        tax = max(pretax, 0) * p("tax_rate", 0.21, 0, 1)
        net = pretax - tax
        da = sum(row["da_usd"] for row in rows.values()) + robot_da
        capex = sum(row["capex_usd"] for row in rows.values()) + p("robotics_capex_usd")
        closing_nwc = revenue * p("nwc_revenue_ratio", 0, 0, 1)
        delta_nwc = closing_nwc - nwc
        economic_fcf = net + da - capex - delta_nwc
        cash_fcf = economic_fcf + sbc
        raised, buybacks, dividends = p("equity_raised_usd"), p("buybacks_usd"), p("dividends_usd")
        split = p("stock_split", 1, 1e-9)
        opening_shares = shares * split
        issue_price, buyback_price = p("equity_issue_price_usd"), p("buyback_price_usd")
        if raised and not issue_price:
            raise ModelError("positive equity_raised_usd requires positive equity_issue_price_usd")
        if buybacks and not buyback_price:
            raise ModelError("positive buybacks_usd requires positive buyback_price_usd")
        issued = raised / issue_price if raised else 0
        retired = buybacks / buyback_price if buybacks else 0
        diluted = opening_shares * (1 + p("sbc_dilution_rate", 0, 0, 1)) + issued - retired
        if diluted <= 0:
            raise ModelError("buybacks cannot eliminate all outstanding shares")
        weighted = (opening_shares + diluted) / 2
        closing_cash = cash + cash_fcf + new_debt - repaid + raised - buybacks - dividends
        # A negative balance is an unfunded deficit, never silently an overdraft/financing round.
        funding_failed = funding_failed or closing_cash < 0
        ev = sum(row["revenue_usd"] * row["ev_sales_multiple"] for row in rows.values()) - corporate_opex * p("corporate_ev_cost_multiple")
        equity = ev + closing_cash - closing_debt
        pe = p("pe_multiple")
        valued = not funding_failed and equity > 0
        result = {
            "year": year, "company": company["name"], "revenue_usd": revenue,
            "cogs_usd": cogs, "gross_profit_usd": gross,
            "gross_margin": gross / revenue if revenue else None,
            "segment_opex_usd": sum(row["opex_usd"] for row in rows.values()),
            "corporate_opex_usd": corporate_opex, "operating_profit_usd": operating,
            "interest_usd": interest, "tax_usd": tax, "net_income_usd": net,
            "da_usd": da, "capex_usd": capex, "delta_nwc_usd": delta_nwc,
            "economic_fcf_usd": economic_fcf, "cash_fcf_usd": cash_fcf,
            "sbc_expense_usd": sbc, "cash_usd": closing_cash, "debt_usd": closing_debt,
            "funding_gap_usd": max(-closing_cash, 0), "funding_failed": funding_failed,
            "shares": diluted, "weighted_average_shares": weighted,
            "eps_usd": net / weighted, "year_end_share_earnings_usd": net / diluted,
            "pe_multiple": pe, "sotp_enterprise_value_usd": ev,
            "sotp_equity_value_usd": equity,
            "price_pe_usd": net * pe / diluted if net > 0 and not funding_failed else None,
            "price_sotp_usd": equity / diluted if valued else None,
            "robotics_savings_usd": savings,
            "robotics_savings_requested_usd": requested_savings,
        }
        for key, row in rows.items():
            row["gross_margin"] = row["gross_profit_usd"] / row["revenue_usd"] if row["revenue_usd"] else None
            row["operating_margin"] = row["operating_profit_usd"] / row["revenue_usd"] if row["revenue_usd"] else None
            details.append({"year": year, "company": company["name"], "segment": key,
                            "segment_name": company["segments"][key]["name"], **row})
        summaries.append(result)
        cash, debt, shares, nwc = closing_cash, closing_debt, diluted, closing_nwc
    return summaries, details


def merger_forecast(config, summaries, years):
    """Pro-forma annual snapshot, not a second funded post-deal cash-flow simulation."""
    if not config.get("enabled", False):
        return []
    allowed = {"enabled", "start_year", "acquirer", "target", "target_exchange_ratio",
               "new_shares", "transaction_cost_usd", "net_operating_synergy_usd",
               "tax_rate", "pe_multiple", "synergy_ev_multiple", "intercompany_revenue_usd",
               "intercompany_ev_elimination_usd", "notes"}
    if set(config) - allowed:
        raise ModelError("unknown merger fields")
    acquirer, target = config["acquirer"], config["target"]
    if acquirer == target or any(key not in summaries for key in [acquirer, target]):
        raise ModelError("merger requires two distinct known companies")
    start = number(config.get("start_year", years[0]), "merger.start_year", years[0])
    if not start.is_integer():
        raise ModelError("merger.start_year must be integer")
    combined = []
    for index, year in enumerate(years):
        if year < start:
            continue
        a, b = summaries[acquirer][index], summaries[target][index]
        def p(key, default=0, minimum=0, maximum=None):
            return parameter(config.get(key, default), year, years[0], "merger." + key, minimum, maximum)
        ratio = p("target_exchange_ratio", 1, 1e-9)
        eliminated = p("intercompany_revenue_usd")
        if eliminated > a["revenue_usd"] + b["revenue_usd"]:
            raise ModelError("merger revenue elimination exceeds combined revenue")
        if eliminated and "intercompany_ev_elimination_usd" not in config:
            raise ModelError("revenue elimination requires explicit intercompany_ev_elimination_usd")
        shares = a["shares"] + b["shares"] * ratio + p("new_shares")
        synergy = p("net_operating_synergy_usd", 0, None)
        cost = p("transaction_cost_usd") if year == start else 0
        tax_rate = p("tax_rate", 0.21, 0, 1)
        # No tax shield assumed for a negative incremental result.
        delta = synergy - cost
        delta_net = delta - max(delta, 0) * tax_rate
        net = a["net_income_usd"] + b["net_income_usd"] + delta_net
        ev = a["sotp_enterprise_value_usd"] + b["sotp_enterprise_value_usd"] - p("intercompany_ev_elimination_usd") + synergy * p("synergy_ev_multiple")
        equity = ev + a["cash_usd"] + b["cash_usd"] - a["debt_usd"] - b["debt_usd"] - cost
        funded = not (a["funding_failed"] or b["funding_failed"]) and a["cash_usd"] + b["cash_usd"] >= cost
        combined.append({"year": year, "company": f"{acquirer}+{target} (pro forma)",
                         "revenue_usd": a["revenue_usd"] + b["revenue_usd"] - eliminated,
                         "intercompany_revenue_eliminated_usd": eliminated,
                         "operating_profit_usd": a["operating_profit_usd"] + b["operating_profit_usd"] + delta,
                         "net_income_usd": net, "shares": shares,
                         "target_exchange_ratio": ratio, "net_operating_synergy_usd": synergy,
                         "transaction_cost_usd": cost, "sotp_equity_value_usd": equity,
                         "price_pe_usd": net * p("pe_multiple") / shares if net > 0 and funded else None,
                         "price_sotp_usd": equity / shares if equity > 0 and funded else None,
                         "funding_failed": not funded})
    return combined


def forecast(config, scenario="base"):
    if not isinstance(config, dict):
        raise ModelError("config must be a JSON object")
    if set(config) - {"schema_version", "metadata", "years", "companies", "merger", "scenarios"}:
        raise ModelError("unknown top-level config fields")
    resolved = resolve(config, scenario)
    if resolved.get("schema_version") != 1:
        raise ModelError("schema_version must be 1")
    years = resolved.get("years", [])
    if not years or any(isinstance(y, bool) or not isinstance(y, int) for y in years):
        raise ModelError("years must be a nonempty list of integer years")
    if years != list(range(years[0], years[-1] + 1)) or len(years) > 50:
        raise ModelError("years must be consecutive ascending years, max 50")
    companies = resolved.get("companies")
    if not isinstance(companies, dict) or not companies:
        raise ModelError("companies must be a nonempty object")
    summaries, details = {}, []
    for key, company in companies.items():
        try:
            summaries[key], segments = company_forecast(company, years)
        except (KeyError, OverflowError) as exc:
            raise ModelError(f"{key}: missing field or overflow: {exc}") from exc
        except ModelError as exc:
            raise ModelError(f"{key}: {exc}") from exc
        for row in summaries[key] + segments:
            row["scenario"] = scenario
            row["company_id"] = key
        details.extend(segments)
    merged = merger_forecast(resolved.get("merger", {}), summaries, years)
    for row in merged:
        row["scenario"] = scenario
    warnings = []
    if resolved.get("metadata", {}).get("input_status") != "calibrated":
        warnings.append("示例假設，未校準公司財報；輸出為情境計算，不是公司指引。")
    if any(row["funding_failed"] for rows in summaries.values() for row in rows):
        warnings.append("有資金缺口：股價欄停用，後續營運僅保留未融資的壓力試算。")
    if any(row["robotics_savings_requested_usd"] > row["robotics_savings_usd"] + 1e-6 for rows in summaries.values() for row in rows):
        warnings.append("機器人節省超過可改善成本上限，已按 robotics_max_cogs_share 截斷。")
    if any(row["drivers"].get("capacity_limited") for row in details):
        warnings.append("部分對外銷量已受 capacity_units 限制。")
    return {"scenario": scenario, "metadata": resolved.get("metadata", {}),
            "companies": summaries, "segments": details, "merger": merged,
            "warnings": warnings, "resolved_assumptions": resolved}


def write_csv(path, rows):
    if not rows:
        return
    fields = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: json.dumps(value, ensure_ascii=False, allow_nan=False) if isinstance(value, (dict, list)) else value for key, value in row.items()})


def money(value, scale=1):
    return "N/A" if value is None else f"{value / scale:,.2f}"


def summary_markdown(results):
    lines = ["# Tesla／SpaceX 年度情境計算", "", "金額：十億美元，股價：美元／股。空值表示不適用或存在資金缺口。", ""]
    for result in results:
        lines += [f"## {result['scenario']}", "", *result["warnings"], "",
                  "| 公司 | 年度 | 營收 | 毛利 | 營業利益 | 淨利 | 經濟 FCF | P/E 股價 | SOTP 股價 |",
                  "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
        for rows in result["companies"].values():
            for row in rows:
                values = [row["company"], str(row["year"])] + [money(row[key], 1e9) for key in ["revenue_usd", "gross_profit_usd", "operating_profit_usd", "net_income_usd", "economic_fcf_usd"]] + [money(row[key]) for key in ["price_pe_usd", "price_sotp_usd"]]
                lines.append("| " + " | ".join(values) + " |")
        if result["merger"]:
            lines += ["", "### 合併年度快照（pro forma）", "", "| 年度 | 營收 | 淨利 | P/E 股價 | SOTP 股價 |", "| --- | ---: | ---: | ---: | ---: |"]
            for row in result["merger"]:
                lines.append(f"| {row['year']} | {money(row['revenue_usd'], 1e9)} | {money(row['net_income_usd'], 1e9)} | {money(row['price_pe_usd'])} | {money(row['price_sotp_usd'])} |")
    lines += ["", "每業務細項與有效輸入請見 segments.csv、results.json。合併為每年獨立的假想快照，沒有交易後資產負債遞推。", ""]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path(__file__).parent / "configs" / "example.json")
    parser.add_argument("--scenario", default="all", help="all or a named JSON scenario")
    parser.add_argument("--set", action="append", default=[], metavar="PATH=JSON", help="override after scenario, repeatable")
    parser.add_argument("--out", type=Path, default=Path("forecast_output"))
    args = parser.parse_args(argv)
    try:
        raw = args.config.read_bytes()
        config = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ModelError(f"invalid JSON number {value}")))
        if not isinstance(config, dict):
            raise ModelError("config must be a JSON object")
        scenarios = list(config.get("scenarios", {})) if args.scenario == "all" else [args.scenario]
        if not scenarios:
            raise ModelError("at least one scenario is required")
        results = []
        for scenario in scenarios:
            effective = resolve(config, scenario)
            for override in args.set:
                path, separator, value = override.partition("=")
                if not separator:
                    raise ModelError("--set needs PATH=JSON")
                patch(effective, path, json.loads(value))
            effective["scenarios"] = {scenario: {}}
            results.append(forecast(effective, scenario))
        # All scenarios validated before writing; never emit partial successful forecasts.
        payload = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
                   "input_sha256": hashlib.sha256(raw).hexdigest(), "overrides": args.set,
                   "results": results}
        serialized = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "results.json").write_text(serialized + "\n", encoding="utf-8")
        write_csv(args.out / "companies.csv", [row for result in results for rows in result["companies"].values() for row in rows])
        write_csv(args.out / "segments.csv", [row for result in results for row in result["segments"]])
        merger_rows = [row for result in results for row in result["merger"]]
        if merger_rows:
            write_csv(args.out / "merger.csv", merger_rows)
        else:
            (args.out / "merger.csv").unlink(missing_ok=True)
        report = summary_markdown(results)
        (args.out / "summary.md").write_text(report, encoding="utf-8")
        print(report)
        print(f"輸出：{args.out.resolve()}")
        return 0
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(f"輸入錯誤：{exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
