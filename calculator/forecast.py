#!/usr/bin/env python3
"""Driver-based Tesla/SpaceX scenario calculator. Python 3.10+, stdlib only.

USD throughout. Sample inputs are illustrative assumptions, not reported actuals.
Public API: forecast(config, scenario='base') -> JSON-serializable dictionary.
"""
from __future__ import annotations

import argparse
import copy
import csv
import calendar
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
    "automation_eligible_cash_cost_ratio",
}
KIND_FIELDS = {
    "unit": {"units", "capacity_units", "price_usd", "unit_cost_usd"},
    "subscription": {"average_subscribers", "monthly_price_usd", "monthly_cost_usd",
                     "opening_subscribers", "additions_source_segment_id", "new_vehicle_attach_rate", "annual_churn_rate"},
    "robotaxi": {"opening_fleet", "additions", "retirements", "vehicle_cost_usd",
                 "depreciation_usd_per_vehicle_year", "km_per_vehicle_day", "operating_days",
                 "paid_km_share", "fare_usd_per_paid_km", "cash_cost_usd_per_total_km",
                 "fixed_cash_usd_per_vehicle_year", "fleet_capacity", "production_ramp"},
    "robot_fleet": {"opening_fleet", "production_units", "retirements", "fleet_capacity",
                    "unit_manufacturing_cost_usd", "opening_net_book_value_usd",
                    "depreciation_usd_per_robot_year", "internal_demand_robots",
                    "internal_avoided_cost_usd_per_robot_year", "rental_utilization",
                    "rental_demand_robots", "monthly_rent_usd", "cash_cost_usd_per_robot_year",
                    "production_quarter_units"},
    "compute": {"capacity_ramp", "average_it_mw", "external_share", "internal_share", "external_utilization",
                "internal_utilization", "availability", "price_usd_per_billable_mw_hour",
                "electricity_usd_per_kwh", "pue", "idle_power_fraction",
                "cash_overhead_usd_per_mw_year", "hardware_da_usd_per_mw_year"},
}
KIND_FIELDS["orbital_compute"] = (KIND_FIELDS["compute"] - {
    "average_it_mw", "hardware_da_usd_per_mw_year"
}) | {
    "opening_it_mw", "opening_inventory_mw", "opening_net_book_value_usd",
    "manufactured_it_mw", "deployment_limit_mw", "commissioning_yield",
    "commissioning_start_month", "hardware_cost_usd_per_mw",
    "deployment_cost_usd_per_mw", "asset_life_years", "launch_network", "manufacture_to_launch_capacity",
}
for _kind in ("robot_fleet", "robotaxi", "orbital_compute"):
    KIND_FIELDS[_kind] |= {"service_life_years", "depreciation_life_years"}
for _kind in ("robot_fleet", "robotaxi"):
    KIND_FIELDS[_kind] |= {"replace_retired"}


def asset_rollforward(state, year, new_assets, service_life, da_life,
                      opening_units=0, opening_unit_cost=0, replace=False,
                      replacement_unit_cost=0):
    """Vintage ledger: historical cost, in-service exposure, expiry and replacement.

    New assets are (quantity, historical unit cost, commissioning month). Monthly
    midpoints reproduce a uniform annual ramp without treating year-end capacity
    as full-year output. Lifetimes are fixed at each vintage's commissioning.
    """
    service_life = number(service_life, "service_life_years", 1)
    da_life = number(da_life, "depreciation_life_years", 1e-9)
    if not isinstance(replace, bool):
        raise ModelError("replace_retired must be boolean")
    if "asset_vintages" not in state:
        state["asset_vintages"] = ([{"units": opening_units, "cost": opening_unit_cost,
            "born": year, "life": service_life, "da_life": da_life}] if opening_units else [])
    vintages = state["asset_vintages"]
    opening = sum(v["units"] for v in vintages if v["born"] <= year and v["born"] + v["life"] >= year)
    for units, cost, month in new_assets:
        if units:
            vintages.append({"units": units, "cost": cost, "born": year + (month - .5) / 12,
                             "life": service_life, "da_life": da_life})
    expired = [v for v in vintages if year <= v["born"] + v["life"] < year + 1]
    replacements = sum(v["units"] for v in expired) if replace else 0
    if replace:
        for v in expired:
            vintages.append({"units": v["units"], "cost": replacement_unit_cost,
                             "born": v["born"] + v["life"],
                             "life": service_life, "da_life": da_life})
    average = depreciation = writeoff = book = closing = pending = 0.0
    for v in vintages:
        born, dead = v["born"], v["born"] + v["life"]
        value = v["units"] * v["cost"]
        average += v["units"] * max(min(year + 1, dead) - max(year, born), 0)
        depreciation += value / v["da_life"] * max(min(year + 1, dead, born + v["da_life"]) - max(year, born), 0)
        if year <= dead < year + 1:
            writeoff += value * max(1 - v["life"] / v["da_life"], 0)
        if dead >= year + 1:
            if born < year + 1:
                closing += v["units"]
            else:
                pending += v["units"]
            book += value * max(1 - max(year + 1 - born, 0) / v["da_life"], 0)
    state["asset_vintages"] = [v for v in vintages if v["born"] + v["life"] >= year + 1]
    return {"opening": opening, "closing": closing, "average": average,
            "retirements": sum(v["units"] for v in expired), "replacements": replacements,
            "da": depreciation + writeoff, "writeoff": writeoff, "book": book, "pending": pending}


