"""Evaluation of the actual compiled revision: signal, no-signal and ineligible."""

from __future__ import annotations

import uuid

from edge_os_api.execution.evaluator import evaluate
from edge_os_api.execution.types import canonical_hash

from admission._builders import AGENT_A, NETWORK, WALLET_A
from execution._builders import (
    DECISION_TIME,
    frozen_entry_exit,
    gt_constant,
    iso,
    lt_constant,
    make_inputs,
    relative_volume_gt,
)


def test_signal_decision_persists_lineage_and_is_owner_scoped(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    inputs = make_inputs(["110"], ["5"], position_open=False)

    decision = execution_service.evaluate_and_decide(
        fresh_owner, revision, inputs, agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)

    assert decision.status == "SIGNAL"
    assert decision.operation == "ENTRY"
    assert decision.decision_at == iso(DECISION_TIME)
    assert decision.revision_id == revision.revision_id
    assert decision.content_hash == revision.content_hash
    assert decision.manifest_hash == revision.manifest_hash
    assert decision.market_binding_id == revision.market_binding_id
    assert decision.inputs_hash == inputs.identity()
    assert [rule.rule for rule in decision.rule_results] == ["entry", "exit", "invalidation"]

    saved = execution_service.retrieve_decisions(fresh_owner, agent_id=AGENT_A, wallet_id=WALLET_A)
    assert [item.decision_id for item in saved] == [decision.decision_id]
    # Another owner sees nothing.
    assert execution_service.retrieve_decisions(uuid.uuid4()) == []


def test_false_rule_is_a_no_signal(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    decision = execution_service.evaluate_and_decide(
        fresh_owner, revision, make_inputs(["90"], ["5"], position_open=False),
        agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    assert decision.status == "NO_SIGNAL"
    assert decision.operation is None


def test_unknown_required_observation_is_ineligible_not_no_signal(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit(entry=relative_volume_gt(), exit_=lt_constant(),
                                 data_inputs=("price", "quote_volume"))
    # Zero prior baseline: relative_volume is UNKNOWN with ZERO_BASELINE.
    decision = execution_service.evaluate_and_decide(
        fresh_owner, revision, make_inputs(["100", "100", "100"], ["0", "0", "0"],
                                           position_open=False, position=2),
        agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    assert decision.status == "INELIGIBLE"
    assert decision.operation is None
    assert "ZERO_BASELINE" in decision.reasons


def test_future_observation_is_ineligible(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit()
    decision = execution_service.evaluate_and_decide(
        fresh_owner, revision,
        make_inputs(["110"], ["5"], position_open=False, price_future={0}),
        agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    assert decision.status == "INELIGIBLE"


def test_open_position_uses_exit_rule(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit(entry=gt_constant(), exit_=lt_constant())
    decision = execution_service.evaluate_and_decide(
        fresh_owner, revision, make_inputs(["90"], ["5"], position_open=True),
        agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    assert decision.status == "SIGNAL"
    assert decision.operation == "EXIT"


def test_invalidation_triggers_exit_without_the_exit_rule(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit(exit_=gt_constant("1000"), invalidation=gt_constant("50"))
    decision = execution_service.evaluate_and_decide(
        fresh_owner, revision, make_inputs(["100"], ["5"], position_open=True),
        agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    assert decision.status == "SIGNAL"
    assert decision.operation == "EXIT"
    states = {rule.rule: rule.state for rule in decision.rule_results}
    assert states["exit"] == "FALSE"
    assert states["invalidation"] == "TRUE"


def test_false_exit_with_unrequested_invalidation_is_a_no_signal(execution_service, fresh_owner) -> None:
    revision = frozen_entry_exit(entry=gt_constant(), exit_=lt_constant())
    # Open position, exit rule FALSE, invalidation NOT_REQUESTED.
    decision = execution_service.evaluate_and_decide(
        fresh_owner, revision, make_inputs(["110"], ["5"], position_open=True),
        agent_id=AGENT_A, wallet_id=WALLET_A, network_id=NETWORK)
    assert decision.status == "NO_SIGNAL"
    assert decision.operation is None
    states = {rule.rule: rule.state for rule in decision.rule_results}
    assert states["exit"] == "FALSE"
    assert states["invalidation"] == "NOT_REQUESTED"


def test_frozen_revision_meaning_cannot_change_after_freeze() -> None:
    revision = frozen_entry_exit()
    before = evaluate(revision, make_inputs(["90"], ["5"], position_open=False))
    # Mutating a returned mapping must not change the frozen meaning or identity.
    revision.strategy["entry"] = gt_constant("50")
    after = evaluate(revision, make_inputs(["90"], ["5"], position_open=False))
    assert before.status == "NO_SIGNAL"
    assert after.status == "NO_SIGNAL"
    assert canonical_hash(revision.strategy) == revision.content_hash
