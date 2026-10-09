"use client";

import { useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import type { InvestigationConfiguration, InvestigationEnvelope, InvestigationProposal, InvestigationSaveResult } from "../lib/types";

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
  const hasSavedDeclarations = useRef(false);
  const [proposalError, setProposalError] = useState("");
  const [refreshingProposal, setRefreshingProposal] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState("");
  const [savedReadFailed, setSavedReadFailed] = useState(false);
  const [reopenId, setReopenId] = useState("");
  const [configuration, setConfiguration] = useState<InvestigationConfiguration | null>(null);
  const [edgeSpec, setEdgeSpec] = useState<InvestigationProposal["edge_spec"] | null>(null);

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
      setProposal(next);
      if (replaceDraft || !configuration || !edgeSpec) {
        setConfiguration(next.configuration); setEdgeSpec(next.edge_spec); setAdopted(false);
      } else {
        setAdopted(false);
        setRefreshNotice("The request interpretation changed. Your unsaved edits remain in place. Review them against this current declaration before saving.");
      }
      return true;
    } catch (cause) { setProposalError(errorDetail(cause)); return false; }
    finally { setRefreshingProposal(false); }
  };

  useEffect(() => {
    if (loading || !proposal || proposal.interpretation_revision_id === interpretationRevisionId) return;
    void refreshProposal(false);
    // The current proposal is the revision guard; edits remain visible during refresh.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [interpretationRevisionId, loading]);

  useEffect(() => { if (error) errorRef.current?.focus(); }, [error]);

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
      setSelected(result); setProposal(null); setAdopted(false);
      try { window.sessionStorage.removeItem(`edge-os:investigation:${intakeId}`); } catch { /* ignore */ }
      requestAnimationFrame(() => savedHeading.current?.focus());
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

  return (
    <section className="panel stack investigation-review" aria-labelledby="investigation-title" data-testid="investigation-review">
      <div>
        <h2 id="investigation-title">Investigation plan</h2>
        <p className="muted">Review the proposed scope and adoption sources. Saving records a pre-outcome declaration. It does not read data, run a study or start a trade.</p>
      </div>
      {error ? <p className="status err" role="alert" tabIndex={-1} ref={errorRef}>{error}</p> : null}
      {refreshingProposal ? <p role="status" aria-busy="true">Refreshing the current review. Your edits are unchanged.</p> : null}
      {proposalError ? <div className="status err" role="alert"><p>{proposalError}</p><button className="btn btn-secondary" type="button" onClick={() => void refreshProposal(false)} disabled={busy || refreshingProposal}>Retry proposal</button></div> : null}
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
          <p>Saved before outcome review. No study started. This profile uses an unqualified synthetic fixture.</p>
          <dl className="kv">
            <dt>Declaration ID</dt><dd className="mono">{selected.declaration.record_id}</dd>
            <dt>Budget version</dt><dd>{selected.declaration.content.configuration.budget_version}</dd>
            <dt>Outcome labels read</dt><dd>{selected.declaration.content.outcome_labels_read ? "Yes" : "No"}</dd>
            <dt>Provider queries</dt><dd>{selected.access_history[0]?.provider_queries ?? 0}</dd>
            <dt>Saved access event</dt><dd>{selected.access_history[0]?.event ?? "Unavailable"}</dd>
          </dl>
          <details>
            <summary>Review the complete saved configuration</summary>
            <pre className="records-json">{JSON.stringify(selected.declaration.content, null, 2)}</pre>
            <p className="muted">Sources, field origins, optional tools, trial identities and evaluation identities are saved with this declaration.</p>
          </details>
        </div>
      ) : null}

      {proposal && configuration && edgeSpec ? (
        <div className="stack">
          <p role="note" className="status stop">{proposal.notice} The proposal keeps your original request unchanged. This synthetic pool is not qualified for production research.</p>
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
              <dt>Pool</dt><dd>{configuration.pool_binding.profile_id} · unqualified synthetic fixture</dd>
              <dt>Limitations</dt><dd>{configuration.pool_binding.limitations.join(" ")}</dd>
              <dt>Data source</dt><dd>{configuration.sources.join(", ")}</dd>
              <dt>Permitted access</dt><dd>Fixture only. No provider queries.</dd>
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
                {edgeSpec.claim.status === "DESCRIPTIVE_ONLY" ? <option value="DESCRIPTIVE">Descriptive, no prediction</option> : null}
                <option value="OUTPERFORM">Primary group outperforms comparison</option>
                <option value="UNDERPERFORM">Primary group underperforms comparison</option>
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
    </section>
  );
}
