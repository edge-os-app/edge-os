"""Read-only stored-write times for one saved owner/deployment scope (P31 `as_of`).

The producer view (`RecurringOperation.projection`) does not expose the deployment row's `updated_at`. These SELECTs
read it, and the newest job, outcome, attempt and queue times of the same deployment, each with its table, id and
field. `as_of` is the newest of them: the newest stored write, not evidence that the producer advanced (activation,
every tick and an end all write the deployment row; reconciliation retries touch job `updated_at`). Nothing here
writes, and every statement is filtered by the verified owner and the saved deployment.
"""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from edge_os_api.execution.models import (EvaluationJobRow, EvaluationOutcomeRow, QueueRow, RecurringDeploymentRow,
                                          SubmissionAttemptRow)
from edge_os_api.execution.types import utc_iso

JOBS = "execution_local.execution_evaluation_jobs"


@dataclass(frozen=True)
class SourceTime:
    table: str
    id: str
    field: str
    at: dt.datetime

    def ref(self) -> dict[str, str]:
        return {"table": self.table, "id": self.id, "field": self.field, "time": utc_iso(self.at)}


def _newest(session: Session, table: str, key: object, field: object, *where: object) -> SourceTime | None:
    # PostgreSQL sorts NULL first in descending order, so an unfinished attempt is excluded explicitly.
    row = session.execute(select(key, field).where(*where, field.is_not(None))  # type: ignore[attr-defined]
                          .order_by(field.desc(), key.desc()).limit(1)).first()  # type: ignore[attr-defined]
    if row is None:
        return None
    return SourceTime(table, str(row[0]), field.key, row[1])  # type: ignore[attr-defined]


def deployment_source_times(session: Session, owner_id: uuid.UUID, deployment_id: uuid.UUID) -> list[SourceTime]:
    """Each named stored time of the saved deployment that exists, newest first."""
    jobs = (EvaluationJobRow.owner_id == owner_id, EvaluationJobRow.deployment_id == deployment_id)
    actions = select(EvaluationJobRow.action_id).where(*jobs, EvaluationJobRow.action_id.is_not(None))
    found = [
        _newest(session, "execution_local.execution_recurring_deployments", RecurringDeploymentRow.deployment_id,
                RecurringDeploymentRow.updated_at, RecurringDeploymentRow.owner_id == owner_id,
                RecurringDeploymentRow.deployment_id == deployment_id),
        _newest(session, JOBS, EvaluationJobRow.job_id, EvaluationJobRow.updated_at, *jobs),
        _newest(session, "execution_local.execution_evaluation_outcomes", EvaluationOutcomeRow.job_id,
                EvaluationOutcomeRow.evaluated_at, EvaluationOutcomeRow.owner_id == owner_id,
                EvaluationOutcomeRow.deployment_id == deployment_id),
        _newest(session, "execution_local.execution_submission_attempts", SubmissionAttemptRow.attempt_id,
                SubmissionAttemptRow.started_at, SubmissionAttemptRow.owner_id == owner_id,
                SubmissionAttemptRow.action_id.in_(actions)),
        _newest(session, "execution_local.execution_submission_attempts", SubmissionAttemptRow.attempt_id,
                SubmissionAttemptRow.completed_at, SubmissionAttemptRow.owner_id == owner_id,
                SubmissionAttemptRow.action_id.in_(actions)),
        _newest(session, "execution_local.execution_queue", QueueRow.queue_id, QueueRow.updated_at,
                QueueRow.owner_id == owner_id, QueueRow.action_id.in_(actions)),
    ]
    return sorted((item for item in found if item is not None), key=lambda item: item.at, reverse=True)

