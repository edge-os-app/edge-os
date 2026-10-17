"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { InvestigationJob, NansenReportBody, NansenReportRecord } from "../lib/api";
import { readNansenRelease } from "../lib/nansen-release-request";
import type { NansenOperatingRelease, NansenReleaseState } from "../lib/nansen-release-request";

const RUNNING = new Set(["QUEUED", "RESERVED", "COLLECTING"]);
const STATE_COPY: Record<string, string> = {
  RESERVED: "Saved and reserved. Waiting for the bounded worker.",
  COLLECTING: "The worker is collecting. The original attempt is saved.",
  REPORTED: "Report saved.",
  CANCELLED: "Cancelled. Anything already collected is kept.",
  DEADLINE_EXCEEDED: "Stopped at its deadline. Anything already collected is kept.",
  BUDGET_EXHAUSTED: "Refused: your research budget cannot reserve this report. Nothing was collected.",
  UNAVAILABLE: "The outcome is unknown. It is never run again; the reserved amounts stay held.",
  FAILED: "Failed. The reserved amounts stay held.",
};
// Ends where nothing was sent: everything was released, so no amount is held.
const REASON_COPY: Record<string, string> = {
  nansen_research_unavailable: "Not run: this server no longer composes the Nansen transport. Nothing was sent; the reserved amounts were released.",
  nansen_composition_failed: "Not run: the transport could not be prepared. Nothing was sent; the reserved amounts were released.",
};
const VERDICT_COPY: Record<string, string> = {
  SUPPORTED: "Supported by the returned records", LIMITED: "Limited", UNRESOLVED: "Unresolved",
  UNAVAILABLE: "Unavailable", UNKNOWN: "Unknown",
};
// Labels come from the saved record's own evidence class, never from this server's current configuration.
const EVIDENCE_COPY: Record<string, string> = {
  PROVIDER_ACTUAL: "Nansen provider data",
  RELEASE_STAND_IN_RESPONSE: "Stand-in responses. Not provider data.",
  AUTHORED_FIXTURE: "Authored responses replayed on this server. Not provider data.",
};
const AUTHORED_LABEL = "Authored Nansen-shaped responses replayed on this server. Not provider data, not market evidence and not a trading signal. The question is your request text, unchanged.";
const LINK_STYLE = { display: "inline-flex", alignItems: "center", minHeight: 44 } as const;

function evidenceCopy(evidenceClass: string): string {
  return EVIDENCE_COPY[evidenceClass] ?? `Unrecognized evidence class ${evidenceClass}. Do not treat this report as provider data.`;
}

function releaseLabel(state: NansenReleaseState | null): string {
  if (state === null) return "Reading which Nansen responses this server uses…";
  if (state.mode === "legacy") return AUTHORED_LABEL;
  if (state.mode === "blocked") return "This server's operating release for Nansen reports could not be read. Each saved report keeps its own label.";
  const name = state.release.release_id;
  return state.release.evidence_class === "PROVIDER_ACTUAL"
    ? `This server is configured for actual Nansen collection under operating release ${name}. Nothing is collected until you save and reserve a report; each saved report states what it holds. The question is your request text, unchanged.`
    : `Stand-in Nansen-shaped responses under operating release ${name}. Not provider data, not market evidence and not a trading signal. The question is your request text, unchanged.`;
}

// `identity` is the request body, plus the release's name and hash under a release, so a changed request gets new keys.
function keysFor(intakeId: string, identity: unknown): { operation_id: string; request_key: string } {
  const storage = `edge-os:nansen:${intakeId}`;
  const fingerprint = JSON.stringify(identity);
  try {
    const saved = JSON.parse(window.sessionStorage.getItem(storage) ?? "null") as { fingerprint?: string; operation_id?: string; request_key?: string } | null;
    if (saved?.fingerprint === fingerprint && saved.operation_id && saved.request_key) {
      return { operation_id: saved.operation_id, request_key: saved.request_key };
    }
  } catch { /* a fresh key is safe: the server keys one job per owner, request and key */ }
  const keys = { operation_id: crypto.randomUUID(), request_key: `ui-${crypto.randomUUID()}` };
  try { window.sessionStorage.setItem(storage, JSON.stringify({ ...keys, fingerprint })); } catch { /* ignore */ }
  return keys;
}

