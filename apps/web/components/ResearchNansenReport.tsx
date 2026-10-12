"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { InvestigationJob, NansenReportBody, NansenReportRecord } from "../lib/api";

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
const VERDICT_COPY: Record<string, string> = {
  SUPPORTED: "Supported by the returned records", LIMITED: "Limited", UNRESOLVED: "Unresolved",
  UNAVAILABLE: "Unavailable", UNKNOWN: "Unknown",
};

function keysFor(intakeId: string, body: Omit<NansenReportBody, "operation_id" | "request_key">): { operation_id: string; request_key: string } {
  const storage = `edge-os:nansen:${intakeId}`;
  const fingerprint = JSON.stringify(body);
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
  const seq = useRef(0);

  const load = useCallback(async () => {
    const current = (seq.current += 1);
    try {
      const result = await api.nansenReports(intakeId);
      if (current === seq.current) { setJobs(result.jobs); setError(""); }
    } catch (failure) {
      if (current === seq.current) {
        setError(failure instanceof ApiError ? failure.detail : "The saved Nansen reports could not be read.");
      }
    }
  }, [intakeId]);

  useEffect(() => { void load(); }, [load]);

  async function startReport() {
    const operations = [...(holders ? ["holders" as const] : []), ...(flows ? ["flows" as const] : [])];
    const body = { token_address: token.trim(), token_symbol: symbol.trim(), window: { start_utc: start.trim(), end_utc: end.trim() },
      operations, limits: { max_requests: 4, max_pages: 2, max_bytes: 200000, max_credits: credits.trim(), per_page: 100 },
      deadline_seconds: 600, compute_seconds: 30 };
    setBusy(true);
    setError("");
    try {
      await api.startNansenReport(intakeId, { ...keysFor(intakeId, body), ...body });
      await load();
    } catch (failure) {
      setError(failure instanceof ApiError ? `${failure.detail} (${failure.code})` : "The report request was not confirmed. Check saved reports before trying again.");
    } finally {
      setBusy(false);
    }
  }

  async function openReport(reportId: string) {
    try {
      setOpen(await api.nansenReport(reportId));
    } catch (failure) {
      setError(failure instanceof ApiError ? failure.detail : "The saved report could not be opened.");
    }
  }

  return (
    <section className="card" aria-labelledby="nansen-title" data-testid="nansen-report">
      <h2 id="nansen-title" style={{ fontSize: 18 }}>Token holder and flow report</h2>
      <p className="muted" data-testid="nansen-label">Authored Nansen-shaped responses replayed on this server. Not provider data, not market evidence
        and not a trading signal. The question is your request text, unchanged.</p>
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
      <div className="btn-row">
        <button className="btn btn-primary" type="button" style={{ minHeight: 44 }} disabled={busy || !token.trim() || !symbol.trim() || (!holders && !flows)}
          onClick={() => void startReport()}>{busy ? "Saving report request…" : "Save and reserve this report"}</button>
        <button className="btn btn-secondary" type="button" style={{ minHeight: 44 }} onClick={() => void load()}>Refresh reports</button>
      </div>
      {error ? <p role="alert" className="status stop">{error}</p> : null}
      <ul data-testid="nansen-jobs">{(jobs ?? []).map((job) => (
        <li key={job.job_id} data-testid="nansen-job" data-state={job.state}>
          <p><strong>{job.state}</strong> · {STATE_COPY[job.state] ?? job.state}{job.terminal_reason ? ` (${job.terminal_reason})` : ""}</p>
          {job.nansen_report ? <>
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

function NansenReportView({ record }: { record: NansenReportRecord }) {
  const report = record.content.report;
  const verified = Object.values(record.hashes_verified).every(Boolean);
  return (
    <div data-testid="nansen-report-view">
      <h3 style={{ fontSize: 16 }}>Saved report for {report.token_symbol}</h3>
      <p data-testid="nansen-question">Question: {report.question}</p>
      <p data-testid="nansen-answer-state">Answer state: {report.answer_state}</p>
      <p className="muted">{record.content.notice}</p>
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
        {" "}{report.coverage.incomplete_buckets} incomplete{report.coverage.stop_reason ? ` · stopped: ${report.coverage.stop_reason}` : ""}</p>
      {report.unknowns.length ? <p className="muted">Unknown: {report.unknowns.join("; ")}</p> : null}
    </div>
  );
}
