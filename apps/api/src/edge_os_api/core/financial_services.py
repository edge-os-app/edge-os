"""Compose the accepted financial services once, over the application's durable session factory.

One combined reader (durable stops, removal and one open position per agent wallet) is handed to admission
and execution, so each control denies at admission and again under the same per-wallet lock immediately
before submission ownership. The trusted provider ports come from the configured execution mode only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.admission.service import AdmissionService
from edge_os_api.consent.service import ConsentService
from edge_os_api.core.provider_ports import ProviderPorts, build_provider_ports
from edge_os_api.core.settings import Settings
from edge_os_api.execution.service import ExecutionService
from edge_os_api.execution.position_limit import CombinedControls, OnePositionPerWallet
from edge_os_api.execution.recurring_scheduler import DeploymentEndControl, RecurringOperation
from edge_os_api.execution.worker import ConnectedExecution
from edge_os_api.recovery.service import RecoveryService
from edge_os_api.revocation.enforcement import SubmissionControls
from edge_os_api.revocation.removal_service import RemovalService
from edge_os_api.stops.service import StopService


@dataclass
class FinancialServices:
    stops: StopService
    removals: RemovalService
    controls: CombinedControls
    admission: AdmissionService
    execution: ExecutionService
    recovery: RecoveryService
    consent: ConsentService
    ports: ProviderPorts
    connected: ConnectedExecution
    recurring: RecurringOperation


def build_financial_services(factory: sessionmaker[Session], settings: Settings,
                             ports: ProviderPorts | None = None, *,
                             role: Literal["api", "worker", "recurring"] = "api") -> FinancialServices:
    if role not in ("api", "worker", "recurring"):
        raise ValueError("unknown financial service role")
    ports = (ports.for_role(role) if ports is not None else
             build_provider_ports(settings.execution_mode, factory, settings.fixture_effects_path,
                                  settings.original_recordings_dir, role=role))
    stops = StopService(factory)
    removals = RemovalService(factory)
    # Stops, removal, the one-position-per-wallet limit and an ended recurring deployment share the single
    # StopReader seam, read under the per-wallet admission lock at admission and submission ownership.
    controls = CombinedControls(SubmissionControls(stops, removals), OnePositionPerWallet(), DeploymentEndControl())
    admission = AdmissionService(factory, stops=controls)
    execution = ExecutionService(factory, admission, stops=controls)
    recovery = RecoveryService(factory, admission, execution)
    consent = ConsentService(factory, admission=admission, stops=stops)
    services = FinancialServices(stops=stops, removals=removals, controls=controls, admission=admission,
                                 execution=execution, recovery=recovery, consent=consent, ports=ports,
                                 connected=None, recurring=None)  # type: ignore[arg-type]
    services.connected = ConnectedExecution(factory, services, ports, qualification=ports.mode)
    services.recurring = RecurringOperation(factory, services, services.connected)
    return services
