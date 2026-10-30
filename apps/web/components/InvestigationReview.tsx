"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { payloadBindingText } from "../lib/types";
import type { HistoryDeclaration, HistorySource, InvestigationJob, InvestigationReport, ResearchBudget, TransportSummary } from "../lib/api";
import type { InvestigationConfiguration, InvestigationEnvelope, InvestigationProposal, InvestigationSaveResult } from "../lib/types";
import { EffectComparisonPanel } from "./EffectComparisonPanel";
import { ResearchNansenReport } from "./ResearchNansenReport";
import { declarationRelease, describeRelease, releaseBounds, sourceRelease, transportRelease } from "../lib/research-release";
import { deriveHistoryPlan, historyUnknowns } from "../lib/history-declaration";
import type { HistoryDirection, HistoryPlan } from "../lib/history-declaration";

const ADOPTED_FIELDS = ["edge_spec", "question", "pool_binding", "variants", "direction", "horizons", "sources",
  "candidate_limit", "parameter_limit", "compute_limit", "period", "partitions", "permitted_access",
  "stopping_rule", "evaluation_plan", "budget_version", "optional_tools"];
function datetimeValue(value: string): string {
  return new Date(value).toISOString().slice(0, 16);
}

function utcValue(value: string): string {
  return new Date(`${value}:00Z`).toISOString();
}

function saveKeys(intakeId: string, body: Record<string, unknown>): { operation_id: string; idempotency_key: string } {
  const key = `edge-os:investigation:${intakeId}`;
  const fingerprint = JSON.stringify(body);
  try {
    const saved = window.sessionStorage.getItem(key);
    if (saved) {
      const parsed = JSON.parse(saved) as { fingerprint?: string; operation_id?: string; idempotency_key?: string };
      if (parsed.fingerprint === fingerprint && parsed.operation_id && parsed.idempotency_key) {
        return { operation_id: parsed.operation_id, idempotency_key: parsed.idempotency_key };
      }
    }
  } catch { /* a new key remains safe because edge identity and version are unique */ }
  const keys = { operation_id: crypto.randomUUID(), idempotency_key: `ui-${crypto.randomUUID()}` };
  try { window.sessionStorage.setItem(key, JSON.stringify({ ...keys, fingerprint })); } catch { /* ignore */ }
  return keys;
}

function errorDetail(error: unknown): string {
  return error instanceof ApiError ? error.detail : "The declaration could not be saved.";
}

