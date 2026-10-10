"use client";

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
      <table className="records">
        <caption className="visually-hidden">Interpreter attempts for this request, oldest first</caption>
        <thead><tr><th scope="col">Attempt</th><th scope="col">What</th><th scope="col">Result</th><th scope="col">Answer</th><th scope="col">Tokens</th><th scope="col">Time</th></tr></thead>
        <tbody>
          {attempts.map((a) => (
            <tr key={a.attempt_id} data-attempt={a.attempt_id} data-status={a.status}>
              <th scope="row">#{a.sequence}<br /><span className="muted">{formatTime(a.started_at)}</span></th>
              <td>{describePurpose(a, byId)}</td>
              <td>{ATTEMPT_STATUS_LABEL[a.status]}{a.error_class ? <><br /><span className="muted">{a.error_class}</span></> : null}</td>
              <td>{describeParse(a.parse_result)}{a.revision_id ? <><br /><span className="muted">Used for the current meaning</span></> : null}</td>
              <td>{describeUsage(a.usage)}</td>
              <td>{describeLatency(a.latency_ms)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {lateResults.map((late) => (
        <p key={late.observation_id} className="muted" data-testid="late-result">
          A result arrived after attempt #{number(late.attempt_id)} was closed. It is kept as evidence and was not used.
        </p>
      ))}
      <p className="muted">Usage shows Unknown when the provider did not report it. Unknown is not zero.</p>
    </details>
  );
}
