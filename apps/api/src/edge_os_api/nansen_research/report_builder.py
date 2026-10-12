"""Deterministic, source-linked report builder.

The builder turns the evidence package into supported findings, visible coverage
and explicit unknowns. It never invents buying, totals, market conclusions or
alpha, and it never replaces the asked question with a narrower supported one.
The same evidence always yields the same report and the same report hash.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from edge_os_api.nansen_research.models import (
    EVIDENCE_SCHEMA,
    PROVIDER_VERSION,
    REQUEST_SCHEMA,
    REPORT_SCHEMA,
    Coverage,
    Finding,
    Limitation,
    NansenEvidence,
    NansenReport,
    NansenRequest,
)

_PACKAGE = "edge_os_api.nansen_research"

# A small documented keyword map, not a language model. It reads the requested
# claims from the question so the report can state truthfully what it answers.
_CLAIM_KEYWORDS = (
    ("inventory", ("holder", "address", "wallet", "hold", "held")),
    ("concentration", ("concentrat", "distribut", "share of supply", "percentage of supply")),
    ("flows", ("flow", "inflow", "outflow", "netflow", "net flow")),
    ("buying", ("bought", "buy", "purchase", "accumulat", "sold", "sell", "pnl", "profit")),
)

_CLAIM_FINDING_CODES = {
    "inventory": ("HOLDER_INVENTORY", "HOLDER_PAGINATION", "HOLDER_LABELS"),
    "concentration": ("CONCENTRATION",),
    "flows": ("FLOW_CATEGORY", "FLOW_BUCKET_COVERAGE", "FLOW_COUNTS", "FLOW_DEX_CEX", "FLOW_PRICE", "FLOW_RECORDS"),
    "buying": ("BUYING",),
}

_CLAIM_LIMITATIONS = {
    "concentration": ("concentration", "a documented total supply and qualified matching balance units"),
    "flows": ("whole_token_flows", "an all-holder flow output; the selected category is not all holders"),
    "buying": ("buying", "trade or transfer records that evidence purchases"),
}


def classify_question(question: str) -> tuple[str, ...]:
    """The requested claims the question names, by a documented keyword map."""
    text = question.lower()
    return tuple(claim for claim, words in _CLAIM_KEYWORDS if any(word in text for word in words))


def _missing_claim_finding(code: str, noun: str, requested: bool, stop_reason: str | None,
                           refs: tuple[str, ...]) -> Finding:
    """An explicit finding for a named claim with no usable evidence.

    It distinguishes a claim that was never requested from one whose operation was
    requested but produced no usable evidence because the run stopped.
    """
    if not requested:
        statement = f"{noun} records were not requested for this run, so the question cannot be answered."
    elif stop_reason is not None:
        statement = (f"{noun} records were requested, but the run stopped before usable evidence "
                     f"({stop_reason}).")
    else:
        statement = f"{noun} records were requested but produced no usable evidence."
    return Finding(code=code, verdict="UNAVAILABLE", statement=statement,
                   source_refs=refs, limitations=())


def _answer_state(evidence: NansenEvidence, claims: tuple[str, ...], findings: list[Finding]) -> str:
    """A truthful state for the adopted question under the returned evidence."""
    verdict_by_code = {finding.code: finding.verdict for finding in findings}
    if not claims:
        if evidence.holder is None and evidence.flows is None:
            return "PARTIAL" if evidence.attempts > 0 else "UNAVAILABLE"
        return "PARTIAL" if evidence.stop_reason is not None else "SUPPORTED_OBSERVATIONS"
    answered = False
    unresolved = False
    for claim in claims:
        verdicts = [verdict_by_code[code] for code in _CLAIM_FINDING_CODES[claim] if code in verdict_by_code]
        if set(verdicts) & {"SUPPORTED", "LIMITED"}:
            answered = True
        if set(verdicts) & {"UNRESOLVED", "UNAVAILABLE"}:
            unresolved = True
    if not answered:
        return "PARTIAL" if evidence.stop_reason is not None else "UNAVAILABLE"
    if unresolved or evidence.stop_reason is not None:
        return "PARTIAL"
    return "SUPPORTED_OBSERVATIONS"


def _values(items: list[str | None]) -> list[Decimal]:
    out: list[Decimal] = []
    for item in items:
        if item is None:
            continue
        try:
            out.append(Decimal(item))
        except InvalidOperation:  # pragma: no cover - extraction already validated the text
            continue
    return out


def _has_fractional(values: list[Decimal]) -> bool:
    return any(value != value.to_integral_value() for value in values)


def _has_negative(values: list[Decimal]) -> bool:
    return any(value < 0 for value in values)


def _refs(evidence: NansenEvidence, operation: str) -> tuple[str, ...]:
    return tuple(source.response_sha256 for source in evidence.sources
                 if source.operation == operation and source.response_sha256)


def _holder_findings(evidence: NansenEvidence) -> list[Finding]:
    holder = evidence.holder
    assert holder is not None
    rows = list(holder.rows)
    refs = _refs(evidence, "holders")
    findings: list[Finding] = []

    if rows:
        findings.append(Finding(
            code="HOLDER_INVENTORY", verdict="SUPPORTED",
            statement=(f"{len(rows)} address records returned in provider descending balance order; "
                       "an address can be a contract or an account, not a distinct person."),
            source_refs=refs, limitations=()))
    else:
        findings.append(Finding(
            code="HOLDER_INVENTORY", verdict="UNAVAILABLE",
            statement=("no holder records were returned; an empty or fully filtered response "
                       "does not prove zero holders."),
            source_refs=refs, limitations=()))

    if holder.pagination_is_last_page is True:
        pagination = ("the provider reports the last page; the returned distinct-address count still "
                      "depends on the applied filters and is not the whole population.")
    else:
        pagination = ("the last collected page is not the provider's last page; the total population and "
                      "uncollected rows are unknown, so this page is never 100 percent.")
    limitations: tuple[str, ...] = ()
    if holder.duplicate_addresses:
        limitations = ("duplicate addresses were returned",)
        pagination += f" Duplicate addresses were seen: {', '.join(holder.duplicate_addresses)}."
    findings.append(Finding(code="HOLDER_PAGINATION", verdict="LIMITED", statement=pagination,
                            source_refs=refs, limitations=limitations))

    labelled = [row for row in rows if row.address_label]
    if labelled:
        findings.append(Finding(
            code="HOLDER_LABELS", verdict="LIMITED",
            statement=("provider address classifications are retained; labelled categories overlap and are "
                       "not disjoint groups, and historical classification is unknown."),
            source_refs=refs, limitations=()))
    else:
        findings.append(Finding(
            code="HOLDER_LABELS", verdict="UNKNOWN",
            statement="no address labels were returned; classification stays unknown.",
            source_refs=refs, limitations=()))

    ownership = [row.ownership_percentage for row in rows]
    if any(value is not None for value in ownership):
        findings.append(Finding(
            code="HOLDER_OWNERSHIP_PERCENTAGE", verdict="UNRESOLVED",
            statement=("raw ownership_percentage text is retained; its denominator and scaling are "
                       "unqualified, so it is not a concentration percentage."),
            source_refs=refs, limitations=()))
    else:
        findings.append(Finding(
            code="HOLDER_OWNERSHIP_PERCENTAGE", verdict="UNAVAILABLE",
            statement="all ownership_percentage values are null.",
            source_refs=refs, limitations=()))

    if any(row.token_amount is not None for row in rows):
        findings.append(Finding(
            code="HOLDER_TOKEN_AMOUNT_UNITS", verdict="UNRESOLVED",
            statement=("raw token_amount text is retained without scaling; no physical balance or amount "
                       "is qualified."),
            source_refs=refs, limitations=()))
    else:
        findings.append(Finding(
            code="HOLDER_TOKEN_AMOUNT_UNITS", verdict="UNAVAILABLE",
            statement="all token_amount values are null.",
            source_refs=refs, limitations=()))

    if any(row.value_usd is not None for row in rows):
        findings.append(Finding(
            code="HOLDER_VALUE_USD", verdict="LIMITED",
            statement="some value_usd values are present; they stay provider-reported and unqualified.",
            source_refs=refs, limitations=()))
    else:
        findings.append(Finding(
            code="HOLDER_VALUE_USD", verdict="UNAVAILABLE",
            statement=("all value_usd values are null with no-price warnings; null is not zero and does not "
                       "prove a zero balance or value."),
            source_refs=refs, limitations=()))
    return findings


def _flow_findings(evidence: NansenEvidence, label: str) -> list[Finding]:
    flows = evidence.flows
    assert flows is not None
    refs = _refs(evidence, "flows")
    findings: list[Finding] = []

    findings.append(Finding(
        code="FLOW_CATEGORY", verdict="LIMITED",
        statement=(f"flows cover the selected provider category {label!r}; this is not an all-holder flow "
                   "output."),
        source_refs=refs, limitations=()))
    seconds = ("complete coverage is unavailable because intervals conflict"
               if flows.complete_seconds is None else f"{flows.complete_seconds} complete seconds")
    findings.append(Finding(
        code="FLOW_BUCKET_COVERAGE", verdict="LIMITED",
        statement=(f"{len(flows.buckets)} buckets returned for {len(flows.expected_starts)} expected starts; "
                   f"{len(flows.missing_starts)} missing and {len(flows.incomplete_starts)} incomplete; "
                   f"{seconds}."),
        source_refs=refs, limitations=tuple(flows.missing_starts)))

    counts = _values([bucket.total_inflows_count for bucket in flows.buckets]
                     + [bucket.total_outflows_count for bucket in flows.buckets])
    if counts:
        qualifier = []
        if _has_fractional(counts):
            qualifier.append("fractional values are present")
        if _has_negative(counts):
            qualifier.append("negative values are present")
        detail = ("; " + ", ".join(qualifier)) if qualifier else ""
        findings.append(Finding(
            code="FLOW_COUNTS", verdict="UNRESOLVED",
            statement=("total_inflows_count and total_outflows_count do not establish event counts, signed "
                       f"amounts or net buying{detail}."),
            source_refs=refs, limitations=()))
    else:
        findings.append(Finding(
            code="FLOW_COUNTS", verdict="UNAVAILABLE",
            statement="all flow count values are null.",
            source_refs=refs, limitations=()))

    dex_cex = [bucket.total_inflows_dex for bucket in flows.buckets] + \
              [bucket.total_outflows_dex for bucket in flows.buckets] + \
              [bucket.total_inflows_cex for bucket in flows.buckets] + \
              [bucket.total_outflows_cex for bucket in flows.buckets]
    if any(value is not None for value in dex_cex):
        findings.append(Finding(
            code="FLOW_DEX_CEX", verdict="LIMITED",
            statement="DEX/CEX quantities are populated only for the exchange label.",
            source_refs=refs, limitations=()))
    else:
        findings.append(Finding(
            code="FLOW_DEX_CEX", verdict="UNAVAILABLE",
            statement="all DEX/CEX quantity fields are null; null stays unavailable and never zero.",
            source_refs=refs, limitations=()))

    if any(bucket.price_usd is not None for bucket in flows.buckets):
        findings.append(Finding(
            code="FLOW_PRICE", verdict="UNRESOLVED",
            statement=("price_usd is a daily median, or the latest spot price for the current day; it is not "
                       "an hourly historical price at the bucket end."),
            source_refs=refs, limitations=()))
    else:
        findings.append(Finding(
            code="FLOW_PRICE", verdict="UNAVAILABLE",
            statement="all flow price values are null.",
            source_refs=refs, limitations=()))
    return findings


def build_report(request: NansenRequest, evidence: NansenEvidence) -> NansenReport:
    """Build the deterministic report bound to the exact evidence package."""
    claims = classify_question(request.question)
    findings: list[Finding] = []
    if evidence.holder is not None:
        findings.extend(_holder_findings(evidence))
    if evidence.flows is not None:
        findings.extend(_flow_findings(evidence, request.flow_query.label))

    all_refs = tuple(source.response_sha256 for source in evidence.sources if source.response_sha256)

    if "concentration" in claims:
        findings.append(Finding(
            code="CONCENTRATION", verdict="UNRESOLVED",
            statement=("concentration percentages are unresolved; they need a documented total supply and "
                       "qualified matching balance units."),
            source_refs=all_refs, limitations=()))
    if "buying" in claims:
        findings.append(Finding(
            code="BUYING", verdict="UNRESOLVED",
            statement=("the returned holder and flow observations do not evidence buying; a purchase or "
                       "accumulation claim needs trade or transfer records."),
            source_refs=all_refs, limitations=()))
    requested = set(request.operations)
    if "flows" in claims and evidence.flows is None:
        findings.append(_missing_claim_finding("FLOW_RECORDS", "flow", "flows" in requested,
                                               evidence.stop_reason, all_refs))
    if "inventory" in claims and evidence.holder is None:
        findings.append(_missing_claim_finding("HOLDER_INVENTORY", "holder", "holders" in requested,
                                               evidence.stop_reason, all_refs))

    limitations: tuple[Limitation, ...] = tuple(
        Limitation(claim=name, missing_dependency=dependency)
        for claim in ("concentration", "flows", "buying")
        if claim in claims
        for (name, dependency) in (_CLAIM_LIMITATIONS[claim],)
    )
    if "flows" in claims and evidence.flows is None:
        if "flows" not in requested:
            flow_missing = "a flow request; flow records were not requested"
        elif evidence.stop_reason is not None:
            flow_missing = (f"flow records were requested but the run stopped before usable evidence "
                            f"({evidence.stop_reason})")
        else:
            flow_missing = "flow records were requested but produced no usable evidence"
        limitations = limitations + (Limitation(claim="flow_records", missing_dependency=flow_missing),)
    answer_state = _answer_state(evidence, claims, findings)

    holder_rows = len(evidence.holder.rows) if evidence.holder is not None else 0
    flow_buckets = len(evidence.flows.buckets) if evidence.flows is not None else 0
    expected = len(evidence.flows.expected_starts) if evidence.flows is not None else 0
    missing = len(evidence.flows.missing_starts) if evidence.flows is not None else 0
    incomplete = len(evidence.flows.incomplete_starts) if evidence.flows is not None else 0
    complete_seconds = evidence.flows.complete_seconds if evidence.flows is not None else 0
    coverage = Coverage(
        attempts=evidence.attempts,
        pages=evidence.pages,
        holder_rows=holder_rows,
        flow_buckets=flow_buckets,
        expected_buckets=expected,
        missing_buckets=missing,
        incomplete_buckets=incomplete,
        complete_seconds=complete_seconds,
        pagination_is_last_page=evidence.holder.pagination_is_last_page if evidence.holder is not None else None,
        stop_reason=evidence.stop_reason,
    )

    engine = {
        "package": _PACKAGE,
        "provider_version": PROVIDER_VERSION,
        "api_schema_version": evidence.api_schema_version,
        "profile_version": evidence.profile_version,
        "conventions_version": evidence.conventions_version,
        "request_schema": REQUEST_SCHEMA,
        "evidence_schema": EVIDENCE_SCHEMA,
        "report_schema": REPORT_SCHEMA,
    }

    return NansenReport(
        question=request.question,
        token_address=request.token_address,
        token_symbol=request.token_symbol,
        network=request.network,
        chain_id=request.chain_id,
        window=request.window,
        request_sha256=request.sha256(),
        answer_state=answer_state,
        findings=tuple(findings),
        limitations=limitations,
        coverage=coverage,
        unknowns=evidence.unknowns,
        source_hashes=tuple(source.response_sha256 for source in evidence.sources if source.response_sha256),
        engine=engine,
    )
