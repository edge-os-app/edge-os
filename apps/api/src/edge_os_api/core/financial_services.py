"""Compose the accepted financial services once, over the application's durable session factory.

One `SubmissionControls` reader (durable stops plus removal) is handed to admission and execution, so a
stop or a requested removal denies at admission and again under the same per-wallet lock immediately
before submission ownership. The trusted provider ports come from the configured execution mode only.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from edge_os_api.admission.service import AdmissionService
from edge_os_api.consent.service import ConsentService
from edge_os_api.core.provider_ports import ProviderPorts, build_provider_ports
from edge_os_api.core.settings import Settings
from edge_os_api.execution.service import ExecutionService
from edge_os_api.execution.worker import ConnectedExecution
from edge_os_api.recovery.service import RecoveryService
from edge_os_api.revocation.enforcement import SubmissionControls
from edge_os_api.revocation.removal_service import RemovalService
from edge_os_api.stops.service import StopService


@dataclass
class FinancialServices:
    stops: StopService
    removals: RemovalService
    controls: SubmissionControls
    admission: AdmissionService
    execution: ExecutionService
    recovery: RecoveryService
    consent: ConsentService
    ports: ProviderPorts
    connected: ConnectedExecution


def build_financial_services(factory: sessionmaker[Session], settings: Settings,
                             ports: ProviderPorts | None = None) -> FinancialServices:
    ports = ports or build_provider_ports(settings.execution_mode, factory, settings.fixture_effects_path)
    stops = StopService(factory)
    removals = RemovalService(factory)
    controls = SubmissionControls(stops, removals)
    admission = AdmissionService(factory, stops=controls)
    execution = ExecutionService(factory, admission, stops=controls)
    recovery = RecoveryService(factory, admission, execution)
    consent = ConsentService(factory, admission=admission, stops=stops)
    services = FinancialServices(stops=stops, removals=removals, controls=controls, admission=admission,
                                 execution=execution, recovery=recovery, consent=consent, ports=ports,
                                 connected=None)  # type: ignore[arg-type]
    services.connected = ConnectedExecution(factory, services, ports, qualification=ports.mode)
    return services
