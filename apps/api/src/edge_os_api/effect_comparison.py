"""Deterministic descriptive comparison over explicitly qualified event inputs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Context, Decimal, DecimalException, ROUND_HALF_EVEN, localcontext
from typing import Any

from . import p02, p06

NUMERIC = Context(prec=50, rounding=ROUND_HALF_EVEN)
CHAIN_ORDER = ("block_number", "transaction_index", "log_index")


def parse_utc(value: str | datetime) -> datetime:
    """Parse an aware UTC instant used by a saved schedule or event."""
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise ValueError("timestamps must be timezone-aware UTC instants")
    return parsed.astimezone(timezone.utc)


def reference_trade(
    trades: list[dict[str, Any]],
    decision_time: datetime,
    offset_seconds: int,
    window_seconds: int = 60,
) -> dict[str, Any] | None:
    """Return the first qualified trade by chain order in one half-open response window."""
    if offset_seconds < 0 or window_seconds <= 0:
        raise ValueError("outcome offsets must be non-negative and windows must be positive")
    start = parse_utc(decision_time) + timedelta(seconds=offset_seconds)
    end = start + timedelta(seconds=window_seconds)
    candidates: list[tuple[tuple[int, int, int], datetime, dict[str, Any]]] = []
    for trade in trades:
        if trade.get("qualified") is not True:
            continue
        try:
            event_time = parse_utc(trade["event_time"])
            order = tuple(trade[key] for key in CHAIN_ORDER)
        except (KeyError, TypeError, ValueError):
            continue
        if not all(isinstance(part, int) and not isinstance(part, bool) and part >= 0 for part in order):
            continue
        if start <= event_time < end:
            candidates.append((order, event_time, trade))
    if not candidates:
        return None
    return dict(min(candidates, key=lambda item: (item[0], item[1]))[2])


def _response(start: dict[str, Any] | None, end: dict[str, Any] | None, horizon_seconds: int) -> dict[str, Any]:
    reasons: list[str] = []
    if start is None:
        reasons.append("MISSING_START_REFERENCE")
    if end is None:
        reasons.append("MISSING_END_REFERENCE")
    result: dict[str, Any] = {
        "start_trade": start,
        "end_trade": end,
        "target_horizon_seconds": horizon_seconds,
        "actual_elapsed_seconds": None,
        "response": None,
        "missing_reasons": reasons,
    }
    if start is None or end is None:
        return result
    start_time, end_time = parse_utc(start["event_time"]), parse_utc(end["event_time"])
    start_price, end_price = Decimal(start["price"]), Decimal(end["price"])
    if start_price <= 0 or end_price <= 0 or not start_price.is_finite() or not end_price.is_finite():
        result["missing_reasons"] = ["INVALID_REFERENCE_PRICE"]
        return result
    if end_time < start_time:
        result["missing_reasons"] = ["END_BEFORE_START"]
        return result
    try:
        with localcontext(NUMERIC):
            change = end_price / start_price - Decimal(1)
    except DecimalException:
        result["missing_reasons"] = ["NUMERIC_FAILURE"]
        return result
    result["actual_elapsed_seconds"] = int((end_time - start_time).total_seconds())
    result["response"] = format(change, "f")
    return result


def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    values = sorted(Decimal(row["response"]) for row in rows if row["response"] is not None)
    if not values:
        return {"opportunity_count": len(rows), "observed_count": 0, "missing_count": len(rows),
                "mean": None, "median": None, "actual_elapsed_seconds": []}
    with localcontext(NUMERIC):
        mean = sum(values, Decimal(0)) / Decimal(len(values))
        middle = len(values) // 2
        median = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / Decimal(2)
    return {
        "opportunity_count": len(rows),
        "observed_count": len(values),
        "missing_count": len(rows) - len(values),
        "mean": format(mean, "f"),
        "median": format(median, "f"),
        "actual_elapsed_seconds": [row["actual_elapsed_seconds"] for row in rows if row["response"] is not None],
    }


def compare_effects(
    *,
    schedule: dict[str, Any],
    evaluation_plan: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    incremental_volume_declared: bool,
) -> dict[str, Any]:
    """Compare P06 truth outputs on a frozen schedule and preserve every opportunity."""
    start, end = parse_utc(schedule["start"]), parse_utc(schedule["end"])
    interval = schedule["interval_seconds"]
    if not isinstance(interval, int) or isinstance(interval, bool) or interval <= 0 or end <= start:
        raise ValueError("decision schedule must have a positive interval and ordered UTC bounds")
    duration = int((end - start).total_seconds())
    if duration % interval:
        raise ValueError("decision schedule bounds must contain whole intervals")
    scheduled = [start + timedelta(seconds=offset) for offset in range(0, duration, interval)]
    plan_by_id = {row["evaluation_id"]: row for row in evaluation_plan}
    if len(plan_by_id) != len(evaluation_plan):
        raise ValueError("evaluation identities must be unique")
    known_variants = {row["variant_id"] for row in evaluation_plan}
    if len(known_variants) != len(evaluation_plan):
        raise ValueError("each comparison row must identify one declared variant")
    scheduled_set = set(scheduled)
    decision_by_key: dict[tuple[str, datetime], dict[str, Any]] = {}
    for decision in decisions:
        key = (decision["evaluation_id"], parse_utc(decision["decision_time"]))
        if key[0] not in plan_by_id:
            raise ValueError("decision uses an undeclared evaluation identity")
        if key[1] not in scheduled_set:
            raise ValueError("decision is outside the frozen schedule")
        if key in decision_by_key:
            raise ValueError("decision schedule contains a duplicate evaluation opportunity")
        decision_by_key[key] = decision

    variant_results: list[dict[str, Any]] = []
    all_opportunities: list[dict[str, Any]] = []
    for plan in evaluation_plan:
        horizon_seconds = plan["horizon"]["value"] * {
            "SECONDS": 1, "MINUTES": 60, "HOURS": 3600, "DAYS": 86400,
        }[plan["horizon"]["unit"]]
        if horizon_seconds <= 0:
            raise ValueError("declared outcome horizons must be positive")
        opportunities: list[dict[str, Any]] = []
        for decision_time in scheduled:
            decision = decision_by_key.get((plan["evaluation_id"], decision_time))
            reasons: list[str] = []
            if decision is None:
                reasons.append("NO_SIGNAL_RECORD")
                price_state = volume_state = "UNKNOWN"
                qualified = False
            else:
                price_state, volume_state = decision["price_state"], decision["volume_state"]
                reasons.extend(decision.get("reasons", []))
                available_at = parse_utc(decision["available_at"])
                qualified = decision.get("qualified") is True and decision.get("essential_evidence_qualified") is True
                if available_at > decision_time:
                    qualified = False
                    reasons.append("SIGNAL_NOT_AVAILABLE_AT_DECISION")
                if decision.get("essential_evidence_qualified") is not True:
                    reasons.append("MISSING_ESSENTIAL_EVIDENCE")
            if price_state not in {"TRUE", "FALSE", "UNKNOWN"} or volume_state not in {"TRUE", "FALSE", "UNKNOWN"}:
                raise ValueError("P06 condition outputs must use TRUE, FALSE, or UNKNOWN")
            rule_state = "FALSE" if "FALSE" in {price_state, volume_state} else (
                "TRUE" if price_state == volume_state == "TRUE" else "UNKNOWN")
            group = "EXCLUDED"
            if qualified and rule_state == "TRUE":
                group = "TRIGGERED"
            elif qualified and rule_state == "FALSE":
                group = "CONTROL"
            elif not reasons:
                reasons.append("UNKNOWN_OR_UNQUALIFIED_SIGNAL")

            first = reference_trade(trades, decision_time, 0)
            last = reference_trade(trades, decision_time, horizon_seconds)
            response = _response(first, last, horizon_seconds)
            row = {
                "opportunity_id": f"{plan['evaluation_id']}:{decision_time.isoformat().replace('+00:00', 'Z')}",
                "decision_id": decision["decision_id"] if decision else None,
                "evaluation_id": plan["evaluation_id"],
                "trial_id": plan["trial_id"],
                "variant_id": plan["variant_id"],
                "decision_time": decision_time.isoformat().replace("+00:00", "Z"),
                "price_state": price_state,
                "volume_state": volume_state,
                "rule_state": rule_state,
                "group": group if response["response"] is not None else "MISSING_OUTCOME",
                "eligibility_group": group,
                "reasons": list(dict.fromkeys(reasons + response["missing_reasons"])),
                **response,
            }
            opportunities.append(row)
            all_opportunities.append(row)

        triggered = [row for row in opportunities if row["eligibility_group"] == "TRIGGERED"]
        controls = [row for row in opportunities if row["eligibility_group"] == "CONTROL"]
        triggered_stats, control_stats = _summary(triggered), _summary(controls)
        contrast = None
        if triggered_stats["mean"] is not None and control_stats["mean"] is not None:
            with localcontext(NUMERIC):
                contrast = format(Decimal(triggered_stats["mean"]) - Decimal(control_stats["mean"]), "f")
        incremental: dict[str, Any] = {"status": "NOT_DECLARED"}
        if incremental_volume_declared:
            incremental_triggered = [row for row in opportunities
                                     if row["eligibility_group"] == "TRIGGERED" and row["price_state"] == "TRUE"]
            incremental_control = [row for row in opportunities
                                   if row["eligibility_group"] == "CONTROL" and row["price_state"] == "TRUE"
                                   and row["volume_state"] == "FALSE"]
            incremental_a, incremental_b = _summary(incremental_triggered), _summary(incremental_control)
            incremental_contrast = None
            if incremental_a["mean"] is not None and incremental_b["mean"] is not None:
                with localcontext(NUMERIC):
                    incremental_contrast = format(Decimal(incremental_a["mean"]) - Decimal(incremental_b["mean"]), "f")
            incremental = {
                "status": "DESCRIPTIVE_ONLY",
                "condition": "same price condition TRUE; quote-volume condition TRUE versus FALSE",
                "triggered": incremental_a, "control": incremental_b,
                "triggered_minus_control_mean": incremental_contrast,
            }
        variant_results.append({
            "evaluation_id": plan["evaluation_id"],
            "trial_id": plan["trial_id"],
            "variant_id": plan["variant_id"],
            "horizon": dict(plan["horizon"]),
            "opportunities": opportunities,
            "general_comparison": {"triggered": triggered_stats, "control": control_stats,
                                   "triggered_minus_control_mean": contrast},
            "incremental_volume_comparison": incremental,
        })

    event_uses: dict[str, int] = {}
    for row in all_opportunities:
        for trade in (row["start_trade"], row["end_trade"]):
            if trade is not None:
                event_uses[trade["event_id"]] = event_uses.get(trade["event_id"], 0) + 1
    shared = sorted(event_id for event_id, count in event_uses.items() if count > 1)
    for row in all_opportunities:
        ids = {trade["event_id"] for trade in (row["start_trade"], row["end_trade"]) if trade is not None}
        row["shared_event_ids"] = sorted(ids & set(shared))
    intervals: list[tuple[datetime, datetime, str, str | None]] = []
    for row in all_opportunities:
        if row["start_trade"] is not None and row["end_trade"] is not None:
            intervals.append((parse_utc(row["start_trade"]["event_time"]),
                              parse_utc(row["end_trade"]["event_time"]), row["opportunity_id"], row["decision_id"]))
    overlapping_opportunities: dict[str, list[str]] = {row["opportunity_id"]: [] for row in all_opportunities}
    overlapping_decisions: dict[str, list[str]] = {row["opportunity_id"]: [] for row in all_opportunities}
    for index, (left_start, left_end, left_key, left_id) in enumerate(intervals):
        for right_start, right_end, right_key, right_id in intervals[index + 1:]:
            if left_start < right_end and right_start < left_end:
                overlapping_opportunities[left_key].append(right_key)
                overlapping_opportunities[right_key].append(left_key)
                if right_id is not None:
                    overlapping_decisions[left_key].append(right_id)
                if left_id is not None:
                    overlapping_decisions[right_key].append(left_id)
    for row in all_opportunities:
        row["overlapping_opportunity_ids"] = sorted(overlapping_opportunities[row["opportunity_id"]])
        row["overlapping_decision_ids"] = sorted(overlapping_decisions[row["opportunity_id"]])

    return {
        "schedule": {"version": schedule["version"], "start": start.isoformat().replace("+00:00", "Z"),
                     "end": end.isoformat().replace("+00:00", "Z"), "interval_seconds": interval},
        "variants": variant_results,
        "status": "UNRESOLVED",
        "statistical_status": "UNRESOLVED",
        "statistical_reasons": ["STAT_Q01_PROFILE_NOT_QUALIFIED"],
        "shared_event_ids": shared,
        "opportunity_count": len(all_opportunities),
        "excluded_count": sum(row["eligibility_group"] == "EXCLUDED" for row in all_opportunities),
        "missing_outcome_count": sum(row["response"] is None for row in all_opportunities),
    }


def evaluate_p06_bindings(
    *,
    schedule: dict[str, Any],
    evaluation_plan: list[dict[str, Any]],
    bindings: list[dict[str, Any]],
    feature_rows: list[dict[str, Any]],
    market: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Evaluate explicitly adopted P06 rule bindings on the independent decision clock.

    The caller must author each binding and its essential-input declaration. No P08 free-text
    hypothesis or falsification text is parsed here.
    """
    market = market or p02.FIXTURE_STRATEGY["market"]
    start, end = parse_utc(schedule["start"]), parse_utc(schedule["end"])
    interval = schedule["interval_seconds"]
    if not isinstance(interval, int) or isinstance(interval, bool) or interval <= 0 or end <= start:
        raise ValueError("decision schedule must have a positive interval and ordered UTC bounds")
    duration = (end - start).total_seconds()
    if duration % interval:
        raise ValueError("decision schedule bounds must contain whole intervals")
    times = [start + timedelta(seconds=offset) for offset in range(0, int(duration), interval)]
    bindings_by_id = {item["evaluation_id"]: item for item in bindings}
    plan_by_id = {item["evaluation_id"]: item for item in evaluation_plan}
    if len(bindings_by_id) != len(bindings) or set(bindings_by_id) != set(plan_by_id):
        raise ValueError("every declared evaluation needs exactly one explicit P06 binding")
    if len(plan_by_id) != len(evaluation_plan):
        raise ValueError("evaluation identities must be unique")

    parsed_features: dict[datetime, dict[str, Any]] = {}
    for feature in feature_rows:
        bucket_end = parse_utc(feature["bucket_end"])
        if bucket_end.minute % 5 or bucket_end.second or bucket_end.microsecond:
            raise ValueError("P06 feature buckets must use five-minute UTC resolution")
        if bucket_end in parsed_features:
            raise ValueError("P06 feature buckets must be unique")
        parsed_features[bucket_end] = feature
    ordered_buckets = sorted(parsed_features)
    if any(right - left != timedelta(minutes=5) for left, right in zip(ordered_buckets, ordered_buckets[1:])):
        raise ValueError("P06 feature buckets must be contiguous; represent gaps as missing observations")
    market_id = p06.market_binding_id(market)
    observations: dict[str, list[p06.Observation | None]] = {"price": [], "quote_volume": []}
    for bucket in ordered_buckets:
        feature = parsed_features[bucket]
        for source in observations:
            raw = feature.get(source)
            if raw is None:
                observations[source].append(None)
                continue
            observations[source].append(p06.Observation(
                value=raw.get("value"), bucket_end=bucket, market_binding_id=market_id,
                qualified=raw.get("qualified") is True,
                available_at=parse_utc(raw["available_at"]) if raw.get("available_at") else None,
                reasons=tuple(raw.get("reasons", [])),
            ))
    outputs: list[dict[str, Any]] = []
    for plan in evaluation_plan:
        binding = bindings_by_id[plan["evaluation_id"]]
        for field in ("trial_id", "variant_id"):
            if binding.get(field) != plan[field]:
                raise ValueError(f"P06 binding {field} must exactly match the adopted evaluation plan")
        essentials = binding.get("essential_inputs")
        if not isinstance(essentials, list) or not essentials or len(set(essentials)) != len(essentials) or not set(essentials) <= set(observations):
            raise ValueError("each P06 binding needs an explicit unique essential-input mapping")
        for name in ("price_expression", "volume_expression"):
            info = p06.expression_info(binding[name], market, f"/{name}")
            if info.kind != "BOOLEAN":
                raise ValueError("each adopted P06 comparison condition must be Boolean")
        horizon = plan["horizon"]
        horizon_seconds = horizon["value"] * {"SECONDS": 1, "MINUTES": 60, "HOURS": 3600, "DAYS": 86400}[horizon["unit"]]
        if horizon_seconds <= 0:
            raise ValueError("adopted outcome horizons must be positive")
        for decision_time in times:
            eligible_buckets = [bucket for bucket in ordered_buckets if bucket <= decision_time]
            if not eligible_buckets:
                position, scheduled = 0, ()
                prices, volumes = (), ()
            else:
                current = eligible_buckets[-1]
                position = ordered_buckets.index(current)
                scheduled = tuple(ordered_buckets)
                prices, volumes = observations["price"], observations["quote_volume"]
            context = p06.EvaluationContext(prices, volumes, scheduled, market_id, decision_time, position)
            price_result = p06.evaluate_expression(binding["price_expression"], market, context)
            volume_result = p06.evaluate_expression(binding["volume_expression"], market, context)
            reasons = list(dict.fromkeys((*price_result.reasons, *volume_result.reasons)))
            essential_qualified = True
            input_evidence: list[dict[str, Any]] = []
            availability = [decision_time]
            for name in essentials:
                bucket = eligible_buckets[-1] if eligible_buckets else None
                feature = None if bucket is None else parsed_features[bucket].get(name)
                available_at = None if feature is None or feature.get("available_at") is None else parse_utc(feature["available_at"])
                if available_at is not None:
                    availability.append(available_at)
                input_evidence.append({
                    "input": name,
                    "bucket_end": None if bucket is None else bucket.isoformat().replace("+00:00", "Z"),
                    "available_at": None if available_at is None else available_at.isoformat().replace("+00:00", "Z"),
                    "qualified": feature is not None and feature.get("qualified") is True,
                    "reasons": [] if feature is None else list(feature.get("reasons", [])),
                })
                qualified = (feature is not None and feature.get("qualified") is True
                             and feature.get("value") is not None and (available_at is None or available_at <= decision_time))
                if not qualified:
                    essential_qualified = False
                    reasons.append(f"MISSING_ESSENTIAL_EVIDENCE:{name}")
            outputs.append({
                "decision_id": f"{plan['evaluation_id']}:{decision_time.isoformat()}",
                "evaluation_id": plan["evaluation_id"], "trial_id": plan["trial_id"],
                "variant_id": plan["variant_id"],
                "decision_time": decision_time.isoformat().replace("+00:00", "Z"),
                "available_at": max(availability).isoformat().replace("+00:00", "Z"),
                "price_state": price_result.state,
                "volume_state": volume_result.state,
                "qualified": essential_qualified,
                "essential_evidence_qualified": essential_qualified,
                "input_evidence": input_evidence,
                "reasons": list(dict.fromkeys(reasons)),
            })
    return outputs
