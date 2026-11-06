"""The real RPC client must preserve the receipt identity used by bound recovery."""
import copy
import json

import pytest

from edge_os_api.core.provider_ports import ControlledRuntime
from edge_os_api.execution.original_transaction import read_original_receipt
from edge_os_api.research_history.http_clients.http_transport import HttpResponse
from recovery.test_bound_original_receipt import BLOCK, FINAL, submitted_original


@pytest.mark.parametrize("fault", [None, "wrong-index", "missing-index", "malformed-index", "not-final", "missing-finality"])
def test_bound_recovery_through_rpc_projection(tmp_path, fault):
    envelope, binding, approvals, receipt = submitted_original(tmp_path)
    receipt = copy.deepcopy(receipt)
    if fault == "wrong-index":
        receipt["transactionIndex"] = "0x1"
    elif fault == "missing-index":
        receipt.pop("transactionIndex")
    elif fault == "malformed-index":
        receipt["transactionIndex"] = "0x00"
    calls = []

    class Http:
        def request(self, **request):
            body = json.loads(request["body"])
            method, params = body["method"], body["params"]
            calls.append((method, params))
            if method == "eth_chainId":
                result = "0x8f"
            elif method == "eth_getTransactionReceipt":
                assert params == [envelope["transaction_hash"]]
                result = receipt
            else:
                assert method == "eth_getBlockByNumber"
                if params == ["finalized", False]:
                    result = {"number":"0x1" if fault == "not-final" else "0x1e8482",
                              "hash":None if fault == "missing-finality" else FINAL, "timestamp":"0x1"}
                else:
                    assert params == [receipt["blockNumber"], False]
                    result = {"number":receipt["blockNumber"], "hash":BLOCK,
                              "timestamp":"0x1", "baseFeePerGas":"0x3b9aca00"}
            return HttpResponse(200, {}, json.dumps({"jsonrpc":"2.0", "id":body["id"], "result":result}).encode())

    def forbidden():
        pytest.fail("recovery acquired an execution credential")

    runtime = ControlledRuntime(binding=binding, http=Http(), signer_access=forbidden, quote_token=forbidden,
        synthetic_bindings=approvals)
    result = read_original_receipt(envelope, runtime.read_only().observer(),
        binding=binding, synthetic_bindings=approvals)
    assert result.outcome == ("CONFIRMED" if fault is None else "SUBMISSION_UNKNOWN")
    assert all(method not in ("eth_signTransaction", "eth_sendRawTransaction", "quote") for method, _ in calls)
    if fault is None:
        assert result.verdict.actual_gas.raw == "600000000000000"