def robotaxi_production(ramp, year, base_year):
    """Gross manufactured vehicles by month; commissioning can occur next year."""
    allowed = {"annual_capacity_units", "full_rate_year", "full_rate_month",
               "initial_rate_fraction", "deployment_delay_months"}
    if not isinstance(ramp, dict) or set(ramp) - allowed:
        raise ModelError("invalid production_ramp fields")
    capacity = parameter(ramp.get("annual_capacity_units", 0), year, base_year, "annual_capacity_units")
    full_year = number(ramp["full_rate_year"], "full_rate_year")
    full_month = number(ramp["full_rate_month"], "full_rate_month", 1, 12)
    delay = number(ramp.get("deployment_delay_months", 0), "deployment_delay_months", 0, 12)
    if not full_year.is_integer() or not full_month.is_integer() or not delay.is_integer():
        raise ModelError("production ramp dates and delay must be integer years/months")
    initial = number(ramp.get("initial_rate_fraction", 0), "initial_rate_fraction", 0, 1)
    duration = (full_year - base_year) * 12 + full_month - 1
    monthly = []
    for month in range(1, 13):
        elapsed = (year - base_year) * 12 + month - .5
        fraction = initial + (1 - initial) * min(max(elapsed / duration, 0), 1) if duration > 0 else 1
        monthly.append((capacity * fraction / 12, month + delay))
    return monthly, capacity


def orbital_launch_capacity(network, year, base_year):
    """Whole flights, phased pads, shared site caps, and competing missions.

    Forecast dates and environmental envelopes are conditional planning inputs,
    not a statement that a site currently holds an operating license.
    """
    allowed = {"payload_tonnes", "it_kw_per_tonne", "payload_efficiency", "ai_flight_share", "sites", "fleet_rate_start", "fleet_rate_end", "capacity_upgrade"}
    if set(network) - allowed or not isinstance(network.get("sites"), list):
        raise ModelError("invalid launch_network fields/sites")
    def p(key, default=0, minimum=0, maximum=None):
        return parameter(network.get(key, default), year, base_year, key, minimum, maximum)
    mw_per_flight = p("payload_tonnes") * p("it_kw_per_tonne") * p("payload_efficiency", 1, 0, 1) / 1000
    per_flight_monthly = [mw_per_flight] * 12
    if "capacity_upgrade" in network:
        upgrade = network["capacity_upgrade"]
        if set(upgrade) != {"year", "month", "net_it_mw_per_flight"}:
            raise ModelError("capacity_upgrade requires year, month, net_it_mw_per_flight")
        uy = number(upgrade["year"], "upgrade year")
        um = number(upgrade["month"], "upgrade month", 1, 12)
        if not uy.is_integer() or not um.is_integer():
            raise ModelError("capacity upgrade requires integer year/month")
        net_mw = number(upgrade["net_it_mw_per_flight"], "net_it_mw_per_flight", 0)
        # An explicit net-MW target already includes payload/packing effects;
        # never apply payload_efficiency a second time.
        per_flight_monthly = [net_mw if (year, month) >= (uy, um) else mw_per_flight
                              for month in range(1, 13)]
    ai_share = p("ai_flight_share", 1, 0, 1)
    monthly_site_slots = [0] * 12
    site_details, ids = [], set()
    for site in network["sites"]:
        if set(site) - {"id", "pads", "annual_site_limit", "limit_status", "notes"} or site["id"] in ids:
            raise ModelError("invalid/duplicate launch site")
        ids.add(site["id"])
        limit = parameter(site["annual_site_limit"], year, base_year, "annual_site_limit")
        pad_details, pad_ids = [], set()
        for pad in site["pads"]:
            if set(pad) - {"id", "online_year", "online_month", "flights_per_year", "flights_per_year_start", "flights_per_year_end", "planned_pads", "notes"}:
                raise ModelError("unknown launch pad field")
            if pad["id"] in pad_ids: raise ModelError("duplicate launch pad")
            pad_ids.add(pad["id"])
            oy=number(pad["online_year"], "online_year", base_year-100)
            om=number(pad["online_month"], "online_month", 1, 12)
            if not oy.is_integer() or not om.is_integer():
                raise ModelError("launch pad activation must use integer year/month")
            ramp_keys={"flights_per_year_start","flights_per_year_end"}
            if ramp_keys & set(pad):
                if not ramp_keys <= set(pad) or "flights_per_year" in pad:
                    raise ModelError("pad ramp requires paired start/end and no constant rate")
                start=parameter(pad["flights_per_year_start"],year,base_year,"pad_rate_start")
                end=parameter(pad["flights_per_year_end"],year,base_year,"pad_rate_end")
            else:
                start=end=parameter(pad["flights_per_year"],year,base_year,"flights_per_year")
            monthly=[(start+(end-start)*(m-.5)/12)/12 if (year,m)>=(oy,om) else 0.0 for m in range(1,13)]
            pad_details.append({"pad":pad["id"],"online_year":int(oy),"online_month":int(om),
                "rate_start":start,"rate_end":end,"active_months":sum((year,m)>=(oy,om) for m in range(1,13)),
                "raw_monthly_flights":monthly,"raw_annual_flights":sum(monthly)})
        raw_monthly=[sum(p["raw_monthly_flights"][i] for p in pad_details) for i in range(12)]
        monthly, cumulative, previous = [], 0.0, 0
        for i, raw in enumerate(raw_monthly):
            # Shared site envelope is a monthly-prorated planning rate; unused
            # earlier capacity is not banked as extra later-month throughput.
            cumulative+=min(raw,limit/12)
            total=math.floor(cumulative+1e-9)
            monthly.append(total-previous)
            monthly_site_slots[i]+=total-previous
            previous=total
        site_details.append({"site":site["id"],"available_flights":previous,
            "raw_annual_flights":sum(raw_monthly),"raw_monthly_flights":raw_monthly,
            "monthly_available_flights":monthly,"annual_site_limit":limit,"pads":pad_details,
            "active_pad_months":sum(p["active_months"] for p in pad_details),
            "limit_status":site.get("limit_status","model_assumption")})
    infrastructure_slots = sum(x["available_flights"] for x in site_details)
    available = infrastructure_slots
    cumulative, allocated, monthly_mw = 0, 0, []
    for i, slots in enumerate(monthly_site_slots):
        cumulative+=slots
        ai=math.floor(cumulative*ai_share+1e-9)
        monthly_mw.append((ai-allocated)*per_flight_monthly[i])
        allocated=ai
    fleet_drivers = {}
    if "fleet_rate_start" in network or "fleet_rate_end" in network:
        if not {"fleet_rate_start", "fleet_rate_end"} <= set(network):
            raise ModelError("fleet ramp requires both start and end annualized rates")
        start, end = p("fleet_rate_start"), p("fleet_rate_end")
        cumulative, available, allocated = 0.0, 0, 0
        monthly_mw = []
        for i, site_slots in enumerate(monthly_site_slots):
            # This is one fleet-wide ramp, never one target per pad.
            rate = start + (end - start) * (i + .5) / 12
            cumulative += min(site_slots, rate / 12)
            flights = math.floor(cumulative + 1e-9)
            ai = math.floor(flights * ai_share + 1e-9)
            monthly_mw.append((ai - allocated) * per_flight_monthly[i])
            available, allocated = flights, ai
        fleet_drivers = {"fleet_rate_start": start, "fleet_rate_end": end}
    return {"infrastructure_site_slots": infrastructure_slots,
            "site_detail_scope": "per-pad capacity after shared site limits; optional legacy fleet cap applied only when configured",
            "raw_pad_capacity_flights":sum(x["raw_annual_flights"] for x in site_details),
            "monthly_available_starship_flights":monthly_site_slots,
            **fleet_drivers, "monthly_launch_capacity_mw": monthly_mw,
            "mw_per_ai_flight": per_flight_monthly[-1],
            "mw_per_ai_flight_start": per_flight_monthly[0],
            "monthly_mw_per_ai_flight": per_flight_monthly,
            "available_starship_flights": available,
            "allocated_ai_flights": allocated,
            "annual_launch_capacity_mw": sum(monthly_mw), "launch_sites": site_details}


