"""Public-seam tests for the deterministic, source-linked report builder."""

from __future__ import annotations

import nansen_fixtures as support
from edge_os_api.nansen_research import NansenReport, NansenTimeout


def _buckets() -> list[dict]:
    starts = support.hourly_starts(25)
    built = []
    for index, item in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else None
        built.append(support.flow_bucket(item, bucket_end=end, is_complete=(index != len(starts) - 1)))
    return built


def _complete_run():
    holders = support.holder_payload(
        [support.holder_row("0xaaa", address_label="Whale"),
         support.holder_row("0xbbb", value_usd=None)],
        is_last_page=True, warnings=["no price data for these holders"],
    )
    flows = support.flow_payload(_buckets(), is_last_page=True,
                                 warnings=["DEX/CEX fields are null for this label"])
    return support.run(support.request(), [
        support.response(200, holders, {"X-Request-Id": "h1"}),
        support.response(200, flows, {"X-Request-Id": "f1"}),
    ])


def test_findings_cover_supported_limited_and_unknown() -> None:
    report = _complete_run().report
    by_code = {finding.code: finding for finding in report.findings}
    assert by_code["HOLDER_INVENTORY"].verdict == "SUPPORTED"
    assert by_code["HOLDER_VALUE_USD"].verdict == "UNAVAILABLE"
    assert by_code["HOLDER_OWNERSHIP_PERCENTAGE"].verdict == "UNRESOLVED"
    assert by_code["FLOW_DEX_CEX"].verdict == "UNAVAILABLE"
    assert by_code["FLOW_COUNTS"].verdict == "UNRESOLVED"
    assert by_code["CONCENTRATION"].verdict == "UNRESOLVED"


def test_every_finding_is_source_linked() -> None:
    report = _complete_run().report
    assert report.source_hashes
    for finding in report.findings:
        assert finding.source_refs
        assert set(finding.source_refs) <= set(report.source_hashes)


def test_limitations_name_the_claim_not_the_question() -> None:
    report = _complete_run().report
    assert report.question == support.QUESTION
    claims = {item.claim for item in report.limitations}
    assert claims == {"concentration", "whole_token_flows"}
    assert all(item.missing_dependency for item in report.limitations)
    assert report.answer_state == "PARTIAL"


def test_a_supported_question_is_not_relabelled_unresolved() -> None:
    question = "How many holder addresses did the provider return?"
    holders = support.holder_payload([support.holder_row("0xaaa")], is_last_page=True)
    run = support.run(support.request(question=question, operations=("holders",)),
                      [support.response(200, holders)])
    assert run.report.question == question
    assert run.report.answer_state == "SUPPORTED_OBSERVATIONS"
    assert run.report.limitations == ()


def test_a_buying_question_is_unresolved_and_explicit() -> None:
    question = "Which wallets bought MOE?"
    holders = support.holder_payload([support.holder_row("0xaaa")], is_last_page=True)
    run = support.run(support.request(question=question, operations=("holders",)),
                      [support.response(200, holders)])
    verdicts = {finding.code: finding.verdict for finding in run.report.findings}
    assert verdicts["BUYING"] == "UNRESOLVED"
    assert run.report.answer_state == "PARTIAL"
    assert run.report.question == question
    assert "buying" in {item.claim for item in run.report.limitations}


def test_a_flow_question_without_flow_records_is_unavailable() -> None:
    question = "What do qualified basic flow records show?"
    holders = support.holder_payload([support.holder_row("0xaaa")], is_last_page=True)
    run = support.run(support.request(question=question, operations=("holders",)),
                      [support.response(200, holders)])
    verdicts = {finding.code: finding.verdict for finding in run.report.findings}
    assert verdicts["FLOW_RECORDS"] == "UNAVAILABLE"
    assert run.report.answer_state == "UNAVAILABLE"
    assert run.report.question == question


def test_a_concentration_question_is_unresolved_not_answered() -> None:
    question = "How concentrated are MOE current holdings?"
    holders = support.holder_payload([support.holder_row("0xaaa")], is_last_page=True)
    run = support.run(support.request(question=question, operations=("holders",)),
                      [support.response(200, holders)])
    verdicts = {finding.code: finding.verdict for finding in run.report.findings}
    assert verdicts["CONCENTRATION"] == "UNRESOLVED"
    assert run.report.answer_state == "PARTIAL"


def test_report_never_claims_buying_or_alpha() -> None:
    report = _complete_run().report
    text = " ".join(finding.statement for finding in report.findings).lower()
    for forbidden in ("purchase", "bought", "profitable", "alpha"):
        assert forbidden not in text
    counts = next(finding for finding in report.findings if finding.code == "FLOW_COUNTS")
    assert "not establish" in counts.statement or "do not establish" in counts.statement