/** Nansen token report for this request: the exact question, derived findings, gaps and the saved report. */
export function ResearchNansenReport({ intakeId }: { intakeId: string }) {
  const [jobs, setJobs] = useState<InvestigationJob[] | null>(null);
  const [available, setAvailable] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [token, setToken] = useState("");
  const [symbol, setSymbol] = useState("");
  const [start, setStart] = useState("2026-10-06T09:44:14Z");
  const [end, setEnd] = useState("2026-10-07T09:44:14Z");
  const [holders, setHolders] = useState(true);
  const [flows, setFlows] = useState(true);
  const [credits, setCredits] = useState("12");
  const [open, setOpen] = useState<NansenReportRecord | null>(null);
  const [release, setRelease] = useState<NansenReleaseState | null>(null);  // null until this intake's listing is read
  const seq = useRef(0);
  const openSeq = useRef(0);
  const currentIntake = useRef(intakeId);

  const load = useCallback(async () => {
    const current = (seq.current += 1);
    try {
      const result = await api.nansenReports(intakeId);
      if (current === seq.current) {
        setJobs(result.jobs); setAvailable(result.available !== false); setRelease(readNansenRelease(result)); setError("");
      }
    } catch (failure) {
      if (current === seq.current) {
        setError(failure instanceof ApiError ? failure.detail : "The saved Nansen reports could not be read.");
      }
    }
  }, [intakeId]);

  useEffect(() => {
    currentIntake.current = intakeId;
    setJobs(null); setRelease(null); setOpen(null); setError("");
    void load();
  }, [intakeId, load]);

  const fixed = release?.mode === "released" ? release.release : null;
  const legacy = release?.mode === "legacy";
  const canStart = !busy && available && (fixed !== null
    || (legacy && Boolean(token.trim()) && Boolean(symbol.trim()) && (holders || flows)));

  async function startReport(fixedRelease: NansenOperatingRelease | null) {
    const requestedIntake = intakeId;
    const operations = [...(holders ? ["holders" as const] : []), ...(flows ? ["flows" as const] : [])];
    // Under a release, the whole fixed request is sent as listed; the authored defaults never fill or replace it.
    const body = fixedRelease ? fixedRelease.request : { token_address: token.trim(), token_symbol: symbol.trim(),
      window: { start_utc: start.trim(), end_utc: end.trim() },
      operations, limits: { max_requests: 4, max_pages: 2, max_bytes: 200000, max_credits: credits.trim(), per_page: 100 },
      deadline_seconds: 600, compute_seconds: 30 };
    const identity = fixedRelease ? { release_id: fixedRelease.release_id, sha256: fixedRelease.sha256, body } : body;
    setBusy(true);
    setError("");
    try {
      await api.startNansenReport(requestedIntake, { ...keysFor(requestedIntake, identity), ...body });
      if (currentIntake.current === requestedIntake) await load();
    } catch (failure) {
      if (currentIntake.current === requestedIntake) {
        setError(failure instanceof ApiError ? `${failure.detail} (${failure.code})` : "The report request was not confirmed. Check saved reports before trying again.");
      }
    } finally {
      setBusy(false);
    }
  }

  async function openReport(reportId: string) {
    const current = (openSeq.current += 1);
    const requestedIntake = intakeId;
    try {
      const saved = await api.nansenReport(reportId);
      if (current === openSeq.current && currentIntake.current === requestedIntake) setOpen(saved);
    } catch (failure) {
      if (current === openSeq.current && currentIntake.current === requestedIntake) {
        setError(failure instanceof ApiError ? failure.detail : "The saved report could not be opened.");
      }
    }
  }

  return (
    <section className="card" aria-labelledby="nansen-title" data-testid="nansen-report">
      <h2 id="nansen-title" style={{ fontSize: 18 }}>Token holder and flow report</h2>
      <p className="muted" data-testid="nansen-label">{releaseLabel(release)}</p>
      {!available ? <p className="status stop" data-testid="nansen-unavailable">This server cannot run Nansen reports. Saved reports still open below; a new request is refused before anything is reserved.</p> : null}
      {release?.mode === "blocked" ? <p className="status stop" data-testid="nansen-release-blocked">{release.reason} A new report
        cannot be requested until the server lists a readable release. Saved reports still open below.</p> : null}
      {fixed ? <ReleasedRequest release={fixed} /> : null}
      {legacy ? <>
      <div className="field">
        <label htmlFor="nansen-token">Token contract address</label>
        <input id="nansen-token" className="input" value={token} onChange={(event) => setToken(event.target.value)} placeholder="0x…" />
      </div>
      <div className="field">
        <label htmlFor="nansen-symbol">Token symbol</label>
        <input id="nansen-symbol" className="input" value={symbol} onChange={(event) => setSymbol(event.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="nansen-start">Window start (UTC)</label>
        <input id="nansen-start" className="input" value={start} onChange={(event) => setStart(event.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="nansen-end">Window end (UTC, inclusive flow cutoff)</label>
        <input id="nansen-end" className="input" value={end} onChange={(event) => setEnd(event.target.value)} />
      </div>
      <fieldset>
        <legend className="legend">Records to collect</legend>
        <label className="choice"><input type="checkbox" checked={holders} onChange={(event) => setHolders(event.target.checked)} /> <span>Holder records</span></label>
        <label className="choice"><input type="checkbox" checked={flows} onChange={(event) => setFlows(event.target.checked)} /> <span>Basic flow records</span></label>
      </fieldset>
      <div className="field">
        <label htmlFor="nansen-credits">Credit limit for this report</label>
        <input id="nansen-credits" className="input" inputMode="decimal" value={credits} onChange={(event) => setCredits(event.target.value)} />
      </div>
      </> : null}
      <div className="btn-row">
        <button className="btn btn-primary" type="button" style={{ minHeight: 44 }} disabled={!canStart}
          onClick={() => void startReport(fixed)}>{busy ? "Saving report request…" : "Save and reserve this report"}</button>
        <button className="btn btn-secondary" type="button" style={{ minHeight: 44 }} onClick={() => void load()}>Refresh reports</button>
      </div>
      {error ? <p role="alert" className="status stop">{error}</p> : null}
      <ul data-testid="nansen-jobs">{(jobs ?? []).map((job) => (
        <li key={job.job_id} data-testid="nansen-job" data-state={job.state}>
          <p><strong>{job.state}</strong> · {(job.terminal_reason && REASON_COPY[job.terminal_reason]) || STATE_COPY[job.state] || job.state}{job.terminal_reason ? ` (${job.terminal_reason})` : ""}</p>
          {job.nansen_report ? <>
            <p className="muted" data-testid="nansen-job-evidence">{evidenceCopy(job.nansen_report.evidence_class)}</p>
            <p data-testid="nansen-job-answer">Answer: {job.nansen_report.answer_state} · requests {job.nansen_report.settlement.provider_requests.state}
              {" "}{job.nansen_report.settlement.provider_requests.measured} · credits {job.nansen_report.settlement.nansen_credits.state}
              {job.nansen_report.settlement.nansen_credits.deducted !== null ? ` ${job.nansen_report.settlement.nansen_credits.deducted}` : " (reserved amount held)"}</p>
            <button className="btn btn-secondary" type="button" style={{ minHeight: 44 }} onClick={() => void openReport(job.nansen_report!.report_id)}>
              Open saved report</button>
          </> : RUNNING.has(job.state) ? <p className="muted">No report yet.</p> : null}
        </li>))}</ul>
      {open ? <NansenReportView record={open} /> : null}
    </section>
  );
}

/** The release's fixed request, shown read-only: the values and cost bounds the server will accept, unchanged. */
function ReleasedRequest({ release }: { release: NansenOperatingRelease }) {
  const request = release.request;
  const limits = request.limits;
  const holderMin = request.holder_query.value_usd_min === null ? "no minimum value" : `minimum value ${request.holder_query.value_usd_min} USD`;
  return (
    <div data-testid="nansen-release-request">
      <p>Fixed by operating release {release.release_id} (SHA-256 {release.sha256.slice(0, 12)}…). These values cannot be changed here.</p>
      <ul>
        <li>Token: {request.token_symbol} ({request.token_address})</li>
        <li>Window (UTC): {request.window.start_utc} to {request.window.end_utc}</li>
        <li>Records: {request.operations.map((item) => (item === "holders" ? "Holder records" : "Basic flow records")).join(" and ")}</li>
        {request.operations.includes("holders") ? <li>Holder query: {request.holder_query.label_type}, ordered by
          {" "}{request.holder_query.order_field}, {request.holder_query.aggregate_by_entity ? "grouped by entity" : "by address"}, {holderMin}</li> : null}
        {request.operations.includes("flows") ? <li>Flow query: {request.flow_query.label}</li> : null}
        <li>Cost bounds: up to {limits.max_requests} provider requests, {limits.max_pages} pages of {limits.per_page} records,
          {" "}{limits.max_bytes} bytes and {limits.max_credits} credits</li>
        <li>Time bounds: {request.deadline_seconds} seconds to finish, {request.compute_seconds} seconds of compute</li>
      </ul>
    </div>
  );
}

function EvidenceLabel({ evidenceClass }: { evidenceClass: string }) {
  if (evidenceClass !== "PROVIDER_ACTUAL") return <p className="muted" data-testid="nansen-evidence">{evidenceCopy(evidenceClass)}</p>;
  return (
    <div data-testid="nansen-evidence">
      <p>Data from <a href="https://www.nansen.ai" target="_blank" rel="noreferrer" style={LINK_STYLE}>Nansen</a>, saved by this server under an
        operating release. See the <a href="https://docs.nansen.ai" target="_blank" rel="noreferrer" style={LINK_STYLE}>Nansen API documentation</a>.</p>
      <p className="muted">Holder records are the partial list Nansen returned, not full ownership. Flow records do not show buying or profit.</p>
    </div>
  );
}

function NansenReportView({ record }: { record: NansenReportRecord }) {
  const report = record.content.report;
  const hashes = Object.values(record.hashes_verified);
  const verified = hashes.length > 0 && hashes.every(Boolean);
  const coverage = report.coverage;
  const partial = coverage.missing_buckets > 0 || coverage.incomplete_buckets > 0 || coverage.pagination_is_last_page === false;
  const settlement = record.content.settlement;
  return (
    <div data-testid="nansen-report-view">
      <h3 style={{ fontSize: 16 }}>Saved report for {report.token_symbol}</h3>
      <p data-testid="nansen-question">Question: {report.question}</p>
      <p data-testid="nansen-answer-state">Answer state: {report.answer_state}</p>
      <EvidenceLabel evidenceClass={record.content.evidence_class} />
      <p className="muted">{record.content.notice}</p>
      <p data-testid="nansen-settlement">Requests {settlement.provider_requests.state} {settlement.provider_requests.measured} ·
        {" "}credits {settlement.nansen_credits.state}{settlement.nansen_credits.deducted !== null ? ` ${settlement.nansen_credits.deducted}` : " (reserved amount held)"}</p>
      <p className="muted" data-testid="nansen-hashes">{verified ? "Saved hashes recomputed and matched." : "A saved hash did not match. Do not rely on this report."}
        {" "}Evidence class {record.content.evidence_class}.</p>
      <h4 style={{ fontSize: 15 }}>Findings</h4>
      <ul data-testid="nansen-findings">{report.findings.map((finding) => (
        <li key={finding.code}><strong>{VERDICT_COPY[finding.verdict] ?? finding.verdict}</strong> · {finding.statement}
          {finding.source_refs.length ? <span className="muted"> (sources: {finding.source_refs.length})</span> : null}</li>))}</ul>
      {report.limitations.length ? <>
        <h4 style={{ fontSize: 15 }}>What this report cannot answer</h4>
        <ul data-testid="nansen-limitations">{report.limitations.map((item) => (
          <li key={item.claim}>{item.claim}: needs {item.missing_dependency}</li>))}</ul>
      </> : null}
      <h4 style={{ fontSize: 15 }}>Coverage</h4>
      <p data-testid="nansen-coverage">{report.coverage.holder_rows} holder address records (not people, not amounts) ·
        {" "}{report.coverage.flow_buckets} of {report.coverage.expected_buckets} flow periods · {report.coverage.missing_buckets} missing ·
        {" "}{report.coverage.incomplete_buckets} incomplete{report.coverage.stop_reason ? ` · stopped: ${report.coverage.stop_reason}` : ""}
        {partial ? " · partial coverage" : ""}</p>
      {report.unknowns.length ? <p className="muted">Unknown: {report.unknowns.join("; ")}</p> : null}
      <p className="muted" data-testid="nansen-sources">Source references: {report.source_hashes.length} saved
        {record.content.evidence_class === "PROVIDER_ACTUAL" ? " provider" : ""} response hashes</p>
    </div>
  );
}