def ground_capacity_rollforward(ramp, year, base_year, state):
    """Net capacity targets with monthly commissioning and funded asset renewal."""
    allowed = {"opening_it_mw", "year_end_it_mw", "hardware_cost_usd_per_mw",
               "infrastructure_cost_usd_per_mw", "hardware_life_years",
               "infrastructure_life_years", "monthly_addition_weights"}
    if not isinstance(ramp, dict) or set(ramp) - allowed:
        raise ModelError("invalid ground capacity_ramp fields")
    def p(key, default=0, minimum=0):
        return parameter(ramp.get(key, default), year, base_year, key, minimum)
    opening = state.get("ground_closing_mw", p("opening_it_mw"))
    target = p("year_end_it_mw")
    if target < opening - 1e-8:
        raise ModelError("ground capacity target cannot decline; explicit decommissioning is not implemented")
    additions = max(target - opening, 0)
    weights = ramp.get("monthly_addition_weights", {}).get(str(year), [1 / 12] * 12)
    if not isinstance(weights, list) or len(weights) != 12:
        raise ModelError("monthly_addition_weights needs 12 weights")
    weights = [number(w, "monthly_addition_weight", 0, 1) for w in weights]
    if not math.isclose(sum(weights), 1, abs_tol=1e-9):
        raise ModelError("monthly_addition_weights must sum to 1")
    costs, ledgers = {}, {}
    for asset, default_life in (("hardware", 4), ("infrastructure", 20)):
        cost = p(asset + "_cost_usd_per_mw")
        life = p(asset + "_life_years", default_life, 1)
        ledger = asset_rollforward(state.setdefault("ground_" + asset, {}), year,
            [(additions * w, cost, m) for m, w in enumerate(weights, 1)], life, life,
            opening_units=p("opening_it_mw"),
            opening_unit_cost=parameter(ramp.get(asset + "_cost_usd_per_mw", 0), base_year, base_year),
            replace=True, replacement_unit_cost=cost)
        costs[asset] = (additions + ledger["replacements"]) * cost
        ledgers[asset] = ledger
    hardware, infra = ledgers["hardware"], ledgers["infrastructure"]
    state["ground_closing_mw"] = hardware["closing"]
    monthly_adds = [additions * w for w in weights]
    monthly_average = [opening + sum(monthly_adds[:m]) + monthly_adds[m] / 2 for m in range(12)]
    drivers = {"opening_it_mw": opening, "year_end_it_mw": hardware["closing"],
        "commissioned_new_it_mw": additions, "average_it_mw": hardware["average"],
        "monthly_new_it_mw": monthly_adds, "monthly_average_it_mw": monthly_average,
        "retired_hardware_mw": hardware["retirements"],
        "replacement_hardware_mw": hardware["replacements"],
        "replacement_infrastructure_mw": infra["replacements"],
        "hardware_capex_usd": costs["hardware"], "infrastructure_capex_usd": costs["infrastructure"],
        "hardware_da_usd": hardware["da"], "infrastructure_da_usd": infra["da"],
        "closing_net_book_value_usd": hardware["book"] + infra["book"]}
    return drivers, sum(costs.values()), hardware["da"] + infra["da"]


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
            subscriber_drivers = {}
            if "additions_source_segment_id" in segment:
                if "average_subscribers" in segment:
                    raise ModelError("linked subscriptions cannot also set average_subscribers")
                opening = state.get("subscribers", p("opening_subscribers"))
                additions = number(state.get("new_units"), "subscription source units", 0) * p("new_vehicle_attach_rate", 1, 0, 1)
                cancellations = opening * p("annual_churn_rate", 0, 0, 1)
                closing = opening + additions - cancellations
                subscribers = (opening + closing) / 2
                state["subscribers"] = closing
                subscriber_drivers = {"opening_subscribers": opening, "new_subscribers": additions,
                                      "cancellations": cancellations, "closing_subscribers": closing}
            revenue, cogs = subscribers * price * 12, subscribers * cost * 12
            inputs = {"average_subscribers": subscribers, "monthly_price_usd": price, "monthly_cost_usd": cost, **subscriber_drivers}
        elif kind == "robotaxi":
            opening = state.setdefault("fleet", number(segment.get("opening_fleet", 0), "opening_fleet", 0))
            adds, retirements = p("additions"), p("retirements")
            production, factory_capacity = None, None
            if "production_ramp" in segment:
                if "additions" in segment or segment.get("replace_retired", False) or "service_life_years" not in segment:
                    raise ModelError("production_ramp requires service_life_years, no additions, and replace_retired=false; gross production already funds replacement")
                production, factory_capacity = robotaxi_production(segment["production_ramp"], year, base_year)
                adds = sum(q for q, month in production)
            if retirements > opening:
                raise ModelError("robotaxi retirements cannot exceed opening fleet")
            closing = opening + adds - retirements
            if "service_life_years" not in segment and closing > p("fleet_capacity", closing):
                raise ModelError("robotaxi closing fleet exceeds fleet_capacity")
            average = (opening + closing) / 2
            total_km = average * p("km_per_vehicle_day") * p("operating_days", 365, 0, 366)
            paid_km = total_km * p("paid_km_share", 0.6, 0, 1)
            revenue = paid_km * p("fare_usd_per_paid_km")
            extra_da = average * p("depreciation_usd_per_vehicle_year")
            cogs = total_km * p("cash_cost_usd_per_total_km") + average * p("fixed_cash_usd_per_vehicle_year") + extra_da
            extra_capex = adds * p("vehicle_cost_usd")
            lifecycle = None
            if "service_life_years" in segment:
                if retirements:
                    raise ModelError("use automatic service-life retirements, not manual retirements, with vintage accounting")
                lifecycle = asset_rollforward(state, year,
                    [(q, p("vehicle_cost_usd"), month) for q, month in production] if production is not None else
                    [(adds / 12, p("vehicle_cost_usd"), month) for month in range(1, 13)],
                    p("service_life_years", 6, 1), p("depreciation_life_years", 6, 1e-9),
                    opening_units=opening, opening_unit_cost=p("vehicle_cost_usd"),
                    replace=segment.get("replace_retired", False), replacement_unit_cost=p("vehicle_cost_usd"))
                opening, closing, average = lifecycle["opening"], lifecycle["closing"], lifecycle["average"]
                retirements = lifecycle["retirements"]
                adds += lifecycle["replacements"]
                if closing > p("fleet_capacity", closing) + 1e-6:
                    raise ModelError("robotaxi closing fleet exceeds fleet_capacity")
                total_km = average * p("km_per_vehicle_day") * p("operating_days", 365, 0, 366)
                paid_km = total_km * p("paid_km_share", .6, 0, 1)
                revenue = paid_km * p("fare_usd_per_paid_km")
                extra_da = lifecycle["da"]
                extra_capex = adds * p("vehicle_cost_usd")
                cogs = total_km * p("cash_cost_usd_per_total_km") + average * p("fixed_cash_usd_per_vehicle_year") + extra_da
            state["fleet"] = closing
            inputs = {"opening_fleet": opening, "additions": adds, "retirements": retirements,
                      "closing_fleet": closing, "average_fleet": average, "total_km": total_km,
                      "paid_km": paid_km, "vehicle_cost_usd": p("vehicle_cost_usd")}
            if lifecycle:
                inputs.update(replacement_units=lifecycle["replacements"],
                              closing_net_book_value_usd=lifecycle["book"], retirement_writeoff_usd=lifecycle["writeoff"])
            if production is not None:
                inputs.update(manufactured_units=adds, annual_factory_capacity_units=factory_capacity,
                              production_months=[{"production_month": int(month - segment["production_ramp"].get("deployment_delay_months", 0)),
                                                  "units": q} for q, month in production],
                              pending_deployment_units=lifecycle["pending"],
                              additions=closing - opening + retirements)
        elif kind == "robot_fleet":
            opening = state.setdefault("fleet", number(segment.get("opening_fleet", 0), "opening_fleet", 0))
            production, retirements = p("production_units"), p("retirements")
            quarter_profiles = segment.get("production_quarter_units", {})
            if not isinstance(quarter_profiles, dict):
                raise ModelError("production_quarter_units must be a year-keyed object")
            monthly_production = [production / 12] * 12
            if str(year) in quarter_profiles:
                profile = quarter_profiles[str(year)]
                if not isinstance(profile, list) or len(profile) != 4:
                    raise ModelError("production_quarter_units requires four quarterly quantities")
                quarters = [number(q, "production_quarter_units", 0) for q in profile]
                if not math.isclose(sum(quarters), production, rel_tol=1e-10, abs_tol=1e-6):
                    raise ModelError("quarterly production must sum to annual production_units")
                if "service_life_years" not in segment:
                    raise ModelError("quarterly production requires vintage accounting")
                monthly_production = [q / 3 for q in quarters for _ in range(3)]
            cost = p("unit_manufacturing_cost_usd")
            if retirements > opening:
                raise ModelError("robot retirements cannot exceed opening fleet")
            closing = opening + production - retirements
            if "service_life_years" not in segment and closing > p("fleet_capacity", closing):
                raise ModelError("robot closing fleet exceeds fleet_capacity")
            average = (opening + closing) / 2
            demand = p("internal_demand_robots")
            internal = min(average, demand)
            rentable = max(average - internal, 0)
            rented = min(rentable * p("rental_utilization", 0, 0, 1), p("rental_demand_robots", rentable))
            opening_book = state.setdefault("robot_book", number(segment.get("opening_net_book_value_usd", opening * cost), "opening_net_book_value_usd", 0))
            retired_book = opening_book * retirements / opening if opening else 0
            extra_capex = production * cost
            book_before_da = opening_book - retired_book + extra_capex
            depreciation = min(book_before_da, average * p("depreciation_usd_per_robot_year"))
            extra_da = depreciation + retired_book
            state["robot_book"] = book_before_da - depreciation
            state["fleet"] = closing
            replacements = 0
            if "service_life_years" in segment:
                if retirements:
                    raise ModelError("use automatic service-life retirements, not manual retirements, with vintage accounting")
                lifecycle = asset_rollforward(state, year,
                    [(q, cost, month) for month, q in enumerate(monthly_production, 1)],
                    p("service_life_years", 5, 1), p("depreciation_life_years", 5, 1e-9),
                    opening_units=opening, opening_unit_cost=opening_book / opening if opening else cost,
                    replace=segment.get("replace_retired", False), replacement_unit_cost=cost)
                opening, closing, average = lifecycle["opening"], lifecycle["closing"], lifecycle["average"]
                retirements, replacements = lifecycle["retirements"], lifecycle["replacements"]
                if closing > p("fleet_capacity", closing) + 1e-6:
                    raise ModelError("robot closing fleet exceeds fleet_capacity")
                internal = min(average, demand)
                rentable = max(average - internal, 0)
                rented = min(rentable * p("rental_utilization", 0, 0, 1), p("rental_demand_robots", rentable))
                extra_capex = (production + replacements) * cost
                extra_da, retired_book = lifecycle["da"], lifecycle["writeoff"]
                state.update(robot_book=lifecycle["book"], fleet=closing)
            revenue = rented * p("monthly_rent_usd") * 12
            # Every retained robot incurs operating costs, even if idle or used internally.
            cogs = average * p("cash_cost_usd_per_robot_year") + extra_da
            inputs = {"opening_fleet": opening, "production_units": production,
                      "replacement_units": replacements, "total_manufactured_units": production + replacements,
                      "production_quarter_units": [sum(monthly_production[i:i+3]) for i in range(0, 12, 3)],
                      "retirements": retirements, "closing_fleet": closing,
                      "average_fleet": average, "average_internal_robots": internal,
                      "average_rentable_robots": rentable, "average_rented_robots": rented,
                      "average_idle_robots": rentable - rented,
                      "year_end_internal_robots": min(closing, demand),
                      "year_end_rentable_robots": max(closing - demand, 0),
                      "internal_savings_requested_usd": internal * p("internal_avoided_cost_usd_per_robot_year"),
                      "unit_manufacturing_cost_usd": cost, "monthly_rent_usd": p("monthly_rent_usd"),
                      "closing_net_book_value_usd": state["robot_book"],
                      "retirement_writeoff_usd": retired_book}
        elif kind in ("compute", "orbital_compute"):
            orbital_drivers = {}
            if kind == "orbital_compute":
                opening = state.setdefault("commissioned_mw", p("opening_it_mw"))
                inventory = state.setdefault("inventory_mw", p("opening_inventory_mw"))
                matched_manufacture = segment.get("manufacture_to_launch_capacity", False)
                if not isinstance(matched_manufacture, bool):
                    raise ModelError("manufacture_to_launch_capacity must be boolean")
                if matched_manufacture and ("manufactured_it_mw" in segment or "launch_network" not in segment):
                    raise ModelError("launch-matched manufacture requires launch_network and no manufactured_it_mw")
                produced = p("manufactured_it_mw")
                deployment = min(inventory + produced, p("deployment_limit_mw", inventory + produced))
                launch_drivers = {}
                deployed_monthly = None
                commissioned = deployment * p("commissioning_yield", 1, 0, 1)
                month = p("commissioning_start_month", 10, 1, 12)
                if not month.is_integer():
                    raise ModelError("commissioning_start_month must be an integer from 1 to 12")
                if "launch_network" in segment:
                    launch_drivers = orbital_launch_capacity(segment["launch_network"], year, base_year)
                    if "service_life_years" not in segment:
                        raise ModelError("launch_network requires vintage asset accounting")
                    # Manufacture across the configured months; do not carry a
                    # missed launch slot forward or deploy inventory before it exists.
                    available_inventory = inventory
                    remaining_limit = p("deployment_limit_mw", sum(launch_drivers["monthly_launch_capacity_mw"]) if matched_manufacture else inventory + produced)
                    deployed_monthly = []
                    manufactured_monthly = []
                    for m in range(1, 13):
                        if matched_manufacture:
                            target = min(remaining_limit, launch_drivers["monthly_launch_capacity_mw"][m - 1]) if m >= month else 0
                            new_hardware = max(target - available_inventory, 0)
                            produced += new_hardware
                        else:
                            new_hardware = produced / (13 - month) if m >= month else 0
                        available_inventory += new_hardware
                        manufactured_monthly.append(new_hardware)
                        deployed = (min(available_inventory, remaining_limit,
                                        launch_drivers["monthly_launch_capacity_mw"][m - 1]) if m >= month else 0)
                        deployed_monthly.append(deployed)
                        available_inventory -= deployed
                        remaining_limit -= deployed
                    deployment = sum(deployed_monthly)
                    commissioned = deployment * p("commissioning_yield", 1, 0, 1)
                    launch_drivers["deployed_monthly_mw"] = deployed_monthly
                    launch_drivers["manufactured_monthly_mw"] = manufactured_monthly
                    launch_drivers["manufacture_to_launch_capacity"] = matched_manufacture
                closing = opening + commissioned
                # New capacity ramps linearly from zero across the remaining months.
                # October start -> 3/12 of a year x 1/2 average of new end-year MW.
                mw = opening + commissioned * (13 - month) / 24
                hardware, launch = p("hardware_cost_usd_per_mw"), p("deployment_cost_usd_per_mw")
                extra_capex = produced * hardware + deployment * launch
                book = state.setdefault("orbital_book", p("opening_net_book_value_usd", opening * (hardware + launch) + inventory * hardware))
                before_da = book + extra_capex
                writeoff = min(before_da, (deployment - commissioned) * (hardware + launch))
                depreciation = min(max(before_da - writeoff, 0), mw * (hardware + launch) / p("asset_life_years", 4, 1e-9))
                extra_da = depreciation + writeoff
                state.update(commissioned_mw=closing, inventory_mw=inventory + produced - deployment,
                             orbital_book=max(before_da - extra_da, 0))
                retired_mw = 0
                if "service_life_years" in segment:
                    lots = state.setdefault("inventory_lots", [[inventory, hardware]] if inventory else [])
                    if produced:
                        lots.append([produced, hardware])
                    remaining, deployed_hardware_cost = deployment, 0.0
                    for lot in lots:
                        used = min(lot[0], remaining)
                        deployed_hardware_cost += used * lot[1]
                        lot[0] -= used
                        remaining -= used
                    state["inventory_lots"] = [lot for lot in lots if lot[0] > 1e-9]
                    per_mw = deployed_hardware_cost / deployment + launch if deployment else 0
                    writeoff = (deployment - commissioned) * per_mw
                    lifecycle = asset_rollforward(state, year,
                        [(q * p("commissioning_yield", 1, 0, 1), per_mw, m) for m, q in enumerate(deployed_monthly, 1)] if deployed_monthly is not None else
                        [(commissioned / (13 - int(month)), per_mw, m) for m in range(int(month), 13)],
                        p("service_life_years", 4, 1), p("depreciation_life_years", p("asset_life_years", 4), 1e-9),
                        opening_units=opening,
                        opening_unit_cost=max(book - inventory * hardware, 0) / opening if opening else 0)
                    opening, closing, mw = lifecycle["opening"], lifecycle["closing"], lifecycle["average"]
                    retired_mw = lifecycle["retirements"]
                    extra_da = lifecycle["da"] + writeoff
                    state.update(commissioned_mw=closing,
                                 orbital_book=lifecycle["book"] + sum(q * cost for q, cost in state["inventory_lots"]))
                orbital_drivers = {"manufactured_it_mw": produced, "opening_it_mw": opening,
                                   "deployment_attempted_mw": deployment, "commissioned_new_it_mw": commissioned,
                                   "year_end_it_mw": closing, "closing_inventory_mw": state["inventory_mw"],
                                   "retired_it_mw": retired_mw,
                                   "commissioning_start_month": month, "deployment_writeoff_usd": writeoff,
                                   "closing_net_book_value_usd": state["orbital_book"], **launch_drivers}
            elif "capacity_ramp" in segment:
                if "average_it_mw" in segment or "hardware_da_usd_per_mw_year" in segment:
                    raise ModelError("capacity_ramp cannot also set average_it_mw or manual hardware depreciation")
                orbital_drivers, extra_capex, extra_da = ground_capacity_rollforward(
                    segment["capacity_ramp"], year, base_year, state)
                mw = orbital_drivers["average_it_mw"]
            else:
                mw = p("average_it_mw")
            external, internal = p("external_share", 1, 0, 1), p("internal_share", 0, 0, 1)
            if external + internal > 1 + 1e-12:
                raise ModelError("compute external_share + internal_share must be <= 1")
            available = p("availability", 1, 0, 1)
            ext_util, own_util = p("external_utilization", 1, 0, 1), p("internal_utilization", 1, 0, 1)
            calendar_hours = 24 * (366 if calendar.isleap(year) else 365)
            billable_mwh = mw * external * ext_util * available * calendar_hours
            busy = available * (external * ext_util + internal * own_util)
            energy_kwh = mw * 1000 * calendar_hours * p("pue", 1, 1) * (busy + (1 - busy) * p("idle_power_fraction", 0.15, 0, 1))
            revenue = billable_mwh * p("price_usd_per_billable_mw_hour")
            if kind == "compute" and "capacity_ramp" not in segment:
                extra_da = mw * p("hardware_da_usd_per_mw_year")
            cogs = energy_kwh * p("electricity_usd_per_kwh") + mw * p("cash_overhead_usd_per_mw_year") + extra_da
            inputs = {"average_it_mw": mw, "external_share": external, "internal_share": internal,
                      "billable_mwh": billable_mwh, "calendar_hours": calendar_hours, "electricity_kwh": energy_kwh, **orbital_drivers}
    # Pre-launch R&D, capex and depreciation are intentionally NOT suppressed.
    opex, capex = p("opex_usd"), p("capex_usd") + revenue * p("capex_revenue_ratio") + extra_capex
    da = p("da_usd") + revenue * p("da_revenue_ratio") + extra_da
    # Explicit/revenue-based DA is part of COGS; special-kind DA already included.
    cogs += da - extra_da
    if kind in ("compute", "orbital_compute") and inputs.get("billable_mwh", 0):
        # Entire segment cost / external billed output: includes internal/idle
        # capacity costs, excludes corporate overhead and funding charges.
        inputs["segment_cost_per_billable_mw_hour_usd"] = (cogs + opex) / inputs["billable_mwh"]
    if kind == "robot_fleet" and inputs.get("average_fleet", 0):
        inputs["segment_cost_per_robot_year_usd"] = (cogs + opex) / inputs["average_fleet"]
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
    "stock_payment",
}


