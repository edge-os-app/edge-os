"""Flow helpers for the scoped-stop tests. They compose public interfaces only.

The true-process probe runs a separate Python interpreter against the same
run-labelled database, so a stop's durability and enforcement are proved across a
real process boundary and not only a fresh engine inside this process.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from edge_os_api.admission.types import ActionIntent, AdmissionContext, ApprovalSnapshot
from edge_os_api.stops.types import StopRequest

from admission._builders import AGENT_A, NETWORK, WALLET_A

API_SRC = Path(__file__).resolve().parents[2] / "src"

_PROBE = r"""
import json, sys, uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from edge_os_api.stops.service import StopService
from edge_os_api.admission.service import AdmissionService
from edge_os_api.admission.types import ActionIntent, ApprovalSnapshot, AdmissionContext

job = json.load(sys.stdin)
engine = create_engine(job["url"], pool_pre_ping=True,
                       connect_args={"options": "-csearch_path=stops_local,recovery_local,"
                                               "execution_local,admission_local,public"})
factory = sessionmaker(engine, expire_on_commit=False)
stops = StopService(factory)
admission = AdmissionService(factory, stops=stops)
owner = uuid.UUID(job["owner"])
scope = job["scope"]
views = stops.retrieve_stops(owner, agent_id=scope["agent_id"], wallet_id=scope["wallet_id"],
                             network_id=scope["network_id"])
result = {"stop_ids": [str(view.stop_id) for view in views], "modes": [view.mode for view in views]}
if job.get("intent") is not None:
    decision = admission.admit_and_reserve(
        owner, ActionIntent.model_validate(job["intent"]),
        ApprovalSnapshot.model_validate(job["approval"]),
        AdmissionContext.model_validate(job["context"]))
    result["decision_status"] = decision.status
    result["decision_reason"] = decision.reason
if job.get("acquire_action_id") is not None:
    result["acquire"] = admission.acquire_submission(owner, job["acquire_action_id"])
print(json.dumps(result))
"""


def stop_request(*, trigger: str = "USER", mode: str = "STOP_NEW_ENTRIES", scope: str = "POSITION",
                 agent_id: str = AGENT_A, wallet_id: str = WALLET_A, network_id: str = NETWORK,
                 position_id: str | None = "position-1") -> StopRequest:
    if scope == "AGENT_WALLET_NETWORK":
        position_id = None
    return StopRequest(trigger=trigger, mode=mode, scope=scope, agent_id=agent_id,
                       wallet_id=wallet_id, network_id=network_id, position_id=position_id)


def restart_probe(url: str, owner: str, scope: dict[str, str], *,
                  intent: ActionIntent | None = None, approval: ApprovalSnapshot | None = None,
                  context: AdmissionContext | None = None,
                  acquire_action_id: str | None = None) -> dict[str, Any]:
    """Run one probe in a separate Python process against the same database."""
    job: dict[str, Any] = {"url": url, "owner": owner, "scope": scope}
    if intent is not None:
        job["intent"] = json.loads(intent.model_dump_json())
        assert approval is not None and context is not None
        job["approval"] = json.loads(approval.model_dump_json())
        job["context"] = json.loads(context.model_dump_json())
    if acquire_action_id is not None:
        job["acquire_action_id"] = acquire_action_id
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(API_SRC), env.get("PYTHONPATH", "")]))
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE], input=json.dumps(job), capture_output=True, text=True,
        cwd=str(API_SRC.parent), env=env, check=False)
    assert completed.returncode == 0, f"probe failed: {completed.stderr}"
    return json.loads(completed.stdout)