def test_coverage_reports_partial_bucket_state() -> None:
    report = _complete_run().report
    assert report.coverage.expected_buckets == 25
    assert report.coverage.missing_buckets == 0
    assert report.coverage.incomplete_buckets == 1
    assert report.coverage.complete_seconds == 24 * 3600


def test_report_is_deterministic_and_round_trips() -> None:
    first = _complete_run().report
    second = _complete_run().report
    assert first.sha256() == second.sha256()
    assert NansenReport.from_dict(first.to_dict()) == first


def test_a_null_value_usd_stays_unavailable_not_zero() -> None:
    holders = support.holder_payload([support.holder_row("0xaaa", value_usd=None)], is_last_page=True)
    run = support.run(support.request(operations=("holders",)), [support.response(200, holders)])
    value = next(finding for finding in run.report.findings if finding.code == "HOLDER_VALUE_USD")
    assert value.verdict == "UNAVAILABLE"
    assert "not zero" in value.statement


def test_a_stopped_holder_run_reports_the_stop_not_a_missing_request() -> None:
    question = "How many holder addresses did the provider return?"
    page1 = support.holder_payload([support.holder_row("0xaaa")], is_last_page=False)
    run = support.run(support.request(question=question, operations=("holders",)),
                      [support.response(200, page1), NansenTimeout("TIMEOUT", "boom")])
    finding = next(item for item in run.report.findings if item.code == "HOLDER_INVENTORY")
    assert finding.verdict == "UNAVAILABLE"
    assert "not requested" not in finding.statement
    assert "TIMEOUT" in finding.statement
    assert run.report.answer_state == "PARTIAL"


def test_a_stopped_flow_run_reports_the_stop_not_a_missing_request() -> None:
    question = "What do qualified basic flow records show?"
    holders = support.holder_payload([support.holder_row("0xaaa")], is_last_page=True)
    run = support.run(support.request(question=question, operations=("holders", "flows")),
                      [support.response(200, holders), support.raw_response(500, b'{"code": "internal_error"}')])
    finding = next(item for item in run.report.findings if item.code == "FLOW_RECORDS")
    assert finding.verdict == "UNAVAILABLE"
    assert "not requested" not in finding.statement
    assert "internal_error" in finding.statement
    assert run.report.answer_state == "PARTIAL"


def test_a_budget_stop_reports_the_stop_not_a_missing_request() -> None:
    question = "How many holder addresses did the provider return?"
    page1 = support.holder_payload([support.holder_row("0xaaa")], is_last_page=False)
    run = support.run(support.request(question=question, operations=("holders",),
                                      limits=support.limits(max_requests=1)),
                      [support.response(200, page1)])
    finding = next(item for item in run.report.findings if item.code == "HOLDER_INVENTORY")
    assert finding.verdict == "UNAVAILABLE"
    assert "not requested" not in finding.statement
    assert "REQUEST_LIMIT" in finding.statement
    assert run.report.answer_state == "PARTIAL"


def test_a_stopped_flow_run_limitation_names_the_stop_not_a_missing_request() -> None:
    question = "What do qualified basic flow records show?"
    holders = support.holder_payload([support.holder_row("0xaaa")], is_last_page=True)
    run = support.run(support.request(question=question, operations=("holders", "flows")),
                      [support.response(200, holders), support.raw_response(500, b'{"code": "internal_error"}')])
    flow_limit = next(item for item in run.report.limitations if item.claim == "flow_records")
    assert "not requested" not in flow_limit.missing_dependency
    assert "internal_error" in flow_limit.missing_dependency


def test_an_unmatched_question_is_not_marked_supported() -> None:
    holders = support.holder_payload([support.holder_row("0xaaa")], is_last_page=True)
    for question in ("What is MOE's market capitalization?",
                     "Did holder addresses commit fraud?"):
        run = support.run(support.request(question=question, operations=("holders",)),
                          [support.response(200, holders)])
        assert run.report.question == question
        assert run.report.answer_state != "SUPPORTED_OBSERVATIONS"
        assert "question_coverage" in {item.claim for item in run.report.limitations}


def test_a_mixed_question_is_partial_and_preserves_the_supported_count() -> None:
    holders = support.holder_payload([support.holder_row("0xaaa")], is_last_page=True)
    for question in (
        "How many holder addresses did the provider return, and which exchanges listed MOE?",
        "Which exchanges listed MOE, and how many holder addresses did the provider return?",
        "Which exchanges listed MOE; how many holder addresses did the provider return?",
    ):
        run = support.run(support.request(question=question, operations=("holders",)),
                          [support.response(200, holders)])
        assert run.report.answer_state == "PARTIAL"
        assert "question_coverage" in {item.claim for item in run.report.limitations}
        inventory = next(item for item in run.report.findings if item.code == "HOLDER_INVENTORY")
        assert inventory.verdict == "SUPPORTED"
        assert run.report.coverage.holder_rows == 1
