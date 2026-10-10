"use client";

import { Fragment } from "react";
import { formatTime } from "../lib/describe";
import { ATTEMPT_STATUS_LABEL, describeLatency, describeParse, describePurpose, describeUsage } from "../lib/interpretation";
import type { Attempt, LateResult } from "../lib/types";

/** Every attempt the interpreter made for this request, oldest first. A failed or unknown attempt stays listed. */
export function InterpretationAttempts({ attempts, lateResults, open }: { attempts: Attempt[]; lateResults: LateResult[]; open: boolean }) {
  if (attempts.length === 0) return null;
  const byId = new Map(attempts.map((a) => [a.attempt_id, a]));
  const number = (id: string) => byId.get(id)?.sequence;
  return (
    <details open={open} data-testid="attempts">
      <summary>Interpreter attempts ({attempts.length})</summary>
      <ol className="attempts" aria-label="Interpreter attempts for this request, oldest first">
        {attempts.map((a) => {
          const rows: [string, string][] = [
            ["Result", ATTEMPT_STATUS_LABEL[a.status] + (a.error_class ? ` (${a.error_class})` : "")],
            ["Answer", describeParse(a.parse_result) + (a.revision_id ? ". Used for the current meaning" : "")],
            ["Tokens", describeUsage(a.usage)],
            ["Time", describeLatency(a.latency_ms)],
          ];
          return (
            <li key={a.attempt_id} data-attempt={a.attempt_id} data-status={a.status}>
              <h3>Attempt #{a.sequence}: {describePurpose(a, byId)}</h3>
              <p className="muted">{formatTime(a.started_at)}</p>
              <dl className="kv">
                {rows.map(([label, value]) => (<Fragment key={label}><dt>{label}</dt><dd>{value}</dd></Fragment>))}
              </dl>
            </li>
          );
        })}
      </ol>
      {lateResults.map((late) => (
        <p key={late.observation_id} className="muted" data-testid="late-result">
          A result arrived after attempt #{number(late.attempt_id)} was closed. It is kept as evidence and was not used.
        </p>
      ))}
      <p className="muted">Tokens show Unknown when the provider did not report them. Unknown is not zero.</p>
    </details>
  );
}