def settle_resources_with_stock(spec, year, base_year, cash_before, capex, cash_opex):
    """Replace eligible cash resource payments with directly issued shares.

    No cash financing proceeds or revenue are created. Contract prices are inputs,
    deliberately independent of the same-year post-dilution valuation.
    """
    if not isinstance(spec, dict):
        raise ModelError("stock_payment must be an object")
    allowed = {"enabled", "capex_eligible_ratio", "opex_eligible_ratio", "acceptance_ratio",
               "reference_price_usd", "discount_rate", "max_new_shares", "cash_buffer_usd", "notes"}
    if set(spec) - allowed:
        raise ModelError("unknown stock_payment fields")
    enabled = spec.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ModelError("stock_payment.enabled must be boolean")
    def p(key, default=0, maximum=None):
        return parameter(spec.get(key, default), year, base_year, "stock_payment." + key, 0, maximum)
    result = {"stock_payment_usd": 0.0, "stock_paid_capex_usd": 0.0,
              "stock_paid_opex_usd": 0.0, "resource_shares_issued": 0.0,
              "stock_payment_price_usd": None}
    if not enabled:
        return result
    acceptance = p("acceptance_ratio", 1, 1)
    eligible_capex = capex * p("capex_eligible_ratio", 1, 1) * acceptance
    eligible_opex = cash_opex * p("opex_eligible_ratio", 0, 1) * acceptance
    needed = max(p("cash_buffer_usd") - cash_before, 0)
    amount = min(needed, eligible_capex + eligible_opex)
    price = p("reference_price_usd") * (1 - p("discount_rate", 0, 1))
    if amount and price <= 0:
        raise ModelError("stock resource payment requires a positive agreed share price after discount")
    if "max_new_shares" in spec:
        amount = min(amount, p("max_new_shares") * price)
    if not amount:
        return result
    capex_part = min(amount, eligible_capex)
    return {"stock_payment_usd": amount, "stock_paid_capex_usd": capex_part,
            "stock_paid_opex_usd": amount - capex_part,
            "resource_shares_issued": amount / price, "stock_payment_price_usd": price}


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
    stock_payment_assumed = False
    for year in years:
        def p(key, default=0, minimum=0, maximum=None):
            return parameter(company.get(key, default), year, base, key, minimum, maximum)
        rows = {}
        # Vehicle-linked subscriptions use actual modeled external sales, including
        # capacity limits, and update after unit businesses regardless of config order.
        ordered = sorted(company["segments"].items(), key=lambda item: "additions_source_segment_id" in item[1])
        for key, segment in ordered:
            if "additions_source_segment_id" in segment:
                source = segment["additions_source_segment_id"]
                if segment["kind"] != "subscription" or source not in rows or company["segments"][source]["kind"] != "unit":
                    raise ModelError("linked subscriptions require a unit-segment sales source")
                states.setdefault(key, {})["new_units"] = rows[source]["drivers"].get("external_units", 0)
            try:
                rows[key] = segment_forecast(segment, year, base, states.setdefault(key, {}))
            except ModelError as exc:
                raise ModelError(f"{year} / {key}: {exc}") from exc
        # One production constraint for external passenger cars plus owned fleet additions.
        if "passenger_production_capacity" in company:
            passenger_id, fleet_id = company["passenger_segment_id"], company["robotaxi_segment_id"]
            try:
                fleet_drivers = rows[fleet_id]["drivers"]
                used = rows[passenger_id]["drivers"].get("external_units", 0) + fleet_drivers.get("manufactured_units", fleet_drivers.get("additions", 0))
            except KeyError as exc:
                raise ModelError("production constraint references unknown segment") from exc
            if used > p("passenger_production_capacity") + 1e-6:
                raise ModelError(f"{year}: passenger sales + owned fleet additions exceed production capacity")
        eligible = [key for key in rows if company["segments"][key].get("robotics_eligible", False)]
        fleet_savings = sum(row["drivers"].get("internal_savings_requested_usd", 0) for row in rows.values())
        explicit_savings = p("robotics_savings_usd")
        if fleet_savings and explicit_savings:
            raise ModelError("robot_fleet derived savings and robotics_savings_usd cannot both be positive")
        requested_savings = explicit_savings + fleet_savings
        if requested_savings and any(company["segments"][key].get("cost_includes_robotics", True) for key in eligible):
            raise ModelError("robotics savings require cost_includes_robotics=false on eligible segments")
        cash_pools = {key: max(rows[key]["cogs_usd"] - rows[key]["da_usd"], 0) *
            parameter(company["segments"][key].get("automation_eligible_cash_cost_ratio", 1),
                      year, base, "automation_eligible_cash_cost_ratio", 0, 1) for key in eligible}
        pool = sum(cash_pools.values())
        savings = min(requested_savings, pool,
                      sum(rows[key]["cogs_usd"] for key in eligible) * p("robotics_max_cogs_share", 0, 0, 1))
        robot_da = p("robotics_da_usd")
        for key in eligible:
            allocated = savings * cash_pools[key] / pool if pool else 0
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
        cash_before_stock = cash + cash_fcf + new_debt - repaid + raised - buybacks - dividends
        # Only resource expenditures are eligible; taxes, interest, dividends,
        # debt repayments and noncash DA/SBC are not a new resource-payment pool.
        cash_operating_cost = max(cogs + sum(row["opex_usd"] for row in rows.values()) + corporate_opex - da - sbc, 0)
        stock = settle_resources_with_stock(company.get("stock_payment", {}), year, base,
                                            cash_before_stock, capex, cash_operating_cost)
        stock_payment_assumed = stock_payment_assumed or stock["stock_payment_usd"] > 0
        cash_fcf += stock["stock_payment_usd"]
        diluted = opening_shares * (1 + p("sbc_dilution_rate", 0, 0, 1)) + issued + stock["resource_shares_issued"] - retired
        if diluted <= 0:
            raise ModelError("buybacks cannot eliminate all outstanding shares")
        weighted = (opening_shares + diluted) / 2
        closing_cash = cash_before_stock + stock["stock_payment_usd"]
        # A negative balance is an unfunded deficit, never silently an overdraft/financing round.
        funding_failed = funding_failed or closing_cash < 0
        ev = sum(row["revenue_usd"] * row["ev_sales_multiple"] for row in rows.values()) - corporate_opex * p("corporate_ev_cost_multiple")
        equity = ev + closing_cash - closing_debt
        pe = p("pe_multiple")
        result = {
            "year": year, "company": company["name"], "revenue_usd": revenue,
            "cogs_usd": cogs, "gross_profit_usd": gross,
            "gross_margin": gross / revenue if revenue else None,
            "segment_opex_usd": sum(row["opex_usd"] for row in rows.values()),
            "corporate_opex_usd": corporate_opex, "operating_profit_usd": operating,
            "interest_usd": interest, "tax_usd": tax, "net_income_usd": net,
            "da_usd": da, "capex_usd": capex, "delta_nwc_usd": delta_nwc,
            "economic_fcf_usd": economic_fcf, "cash_fcf_usd": cash_fcf,
            "cash_capex_usd": capex - stock["stock_paid_capex_usd"],
            "cash_before_stock_payment_usd": cash_before_stock,
            "funding_gap_before_stock_usd": max(0.0, -cash_before_stock),
            "cash_equity_raised_usd": raised, "cash_equity_shares_issued": issued,
            "resource_dilution_fraction": stock["resource_shares_issued"] / diluted,
            "stock_payment_assumed": stock_payment_assumed, **stock,
            "sbc_expense_usd": sbc, "cash_usd": closing_cash, "debt_usd": closing_debt,
            "funding_gap_usd": max(0.0, -closing_cash), "funding_failed": funding_failed,
            "shares": diluted, "weighted_average_shares": weighted,
            "eps_usd": net / weighted, "year_end_share_earnings_usd": net / diluted,
            "pe_multiple": pe, "sotp_enterprise_value_usd": ev,
            "sotp_equity_value_usd": equity,
            # A financing gap is a risk/condition, not undefined valuation arithmetic.
            # These prices use the specified debt and shares BEFORE unspecified financing.
            "price_pe_usd": net * pe / diluted if net > 0 else None,
            "price_sotp_usd": equity / diluted if equity > 0 else None,
            "valuation_status": "conditional_unfunded" if funding_failed else ("stock_payment_assumed" if stock_payment_assumed else "scenario"),
            "price_pe_unavailable_reason": "non_positive_net_income" if net <= 0 else None,
            "price_sotp_unavailable_reason": "non_positive_equity_value" if equity <= 0 else None,
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
        stock_assumed = a.get("stock_payment_assumed", False) or b.get("stock_payment_assumed", False)
        combined.append({"year": year, "company": f"{acquirer}+{target} (pro forma)",
                         "revenue_usd": a["revenue_usd"] + b["revenue_usd"] - eliminated,
                         "intercompany_revenue_eliminated_usd": eliminated,
                         "operating_profit_usd": a["operating_profit_usd"] + b["operating_profit_usd"] + delta,
                         "net_income_usd": net, "shares": shares,
                         "target_exchange_ratio": ratio, "net_operating_synergy_usd": synergy,
                         "transaction_cost_usd": cost, "sotp_equity_value_usd": equity,
                         "price_pe_usd": net * p("pe_multiple") / shares if net > 0 else None,
                         "price_sotp_usd": equity / shares if equity > 0 else None,
                         "valuation_status": ("stock_payment_assumed" if stock_assumed else "scenario") if funded else "conditional_unfunded",
                         "stock_payment_assumed": stock_assumed,
                         "price_pe_unavailable_reason": "non_positive_net_income" if net <= 0 else None,
                         "price_sotp_unavailable_reason": "non_positive_equity_value" if equity <= 0 else None,
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
        warnings.append("部分期初財務值有申報錨點，其餘營運、估值及融資條件仍是假設；輸出不是公司指引。")
    if resolved.get("metadata", {}).get("opening_balance_anchor"):
        warnings.append("期初股數取2026-10-15、流動資金及債務取2026-09-30，暫假設至2026年底淨變動為0；非已確認年末實績。流動資金包含短期投資。")
    if resolved.get("metadata", {}).get("assumption_review_status") == "searched_not_fully_validated":
        warnings.append("使用者假設已做網路與Musk訊息搜尋；部分僅支持方向或長期產能，尚未支持指定年度產量、滿產時點或股票普遍接受度。")
    if any(row["funding_failed"] for rows in summaries.values() for row in rows):
        warnings.append("有未融資缺口：仍顯示融資前條件估值；補入借款、利息或增發稀釋後須重新計算。")
    if any(row["stock_payment_usd"] > 0 for rows in summaries.values() for row in rows):
        warnings.append("已依股票交換資源假設減少現金支出並增發股份；估值已計稀釋，仍以交易對手接受指定條件為前提。")
    if any(row["robotics_savings_requested_usd"] > row["robotics_savings_usd"] + 1e-6 for rows in summaries.values() for row in rows):
        warnings.append("機器人節省已受可自動化現金成本與 robotics_max_cogs_share 雙重限制，未抵銷折舊或不可改善成本。")
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
    lines = ["# Tesla／SpaceX 年度預測", "", "金額：十億美元，股價：美元／股。淨利不正時 P/E 估值不適用；股權價值不正時 SOTP 不適用。資金缺口另列，不隱藏融資前條件估值。", ""]
    for result in results:
        label = "主預測" if result["scenario"] == "base" else f"敏感度檢查：{result['scenario']}"
        lines += [f"## {label}", "", *result["warnings"], "",
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
    parser.add_argument("--config", type=Path, default=Path(__file__).parent / "configs" / "current.json")
    parser.add_argument("--scenario", default="base", help="base = primary forecast; bear/bull/all = optional sensitivity checks")
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
