"""One original transaction per admitted action: prepare, persist, sign, validate, persist, broadcast once.

This is the application seam for the original-action lifecycle (#58 ORIGINAL-LOCAL). It drives injected clients
in a fixed order and saves each stage through the caller's journal before the next external effect:

    route quote + nonce → PREPARED → SIGN_REQUESTED → stop/expiry recheck → signer
    → signed bytes validated → SIGNED (bytes + Keccak hash) → BROADCAST_REQUESTED → recheck → one broadcast
    → BROADCAST_RETURNED

Nothing is retried, re-quoted, re-nonced, re-fee'd or re-signed, and no second action exists. A failed save stops
the sequence before the next call. Anything after a signer call that is not a definite refusal keeps the original
liability (`SUBMISSION_POSSIBLE`); only the independent receipt reconciliation can settle it.

Three identities stay distinct: the P20 `candidate_hash` (application SHA-256 of the normalized candidate), the
`transaction_hash` (Keccak-256 of the entire signed serialization, never `TypedTransaction.hash()`, which is the
signing preimage) and the provider references (signer request id, broadcast reply). This module holds no key and
signs nothing; it validates bytes an injected signer returns.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from eth_account import Account
from eth_account.typed_transactions import TypedTransaction
from eth_utils import keccak
from hexbytes import HexBytes
from sqlalchemy import select
from sqlalchemy.orm import Session

from edge_os_api.admission.types import AssetAmount, parse_utc
from edge_os_api.execution.transport import PreparedSubmission, TransportOutcome
from edge_os_api.kuru_flow import (
    AdapterError,
    ApprovedAdapterConfiguration,
    ObservationInput,
    ObservationState,
    ObservationVerdict,
    PreparationOutcome,
    ResponseProvenance,
    normalize_observation,
    prepare_unsigned_transaction,
)
from edge_os_api.wallet_setup.persistence import WalletSetupEventRow, load_setup

if TYPE_CHECKING:
    from edge_os_api.execution.operating_release import BoundRelease

SCHEMA = "edge-os.original-transaction/1"
TRANSPORT_ID = "original-transaction/1"
EVIDENCE_CLASS = "AUTHORED_RECORDING"
SIGNED_BYTES_LIMIT = 8192
EIP1559_TYPE = 2
TRANSFER_TOPIC = "0x" + keccak(b"Transfer(address,address,uint256)").hex()
BALANCE_OF_SELECTOR = "0x" + keccak(b"balanceOf(address)")[:4].hex()
DECIMALS_SELECTOR = "0x" + keccak(b"decimals()")[:4].hex()
NATIVE_SUFFIX = "/native"
_HEX = re.compile(r"0x(?:[0-9a-fA-F]{2})+")
_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_TX_HASH = re.compile(r"0x[0-9a-fA-F]{64}")
_INDEXED_ADDRESS = re.compile(r"0x0{24}[0-9a-f]{40}")


class JournalError(Exception):
    """The original stage could not be saved. No later external call is made."""


class ReplyLost(Exception):
    """An injected client made (or may have made) its effect and its reply did not arrive."""


class RpcError(Exception):
    """A JSON-RPC error reply. It proves nothing about whether an effect happened."""


class RouteQuoteClient(Protocol):
    def quote(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


class SignerClient(Protocol):
    def rpc(self, wallet_id: str, body: Mapping[str, Any]) -> Mapping[str, Any]: ...


class RpcClient(Protocol):
    def call(self, method: str, params: list[Any]) -> Any: ...


@dataclass(frozen=True)
class OriginalClients:
    """The injected clients. The broadcast and observation RPC clients are separate on purpose."""

    route: RouteQuoteClient
    signer: SignerClient | None
    broadcast: RpcClient
    observer: RpcClient
    signer_for_attempt: Callable[[PreparedSubmission], SignerClient] | None = None
    begin_attempt: Callable[[PreparedSubmission], None] | None = None


@dataclass(frozen=True)
class RouteProfile:
    """The approved route constants for one network. Authored for local use; never a qualified deployment."""

    chain_id: int
    entrypoint: str
    method: str
    selector: str
    program_hex: str
    fee_bps: int
    referrer_fee_bps: int
    fee_collector: str
    referrer: str
    is_in_token_fee: bool
    min_output_bps: int
    max_quote_age_seconds: int
    max_input_age_seconds: int
    gas_limit: int
    max_fee_per_gas: int
    max_priority_fee_per_gas: int

    @classmethod
    def from_mapping(cls, values: Mapping[str, Any]) -> "RouteProfile":
        return cls(**{name: values[name] for name in cls.__dataclass_fields__})


@dataclass(frozen=True)
class Leg:
    asset_id: str
    token: str
    decimals: int
    raw: int


@dataclass(frozen=True)
class OriginalContext:
    """Everything the original transaction binds, from the verified owner and the saved job, intent and approval."""

    owner_id: str
    agent_id: str
    wallet_id: str
    wallet_address: str
    network_id: str
    chain_id: int
    identity: dict[str, Any]
    action_id: str
    payload_hash: str
    operation: str
    sell: Leg
    buy: Leg
    gas_asset_id: str
    gas_cap_raw: int
    allowance_raw: int
    decision_slot: dt.datetime
    intent_expires_at: dt.datetime
    mandate_expires_at: str


def signing_request_key(transaction: Mapping[str, Any]) -> str:
    """The identity of one exact signing request body (`params.transaction`)."""
    encoded = json.dumps(dict(transaction), sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def wallet_address(session: Session, owner_id: uuid.UUID, agent_id: str, wallet_id: str) -> str | None:
    """The provider-reported address bound to the confirmed wallet, read from the saved setup evidence."""
    setup = load_setup(session, owner_id, agent_id, lock=False)
    if setup is None or setup.wallet_id != wallet_id:
        return None
    events = session.execute(select(WalletSetupEventRow).where(
        WalletSetupEventRow.setup_id == setup.setup_id, WalletSetupEventRow.owner_id == owner_id,
        WalletSetupEventRow.event_type.in_(("WALLET_BOUND", "RECONCILED")))
        .order_by(WalletSetupEventRow.sequence)).scalars().all()
    addresses = set()
    for event in events:
        evidence = event.content.get("evidence") if isinstance(event.content.get("evidence"), dict) else event.content
        if event.content.get("wallet_id", wallet_id) == wallet_id and evidence.get("address"):
            addresses.add(str(evidence["address"]))
    if len(addresses) != 1:
        return None
    address = addresses.pop()
    return address if _ADDRESS.fullmatch(address) else None


def token_of(asset_id: str) -> str | None:
    """The ERC-20 address in an `{network}/{address}` asset id; None for native MON."""
    if asset_id.endswith(NATIVE_SUFFIX):
        return None
    suffix = asset_id.rsplit("/", 1)[-1]
    return suffix if _ADDRESS.fullmatch(suffix) else None


def _iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat()


def hex_quantity(value: Any) -> int | None:
    if isinstance(value, str) and re.fullmatch(r"0x(?:0|[1-9a-fA-F][0-9a-fA-F]*)", value):
        return int(value, 16)
    return None


def is_signer_refusal(reply: Any) -> bool:
    """Only an explicit error envelope with no `data` proves the signer refused; nothing else does."""
    return (isinstance(reply, Mapping) and isinstance(reply.get("error"), Mapping) and "data" not in reply)


def abi_word(value: Any) -> int | None:
    """An unsigned integer from one ABI-encoded 32-byte `DATA` word (`eth_call` result, log data), else None."""
    if isinstance(value, str) and re.fullmatch(r"0x[0-9a-fA-F]{64}", value):
        return int(value, 16)
    return None


def validate_signed(signed_hex: Any, unsigned: Mapping[str, Any], wallet: str) -> tuple[str | None, list[str]]:
    """Validate injected signed bytes against the frozen unsigned transaction and wallet.

    Returns the Keccak-256 hash of the entire signed serialization and no reasons, or no hash and the reasons.
    Only EIP-1559 (type 2) is supported; everything else is refused rather than interpreted.
    """
    if not isinstance(signed_hex, str) or not _HEX.fullmatch(signed_hex):
        return None, ["SIGNED_BYTES_MALFORMED"]
    raw = bytes.fromhex(signed_hex[2:])
    if len(raw) > SIGNED_BYTES_LIMIT:
        return None, ["SIGNED_BYTES_OVERSIZE"]
    if raw[0] != EIP1559_TYPE:
        return None, ["TRANSACTION_TYPE_UNSUPPORTED"]
    try:
        decoded = TypedTransaction.from_bytes(HexBytes(raw))
        fields = decoded.as_dict()
        sender = Account.recover_transaction(raw)
        canonical = decoded.encode() == raw
    except Exception:  # noqa: BLE001 - untrusted bytes: any decoder or recovery failure is a refusal
        return None, ["SIGNED_BYTES_MALFORMED"]
    reasons = []
    if not canonical:
        reasons.append("SIGNED_BYTES_NON_CANONICAL")
    expected = {"chainId": unsigned["chain_id"], "nonce": unsigned["nonce"], "value": unsigned["value"],
                "gas": unsigned["gas_limit"], "maxFeePerGas": unsigned["max_fee_per_gas"],
                "maxPriorityFeePerGas": unsigned["max_priority_fee_per_gas"]}
    for name, value in expected.items():
        if fields.get(name) != value:
            reasons.append(f"SIGNED_{name.upper()}_MISMATCH")
    if HexBytes(fields.get("to") or b"").hex().lower() != HexBytes(unsigned["to"]).hex().lower():
        reasons.append("SIGNED_TO_MISMATCH")
    if bytes(fields.get("data") or b"") != bytes(HexBytes(unsigned["data"])):
        reasons.append("SIGNED_DATA_MISMATCH")
    if tuple(fields.get("accessList") or ()) != ():
        reasons.append("SIGNED_ACCESS_LIST_NOT_EMPTY")
    if sender.lower() != wallet.lower():
        reasons.append("SIGNED_SENDER_MISMATCH")
    if reasons:
        return None, reasons
    return "0x" + keccak(raw).hex(), []


class OriginalTransactionTransport:
    """The original-transaction transport for one admitted action. Used once, under the existing claim."""

    transport_id = TRANSPORT_ID

    def __init__(self, context: OriginalContext, clients: OriginalClients, profile: RouteProfile, *,
                 controls: Callable[[], list[str]], clock: Callable[[], dt.datetime],
                 approved_route: ApprovedAdapterConfiguration | None = None,
                 binding: BoundRelease | None = None, synthetic_bindings: Mapping[str, str] | None = None) -> None:
        self._context, self._clients, self._profile = context, clients, profile
        self._controls, self._clock = controls, clock
        self._approved_route = (None if approved_route is None else
                                ApprovedAdapterConfiguration.model_validate(approved_route.model_dump(mode="json")))
        self._binding = binding
        self._synthetic_bindings = None if synthetic_bindings is None else dict(synthetic_bindings)
        if binding is not None:
            self._approved_route = ApprovedAdapterConfiguration.model_validate(binding.release.content()["route"])

    def original_references(self, prepared: PreparedSubmission) -> dict[str, Any]:
        """IC06 keys, saved with the IN_FLIGHT attempt. The chain identities follow in `original_transaction`."""
        return {"schema_version": "edge-os.original-transaction-references/1", "transport_id": TRANSPORT_ID,
                "evidence_class": self._evidence_class(), "signing_request_id": None, "nonce": None, "fee_envelope": None,
                "unsigned_bytes": None, "signed_bytes": None, "transaction_hash": None, "provider_reference": None,
                "absent_reason": "RECORDED_IN_ORIGINAL_TRANSACTION"}

    def submit(self, prepared: PreparedSubmission) -> TransportOutcome:
        raise JournalError("the original transaction needs a journal; use submit_original")

    # ------------------------------------------------------------------------------- lifecycle

    def submit_original(self, prepared: PreparedSubmission,
                        journal: Callable[[str, dict[str, Any]], None]) -> TransportOutcome:
        context = self._context
        if (prepared.action_id, prepared.payload_hash, prepared.wallet_id, prepared.owner_id,
                prepared.network_id, prepared.operation) != (
                context.action_id, context.payload_hash, context.wallet_id, context.owner_id,
                context.network_id, context.operation):
            return self._unsent(journal, "PREPARED_SUBMISSION_MISMATCH")
        if self._clients.signer_for_attempt is not None and not prepared.attempt_id:
            return self._unsent(journal, "SAVED_ATTEMPT_REQUIRED")
        if self._clients.begin_attempt is not None:
            try:
                self._clients.begin_attempt(prepared)
            except RpcError:
                return self._unsent(journal, "SAVED_ATTEMPT_UNAVAILABLE")
        prepared_values, refusal = self._prepare(prepared)
        if refusal is not None:
            return self._unsent(journal, refusal, prepared_values)
        assert prepared_values is not None
        try:
            journal("PREPARED", prepared_values)
        except JournalError:
            return TransportOutcome(outcome="DEFINITELY_UNSENT", detail="PERSISTENCE_FAILED_BEFORE_SIGNING")
        unsigned = prepared_values["unsigned"]
        try:
            journal("SIGN_REQUESTED", {})
        except JournalError:
            return TransportOutcome(outcome="DEFINITELY_UNSENT", detail="PERSISTENCE_FAILED_BEFORE_SIGNING")
        # After the save, immediately before the signer call: a slow save never grants a grace interval.
        stop = self._recheck()
        if stop is not None:
            return self._unsent(journal, stop)

        try:
            signer = (self._clients.signer_for_attempt(prepared) if self._clients.signer_for_attempt is not None
                      else self._clients.signer)
            if signer is None:
                return self._unsent(journal, "SIGNER_UNAVAILABLE")
            reply = signer.rpc(context.wallet_id, prepared_values["signing_request"]["body"])
        except (ReplyLost, TimeoutError, OSError, RpcError):
            return self._possible(journal, "SIGNING_UNKNOWN")
        if is_signer_refusal(reply):
            return self._unsent(journal, "SIGNER_REFUSED")
        data = reply.get("data") if isinstance(reply, Mapping) else None
        signed_hex = data.get("signed_transaction") if isinstance(data, Mapping) else None
        if signed_hex is None:
            # Not a recognized refusal and no usable bytes: a signature may still exist, so the liability stays.
            return self._possible(journal, "SIGNED_RESPONSE_REJECTED", {"reasons": ["SIGNER_REPLY_UNRECOGNIZED"]})
        if data.get("encoding") != "rlp":
            return self._possible(journal, "SIGNED_RESPONSE_REJECTED", {"reasons": ["SIGNED_ENCODING_UNSUPPORTED"]})
        transaction_hash, reasons = validate_signed(signed_hex, unsigned, context.wallet_address)
        if transaction_hash is None:
            return self._possible(journal, "SIGNED_RESPONSE_REJECTED", {"reasons": reasons})
        signed = bytes.fromhex(signed_hex[2:])
        try:
            journal("SIGNED", {"signed_bytes": signed_hex, "transaction_hash": transaction_hash,
                               "signed_bytes_sha256": "sha256:" + hashlib.sha256(signed).hexdigest(),
                               "signed_bytes_length": len(signed)})
        except JournalError:
            return TransportOutcome(outcome="SUBMISSION_POSSIBLE", detail="PERSISTENCE_FAILED_AFTER_SIGNING")
        try:
            journal("BROADCAST_REQUESTED", {})
        except JournalError:
            return TransportOutcome(outcome="SUBMISSION_POSSIBLE", detail="PERSISTENCE_FAILED_AFTER_SIGNING")
        # After the save, immediately before the send: a slow save never grants a grace interval.
        stop = self._recheck()
        if stop is not None:
            return self._possible(journal, f"STOPPED_AFTER_SIGNING:{stop}")

        try:
            returned = self._clients.broadcast.call("eth_sendRawTransaction", [signed_hex])
        except (ReplyLost, TimeoutError, OSError):
            return self._possible(journal, "BROADCAST_UNKNOWN")
        except RpcError:
            # Provider error text is never saved or shown: it can echo the request, including the signed bytes.
            return self._possible(journal, "BROADCAST_ERROR")
        if not isinstance(returned, str) or returned.lower() != transaction_hash:
            # A reply other than our own hash is never kept: even a hash-shaped one can be a slice of the signed bytes.
            return self._possible(journal, "BROADCAST_HASH_MISMATCH")
        return self._possible(journal, "BROADCAST_RETURNED", {"broadcast_returned": returned.lower()})

    # ------------------------------------------------------------------------------- stages

    def _prepare(self, prepared: PreparedSubmission) -> tuple[dict[str, Any] | None, str | None]:
        context, profile = self._context, self._profile
        refusal = self._release_problem()
        if refusal is not None:
            return None, refusal
        if context.chain_id != profile.chain_id:
            return None, "ROUTE_NETWORK_UNSUPPORTED"
        if not context.sell.token or not context.buy.token:
            return None, "NATIVE_TRADING_UNSUPPORTED"
        if profile.gas_limit * profile.max_fee_per_gas > context.gas_cap_raw:
            return None, "FEE_EXCEEDS_GAS_RESERVATION"
        now = self._clock()
        if now >= context.intent_expires_at:
            return None, "INTENT_EXPIRED"
        if self._approved_route is not None:
            route = self._approved_route
            if (route.network_id, route.input_asset.asset_id, route.input_asset.decimals,
                    route.output_asset.asset_id, route.output_asset.decimals, route.recipient.lower(),
                    route.approved_input_raw, route.approved_allowance_raw) != (
                    context.network_id, context.sell.asset_id, context.sell.decimals,
                    context.buy.asset_id, context.buy.decimals, context.wallet_address.lower(),
                    str(context.sell.raw), str(context.allowance_raw)):
                return None, "APPROVED_ROUTE_BINDING_MISMATCH"
        envelope: dict[str, Any] = {
            "schema": SCHEMA, "evidence_class": self._evidence_class(), "transport_id": TRANSPORT_ID, **context.identity,
            "owner_id": context.owner_id, "agent_id": context.agent_id, "wallet_id": context.wallet_id,
            "wallet_address": context.wallet_address, "network_id": context.network_id,
            "chain_id": context.chain_id, "action_id": context.action_id, "payload_hash": context.payload_hash,
            "operation": context.operation, "attempt_id": prepared.attempt_id,
            "sell": {"asset_id": context.sell.asset_id, "token": context.sell.token,
                     "decimals": context.sell.decimals, "raw": str(context.sell.raw)},
            "buy": {"asset_id": context.buy.asset_id, "token": context.buy.token,
                    "decimals": context.buy.decimals, "raw": str(context.buy.raw)},
            "gas_asset_id": context.gas_asset_id}
        if self._binding is not None:
            from edge_os_api.execution.operating_release import release_sha256

            gas = self._binding.release.content()["gas"]
            if (profile.gas_limit, profile.max_fee_per_gas, profile.max_priority_fee_per_gas) != (
                    gas["gas_limit"], gas["max_fee_per_gas"], gas["max_priority_fee_per_gas"]):
                return envelope, "RELEASE_GAS_MISMATCH"
            envelope.update(binding_sha256=self._binding.sha256,
                            release_sha256=release_sha256(self._binding.release), prepared_at=_iso(now))
            released = self._binding.release.content()
            envelope.update(scope=released["purpose"], release_id=released["release_id"],
                approved_minimum={"asset_id": released["route"]["output_asset"]["asset_id"],
                    "decimals": released["route"]["output_asset"]["decimals"],
                    "raw": released["route"]["approved_min_output_raw"]})
        try:
            response = self._clients.route.quote({"chain_id": context.chain_id, "sell_token": context.sell.token,
                                                  "buy_token": context.buy.token, "amount": str(context.sell.raw),
                                                  "user": context.wallet_address})
        except (ReplyLost, TimeoutError, OSError, RpcError):
            return envelope, "ROUTE_UNAVAILABLE"
        received_at = self._clock()
        if received_at < now:
            return envelope, "ROUTE_CLOCK_INVALID"
        envelope["quote_observation"] = {"requested_at": _iso(now), "received_at": _iso(received_at),
                                          "provider_created_at": None,
                                          "elapsed_seconds": math.ceil((received_at - now).total_seconds())}
        minimum = (int(self._approved_route.approved_min_output_raw) if self._approved_route is not None else
                   context.buy.raw * profile.min_output_bps // 10000)
        try:
            return self._candidate(prepared, envelope, response, minimum, received_at)
        except (AdapterError, ValueError):  # a malformed declaration or response is refused before signing
            return envelope, "ROUTE_DECLARATION_INVALID"

    def _candidate(self, prepared: PreparedSubmission, envelope: dict[str, Any], response: Any, minimum: int,
                   now: dt.datetime) -> tuple[dict[str, Any] | None, str | None]:
        context, profile = self._context, self._profile
        config = ApprovedAdapterConfiguration(
            network_id=context.network_id, entrypoint_address=profile.entrypoint, method=profile.method,
            selector=profile.selector,
            input_asset={"asset_id": context.sell.asset_id, "token_address": context.sell.token,
                         "decimals": context.sell.decimals},
            output_asset={"asset_id": context.buy.asset_id, "token_address": context.buy.token,
                          "decimals": context.buy.decimals},
            recipient=context.wallet_address, approved_input_raw=str(context.sell.raw),
            approved_min_output_raw=str(minimum), approved_program_hex=profile.program_hex,
            fees={"fee_bps": profile.fee_bps, "referrer_fee_bps": profile.referrer_fee_bps,
                  "fee_collector_address": profile.fee_collector, "referrer_address": profile.referrer,
                  "is_in_token_fee": profile.is_in_token_fee},
            approved_allowance_raw=str(context.allowance_raw),
            freshness={"max_quote_age_seconds": profile.max_quote_age_seconds,
                       "max_input_age_seconds": profile.max_input_age_seconds,
                       "intent_expires_at": _iso(context.intent_expires_at),
                       "mandate_expires_at": context.mandate_expires_at},
            supported_schema_variants=["TRANSACTION_CALLDATA"])
        config = self._approved_route or config
        result = prepare_unsigned_transaction(
            quote_response=response if isinstance(response, Mapping) else {}, provenance=ResponseProvenance.AUTHORED,
            config=config, now=_iso(now), quote_age_seconds=envelope["quote_observation"]["elapsed_seconds"],
            input_age_seconds=max(0, int((now - context.decision_slot).total_seconds())))
        if result.outcome != PreparationOutcome.ACCEPTED or result.candidate is None:
            envelope["route_reasons"] = list(result.reasons)
            return envelope, f"ROUTE_{result.outcome.value}"
        candidate = result.candidate
        try:
            nonce = hex_quantity(self._clients.broadcast.call(
                "eth_getTransactionCount", [context.wallet_address, "pending"]))
        except (ReplyLost, TimeoutError, OSError, RpcError):
            nonce = None
        if nonce is None:
            return envelope, "NONCE_UNAVAILABLE"
        fee_envelope = {"gas_limit": profile.gas_limit, "max_fee_per_gas": profile.max_fee_per_gas,
                        "max_priority_fee_per_gas": profile.max_priority_fee_per_gas}
        unsigned = {"type": EIP1559_TYPE, "chain_id": context.chain_id, "nonce": nonce, "to": candidate.to,
                    "value": int(candidate.value_raw), "data": candidate.data_hex, **fee_envelope}
        body = {"method": "eth_signTransaction", "params": {"transaction": unsigned}}
        envelope.update({
            "candidate": candidate.model_dump(mode="json", include={
                "candidate_hash", "chain_id", "to", "value_raw", "data_hex", "selector", "method", "intent", "fees",
                "program_hex"}),
            "candidate_hash": candidate.candidate_hash, "nonce": nonce, "fee_envelope": fee_envelope,
            "unsigned": unsigned,
            "signing_request": {"request_id": prepared.attempt_id, "route": f"POST /v1/wallets/{context.wallet_id}/rpc",
                                "request_key": signing_request_key(unsigned), "body": body}})
        return envelope, None

    def _recheck(self) -> str | None:
        problem = self._release_problem()
        if problem is not None:
            return problem
        reasons = self._controls()
        if reasons:
            return ";".join(reasons)
        now = self._clock()
        if now >= self._context.intent_expires_at:
            return "INTENT_EXPIRED"
        if now >= parse_utc(self._context.mandate_expires_at):  # the saved mandate, never renewed or replaced
            return "MANDATE_EXPIRED"
        return None

    def _evidence_class(self) -> str:
        return EVIDENCE_CLASS if self._binding is None else self._binding.release.content()["evidence_class"]

    def _release_problem(self) -> str | None:
        if self._binding is None:
            return None
        from edge_os_api.execution.operating_release import ReleaseRefused

        context = self._context
        identity = {**context.identity, "owner_id": context.owner_id, "agent_id": context.agent_id,
                    "wallet_id": context.wallet_id, "wallet_address": context.wallet_address,
                    "network_id": context.network_id}
        identity = {key: identity.get(key) for key in self._binding.identity()}
        try:
            self._binding.admit(identity, now=self._clock(), synthetic_bindings=self._synthetic_bindings)
        except ReleaseRefused as error:
            return str(error)
        return None

    @staticmethod
    def _unsent(journal: Callable[[str, dict[str, Any]], None], reason: str,
                values: dict[str, Any] | None = None) -> TransportOutcome:
        try:
            journal("REFUSED_UNSENT", {**(values or {}), "reason": reason})
        except JournalError:
            pass  # nothing was sent; the attempt outcome still records the reason
        return TransportOutcome(outcome="DEFINITELY_UNSENT", detail=reason)

    @staticmethod
    def _possible(journal: Callable[[str, dict[str, Any]], None], stage: str,
                  values: dict[str, Any] | None = None) -> TransportOutcome:
        try:
            journal(stage.split(":", 1)[0], {**(values or {}), "reason": stage})
        except JournalError:
            pass  # the liability stays; the attempt outcome still records the stage
        return TransportOutcome(outcome="SUBMISSION_POSSIBLE", detail=stage)


# ------------------------------------------------------------------------------------ receipts

@dataclass(frozen=True)
class ReceiptReading:
    """One independent receipt reading bound through P20 to the saved original transaction.

    `outcome` is the recovery vocabulary (`CONFIRMED`, `REVERTED`, `SUBMISSION_UNKNOWN`) or `REJECTED` when the
    reading does not bind to the saved identity; a rejected reading is never applied.
    """

    verdict: ObservationVerdict
    source_ref: str

    @property
    def outcome(self) -> str:
        return "REJECTED" if self.verdict.state == ObservationState.REJECTED else RECEIPT_OUTCOMES[self.verdict.state]


def read_original_receipt(envelope: Mapping[str, Any], observer: RpcClient, *,
                          binding: BoundRelease | None = None,
                          synthetic_bindings: Mapping[str, str] | None = None) -> ReceiptReading:
    """Read the receipt for the saved transaction hash and normalize it with the saved identity."""
    tx_hash = envelope.get("transaction_hash") or ""
    wallet = envelope.get("wallet_address") or ""
    expected_chain = envelope.get("chain_id")
    candidate_hash = envelope.get("candidate_hash") or ""
    valid_identity = (is_hash(tx_hash) and isinstance(wallet, str) and _ADDRESS.fullmatch(wallet) is not None
                      and type(expected_chain) is int and isinstance(candidate_hash, str) and bool(candidate_hash))
    wallet = wallet.lower() if isinstance(wallet, str) else ""
    expected_chain = expected_chain if type(expected_chain) is int else 0
    candidate_hash = candidate_hash if isinstance(candidate_hash, str) else ""
    source_ref = f"original-receipt:{tx_hash}"

    def normalized(observation: ObservationInput) -> ReceiptReading:
        verdict = normalize_observation(observation=observation, expected_candidate_hash=candidate_hash,
                                        expected_chain_id=expected_chain, expected_wallet=wallet,
                                        expected_tx_hash=tx_hash)
        return ReceiptReading(verdict=verdict, source_ref=source_ref)

    if not valid_identity:
        return normalized(ObservationInput(timeout=True))

    controlled = binding is not None or "binding_sha256" in envelope or "release_sha256" in envelope
    if controlled:
        try:
            if binding is None:
                return normalized(ObservationInput(timeout=True))
            binding.qualify_original(envelope, synthetic_bindings=synthetic_bindings)
        except Exception:  # malformed saved evidence cannot establish a receipt identity
            return normalized(ObservationInput(timeout=True))

    try:
        chain_id = hex_quantity(observer.call("eth_chainId", []))
        receipt = observer.call("eth_getTransactionReceipt", [tx_hash])
    except (ReplyLost, TimeoutError, OSError, RpcError):
        return normalized(ObservationInput(timeout=True))
    if receipt is None:
        return normalized(ObservationInput(chain_id=chain_id, wallet_id=wallet, candidate_hash=candidate_hash,
                                           tx_hash=tx_hash))
    if not isinstance(receipt, Mapping):
        return normalized(ObservationInput(chain_id=chain_id))
    charge = None
    if controlled:
        from edge_os_api.execution.provider_observations import observe_monad_charge

        try:
            finalized = observer.call("eth_getBlockByNumber", ["finalized", False])
            canonical = observer.call("eth_getBlockByNumber", [receipt["blockNumber"], False])
            charge = observe_monad_charge(original=envelope, receipt=receipt, canonical_block=canonical,
                finalized_block=finalized, evidence_class=envelope["evidence_class"], finality_qualified=False,
                binding=binding, synthetic_bindings=synthetic_bindings)
            logs = receipt["logs"]
            indices = [log["logIndex"] for log in logs]
            logs_bound = (isinstance(logs, list) and len(set(indices)) == len(indices)
                and all(log.get("removed") is False and hex_quantity(log["logIndex"]) is not None
                    and all(log.get(key) == receipt.get(key) for key in ("transactionHash", "blockHash", "blockNumber"))
                    for log in logs))
            if charge.state != "OBSERVED" or not logs_bound:
                return normalized(ObservationInput(timeout=True))
            source_ref = f"original-receipt:{tx_hash}:finalized:{charge.block_hash}"
        except (ReplyLost, TimeoutError, OSError, RpcError, KeyError, TypeError, ValueError):
            return normalized(ObservationInput(timeout=True))
    status = {"0x1": "SUCCESS", "0x0": "REVERTED"}.get(str(receipt.get("status")))
    returned_hash = str(receipt.get("transactionHash") or "").lower() or None
    sender = str(receipt.get("from") or "").lower() or None
    target = str(receipt.get("to") or "").lower()
    bound = (returned_hash == tx_hash and sender == wallet
             and target == str(envelope["candidate"]["to"]).lower())
    sell, buy = envelope["sell"], envelope["buy"]
    sell_decimals, buy_decimals = int(sell["decimals"]), int(buy["decimals"])
    spent = _transfers(receipt, sell["token"], source=wallet)
    received = _transfers(receipt, buy["token"], target=wallet)
    if controlled and receipt.get("status") == "0x1":
        assert binding is not None
        route = binding.release.content()["route"]
        if (spent != int(route["approved_input_raw"]) or received is None
                or received < int(route["approved_min_output_raw"])
                or _transfers(receipt, sell["token"], target=wallet) not in (None, 0)
                or _transfers(receipt, buy["token"], source=wallet) not in (None, 0)):
            return normalized(ObservationInput(timeout=True))
    gas_used, gas_price = hex_quantity(receipt.get("gasUsed")), hex_quantity(receipt.get("effectiveGasPrice"))
    gas_asset = str(envelope["gas_asset_id"])
    return normalized(ObservationInput(
        status=status, tx_hash=returned_hash, chain_id=chain_id, wallet_id=sender,
        candidate_hash=candidate_hash if bound else None, receipt_present=True,
        actual_input=None if spent is None else AssetAmount(asset_id=sell["asset_id"], raw=str(spent),
                                                            decimals=sell_decimals),
        actual_output=None if received is None else AssetAmount(asset_id=buy["asset_id"], raw=str(received),
                                                                decimals=buy_decimals),
        actual_gas=(AssetAmount(asset_id=gas_asset, raw=charge.raw, decimals=18) if charge is not None else
                    None if gas_used is None or gas_price is None else AssetAmount(
                        asset_id=gas_asset, raw=str(gas_used * gas_price), decimals=18))))


def _transfers(receipt: Mapping[str, Any], token: str, *, source: str | None = None,
               target: str | None = None) -> int | None:
    """The total ERC-20 `Transfer` of `token` from `source` or to `target`; None when no such log exists."""
    total, found = 0, False
    logs = receipt.get("logs") or []
    # Any malformed log could be a skipped part of this leg, so a receipt with one proves no amount at all.
    if not isinstance(logs, list) or not all(_well_formed_log(log) for log in logs):
        return None
    for log in logs:
        if str(log["address"]).lower() != token.lower():
            continue
        topics = [str(item).lower() for item in log["topics"]]
        if not topics or topics[0] != TRANSFER_TOPIC:
            continue
        # A Transfer of this token whose indexed addresses are not exact padded 32-byte words proves nothing.
        if len(topics) != 3 or not all(_INDEXED_ADDRESS.fullmatch(item) for item in topics[1:]):
            return None
        sender, recipient = "0x" + topics[1][-40:], "0x" + topics[2][-40:]
        if (source is not None and sender != source) or (target is not None and recipient != target):
            continue
        amount = abi_word(log.get("data"))
        if amount is None:
            return None
        total, found = total + amount, True
    return total if found else None


def _well_formed_log(log: Any) -> bool:
    """A log with a 20-byte address and topics that are exact 32-byte words (JSON-RPC `DATA`)."""
    if not isinstance(log, Mapping) or not isinstance(log.get("address"), str) or not isinstance(log.get("topics"), list):
        return False
    return (_ADDRESS.fullmatch(log["address"]) is not None
            and all(isinstance(item, str) and _TX_HASH.fullmatch(item) for item in log["topics"]))


RECEIPT_OUTCOMES = {ObservationState.CONFIRMED: "CONFIRMED", ObservationState.REVERTED: "REVERTED",
                    ObservationState.PENDING: "SUBMISSION_UNKNOWN",
                    ObservationState.SUBMISSION_UNKNOWN: "SUBMISSION_UNKNOWN",
                    ObservationState.ACKNOWLEDGEMENT_LOST: "SUBMISSION_UNKNOWN",
                    ObservationState.TIMEOUT: "SUBMISSION_UNKNOWN"}


# The only saved fields the owner sees: identities, codes, digests and stages. Anything else (signed bytes, request
# bodies, provider replies) stays private, including fields a future stage might add.
OWNER_FIELDS = frozenset({
    "scope", "release_id", "release_sha256", "binding_sha256", "approved_minimum", "quote_observation",
    "schema", "evidence_class", "transport_id", "strategy_id", "publication_revision_id", "execution_revision_id",
    "content_hash", "consent_adoption_id", "consent_hash", "policy_binding", "job_id", "owner_id", "agent_id",
    "wallet_id", "wallet_address", "network_id", "chain_id", "action_id", "payload_hash", "operation", "attempt_id",
    "sell", "buy", "gas_asset_id", "candidate_hash", "nonce", "fee_envelope", "transaction_hash",
    "signed_bytes_sha256", "signed_bytes_length", "stage", "stages", "reason", "reasons", "route_reasons"})


def is_hash(value: Any) -> bool:
    return isinstance(value, str) and _TX_HASH.fullmatch(value) is not None


def owner_projection(envelope: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """The owner-visible original transaction: identities and stages, never signed bytes or the request body."""
    if not envelope:
        return None
    view = {key: value for key, value in envelope.items() if key in OWNER_FIELDS}
    returned = envelope.get("broadcast_returned")
    view["broadcast_returned"] = returned if is_hash(returned) and returned == envelope.get("transaction_hash") else None
    request = envelope.get("signing_request")
    if isinstance(request, Mapping):
        view["signing_request_id"] = request.get("request_id")
        view["signing_request_key"] = request.get("request_key")
    candidate = envelope.get("candidate")
    if isinstance(candidate, Mapping):
        view["candidate_to"] = candidate.get("to")
    return view
