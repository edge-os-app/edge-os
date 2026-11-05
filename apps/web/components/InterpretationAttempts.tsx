"use client";

import { Fragment } from "react";
import { formatTime } from "../lib/describe";
import { ATTEMPT_STATUS_LABEL, describeAttemptCost, describeCreditSpend, describeLatency, describeModelBudget, describeModelCost, describeParse, describePurpose, describeUsage } from "../lib/interpretation";
import type { Attempt, LateResult, ModelBudget, ModelCost } from "../lib/types";
import { Details } from "./Details";

/** Every attempt the interpreter made for this request, oldest first. A failed or unknown attempt stays listed. */
export function InterpretationAttempts({ attempts, modelCost = null, modelBudget = null, lateResults, open, currentRevisionId = null }: { attempts: Attempt[]; modelCost?: ModelCost | null; modelBudget?: ModelBudget | null; lateResults: LateResult[]; open: boolean; currentRevisionId?: string | null }) {
  const budgetLine = modelCost && <p data-testid="model-budget">Model budget: {describeModelBudget(modelBudget)}</p>;
  if (attempts.length === 0) return budgetLine;
  const byId = new Map(attempts.map((a) => [a.attempt_id, a]));
  const number = (id: string) => byId.get(id)?.sequence;
  return (
    <>
      {modelCost && <p data-testid="model-cost-total">Total model cost: {describeModelCost(modelCost)}</p>}
      {modelCost && <p data-testid="model-credit">Model spend: {describeCreditSpend(modelCost)}</p>}
      {budgetLine}
      <details open={open} data-testid="attempts">
        <summary>Research agent reads ({attempts.length})</summary>
        <ol className="attempts" aria-label="Research agent attempts for this request, oldest first">
          {attempts.map((a) => {
            const rows: [string, string][] = [
              ["Result", ATTEMPT_STATUS_LABEL[a.status] + (a.error_class ? ` (${a.error_class})` : "")],
              ["Answer", describeParse(a.parse_result) + (a.revision_id ? (a.revision_id === currentRevisionId ? ". Used for the current meaning" : ". Used for an earlier meaning") : "")],
              ["Tokens", describeUsage(a.usage)],
              ["Time", describeLatency(a.latency_ms)],
              ["Model cost", describeAttemptCost(a.spend)],
            ];
            return (
              <li key={a.attempt_id} data-attempt={a.attempt_id} data-status={a.status}>
                <h3>Read #{a.sequence}: {describePurpose(a, byId)}</h3>
                <p className="muted">{formatTime(a.started_at)}</p>
                <dl className="kv">
                  {rows.map(([label, value]) => (<Fragment key={label}><dt>{label}</dt><dd>{value}</dd></Fragment>))}
                </dl>
                <Details summary="Details"><p className="mono">Read {a.attempt_id} · status {a.status}{a.error_class ? ` · error ${a.error_class}` : ""}{a.revision_id ? ` · version ${a.revision_id}` : ""}</p></Details>
              </li>
            );
          })}
        </ol>
        {lateResults.map((late) => (
          <p key={late.observation_id} className="muted" data-testid="late-result">
            A result arrived after read #{number(late.attempt_id)} was closed. It is kept as evidence and was not used.
          </p>
        ))}
        <p className="muted">Tokens show Unknown when the provider did not report them. Model cost shows Unknown unless the ledger settled the exact charge. Unknown is not zero. 1 CREDIT is exactly USD 1 of usage.</p>
      </details>
    </>
  );
}
