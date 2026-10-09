"""Deterministic P12/1 spot replay over an explicitly qualified schedule."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, DecimalException, localcontext
from typing import Any, Sequence

from edge_os_api import p02, p06

PROFILE_VERSION = "p12.spot-replay/1"
ESSENTIAL_VERSION = "p12.essential-evidence/1"
_COMPLETE = {"COMPLETE_OCCUPIED", "COMPLETE_EMPTY"}


class ReplayError(ValueError):
    """A replay input is malformed or outside the adopted P12/1 subset."""

    def __init__(self, code: str, path: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.path = path
        self.detail = detail


@dataclass(frozen=True)
class ReplayBucket:
    """One scheduled P07 bucket with the P06 observations for that time."""

    bucket_end: datetime
    status: str
    price: p06.Observation | None
    quote_volume: p06.Observation | None


@dataclass(frozen=True)
class ReplayDataset:
    """Exact dataset revision and its retained qualification/coverage state."""

    revision_id: str
    qualification: str
    coverage_complete: bool
    market_binding_id: str
    buckets: tuple[ReplayBucket, ...]
    evidence_class: str = "SYNTHETIC_FIXTURE"


@dataclass(frozen=True)
class ReplayInput:
    """Immutable run identities, window, starting cash and adopted evidence binding."""

    strategy_revision_id: str
    run_configuration_id: str
    dataset: ReplayDataset
    essential_evidence: dict[str, Any] | None
    window_start: datetime
    window_end: datetime
    initial_cash_quote: str
    initial_base_amount: str = "0"
    initial_basis_quote: str = "0"


@dataclass(frozen=True)
class ReplayResult:
    """Ordered simulation events and quote-denominated output metrics."""

    repeatability_id: str
    evidence_class: str
    samples: tuple[dict[str, Any], ...]
    events: tuple[dict[str, Any], ...]
    trades: tuple[dict[str, Any], ...]
    metrics: dict[str, Decimal | int | None]
    metric_statuses: dict[str, str]
    metric_reasons: dict[str, tuple[str, ...]]
    open_position: dict[str, Any] | None


@dataclass(frozen=True)
class QuoteMetrics:
    """Independent quote-unit metrics and their availability state."""

    values: dict[str, Decimal | int | None]
    statuses: dict[str, str]
    reasons: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class _Order:
    side: str
    signal_index: int
    fill_index: int
    reserved_quote: Decimal
    reserved_base: Decimal


def _invalid(code: str, path: str, detail: str) -> ReplayError:
    return ReplayError(code, path, detail)


def _decimal(value: object, path: str, *, positive: bool = False) -> Decimal:
    if not isinstance(value, str):
        raise _invalid("INVALID_REPLAY_NUMBER", path, "Use a canonical decimal string.")
    try:
        result = p02._checker.canonical_decimal(value)
    except (p02.Invalid, TypeError) as error:
        raise _invalid("INVALID_REPLAY_NUMBER", path, str(error)) from None
    if not result.is_finite() or positive and result <= 0:
        raise _invalid("INVALID_REPLAY_NUMBER", path, "The decimal value is outside the supported range.")
    return result


def _utc(value: datetime, path: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise _invalid("INVALID_REPLAY_TIME", path, "Use an explicit UTC timestamp.")


def _validate_descriptor(strategy: dict[str, Any], run: ReplayInput, market_id: str) -> dict[str, list[dict[str, Any]]]:
    descriptor = run.essential_evidence
    if not isinstance(descriptor, dict):
        raise _invalid("UNRESOLVED_ESSENTIAL_EVIDENCE", "/essential_evidence", "Bind both action fields.")
    required = {"schema_version", "strategy_revision", "run_configuration_id", "dataset_revision", "market_binding_id", "fields"}
    if set(descriptor) != required or descriptor.get("schema_version") != ESSENTIAL_VERSION:
        raise _invalid("INVALID_ESSENTIAL_BINDING", "/essential_evidence", "The adopted descriptor fields are malformed.")
    identities = {
        "strategy_revision": run.strategy_revision_id,
        "run_configuration_id": run.run_configuration_id,
        "dataset_revision": run.dataset.revision_id,
        "market_binding_id": market_id,
    }
    if any(descriptor.get(key) != value for key, value in identities.items()):
        raise _invalid("ESSENTIAL_BINDING_IDENTITY_MISMATCH", "/essential_evidence", "The descriptor names another saved run input.")
    fields = descriptor.get("fields")
    if isinstance(fields, dict) and set(fields) - {"entry", "exit"}:
        raise _invalid("INVALID_ESSENTIAL_BINDING", "/essential_evidence/fields", "The descriptor contains an unknown action field.")
    if not isinstance(fields, dict) or set(fields) != {"entry", "exit"}:
        raise _invalid("UNRESOLVED_ESSENTIAL_EVIDENCE", "/essential_evidence/fields", "Bind entry and exit separately.")
    normalized: dict[str, list[dict[str, Any]]] = {}
    for field_name, field in fields.items():
        path = f"/essential_evidence/fields/{field_name}"
        if not isinstance(field, dict):
            raise _invalid("INVALID_ESSENTIAL_BINDING", path, "The field binding must be an object.")
        if field.get("state") != "BOUND" or set(field) != {"state", "essential_dependencies"}:
            code = "UNRESOLVED_ESSENTIAL_EVIDENCE" if field.get("state") == "UNBOUND" else "INVALID_ESSENTIAL_BINDING"
            raise _invalid(code, path, "Each field must be explicitly BOUND with its dependency list.")
        dependencies = field["essential_dependencies"]
        if not isinstance(dependencies, list):
            raise _invalid("INVALID_ESSENTIAL_BINDING", f"{path}/essential_dependencies", "Use a dependency list.")
        seen: set[tuple[str, int]] = set()
        normalized[field_name] = []
        for index, dependency in enumerate(dependencies):
            dep_path = f"{path}/essential_dependencies/{index}"
            if not isinstance(dependency, dict) or set(dependency) != {"series", "offset_buckets"}:
                raise _invalid("INVALID_ESSENTIAL_BINDING", dep_path, "Each dependency needs a series and scheduled offset.")
            series, offset = dependency["series"], dependency["offset_buckets"]
            if series not in {"price", "quote_volume"} or series not in strategy["data_inputs"]:
                raise _invalid("INVALID_ESSENTIAL_BINDING", f"{dep_path}/series", "The series must be declared by the saved strategy.")
            if isinstance(offset, bool) or not isinstance(offset, int) or offset > 0:
                raise _invalid("INVALID_ESSENTIAL_BINDING", f"{dep_path}/offset_buckets", "Use a non-positive whole scheduled offset.")
            pair = (series, offset)
            if pair in seen:
                raise _invalid("INVALID_ESSENTIAL_BINDING", dep_path, "Duplicate dependencies are not allowed.")
            seen.add(pair)
            normalized[field_name].append({"series": series, "offset_buckets": offset})
    return normalized


def _validate_run(strategy: dict[str, Any], run: ReplayInput) -> tuple[str, int, int, dict[str, list[dict[str, Any]]]]:
    if strategy.get("additions") is not False or strategy.get("partial_exits") is not False:
        raise _invalid("UNSUPPORTED_ACTION_SCOPE", "/strategy/action_scope", "P12/1 supports no additions or partial exits.")
    costs = strategy.get("cost_assumptions")
    if not isinstance(costs, dict) or not isinstance(costs.get("source_ref"), str) or not costs["source_ref"]:
        raise _invalid("UNSUPPORTED_COST_ASSUMPTIONS", "/strategy/cost_assumptions/source_ref", "Retain a saved cost source.")
    p06.validate_strategy(strategy)
    if p02._checker.canonical_decimal(strategy["cost_assumptions"]["slippage_rate"]) == 1:
        raise _invalid("UNSUPPORTED_COST_ASSUMPTIONS", "/strategy/cost_assumptions/slippage_rate",
                       "The saved slippage makes a sell fill non-positive.")
    if not run.strategy_revision_id or not run.run_configuration_id or not run.dataset.revision_id:
        raise _invalid("INVALID_REPLAY_IDENTITY", "/identity", "Bind immutable strategy, configuration and dataset revisions.")
    if run.dataset.evidence_class != "SYNTHETIC_FIXTURE":
        raise _invalid("EVIDENCE_CLASS_UNSUPPORTED", "/dataset/evidence_class", "This P13 slice accepts synthetic fixtures only.")
    if isinstance(strategy["invalidation"], dict) and strategy["invalidation"].get("state") != "NOT_REQUESTED":
        raise _invalid("UNSUPPORTED_INVALIDATION", "/strategy/invalidation", "Boolean invalidation is outside P12/1.")
    if run.dataset.qualification != "QUALIFIED" or run.dataset.coverage_complete is not True:
        raise _invalid("DATASET_COVERAGE_UNPROVEN", "/dataset", "P12/1 requires a qualified dataset and proven interval coverage.")
    if not run.dataset.market_binding_id or run.dataset.market_binding_id != p06.market_binding_id(strategy["market"]):
        raise _invalid("MARKET_BINDING_MISMATCH", "/dataset/market_binding_id", "The dataset must match the saved market binding.")
    _utc(run.window_start, "/window_start")
    _utc(run.window_end, "/window_end")
    if run.window_start >= run.window_end or run.window_start.minute % 5 or run.window_start.second or run.window_start.microsecond:
        raise _invalid("INVALID_REPLAY_WINDOW", "/window", "Use a non-empty UTC five-minute window.")
    if not run.dataset.buckets:
        raise _invalid("DATASET_COVERAGE_UNPROVEN", "/dataset/buckets", "The requested interval has no scheduled coverage.")
    schedule = tuple(bucket.bucket_end for bucket in run.dataset.buckets)
    for index, bucket in enumerate(run.dataset.buckets):
        _utc(bucket.bucket_end, f"/dataset/buckets/{index}/bucket_end")
        if bucket.bucket_end.minute % 5 or bucket.bucket_end.second or bucket.bucket_end.microsecond:
            raise _invalid("INVALID_REPLAY_SCHEDULE", f"/dataset/buckets/{index}/bucket_end", "Use scheduled five-minute bucket ends.")
        if index and bucket.bucket_end - schedule[index - 1] != timedelta(minutes=5):
            raise _invalid("INVALID_REPLAY_SCHEDULE", "/dataset/buckets", "Keep every scheduled position, including empty buckets.")
        if bucket.status not in {"COMPLETE_OCCUPIED", "COMPLETE_EMPTY", "INCOMPLETE", "UNQUALIFIED"}:
            raise _invalid("INVALID_REPLAY_BUCKET", f"/dataset/buckets/{index}/status", "Use a recognized P07 bucket status.")
        if bucket.status == "COMPLETE_EMPTY":
            if bucket.price is not None and bucket.price.value is not None:
                raise _invalid("INVALID_REPLAY_BUCKET", f"/dataset/buckets/{index}/price", "A complete empty bucket has no close price.")
            if bucket.quote_volume is None or bucket.quote_volume.value is None or _decimal(str(bucket.quote_volume.value), f"/dataset/buckets/{index}/quote_volume") != 0:
                raise _invalid("INVALID_REPLAY_BUCKET", f"/dataset/buckets/{index}/quote_volume", "A complete empty bucket proves zero quote volume.")
        for series_name, observation in (("price", bucket.price), ("quote_volume", bucket.quote_volume)):
            if observation is None:
                continue
            if observation.value is not None and not isinstance(observation.value, (str, Decimal)):
                raise _invalid("INVALID_REPLAY_NUMBER", f"/dataset/buckets/{index}/{series_name}/value", "Use a decimal string or Decimal value.")
            if observation.available_at is not None:
                _utc(observation.available_at, f"/dataset/buckets/{index}/{series_name}/available_at")
    if schedule[0] > run.window_start or schedule[-1] >= run.window_end:
        raise _invalid("DATASET_COVERAGE_UNPROVEN", "/dataset/buckets", "Coverage must include the whole half-open run window.")
    start_index = schedule.index(run.window_start) if run.window_start in schedule else -1
    if start_index < 0:
        raise _invalid("DATASET_COVERAGE_UNPROVEN", "/dataset/buckets", "The run start must be a scheduled decision point.")
    if start_index < strategy["warmup_buckets"]:
        raise _invalid("DATASET_COVERAGE_UNPROVEN", "/dataset/buckets", "The saved strategy warm-up must be scheduled before the run window.")
    decision_indices = [index for index, moment in enumerate(schedule) if run.window_start <= moment < run.window_end]
    if not decision_indices or decision_indices[-1] != len(schedule) - 1:
        raise _invalid("INVALID_REPLAY_SCHEDULE", "/dataset/buckets", "Include every in-window scheduled point and no exclusive-end point.")
    expected_terminal = run.window_end - timedelta(microseconds=1)
    expected_terminal = expected_terminal.replace(
        minute=expected_terminal.minute // 5 * 5, second=0, microsecond=0,
    )
    if schedule[decision_indices[-1]] != expected_terminal:
        raise _invalid("DATASET_COVERAGE_UNPROVEN", "/dataset/buckets",
                       "Include the final scheduled point inside the half-open run window.")
    for index in decision_indices:
        if run.dataset.buckets[index].status not in _COMPLETE | {"INCOMPLETE", "UNQUALIFIED"}:
            raise _invalid("INVALID_REPLAY_BUCKET", f"/dataset/buckets/{index}/status", "The bucket status is malformed.")
    cash = _decimal(run.initial_cash_quote, "/initial_cash_quote")
    initial_base = _decimal(run.initial_base_amount, "/initial_base_amount")
    initial_basis = _decimal(run.initial_basis_quote, "/initial_basis_quote")
    if cash < 0 or initial_base < 0 or initial_basis < 0:
        raise _invalid("INVALID_INITIAL_ACCOUNT", "/initial_state", "Starting balances and basis cannot be negative.")
    if (initial_base == 0 and initial_basis != 0) or (initial_base > 0 and initial_basis <= 0):
        raise _invalid("INVALID_INITIAL_ACCOUNT", "/initial_state", "An open starting position needs a positive basis; a flat state needs zero basis.")
    if cash == 0 and initial_base == 0:
        raise _invalid("INVALID_INITIAL_ACCOUNT", "/initial_state", "Starting capital or inventory must be positive.")
    return run.dataset.market_binding_id, start_index, decision_indices[-1], _validate_descriptor(strategy, run, run.dataset.market_binding_id)


def _observation_for(bucket: ReplayBucket, series: str) -> p06.Observation | None:
    return bucket.price if series == "price" else bucket.quote_volume


def _essential_reasons(
    dependencies: list[dict[str, Any]], index: int, decision_time: datetime, run: ReplayInput,
) -> tuple[str, ...]:
    reasons: list[str] = []
    for dependency in dependencies:
        position = index + dependency["offset_buckets"]
        if position < 0 or position >= len(run.dataset.buckets):
            reasons.append(f"MISSING_POSITION:{position}")
            continue
        bucket = run.dataset.buckets[position]
        observation = _observation_for(bucket, dependency["series"])
        if bucket.status == "INCOMPLETE":
            reasons.append("COVERAGE_NOT_PROVEN")
        elif bucket.status == "UNQUALIFIED":
            reasons.append("UNQUALIFIED_RECORDS")
        elif observation is None:
            reasons.append(f"MISSING_POSITION:{position}")
        elif observation.market_binding_id != run.dataset.market_binding_id:
            reasons.extend(observation.reasons)
            reasons.append(f"MARKET_BINDING_MISMATCH:{position}")
        elif observation.bucket_end != bucket.bucket_end:
            reasons.extend(observation.reasons)
            reasons.append(f"SCHEDULE_MISMATCH:{position}")
        elif observation.value is None:
            source_reasons = observation.reasons if observation else ()
            reasons.extend(source_reasons or (f"MISSING_{dependency['series'].upper()}:{position}",))
        elif not observation.qualified:
            reasons.extend(observation.reasons)
            reasons.append(f"UNQUALIFIED_{dependency['series'].upper()}:{position}")
        elif observation.available_at is None:
            reasons.extend(observation.reasons)
            reasons.append("AVAILABILITY_UNKNOWN")
        elif observation.available_at > decision_time:
            reasons.extend(observation.reasons)
            reasons.append("LATE_INPUT")
    return tuple(dict.fromkeys(reasons))


def _expression_observations(node: dict[str, Any], position: int) -> tuple[tuple[str, int], ...]:
    """Return primitive observations P06 actually consumes, including both Boolean branches."""
    op = node["op"]
    if op == "price":
        return (("price", position),)
    if op == "quote_volume":
        return (("quote_volume", position),)
    if op == "price_return":
        lookback = node["lookback_buckets"]
        return (("price", position), ("price", position - lookback))
    if op == "relative_volume":
        lookback = node["lookback_buckets"]
        return (("quote_volume", position),) + tuple(
            ("quote_volume", prior) for prior in range(position - lookback, position)
        )
    if op == "lag":
        return _expression_observations(node["value"], position - node["buckets"])
    if op in {"sum", "mean"}:
        return tuple(
            dependency
            for current in range(position - node["buckets"] + 1, position + 1)
            for dependency in _expression_observations(node["value"], current)
        )
    if op == "not":
        return _expression_observations(node["value"], position)
    if op in {"gt", "gte", "lt", "lte", "and", "or"}:
        return tuple(
            dependency
            for child in node["args"]
            for dependency in _expression_observations(child, position)
        )
    return ()


def _mandatory_timing_reasons(
    expression: dict[str, Any], index: int, decision_time: datetime, run: ReplayInput,
) -> tuple[str, ...]:
    reasons: list[str] = []
    for series, position in _expression_observations(expression, index):
        if position < 0 or position >= len(run.dataset.buckets):
            continue
        bucket = run.dataset.buckets[position]
        observation = _observation_for(bucket, series)
        if observation is None or observation.value is None:
            continue
        if (observation.bucket_end > decision_time
                or observation.available_at is not None and observation.available_at > decision_time):
            reasons.append(f"FUTURE_INFORMATION:{position}")
        elif observation.available_at is None:
            reasons.append(f"AVAILABILITY_UNKNOWN:{position}")
    return tuple(dict.fromkeys(reasons))


def _account_mark(bucket: ReplayBucket, moment: datetime, market_id: str, position: int) -> tuple[Decimal | None, tuple[str, ...]]:
    observation = bucket.price
    if bucket.status == "INCOMPLETE":
        return None, tuple(dict.fromkeys((observation.reasons if observation else ()) + ("COVERAGE_NOT_PROVEN",)))
    if bucket.status == "UNQUALIFIED":
        return None, tuple(dict.fromkeys((observation.reasons if observation else ()) + ("UNQUALIFIED_RECORDS",)))
    if observation is None or observation.value is None:
        return None, observation.reasons if observation else ("EMPTY_BUCKET_NO_CLOSE",)
    if observation.market_binding_id != market_id or observation.bucket_end != bucket.bucket_end:
        reason = f"MARKET_BINDING_MISMATCH:{position}" if observation.market_binding_id != market_id else f"SCHEDULE_MISMATCH:{position}"
        return None, tuple(dict.fromkeys(observation.reasons + (reason,)))
    if not observation.qualified:
        return None, observation.reasons or ("UNQUALIFIED_PRICE",)
    if observation.available_at is None:
        return None, observation.reasons + ("AVAILABILITY_UNKNOWN",)
    if observation.available_at > moment:
        return None, observation.reasons + ("LATE_INPUT",)
    try:
        mark = Decimal(observation.value)
    except (DecimalException, TypeError, ValueError):
        return None, observation.reasons + ("INVALID_NUMERIC_INPUT",)
    if not mark.is_finite() or mark <= 0:
        return None, observation.reasons + ("INVALID_NUMERIC_INPUT",)
    return mark, observation.reasons


def _fingerprint(strategy: dict[str, Any], run: ReplayInput) -> str:
    input_record = {
        "profile_version": PROFILE_VERSION,
        "strategy_sha256": p02.sha256_hex(strategy),
        "strategy_revision_id": run.strategy_revision_id,
        "run_configuration_id": run.run_configuration_id,
        "dataset_revision_id": run.dataset.revision_id,
        "dataset_qualification": run.dataset.qualification,
        "coverage_complete": run.dataset.coverage_complete,
        "evidence_class": run.dataset.evidence_class,
        "market_binding_id": run.dataset.market_binding_id,
        "window_start": p02.utc_string(run.window_start),
        "window_end": p02.utc_string(run.window_end),
        "initial_cash_quote": run.initial_cash_quote,
        "initial_base_amount": run.initial_base_amount,
        "initial_basis_quote": run.initial_basis_quote,
        "essential_evidence": run.essential_evidence,
        "buckets": [
            {
                "bucket_end": p02.utc_string(bucket.bucket_end),
                "status": bucket.status,
                "price": _observation_payload(bucket.price),
                "quote_volume": _observation_payload(bucket.quote_volume),
            }
            for bucket in run.dataset.buckets
        ],
    }
    return hashlib.sha256(p02.canonical_bytes(input_record)).hexdigest()


def _observation_payload(observation: p06.Observation | None) -> dict[str, Any] | None:
    if observation is None:
        return None
    return {
        "value": str(observation.value) if observation.value is not None else None,
        "bucket_end": p02.utc_string(observation.bucket_end),
        "market_binding_id": observation.market_binding_id,
        "qualified": observation.qualified,
        "available_at": p02.utc_string(observation.available_at) if observation.available_at else None,
        "reasons": list(observation.reasons),
    }


def calculate_quote_metrics(
    samples: Sequence[dict[str, Any]], initial_capital_quote: Decimal | None, completed_trade_pairs: int,
) -> QuoteMetrics:
    """Calculate only adopted P12 quote metrics from the actual ordered samples."""
    values = [sample["account_value_quote"] for sample in samples]
    final_value = values[-1] if values else None
    gain_available = isinstance(initial_capital_quote, Decimal) and isinstance(final_value, Decimal)
    complete_samples = bool(values) and all(isinstance(value, Decimal) for value in values)
    high_water: Decimal | None = None
    largest_drawdown = Decimal(0)
    if complete_samples:
        with localcontext(p06.NUMERIC):
            for value in values:
                assert isinstance(value, Decimal)
                high_water = value if high_water is None else max(high_water, value)
                largest_drawdown = max(largest_drawdown, high_water - value)
    unavailable_reasons = tuple(dict.fromkeys(
        reason
        for sample in samples if sample["account_value_quote"] is None
        for reason in sample.get("mark_reasons", ())
    ))
    gain_reasons = () if gain_available else unavailable_reasons
    drawdown_reasons = () if complete_samples else unavailable_reasons
    with localcontext(p06.NUMERIC):
        gain_loss = final_value - initial_capital_quote if gain_available else None
    values_by_metric: dict[str, Decimal | int | None] = {
        "gain_loss_quote": gain_loss,
        "completed_trade_pairs": completed_trade_pairs,
        "largest_drawdown_quote": largest_drawdown if complete_samples else None,
    }
    statuses = {
        "gain_loss_quote": "AVAILABLE" if gain_available else "UNAVAILABLE",
        "completed_trade_pairs": "AVAILABLE",
        "largest_drawdown_quote": "AVAILABLE" if complete_samples else "UNAVAILABLE",
    }
    reasons = {
        "gain_loss_quote": gain_reasons,
        "completed_trade_pairs": (),
        "largest_drawdown_quote": drawdown_reasons,
    }
    return QuoteMetrics(values_by_metric, statuses, reasons)


def run_spot_replay(strategy: dict[str, Any], run: ReplayInput) -> ReplayResult:
    """Replay one immutable P06 spot strategy against one qualified P07 schedule.

    P06 values and reasons remain visible. Only an explicit, matching P12 essential
    binding controls action eligibility; this function grants no execution permission.
    """
    market_id, first_index, last_index, essential = _validate_run(strategy, run)
    cash = _decimal(run.initial_cash_quote, "/initial_cash_quote")
    initial_base = _decimal(run.initial_base_amount, "/initial_base_amount")
    initial_basis = _decimal(run.initial_basis_quote, "/initial_basis_quote")
    initial_capital: Decimal | None = None
    base = initial_base
    basis_quote = initial_basis
    position_entry_at: datetime | None = None
    fee_rate = _decimal(strategy["cost_assumptions"]["fee_rate"], "/strategy/cost_assumptions/fee_rate")
    slippage_rate = _decimal(strategy["cost_assumptions"]["slippage_rate"], "/strategy/cost_assumptions/slippage_rate")
    quote_size = _decimal(strategy["sizing"]["amount"], "/strategy/sizing/amount", positive=True)
    if not strategy["cost_assumptions"].get("source_ref"):
        raise _invalid("UNSUPPORTED_COST_ASSUMPTIONS", "/strategy/cost_assumptions/source_ref", "Retain a saved cost source.")
    schedule = tuple(bucket.bucket_end for bucket in run.dataset.buckets)
    prices = tuple(bucket.price for bucket in run.dataset.buckets)
    volumes = tuple(bucket.quote_volume for bucket in run.dataset.buckets)
    samples: list[dict[str, Any]] = []
    events: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    pending: _Order | None = None
    completed_pairs = 0
    reservation_quote = Decimal(0)
    reservation_base = Decimal(0)

    for index in range(first_index, last_index + 1):
        bucket = run.dataset.buckets[index]
        moment = bucket.bucket_end
        if pending is not None:
            mark, mark_reasons = _account_mark(bucket, moment, market_id, index)
            if mark is None:
                events.append({"kind": "ORDER", "at": moment, "status": "FILL_UNAVAILABLE",
                               "side": pending.side, "reasons": mark_reasons,
                               "reservation_released_quote": pending.reserved_quote,
                               "reservation_released_base": pending.reserved_base})
                reservation_quote = Decimal(0)
                reservation_base = Decimal(0)
            elif pending.side == "BUY":
                with localcontext(p06.NUMERIC):
                    fill_price = mark * (Decimal(1) + slippage_rate)
                    if fill_price <= 0:
                        raise _invalid("NON_POSITIVE_FILL", "/strategy/cost_assumptions/slippage_rate", "The saved cost produces a non-positive buy fill.")
                    fee = quote_size * fee_rate
                    acquired = quote_size / fill_price
                    cash -= quote_size + fee
                    base += acquired
                    basis_quote = quote_size + fee
                    position_entry_at = schedule[pending.signal_index]
                events.append({"kind": "ORDER", "at": moment, "status": "BUY_FILLED", "fill_price": fill_price,
                               "base_amount": acquired, "quote_notional": quote_size, "fee_quote": fee,
                               "cash_quote": cash, "base_balance": base})
            else:
                with localcontext(p06.NUMERIC):
                    fill_price = mark * (Decimal(1) - slippage_rate)
                    if fill_price <= 0:
                        raise _invalid("NON_POSITIVE_FILL", "/strategy/cost_assumptions/slippage_rate", "The saved cost produces a non-positive sell fill.")
                    gross = base * fill_price
                    fee = gross * fee_rate
                    realized = gross - fee - basis_quote
                    sold_base = base
                    cash += gross - fee
                    trades.append({"entry_at": position_entry_at,
                                   "entry_origin": "REPLAY_SIGNAL" if position_entry_at else "PREEXISTING_AT_RUN_START",
                                   "exit_at": moment,
                                   "base_amount": sold_base, "entry_basis_quote": basis_quote,
                                   "gross_quote": gross, "exit_fee_quote": fee, "gain_loss_quote": realized})
                    base = Decimal(0)
                    basis_quote = Decimal(0)
                    position_entry_at = None
                    completed_pairs += 1
                events.append({"kind": "ORDER", "at": moment, "status": "SELL_FILLED", "fill_price": fill_price,
                               "base_amount": sold_base, "gross_quote": gross, "fee_quote": fee,
                               "cash_quote": cash, "base_balance": base})
            reservation_quote = Decimal(0)
            reservation_base = Decimal(0)
            pending = None

        mark, mark_reasons = _account_mark(bucket, moment, market_id, index)
        with localcontext(p06.NUMERIC):
            account_value: Decimal | None = cash + base * mark if mark is not None else None
        samples.append({"at": moment, "cash_quote": cash, "base_amount": base,
                        "reserved_quote": reservation_quote, "reserved_base": reservation_base,
                        "account_value_quote": account_value,
                        "mark_price": mark if base else None,
                        "mark_reasons": mark_reasons if mark is None else ()})
        if index == first_index and account_value is not None:
            initial_capital = account_value
        context = p06.EvaluationContext(prices, volumes, schedule, market_id, moment, index)
        entry = p06.evaluate_expression(strategy["entry"], strategy["market"], context)
        exit_result = p06.evaluate_expression(strategy["exit"], strategy["market"], context)
        entry_reasons = _essential_reasons(essential["entry"], index, moment, run)
        exit_reasons = _essential_reasons(essential["exit"], index, moment, run)
        entry_timing = _mandatory_timing_reasons(strategy["entry"], index, moment, run)
        exit_timing = _mandatory_timing_reasons(strategy["exit"], index, moment, run)
        entry_eligible = not entry_reasons and not entry_timing
        exit_eligible = not exit_reasons and not exit_timing
        entry_eligibility_reasons = tuple(dict.fromkeys(entry_reasons + entry_timing))
        exit_eligibility_reasons = tuple(dict.fromkeys(exit_reasons + exit_timing))
        entry_status = ("ESSENTIAL_EVIDENCE_UNAVAILABLE" if entry_reasons else
                        "TIMING_UNAVAILABLE" if entry_timing else "ELIGIBLE")
        exit_status = ("ESSENTIAL_EVIDENCE_UNAVAILABLE" if exit_reasons else
                       "TIMING_UNAVAILABLE" if exit_timing else "ELIGIBLE")
        events.append({"kind": "DECISION", "at": moment,
                       "entry": {"value": entry.value, "reasons": entry.reasons, "eligible": entry_eligible,
                                 "eligibility_status": entry_status,
                                 "eligibility_reasons": entry_eligibility_reasons},
                       "exit": {"value": exit_result.value, "reasons": exit_result.reasons, "eligible": exit_eligible,
                                "eligibility_status": exit_status,
                                "eligibility_reasons": exit_eligibility_reasons}})

        if pending is not None:
            continue
        if base > 0:
            if exit_eligible and exit_result.value == p06.Truth.TRUE:
                if index + 1 > last_index:
                    events.append({"kind": "ORDER", "at": moment, "status": "NO_NEXT_BUCKET", "side": "SELL"})
                    continue
                pending = _Order("SELL", index, index + 1, Decimal(0), base)
                reservation_base = base
                samples[-1]["reserved_base"] = reservation_base
                events.append({"kind": "ORDER", "at": moment, "status": "RESERVED", "side": "SELL",
                               "reserved_base": base, "fill_at": schedule[index + 1]})
            continue
        if entry_eligible and entry.value == p06.Truth.TRUE:
            if index + 1 > last_index:
                events.append({"kind": "ORDER", "at": moment, "status": "NO_NEXT_BUCKET", "side": "BUY"})
                continue
            with localcontext(p06.NUMERIC):
                required_cash = quote_size + quote_size * fee_rate
            if required_cash > cash:
                events.append({"kind": "ORDER", "at": moment, "status": "INSUFFICIENT_CASH",
                               "requested_quote": quote_size, "required_cash_quote": required_cash})
                continue
            pending = _Order("BUY", index, index + 1, required_cash, Decimal(0))
            reservation_quote = required_cash
            samples[-1]["reserved_quote"] = reservation_quote
            events.append({"kind": "ORDER", "at": moment, "status": "RESERVED", "side": "BUY",
                           "reserved_quote": required_cash, "fill_at": schedule[index + 1]})

    quote_metrics = calculate_quote_metrics(samples, initial_capital, completed_pairs)
    metrics = quote_metrics.values
    metric_statuses = quote_metrics.statuses
    metric_reasons = quote_metrics.reasons
    last_observation = run.dataset.buckets[last_index].price
    open_position = None if base == 0 else {
        "base_amount": base,
        "weighted_basis_quote": basis_quote,
        "last_qualified_mark": samples[-1]["mark_price"],
        "last_mark_at": schedule[last_index] if samples[-1]["mark_price"] is not None else None,
        "last_available_at": last_observation.available_at if last_observation and samples[-1]["mark_price"] is not None else None,
    }
    return ReplayResult(_fingerprint(strategy, run), run.dataset.evidence_class,
                        tuple(samples), tuple(events), tuple(trades), metrics,
                        metric_statuses, metric_reasons, open_position)
