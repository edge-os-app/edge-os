"""Local deterministic admission, reservation and reconciliation domain (P22 local stage).

Owned application package. No API/UI wiring is provided by this stage; live
admission remains closed pending P21 and operational gates.
"""

from edge_os_api.admission.service import AdmissionError, AdmissionService, StaleInput

__all__ = ["AdmissionError", "AdmissionService", "StaleInput"]