export function InvestigationReview({ intakeId, interpretationRevisionId }: { intakeId: string; interpretationRevisionId: string | null }) {
  const [proposal, setProposal] = useState<InvestigationProposal | null>(null);
  const [declarations, setDeclarations] = useState<InvestigationEnvelope[] | null>(null);
  const [selected, setSelected] = useState<InvestigationSaveResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [adopted, setAdopted] = useState(false);
  const [error, setError] = useState("");
  const errorRef = useRef<HTMLParagraphElement>(null);
  const savedHeading = useRef<HTMLHeadingElement>(null);
  // Set only by a successful save; the effect below moves focus once the saved heading is committed.
  const focusSavedHeading = useRef(false);
  const hasSavedDeclarations = useRef(false);
  const [proposalError, setProposalError] = useState("");
  const [proposalRetryReplacesDraft, setProposalRetryReplacesDraft] = useState(false);
  const [refreshingProposal, setRefreshingProposal] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState("");
  const [savedReadFailed, setSavedReadFailed] = useState(false);
  const [reopenId, setReopenId] = useState("");
  const [configuration, setConfiguration] = useState<InvestigationConfiguration | null>(null);
  const [edgeSpec, setEdgeSpec] = useState<InvestigationProposal["edge_spec"] | null>(null);
  // The real source this server serves when it composes an approved ACTUAL release. Wording only; the server still
  // decides which sources exist. A read failure leaves the recorded labels in place.
  const [realSource, setRealSource] = useState<HistorySource | null>(null);

  useEffect(() => {
    let current = true;
    api.historySources().then((catalog) => {
      if (!current) return;
      setRealSource(catalog.sources.find((item) => sourceRelease(item)?.kind === "ACTUAL") ?? null);
    }).catch(() => { /* the recorded wording is the safe fallback */ });
    return () => { current = false; };
  }, []);

  useEffect(() => {
    let current = true;
    setLoading(true); setError(""); setProposalError(""); setSavedReadFailed(false);
    api.investigations(intakeId).then((saved) => {
      if (!current) return;
      setDeclarations(saved.declarations);
      hasSavedDeclarations.current = saved.declarations.length > 0;
      if (saved.declarations.length) {
        setSelected({ declaration: saved.declarations[0], access_history: saved.access_history,
          study_started: false, idempotent_replay: false });
        setProposal(null);
      }
    }).catch((cause: unknown) => { if (current) { setError(errorDetail(cause)); setSavedReadFailed(true); } })
      .finally(() => { if (current) setLoading(false); });
    void api.investigationProposal(intakeId).then((next) => {
      if (!current) return;
      if (hasSavedDeclarations.current) return;
      setProposal(next);
      setConfiguration((existing) => existing ?? next.configuration);
      setEdgeSpec((existing) => existing ?? next.edge_spec);
    }).catch((cause: unknown) => { if (current) setProposalError(errorDetail(cause)); });
    return () => { current = false; };
  }, [intakeId]);

  const refreshProposal = async (replaceDraft: boolean) => {
    setProposalError(""); setAdopted(false); setRefreshingProposal(true);
    try {
      const next = await api.investigationProposal(intakeId);
      const keepingDraft = !replaceDraft && Boolean(configuration && edgeSpec && proposal);
      const reviewedProposal = keepingDraft && proposal
        ? { ...next, trial_ids: proposal.trial_ids, evaluation_ids: proposal.evaluation_ids }
        : next;
      setProposal(reviewedProposal);
      if (replaceDraft || !configuration || !edgeSpec) {
        setConfiguration(next.configuration); setEdgeSpec(next.edge_spec); setAdopted(false);
      } else {
        setAdopted(false);
        setRefreshNotice("The request interpretation changed. Your unsaved edits remain in place. Review them against this current declaration before saving.");
      }
      setProposalRetryReplacesDraft(false);
      return true;
    } catch (cause) {
      setProposalRetryReplacesDraft(replaceDraft);
      setProposalError(errorDetail(cause));
      return false;
    }
    finally { setRefreshingProposal(false); }
  };

  useEffect(() => {
    if (loading || !proposal || proposal.interpretation_revision_id === interpretationRevisionId) return;
    void refreshProposal(false);
    // The current proposal is the revision guard; edits remain visible during refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interpretationRevisionId, loading]);

  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);

  useEffect(() => {
    if (!selected || !focusSavedHeading.current) return;
    focusSavedHeading.current = false;
    savedHeading.current?.focus();
  }, [selected]);

  const beginAnother = async () => {
    setBusy(true); setError(""); setSelected(null); setAdopted(false);
    setRefreshNotice("");
    try { await refreshProposal(true); }
    finally { setBusy(false); }
  };

  const updateConfiguration = <K extends keyof InvestigationConfiguration>(key: K, value: InvestigationConfiguration[K]) => {
    setConfiguration((current) => current ? { ...current, [key]: value } : current);
  };

  const updatePeriod = (period: InvestigationConfiguration["period"]) => {
    setConfiguration((current) => current ? { ...current, period,
      partitions: current.direction === "DESCRIPTIVE" && current.partitions[0]
        ? [{ ...current.partitions[0], start: period.start, end: period.end }]
        : current.partitions } : current);
  };

  const save = async () => {
    if (!proposal || !configuration || !edgeSpec || !adopted || busy || refreshingProposal) return;
    const fieldOrigins = Object.fromEntries(ADOPTED_FIELDS.map((field) => {
      if (field === "edge_spec" || field === "evaluation_plan") return [field, { origin: "USER_CONFIRMED", source_ref: "investigation-review/2", adoption: "ADOPTED" }];
      if (field === "question") return [field, { origin: "USER_STATED", source_ref: "original_request", adoption: "ADOPTED" }];
      const changed = JSON.stringify(configuration[field as keyof InvestigationConfiguration]) !==
        JSON.stringify(proposal.configuration[field as keyof InvestigationConfiguration]);
      return [field, { origin: changed ? "USER_CONFIRMED" : "APPLICATION_CONFIGURED",
        source_ref: changed ? "investigation-review/2" : `proposal:${proposal.proposal_version}`, adoption: "ADOPTED" }];
    }));
    const body = {
      expected_interpretation_revision_id: proposal.interpretation_revision_id,
      edge_spec: edgeSpec,
      configuration,
      adopted_fields: ADOPTED_FIELDS,
      field_origins: fieldOrigins,
      trial_ids: proposal.trial_ids,
      evaluation_ids: proposal.evaluation_ids,
    };
    const keys = saveKeys(intakeId, body);
    setBusy(true); setError("");
    try {
      const result = await api.saveInvestigation(intakeId, { ...keys, ...body });
      setDeclarations((current) => current ? [...current.filter((item) => item.record_id !== result.declaration.record_id), result.declaration]
        : [result.declaration]);
      focusSavedHeading.current = true;
      setSelected(result); setProposal(null); setAdopted(false);
      setRefreshNotice("");
      try { window.sessionStorage.removeItem(`edge-os:investigation:${intakeId}`); } catch { /* ignore */ }
    } catch (cause) {
      setError(errorDetail(cause));
      if (cause instanceof ApiError && cause.code === "interpretation_revision_conflict") await refreshProposal(false);
    }
    finally { setBusy(false); }
  };

  const reopen = async (declarationId: string) => {
    setBusy(true); setError("");
    try { setSelected(await api.investigation(intakeId, declarationId)); setReopenId(""); }
    catch (cause) { setError(errorDetail(cause)); setReopenId(declarationId); }
    finally { setBusy(false); }
  };

  const retrySavedReads = async () => {
    setBusy(true); setError(""); setSavedReadFailed(false);
    try {
      const saved = await api.investigations(intakeId);
      setDeclarations(saved.declarations);
      hasSavedDeclarations.current = saved.declarations.length > 0;
      if (saved.declarations.length) setSelected({ declaration: saved.declarations[0], access_history: saved.access_history,
        study_started: false, idempotent_replay: false });
      else await refreshProposal(false);
    } catch (cause) { setError(errorDetail(cause)); setSavedReadFailed(true); }
    finally { setBusy(false); }
  };

  const changeClaimStatus = (status: InvestigationProposal["edge_spec"]["claim"]["status"]) => {
    if (!edgeSpec || !configuration) return;
    const descriptive = status === "DESCRIPTIVE_ONLY";
    const start = Date.parse(configuration.period.start);
    const end = Date.parse(configuration.period.end);
    const third = Math.floor((end - start) / 3);
    const partitions = descriptive ? [{ partition_id: "descriptive", role: "DESCRIPTIVE" as const,
      start: configuration.period.start, end: configuration.period.end }] : [
      { partition_id: "training", role: "TRAINING" as const, start: new Date(start).toISOString(), end: new Date(start + third).toISOString() },
      { partition_id: "validation", role: "VALIDATION" as const, start: new Date(start + third).toISOString(), end: new Date(start + 2 * third).toISOString() },
      { partition_id: "holdout", role: "HOLDOUT" as const, start: new Date(start + 2 * third).toISOString(), end: new Date(end).toISOString() },
    ];
    setEdgeSpec({ ...edgeSpec,
      claim: { status, text: descriptive ? "Describe only. No predictive claim is declared." : "The primary group outperforms its comparison." },
      falsification: { status: descriptive ? "DESCRIPTIVE_ONLY" : "DECLARED",
        criteria: descriptive ? "No outcome claim is evaluated." : "The effect is absent in the declared comparison." },
    });
    setConfiguration({ ...configuration, direction: descriptive ? "DESCRIPTIVE" : "OUTPERFORM", partitions,
      evaluation_plan: configuration.evaluation_plan.map((item) => ({ ...item,
        partition_ids: [descriptive ? "descriptive" : "validation"] })) });
  };

  if (loading) return <section className="panel" aria-busy="true"><h2>Investigation plan</h2><p role="status">Loading the saved plan.</p></section>;

  const realRelease = realSource ? sourceRelease(realSource) : null;

  return (
    <section className="panel stack investigation-review" aria-labelledby="investigation-title" data-testid="investigation-review">
      <div>
        <h2 id="investigation-title">Investigation plan</h2>
        <p className="muted">Review the proposed scope and adoption sources. Saving records a pre-outcome declaration. It does not read data, run a study or start a trade.</p>
      </div>
      {error ? <p className="status err" role="alert" tabIndex={-1} ref={errorRef}>{error}</p> : null}
      {refreshingProposal ? <p role="status" aria-busy="true">Refreshing the current review. Your edits are unchanged.</p> : null}
      {proposalError ? <div className="status err" role="alert">
        <p>{proposalRetryReplacesDraft
          ? `A new hypothesis could not be prepared. ${proposalError} The saved declaration is unchanged.`
          : proposalError}</p>
        <button className="btn btn-secondary" type="button" onClick={() => void refreshProposal(proposalRetryReplacesDraft)} disabled={busy || refreshingProposal}>
          {proposalRetryReplacesDraft ? "Retry new hypothesis" : "Retry proposal"}
        </button>
      </div> : null}
      {reopenId ? <button className="btn btn-secondary" type="button" onClick={() => void reopen(reopenId)} disabled={busy}>Retry opening saved declaration</button> : null}
      {refreshNotice ? <p className="status stop" role="status">{refreshNotice}</p> : null}
      {savedReadFailed ? <button className="btn btn-secondary" type="button" onClick={() => void retrySavedReads()} disabled={busy}>Retry saved declarations</button> : null}

      {declarations?.length ? (
        <div className="stack">
          <h3>Saved declarations</h3>
          {declarations.map((item) => (
            <div className="card" key={item.record_id}>
              <strong>{item.content.edge_spec.hypothesis}</strong>
              <span className="muted">{item.content.edge_spec.claim.status === "DESCRIPTIVE_ONLY" ? "Descriptive only" : "Hypothesis"} · {item.content.configuration.budget_version}</span>
              <button className="btn btn-secondary" type="button" onClick={() => void reopen(item.record_id)} disabled={busy}>
                {busy ? "Opening…" : "Reopen saved declaration"}
              </button>
            </div>
          ))}
          <button className="btn btn-secondary" type="button" onClick={() => void beginAnother()} disabled={busy}>
            Review another hypothesis
          </button>
        </div>
      ) : null}

      {selected ? (
        <div className="status ok" data-testid="investigation-saved">
          <p className="visually-hidden" role="status">Declaration saved before outcome review. No study started.</p>
          <h3 ref={savedHeading} tabIndex={-1}>Declaration saved</h3>
          <p>{realRelease
            ? "Saved before outcome review. No study started. This saved profile is an interface example; the real-MOE study on this page is the history investigation below."
            : "Saved before outcome review. No study started. This profile uses an unqualified synthetic fixture."}</p>
          <dl className="kv">
            <dt>Declaration ID</dt><dd className="mono">{selected.declaration.record_id}</dd>
            <dt>Budget version</dt><dd>{selected.declaration.content.configuration.budget_version}</dd>
            <dt>P08 declaration-time outcome labels read</dt><dd>{selected.declaration.content.outcome_labels_read ? "Yes" : "No"}</dd>
            <dt>Provider queries</dt><dd>{selected.access_history[0]?.provider_queries ?? 0}</dd>
            <dt>Saved access event</dt><dd>{selected.access_history[0]?.event ?? "Unavailable"}</dd>
          </dl>
          <details>
            <summary>Review the complete saved configuration</summary>
            <pre className="records-json">{JSON.stringify(selected.declaration.content, null, 2)}</pre>
            <p className="muted">Sources, field origins, optional tools, trial identities and evaluation identities are saved with this declaration.</p>
          </details>
          <EffectComparisonPanel intakeId={intakeId} saved={selected} />
        </div>
      ) : null}

      {proposal && configuration && edgeSpec ? (
        <div className="stack">
          <p role="note" className="status stop">{realRelease && realSource
            ? `The real-MOE study on this page is the history investigation below. It uses the approved operating release ${realRelease.release_id} on pool ${realSource.market.pool_address} (base ${realSource.market.base_asset}, quote ${realSource.market.quote_asset}). This separate bounded review is an interface example: adoption saves a pre-outcome declaration and runs no study. Its example pool is not the real-MOE study's market and is not qualified for production research.`
            : `${proposal.notice} The proposal keeps your original request unchanged. This synthetic pool is not qualified for production research.`}</p>
          <section aria-labelledby="request-review-title" className="stack">
            <h3 id="request-review-title">Your request and hypothesis</h3>
            <p className="words" data-testid="investigation-original-request">{configuration.question}</p>
            <div className="field">
              <label htmlFor="edge-hypothesis">Hypothesis or descriptive question</label>
              <textarea id="edge-hypothesis" className="input" value={edgeSpec.hypothesis}
                onChange={(event) => setEdgeSpec({ ...edgeSpec, hypothesis: event.target.value })} />
            </div>
            <div className="field">
              <label htmlFor="edge-claim-status">Claim status</label>
              <select id="edge-claim-status" className="input" value={edgeSpec.claim.status}
                onChange={(event) => {
                  const status = event.target.value as typeof edgeSpec.claim.status;
                  changeClaimStatus(status);
                }}>
                <option value="DESCRIPTIVE_ONLY">Descriptive only</option>
                <option value="HYPOTHESIS">Test a stated hypothesis</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="edge-claim">Claim</label>
              <textarea id="edge-claim" className="input" value={edgeSpec.claim.text}
                onChange={(event) => setEdgeSpec({ ...edgeSpec, claim: { ...edgeSpec.claim, text: event.target.value } })} />
            </div>
            <div className="field">
              <label htmlFor="edge-falsification">Falsification condition or descriptive status</label>
              <textarea id="edge-falsification" className="input" value={edgeSpec.falsification.criteria}
                onChange={(event) => setEdgeSpec({ ...edgeSpec,
                  falsification: { ...edgeSpec.falsification, status: edgeSpec.claim.status === "DESCRIPTIVE_ONLY" ? "DESCRIPTIVE_ONLY" : "DECLARED",
                    criteria: event.target.value } })} />
            </div>
            <div className="field">
              <label htmlFor="edge-alternative">Alternative explanation</label>
              <textarea id="edge-alternative" className="input" value={edgeSpec.alternatives.join("\n")}
                onChange={(event) => setEdgeSpec({ ...edgeSpec, alternatives: event.target.value.split("\n").slice(0, 10) })} />
            </div>
            <div className="field">
              <label htmlFor="edge-unknowns">Unverified mechanism details and evidence gaps</label>
              <textarea id="edge-unknowns" className="input" value={edgeSpec.unknowns.join("\n")}
                onChange={(event) => setEdgeSpec({ ...edgeSpec, unknowns: event.target.value.split("\n").slice(0, 20) })} />
              <span className="muted">Participant incentives, persistence, capacity, costs and capture remain unknown until evidence supports a claim.</span>
            </div>
          </section>

          <section aria-labelledby="scope-title" className="stack">
            <h3 id="scope-title">Proposed scope and budget</h3>
            <dl className="kv">
              <dt>{realRelease ? "Example pool (not the real-MOE study market)" : "Pool"}</dt>
              <dd>{realRelease ? "Unqualified interface example; the saved declaration keeps its exact identifier."
                : `${configuration.pool_binding.profile_id} · unqualified synthetic fixture`}</dd>
              <dt>Limitations</dt><dd>{realRelease
                ? "Interface example only; no production pool or source is qualified."
                : configuration.pool_binding.limitations.join(" ")}</dd>
              <dt>Data source</dt><dd>{realRelease ? "Interface example only" : configuration.sources.join(", ")}</dd>
              <dt>Permitted access</dt><dd>{realRelease ? "Interface example only. No provider queries." : "Fixture only. No provider queries."}</dd>
              <dt>Budget version</dt><dd>{configuration.budget_version}</dd>
              <dt>Cost ceiling</dt><dd>$0. No paid access is permitted.</dd>
              <dt>Partitions</dt><dd>{configuration.partitions.map((item) => `${item.partition_id}: ${item.role}`).join(", ")}</dd>
            </dl>
            <div className="field">
              <label htmlFor="variant-primary">Primary variant</label>
              <input id="variant-primary" className="input" value={configuration.variants[0]?.hypothesis ?? ""}
                onChange={(event) => updateConfiguration("variants", configuration.variants.map((item, index) => index === 0 ? { ...item, hypothesis: event.target.value } : item))} />
            </div>
            <div className="field">
              <label htmlFor="variant-comparison">Comparison variant</label>
              <input id="variant-comparison" className="input" value={configuration.variants[1]?.hypothesis ?? ""}
                onChange={(event) => updateConfiguration("variants", configuration.variants.map((item, index) => index === 1 ? { ...item, hypothesis: event.target.value } : item))} />
            </div>
            <div className="field">
              <label htmlFor="investigation-direction">Expected direction</label>
              <select id="investigation-direction" className="input" value={configuration.direction}
                onChange={(event) => updateConfiguration("direction", event.target.value as InvestigationConfiguration["direction"])}>
                {edgeSpec.claim.status === "DESCRIPTIVE_ONLY" ? (
                  <option value="DESCRIPTIVE">Descriptive, no prediction</option>
                ) : <>
                  <option value="OUTPERFORM">Primary group outperforms comparison</option>
                  <option value="UNDERPERFORM">Primary group underperforms comparison</option>
                </>}
              </select>
            </div>
            <div className="field">
              <label htmlFor="investigation-horizon">Outcome horizon (positive integer)</label>
              <input id="investigation-horizon" className="input" type="number" min={1} step={1} value={configuration.horizons[0]?.value ?? 1}
                onChange={(event) => {
                  const horizon = { ...(configuration.horizons[0] ?? { value: 15, unit: "MINUTES" as const }), value: Number(event.target.value) };
                  setConfiguration({ ...configuration, horizons: [horizon], evaluation_plan: configuration.evaluation_plan.map((item) => ({ ...item, horizon })) });
                }} />
              <label htmlFor="investigation-horizon-unit">Horizon unit</label>
              <select id="investigation-horizon-unit" className="input" value={configuration.horizons[0]?.unit ?? "MINUTES"}
                onChange={(event) => {
                  const horizon = { ...(configuration.horizons[0] ?? { value: 15, unit: "MINUTES" as const }), unit: event.target.value as InvestigationConfiguration["horizons"][number]["unit"] };
                  setConfiguration({ ...configuration, horizons: [horizon], evaluation_plan: configuration.evaluation_plan.map((item) => ({ ...item, horizon })) });
                }}>
                <option value="SECONDS">Seconds</option><option value="MINUTES">Minutes</option>
                <option value="HOURS">Hours</option><option value="DAYS">Days</option>
              </select>
            </div>
            <div className="field">
              <label htmlFor="period-start">Period start (UTC)</label>
              <input id="period-start" className="input" type="datetime-local" value={datetimeValue(configuration.period.start)}
                onChange={(event) => { if (event.target.value) updatePeriod({ ...configuration.period, start: utcValue(event.target.value) }); }} />
            </div>
            <fieldset>
              <legend className="legend">Temporal partitions in UTC</legend>
              <p className="muted">Every interval is explicit. Predictive review keeps training, validation and holdout separate. Descriptive work covers the complete period without an invented holdout.</p>
              {configuration.partitions.map((partition) => (
                <div className="field" key={partition.partition_id}>
                  <strong>{partition.role} · {partition.partition_id}</strong>
                  <label htmlFor={`partition-${partition.partition_id}-start`}>Start</label>
                  <input id={`partition-${partition.partition_id}-start`} className="input" type="datetime-local" value={datetimeValue(partition.start)}
                    onChange={(event) => { if (event.target.value) updateConfiguration("partitions", configuration.partitions.map((item) => item.partition_id === partition.partition_id ? { ...item, start: utcValue(event.target.value) } : item)); }} />
                  <label htmlFor={`partition-${partition.partition_id}-end`}>End</label>
                  <input id={`partition-${partition.partition_id}-end`} className="input" type="datetime-local" value={datetimeValue(partition.end)}
                    onChange={(event) => { if (event.target.value) updateConfiguration("partitions", configuration.partitions.map((item) => item.partition_id === partition.partition_id ? { ...item, end: utcValue(event.target.value) } : item)); }} />
                </div>
              ))}
            </fieldset>
            <section aria-labelledby="evaluation-plan-title" className="stack">
              <h4 id="evaluation-plan-title">Explicit proposed evaluations</h4>
              <p className="muted">Each row binds one evaluation identity to one trial, variant, horizon and exact partition. Rows are adopted individually as listed; no combinations are generated.</p>
              {configuration.evaluation_plan.map((item) => (
                <p className="mono" key={item.evaluation_id}>{item.evaluation_id} · trial {item.trial_id} · {item.variant_id} · {item.horizon.value} {item.horizon.unit.toLowerCase()} · {item.partition_ids.join(", ")}</p>
              ))}
            </section>
            <div className="field">
              <label htmlFor="period-end">Period end (UTC)</label>
              <input id="period-end" className="input" type="datetime-local" value={datetimeValue(configuration.period.end)}
                onChange={(event) => { if (event.target.value) updatePeriod({ ...configuration.period, end: utcValue(event.target.value) }); }} />
            </div>
            <div className="field">
              <label htmlFor="candidate-limit">Candidate limit</label>
              <input id="candidate-limit" className="input" type="number" min={1} max={100} value={configuration.candidate_limit}
                onChange={(event) => updateConfiguration("candidate_limit", Number(event.target.value))} />
            </div>
            <div className="field">
              <label htmlFor="parameter-limit">Parameter limit</label>
              <input id="parameter-limit" className="input" type="number" min={1} max={1000} value={configuration.parameter_limit}
                onChange={(event) => updateConfiguration("parameter_limit", Number(event.target.value))} />
            </div>
            <div className="field">
              <label htmlFor="evaluation-limit">Compute limit, evaluations</label>
              <input id="evaluation-limit" className="input" type="number" min={1} max={100} value={configuration.compute_limit.max_evaluations}
                onChange={(event) => updateConfiguration("compute_limit", { ...configuration.compute_limit, max_evaluations: Number(event.target.value) })} />
            </div>
            <div className="field">
              <label htmlFor="runtime-limit">Compute limit, seconds</label>
              <input id="runtime-limit" className="input" type="number" min={1} max={3600} value={configuration.compute_limit.max_runtime_seconds}
                onChange={(event) => updateConfiguration("compute_limit", { ...configuration.compute_limit, max_runtime_seconds: Number(event.target.value) })} />
            </div>
            <div className="field">
              <label htmlFor="stopping-rule">Stopping rule</label>
              <textarea id="stopping-rule" className="input" value={configuration.stopping_rule}
                onChange={(event) => updateConfiguration("stopping_rule", event.target.value)} />
            </div>
            <fieldset>
              <legend className="legend">Optional tools</legend>
              <p className="muted">These tools are unavailable in this build. Mark each unavailable or not required.</p>
              {(["creator_history", "wallet_pnl", "social_signals"] as const).map((tool) => (
                <div className="field" key={tool}>
                  <label htmlFor={`tool-${tool}`}>{tool.replaceAll("_", " ")}</label>
                  <select id={`tool-${tool}`} className="input" value={configuration.optional_tools[tool]}
                    onChange={(event) => updateConfiguration("optional_tools", { ...configuration.optional_tools,
                      [tool]: event.target.value as "UNAVAILABLE" | "NOT_REQUIRED" })}>
                    <option value="UNAVAILABLE">Unavailable</option>
                    <option value="NOT_REQUIRED">Not required for this question</option>
                  </select>
                </div>
              ))}
            </fieldset>
          </section>

          <label className="choice">
            <input type="checkbox" checked={adopted} onChange={(event) => setAdopted(event.target.checked)} />
            <span>I reviewed the hypothesis and every required setting above. I adopt this exact, fixture-only declaration for a future investigation.</span>
          </label>
          <div className="btn-row">
            <button className="btn btn-primary" type="button" onClick={() => void save()} disabled={!adopted || busy || refreshingProposal}>
              {busy ? "Saving declaration…" : "Adopt and save declaration"}
            </button>
            <span className="muted">Save records the plan before outcomes. It starts no study and grants no provider, wallet or financial permission.</span>
          </div>
        </div>
      ) : null}
      <HistoryInvestigation intakeId={intakeId} interpretationRevisionId={interpretationRevisionId} />
      <ResearchNansenReport intakeId={intakeId} />
    </section>
  );
}

const HISTORY_FIELDS = ["edge_spec", "question", "source", "market", "window", "variants", "direction", "horizons",
  "partitions", "evaluation_plan", "schedule", "rule_map", "resource_bounds", "permitted_access", "stopping_rule",
  "budget_version"];
const HISTORY_REVIEW = "history-investigation-review/1";
const RUNNING = new Set(["QUEUED", "RESERVED", "COLLECTING", "EVALUATING"]);
const STATE_COPY: Record<string, string> = {
  QUEUED: "Saved. Waiting for capacity.",
  RESERVED: "Waiting for the research worker. Its budget is reserved; nothing is collected yet.",
  COLLECTING: "Collecting the recorded responses.",
  EVALUATING: "Comparing with your adopted rules.",
  REPORTED: "Report saved.",
  CANCELLED: "Cancelled. Saved attempts and any partial dataset are kept.",
  DEADLINE_EXCEEDED: "Stopped at its deadline. Saved attempts are kept.",
  BUDGET_EXHAUSTED: "Refused: your research budget cannot reserve this job. Nothing was collected.",
  UNAVAILABLE: "The collection outcome is unknown after a stop. It is not collected again; its full reservation stays counted.",
  FAILED: "The job failed. Its attempts and unknown usage are kept.",
};

interface RuleRow { lookback: string; rise: "gt" | "lt"; threshold: string; volume: string }

function expressions(row: RuleRow, quoteUnit: string) {
  return {
    price: { op: row.rise, args: [{ op: "price_return", lookback_buckets: Number(row.lookback) },
      { op: "constant", value: row.threshold, unit: "DIMENSIONLESS" }] },
    volume: { op: "gt", args: [{ op: "quote_volume" }, { op: "constant", value: row.volume, unit: quoteUnit }] },
  };
}

function storedKey(name: string): string {
  try {
    const saved = window.sessionStorage.getItem(name);
    if (saved) return saved;
  } catch { /* storage may be blocked; a new key is still a single original start */ }
  const key = `ui-${crypto.randomUUID()}`;
  try { window.sessionStorage.setItem(name, key); } catch { /* ignore */ }
  return key;
}

function forgetKey(name: string): void {
  try { window.sessionStorage.removeItem(name); } catch { /* ignore */ }
}

function JobReport({ report }: { report: InvestigationReport }) {
  const content = report.content;
  return (
    <div className="stack" data-testid="history-report">
      <h5>Saved report: {content.outcome}</h5>
      <p>{content.notice}</p>
      <dl className="kv">
        <dt>Report ID</dt><dd className="mono" data-testid="history-report-id">{report.report_id}</dd>
        <dt>Stored copy</dt><dd>{report.stored_hash_matches_content ? "Read back. Its hash matches." : "Could not be confirmed."}</dd>
        <dt>Reasons</dt><dd>{content.outcome_reasons.join(", ")}</dd>
        <dt>Dataset</dt><dd className="mono" data-testid="history-report-dataset">{content.dataset_id}</dd>
        <dt>Data</dt><dd>{content.source_id}; {content.evidence_class}; {content.content_label}; verdict {content.dataset_verdict.overall}</dd>
        <dt>Statistics</dt><dd>{content.statistical_status}; significance {content.claims.significance}; capital authority {content.claims.capital_authority}</dd>
      </dl>
      {content.variants.length ? (
        <table>
          <caption>Adopted rules, triggered minus untriggered mean response</caption>
          <thead><tr><th scope="col">Variant</th><th scope="col">Outcome</th><th scope="col">Triggered</th><th scope="col">Control</th><th scope="col">Difference</th></tr></thead>
          <tbody>{content.variants.map((item) => (
            <tr key={item.evaluation_id}><td>{item.variant_id}</td><td>{item.outcome}</td><td>{item.triggered_observed}</td>
              <td>{item.control_observed}</td><td className="mono">{item.triggered_minus_control_mean ?? "none"}</td></tr>))}</tbody>
        </table>
      ) : null}
      {content.contrary_findings.length ? <p className="status stop">Contrary findings kept: {content.contrary_findings.map((item) => `${item.variant_id} ${item.finding}`).join("; ")}</p> : null}
      {content.protected_partitions?.length ? <p className="muted">Not read: {content.protected_partitions.map((item) => `${item.role} partition`).join(", ")}.</p> : null}
    </div>
  );
}

/** What the P07 transport computed from a native recording, apart from what the recording only declares. */
function TransportFacts({ transport }: { transport: TransportSummary }) {
  const corroboration = transport.corroboration;
  const release = transportRelease(transport);
  const chainPhrase = release?.operating_release?.kind === "ACTUAL"
    ? "chain id checked against provider responses"
    : release?.operating_release?.kind === "STAND_IN"
    ? "chain id checked against stand-in responses"
    : "chain id checked against recorded responses";
  return (
    <p className="muted" data-testid="history-transport">
      {release
        ? `Operating release ${release.operating_release?.release_id ?? "unknown"} through the accepted P07 HTTP clients (${Object.values(transport.client_classes ?? {}).join(", ")}) over ${(release.transport_kind ?? "").replaceAll("_", " ").toLowerCase()}. ${release.operating_release?.kind === "ACTUAL" ? "Provider responses" : "Stand-in responses, not provider data"}; ${release.requests_hashed ?? 0} request hashes kept; endpoint hosts ${Object.values(release.endpoint_hosts ?? {}).join(", ")}: `
        : transport.clients === "P07_HTTP_CLIENTS_AUTHORED_TRANSPORT"
        ? `Authored HTTP responses served on this server through the accepted P07 HTTP clients (${Object.values(transport.client_classes ?? {}).join(", ")}), no network. Not provider data: `
        : "Native recording, replayed locally: "}{transport.envio_pages_framed} Envio pages framed; {chainPhrase}: {transport.chain_id === null ? "not read" : `${transport.chain_id}${transport.chain_network ? ` (${transport.chain_network})` : " (not Monad)"}`}; receipt corroboration {corroboration.class}, {corroboration.sample_size} of {corroboration.population_size} checked, {corroboration.mismatches} mismatches{transport.corroboration_reason ? ` (${transport.corroboration_reason})` : ""}. Client calls: {Object.entries(transport.client_calls).map(([name, count]) => `${name} ${count}`).join(", ")}. Recorded declarations, not read by the application: {transport.recorded_declarations.join(", ").replaceAll("_", " ")}.
    </p>
  );
}

/** One recorded-history investigation: declare first, then run one original job at a time. */
export function HistoryInvestigation({ intakeId, interpretationRevisionId }: { intakeId: string; interpretationRevisionId: string | null }) {
  const [question, setQuestion] = useState("");
  const [sources, setSources] = useState<HistorySource[]>([]);
  const [researchUnavailable, setResearchUnavailable] = useState(false);
  const [budget, setBudget] = useState<ResearchBudget | null>(null);
  const [declarations, setDeclarations] = useState<HistoryDeclaration[]>([]);
  const [selected, setSelected] = useState<HistoryDeclaration | null>(null);
  const [jobs, setJobs] = useState<InvestigationJob[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [hypothesis, setHypothesis] = useState("");
  const [direction, setDirection] = useState("DESCRIPTIVE");
  const [rules, setRules] = useState<RuleRow[]>([{ lookback: "", rise: "gt", threshold: "", volume: "" }]);
  const [bounds, setBounds] = useState({ provider_requests: "2", compute_seconds: "30", deadline_seconds: "600" });
  const [adopted, setAdopted] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [loadError, setLoadError] = useState("");
  const [uncertainStart, setUncertainStart] = useState(false);
  // A save with no answer keeps its exact body; a retry resends it unchanged so the server can return the original.
  const pendingName = `edge-os:history-declaration-pending:${intakeId}`;
  const [pendingDeclaration, setPendingState] = useState<Record<string, unknown> | null>(() => {
    try { const saved = window.sessionStorage.getItem(pendingName); return saved ? JSON.parse(saved) : null; }
    catch { return null; }
  });
  // The unconfirmed body also survives a reload in this tab, so a retry after a reload resends the same request.
  const setPendingDeclaration = (body: Record<string, unknown> | null) => {
    setPendingState(body);
    try {
      if (body) window.sessionStorage.setItem(pendingName, JSON.stringify(body));
      else window.sessionStorage.removeItem(pendingName);
    } catch { /* storage may be blocked; the in-page retry still works */ }
  };

  const refreshBudget = async () => { try { setBudget(await api.researchBudget()); } catch { setBudget(null); } };
  // Every call goes through a try: a missing or failing read shows a retry instead of breaking the plan above.
  const loadAll = async () => {
    setLoadError("");
    try {
      const [catalog, saved, request] = await Promise.all([api.historySources(), api.historyInvestigations(intakeId),
        api.get(intakeId)].map((call) => Promise.resolve(call))) as [Awaited<ReturnType<typeof api.historySources>>,
        Awaited<ReturnType<typeof api.historyInvestigations>>, Awaited<ReturnType<typeof api.get>>];
      setSources(catalog.sources);
      setResearchUnavailable(catalog.mode === "unavailable" && !catalog.operating_release);
      setDeclarations(saved.declarations); setQuestion(request.intake.content.original_request);
      await refreshBudget();
    } catch (cause) { setLoadError(cause instanceof ApiError ? cause.detail : "Recorded-history research could not be loaded."); }
  };
  useEffect(() => { void loadAll(); }, [intakeId]); // eslint-disable-line react-hooks/exhaustive-deps

  const loadJobs = async (declaration: HistoryDeclaration) => {
    try { setJobs((await api.investigationJobs(intakeId, declaration.declaration.record_id)).jobs); }
    catch (cause) { setError(cause instanceof ApiError ? cause.detail : "The saved jobs could not be loaded. Check again."); }
  };
  const open = async (declaration: HistoryDeclaration) => { setSelected(declaration); setError(""); setNotice(""); await loadJobs(declaration); };

  const source = sources.find((item) => item.source_id === sourceId) ?? null;
  const frozenRelease = selected ? declarationRelease(selected.declaration.content.frozen as unknown as Record<string, unknown>) : null;
  const rulesComplete = rules.every((row) => /^[1-9][0-9]?$/.test(row.lookback) && /^-?[0-9]+(\.[0-9]+)?$/.test(row.threshold)
    && /^[0-9]+(\.[0-9]+)?$/.test(row.volume));
  // The longest rule lookback decides how much history a decision needs before the schedule can start.
  const lookbackBuckets = rules.reduce((longest, row) => {
    const value = Number(row.lookback);
    return Number.isInteger(value) && value > longest ? value : longest;
  }, 0);
  const plan = source ? deriveHistoryPlan({ window: source.window, direction: direction as HistoryDirection, lookbackBuckets }) : null;
  const planRefusal = plan && !plan.ok && rulesComplete ? plan.reason : "";
  const ready = source !== null && question.length > 0 && hypothesis.trim().length > 0 && rulesComplete && adopted
    && plan !== null && plan.ok;

  const buildDeclaration = (source: HistorySource, plan: Extract<HistoryPlan, { ok: true }>): Record<string, unknown> => {
    const release = sourceRelease(source);
    const fixedBounds = release ? releaseBounds(release) : null;
    const quoteUnit = `QUOTE:${source.market.quote_asset}`;
    const trial = crypto.randomUUID();
    const evaluations = rules.map(() => crypto.randomUUID());
    const variants = rules.map((_, index) => `rule-${index + 1}`);
    const descriptive = direction === "DESCRIPTIVE";
    const partitions = plan.partitions;
    return {
      operation_id: crypto.randomUUID(), idempotency_key: `ui-history-${crypto.randomUUID()}`,
      expected_interpretation_revision_id: interpretationRevisionId,
      edge_spec: { edge_id: crypto.randomUUID(), version: 1, parent_declaration_id: null, hypothesis: hypothesis.trim(),
        claim: descriptive ? { status: "DESCRIPTIVE_ONLY", text: "Describe only." } : { status: "HYPOTHESIS", text: hypothesis.trim() },
        falsification: descriptive ? { status: "DESCRIPTIVE_ONLY", criteria: "No outcome claim is evaluated." }
          : { status: "DECLARED", criteria: direction === "OUTPERFORM" ? "The triggered minus untriggered mean is not positive." : "The triggered minus untriggered mean is not negative." },
        alternatives: ["Short-term noise explains any difference."],
        unknowns: historyUnknowns(source.evidence_class, sourceRelease(source)?.release_id ?? null) },
      configuration: {
        question, source: { source_id: source.source_id, profile_sha256: source.profile_sha256, evidence_class: source.evidence_class },
        market: source.market, window: source.window,
        variants: variants.map((variant_id, index) => ({ variant_id, hypothesis: `Adopted rule ${index + 1}` })),
        direction, horizons: [{ value: 5, unit: "MINUTES" }], partitions,
        evaluation_plan: evaluations.map((evaluation_id, index) => ({ evaluation_id, trial_id: trial, variant_id: variants[index],
          horizon: { value: 5, unit: "MINUTES" }, partition_ids: [partitions[0].partition_id] })),
        schedule: plan.schedule,
        rule_map: { schema_version: "edge-os.hypothesis-rule-map/1", control: "UNTRIGGERED_DECISIONS", incremental_volume_declared: true,
          rules: rules.map((row, index) => {
            const built = expressions(row, quoteUnit);
            return { evaluation_id: evaluations[index], trial_id: trial, variant_id: variants[index], price_expression: built.price,
              volume_expression: built.volume, essential_inputs: ["price", "quote_volume"], rule_source: "USER_ADOPTED" };
          }) },
        // An operating-release source runs under its fixed limits; the server refuses any other bounds.
        resource_bounds: fixedBounds ?? { provider_requests: Number(bounds.provider_requests), compute_seconds: Number(bounds.compute_seconds),
          max_pages: Math.min(Number(bounds.provider_requests), source.page_requests_recorded + 1) || 1, max_rows: 2000,
          max_bytes: 1_048_576, deadline_seconds: Number(bounds.deadline_seconds) },
        permitted_access: [source.evidence_class], stopping_rule: "Stop after the declared evaluations on the declared window.",
        budget_version: "edge-os.research-budget/1",
      },
      field_origins: Object.fromEntries(HISTORY_FIELDS.map((name) => [name, name === "question"
        ? { origin: "USER_STATED", source_ref: "original_request", adoption: "ADOPTED" }
        : { origin: "USER_CONFIRMED", source_ref: HISTORY_REVIEW, adoption: "ADOPTED" }])),
      trial_ids: [trial], evaluation_ids: evaluations,
    };
  };

  const saveDeclaration = async (body: Record<string, unknown>) => {
    setBusy(true); setError(""); setNotice(""); setPendingDeclaration(body);
    try {
      const saved = await api.saveHistoryInvestigation(intakeId, body);
      setPendingDeclaration(null);
      setDeclarations((current) => [...current.filter((item) => item.declaration.record_id !== saved.declaration.record_id), saved]);
      setAdopted(false); await open(saved);
      setNotice("Declaration saved before any collection. No data was read.");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status !== 0) {
        setPendingDeclaration(null);
        setError(cause.detail);
      } else {
        setError("We could not confirm the save. Retry sends the same declaration, so it cannot save twice.");
      }
    } finally { setBusy(false); }
  };

  const declare = () => {
    if (!ready || busy || !source || pendingDeclaration) return;
    const current = deriveHistoryPlan({ window: source.window, direction: direction as HistoryDirection, lookbackBuckets });
    if (!current.ok) return;
    void saveDeclaration(buildDeclaration(source, current));
  };

  const startJob = async (fresh: boolean) => {
    if (!selected || busy) return;
    const name = `edge-os:history-job:${selected.declaration.record_id}`;
    if (fresh) forgetKey(name);
    const requestKey = storedKey(name);
    const operation = storedKey(`${name}:operation`).replace(/^ui-/, "");
    setBusy(true); setError(""); setNotice(""); setUncertainStart(false);
    try {
      await api.startInvestigationJob(intakeId, selected.declaration.record_id, { operation_id: operation, request_key: requestKey });
      forgetKey(name); forgetKey(`${name}:operation`);
      setNotice("Job saved and its budget reserved. It waits for the research worker.");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 0) {
        setUncertainStart(true);
        setError("We could not confirm the start. Check again: it reuses the same request, so it cannot start twice.");
      } else {
        forgetKey(name); forgetKey(`${name}:operation`);
        setError(cause instanceof ApiError ? cause.detail : "The job was not started.");
      }
    } finally { await loadJobs(selected); await refreshBudget(); setBusy(false); }
  };

  const cancel = async (job: InvestigationJob) => {
    if (busy || !selected) return;
    setBusy(true); setError("");
    try { await api.cancelInvestigationJob(job.job_id); setNotice("Cancellation saved."); }
    catch (cause) { setError(cause instanceof ApiError ? cause.detail : "We could not confirm the cancellation. Check again."); }
    finally { await loadJobs(selected); await refreshBudget(); setBusy(false); }
  };

  const actualSource = sources.find((item) => sourceRelease(item)?.kind === "ACTUAL") ?? null;

  return (
    <section className="stack" aria-labelledby="history-title" data-testid="history-investigation"
      style={{ overflowWrap: "anywhere" }}>
      <h3 id="history-title">{actualSource ? "History investigation" : "Recorded-history investigation"}</h3>
      {researchUnavailable
        ? <p className="status stop" data-testid="research-unavailable" role="status">Research is not available here yet. This server composes no research release, so a new study cannot start. Saved studies still open below; nothing is read or sent.</p>
        : actualSource
        ? <p className="status stop">{`This server composes the approved actual operating release ${sourceRelease(actualSource)!.release_id}: its history source calls the named providers within the fixed limits. Results are descriptive and grant no trading permission.`}</p>
        : <p className="status stop">Recorded responses only: every source here is a SYNTHETIC recording replayed locally. No provider is called and nothing here is observed market history. Results are descriptive and grant no trading permission.</p>}
      {loadError ? <div className="status err" role="alert"><p>{loadError}</p><button className="btn btn-secondary" type="button" onClick={() => void loadAll()}>Retry</button></div> : null}
      {budget ? (
        <p data-testid="research-budget">Research budget available: {budget.available.provider_requests} provider requests, {budget.available.compute_seconds} compute seconds. Reserved {budget.reserved.provider_requests}; unknown liability {budget.unknown_liability.provider_requests}.</p>
      ) : null}
      {error ? <p className="status err" role="alert">{error}</p> : null}
      {notice ? <p className="status ok" role="status">{notice}</p> : null}
      {pendingDeclaration && !busy ? <button className="btn btn-secondary" type="button" onClick={() => void saveDeclaration(pendingDeclaration)}>Retry the same declaration</button> : null}
      {uncertainStart ? <button className="btn btn-secondary" type="button" onClick={() => void startJob(false)} disabled={busy}>Check again with the same start</button> : null}

      {declarations.length ? (
        <div className="stack">
          <h4>Saved history declarations</h4>
          {declarations.map((item) => (
            <div className="card" key={item.declaration.record_id}>
              <strong>{item.declaration.content.edge_spec.hypothesis}</strong>
              <span className="muted">{item.declaration.content.configuration.source.source_id} · {item.declaration.content.configuration.direction}</span>
              <button className="btn btn-secondary" type="button" onClick={() => void open(item)} disabled={busy}>Open this declaration</button>
            </div>
          ))}
        </div>
      ) : null}

      {selected ? (
        <div className="stack" data-testid="history-declaration">
          <h4>Declaration {selected.declaration.record_id}</h4>
          <dl className="kv">
            <dt>Declaration ID</dt><dd className="mono" data-testid="history-declaration-id">{selected.declaration.record_id}</dd>
            <dt>Saved before data</dt><dd>{selected.declaration.content.declaration_state}; provider queries {selected.access_history[0]?.provider_queries ?? 0}</dd>
            <dt>Configuration hash</dt><dd className="mono">{selected.declaration.content.frozen.configuration_sha256}</dd>
            <dt>Rule map hash</dt><dd className="mono">{selected.declaration.content.frozen.rule_map_sha256}</dd>
            <dt>Reserved per job</dt><dd>{selected.declaration.content.configuration.resource_bounds.provider_requests} provider requests, {selected.declaration.content.configuration.resource_bounds.compute_seconds} compute seconds</dd>
            {frozenRelease ? <>
              <dt>Operating release</dt><dd className="mono" data-testid="history-declaration-release">{frozenRelease.id} · {frozenRelease.sha256}</dd>
            </> : null}
          </dl>
          <div className="btn-row">
            <button className="btn btn-primary" type="button" onClick={() => void startJob(false)} disabled={busy}>Start investigation job</button>
            <button className="btn btn-secondary" type="button" onClick={() => void loadJobs(selected)} disabled={busy}>Check job status</button>
          </div>
          {jobs.map((job) => (
            <div className="card stack" key={job.job_id} data-testid="history-job" data-state={job.state}>
              <strong>Job {job.job_id.slice(0, 8)}: {job.state}</strong>
              <p role="status">{STATE_COPY[job.state] ?? job.state}{job.terminal_reason ? ` (${job.terminal_reason})` : ""}</p>
              <p className="muted">Attempts and events: {job.events.map((event) => event.kind).join(" → ")}</p>
              <p className="muted">Provider requests: reserved {job.budget.reserved?.provider_requests ?? 0}, consumed {job.budget.consumed?.provider_requests ?? 0}, released {job.budget.released?.provider_requests ?? 0}, unknown liability {job.budget.unknown_liability?.provider_requests ?? 0}.</p>
              {job.dataset?.transport ? <TransportFacts transport={job.dataset.transport} /> : null}
              {job.dataset ? <p>Dataset <span className="mono">{job.dataset.dataset_id}</span>: {job.dataset.summary.status}, {job.dataset.summary.verdict.overall}, {job.dataset.summary.binding_state}{job.dataset.summary.unavailable_states.length ? `; ${job.dataset.summary.unavailable_states.join(", ")}` : ""}; provider usage {job.dataset.summary.provider_requests_state}.</p> : null}
              {job.dataset?.payload_binding && job.dataset.payload_binding.status !== "NOT_REQUIRED"
                ? <p data-testid="history-payload-binding" data-status={job.dataset.payload_binding.status}
                  style={{ overflowWrap: "anywhere" }}>{payloadBindingText(job.dataset.payload_binding)}</p> : null}
              {RUNNING.has(job.state) && !job.cancel_requested_at ? <button className="btn btn-secondary" type="button" onClick={() => void cancel(job)} disabled={busy}>Cancel this job</button> : null}
              {!RUNNING.has(job.state) && job.state !== "REPORTED" ? <button className="btn btn-secondary" type="button" onClick={() => void startJob(true)} disabled={busy}>Retry as a new job</button> : null}
              {job.report ? <JobReport report={job.report} /> : null}
            </div>
          ))}
        </div>
      ) : null}

      {researchUnavailable ? null : <details open={declarations.length === 0}>
        <summary>{actualSource ? "Declare a new history investigation" : "Declare a new recorded-history investigation"}</summary>
        <div className="stack">
          <div className="field">
            <label htmlFor="history-source">Recorded source</label>
            <select id="history-source" className="input" value={sourceId} onChange={(event) => {
              const next = sources.find((item) => item.source_id === event.target.value);
              setSourceId(event.target.value); setAdopted(false);
              // A native recording also needs one chain read and one receipt per corroborated swap.
              const fixed = sourceRelease(next ?? null)?.history?.limits;
              if (next && fixed) setBounds({ provider_requests: String(fixed.provider_requests), compute_seconds: String(fixed.compute_seconds),
                deadline_seconds: String(fixed.deadline_seconds) });
              else if (next) setBounds((current) => ({ ...current,
                provider_requests: String(next.transport ? next.transport.provider_requests_needed : next.page_requests_recorded) }));
            }}>
              <option value="">Choose a recorded source</option>
              {sources.map((item) => <option key={item.source_id} value={item.source_id} disabled={item.available === false}>
                {item.title}{item.available === false ? " (not available on this server)" : ""}</option>)}
            </select>
          </div>
          {source ? <p className="muted">{source.evidence_class}, {source.content_label}. Pool <span className="mono">{source.market.pool_address}</span>; window {source.window.start} to {source.window.end}.</p> : null}
          {sourceRelease(source) ? <p className="muted" data-testid="history-source-release">{describeRelease(sourceRelease(source)!)}</p> : null}
          {source?.transport ? <p className="muted" data-testid="history-source-transport">{sourceRelease(source)
            ? `Served through the accepted P07 HTTP clients under operating release ${sourceRelease(source)!.release_id} (${sourceRelease(source)!.kind.replace("_", "-").toLowerCase()}), ${sourceRelease(source)!.evidence_class}. ${sourceRelease(source)!.kind === "ACTUAL" ? "Provider responses under an approved release." : "Stand-in responses on this server, not provider data."}`
            : source.transport.clients === "P07_HTTP_CLIENTS_AUTHORED_TRANSPORT"
            ? "Served through the accepted P07 HTTP clients over authored responses on this server, with no network and no credential."
            : "Replayed through the accepted Envio HyperSync transport with QuickNode receipt checks, against recorded responses only."} It needs {source.transport.provider_requests_needed} provider requests: {source.page_requests_recorded} pages, one chain read and {source.transport.corroboration_sample_size} receipts.</p> : null}
          <div className="field">
            <label htmlFor="history-hypothesis">Your hypothesis in your own words</label>
            <textarea id="history-hypothesis" className="input" value={hypothesis} onChange={(event) => { setHypothesis(event.target.value); setAdopted(false); }} />
          </div>
          <div className="field">
            <label htmlFor="history-direction">What you will check</label>
            <select id="history-direction" className="input" value={direction} onChange={(event) => { setDirection(event.target.value); setAdopted(false); }}>
              <option value="DESCRIPTIVE">Describe only</option>
              <option value="OUTPERFORM">Triggered decisions outperform</option>
              <option value="UNDERPERFORM">Triggered decisions underperform</option>
            </select>
          </div>
          {rules.map((row, index) => (
            <fieldset key={index} className="stack">
              <legend>Rule {index + 1} (your own rule; worked-example rules are refused)</legend>
              <label className="field">Price return lookback (buckets)
                <input className="input" aria-label={`Rule ${index + 1} lookback buckets`} value={row.lookback} inputMode="numeric"
                  onChange={(event) => { setRules(rules.map((item, at) => at === index ? { ...item, lookback: event.target.value.trim() } : item)); setAdopted(false); }} />
              </label>
              <label className="field">Return condition
                <select className="input" aria-label={`Rule ${index + 1} return condition`} value={row.rise}
                  onChange={(event) => { setRules(rules.map((item, at) => at === index ? { ...item, rise: event.target.value as "gt" | "lt" } : item)); setAdopted(false); }}>
                  <option value="gt">is above</option><option value="lt">is below</option>
                </select>
              </label>
              <label className="field">Return threshold (fraction, for example 0.004)
                <input className="input" aria-label={`Rule ${index + 1} return threshold`} value={row.threshold}
                  onChange={(event) => { setRules(rules.map((item, at) => at === index ? { ...item, threshold: event.target.value.trim() } : item)); setAdopted(false); }} />
              </label>
              <label className="field">Quote volume above (quote units)
                <input className="input" aria-label={`Rule ${index + 1} volume threshold`} value={row.volume}
                  onChange={(event) => { setRules(rules.map((item, at) => at === index ? { ...item, volume: event.target.value.trim() } : item)); setAdopted(false); }} />
              </label>
            </fieldset>
          ))}
          <div className="btn-row">
            {rules.length < 3 ? <button className="btn btn-secondary" type="button" onClick={() => { setRules([...rules, { lookback: "", rise: "gt", threshold: "", volume: "" }]); setAdopted(false); }}>Add another rule</button> : null}
            {rules.length > 1 ? <button className="btn btn-secondary" type="button" onClick={() => { setRules(rules.slice(0, -1)); setAdopted(false); }}>Remove the last rule</button> : null}
          </div>
          <fieldset className="stack">
            <legend>Resource bounds reserved before any collection</legend>
            {(["provider_requests", "compute_seconds", "deadline_seconds"] as const).map((name) => (
              <label className="field" key={name}>{name.replace("_", " ")}
                <input className="input" aria-label={`Bound ${name}`} value={bounds[name]} inputMode="numeric"
                  readOnly={sourceRelease(source) !== null}
                  onChange={(event) => { setBounds({ ...bounds, [name]: event.target.value.trim() }); setAdopted(false); }} />
              </label>
            ))}
          </fieldset>
          <label className="choice">
            <input type="checkbox" checked={adopted} disabled={!source || !hypothesis.trim() || !rulesComplete}
              onChange={(event) => setAdopted(event.target.checked)} />
            I reviewed and adopt every setting above before any data is read
          </label>
          {planRefusal ? <p className="status stop" role="alert" data-testid="history-window-refusal">{planRefusal}</p> : null}
          <button className="btn btn-primary" type="button" onClick={declare} disabled={!ready || pendingDeclaration !== null} aria-disabled={busy || undefined}>
            {busy ? "Saving…" : "Save history declaration"}
          </button>
        </div>
      </details>}
    </section>
  );
}
