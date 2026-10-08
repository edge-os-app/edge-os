"use client";

import { useEffect, useId, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { CLASS_LABEL, JOB_LABEL, OUTCOME_COPY, SUPPORTED_RESTRICTIONS, formatTime } from "../lib/describe";
import type { InputClass, Job, RequestSummary, Sample } from "../lib/types";
import { MoeExample } from "./MoeExample";

const KINDS: { id: InputClass; job: Job; label: string; hint: string }[] = [
  { id: "LOOSE_INTUITION", job: "CREATE_STRATEGY", label: "Rough hunch", hint: "You noticed something but have no rule yet." },
  { id: "CONCRETE_THESIS", job: "CREATE_STRATEGY", label: "Specific rule or thesis", hint: "You can say when to enter and exit." },
  { id: "BOUNDED_NO_THESIS", job: "INVESTIGATE_EFFECT", label: "No thesis, a bounded question", hint: "You want to look at a market without a view." },
];

export function ResearchHome({ go, consumeReturn }: { go: (hash: string, from?: string) => void; consumeReturn: () => string | null }) {
  const heading = useRef<HTMLHeadingElement>(null);
  const formId = useId();
  const [text, setText] = useState("");
  const [kind, setKind] = useState<InputClass>("LOOSE_INTUITION");
  const [restrictions, setRestrictions] = useState<string[]>([]);
  const [custom, setCustom] = useState("");
  const [useMarket, setUseMarket] = useState(false);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [fixtureNotice, setFixtureNotice] = useState("");
  const [saved, setSaved] = useState<RequestSummary[] | null>(null);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const job = KINDS.find((k) => k.id === kind)!.job;

  // Focus returns to the control that opened the request. The saved list loads after mount, so wait for it.
  const pendingFocus = useRef<string | null>(null);
  useEffect(() => { pendingFocus.current = consumeReturn(); if (!pendingFocus.current) heading.current?.focus(); }, [consumeReturn]);
  useEffect(() => {
    const target = pendingFocus.current;
    if (!target || (saved === null && !loadError)) return;
    pendingFocus.current = null;
    (document.getElementById(target) ?? heading.current)?.focus();
  }, [saved, loadError]);

  useEffect(() => {
    let cancelled = false;
    api.interpreter().then((r) => { if (!cancelled) { setSamples(r.samples); setFixtureNotice(r.interpreter.notice); } }).catch(() => {});
    api.list().then((r) => { if (!cancelled) setSaved(r); }).catch((e: unknown) => {
      if (!cancelled) setLoadError(e instanceof ApiError ? e.detail : "Saved requests could not be loaded.");
    });
    return () => { cancelled = true; };
  }, []);

  const addRestriction = (value: string) => {
    const trimmed = value.trim();
    if (trimmed && !restrictions.includes(trimmed)) setRestrictions([...restrictions, trimmed]);
  };

  const fill = (sample: Sample) => {
    setText(sample.text); setKind(sample.input_class); setRestrictions(sample.restrictions);
    setUseMarket(Boolean(sample.declared_market));
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!text.trim()) { setError("Write your request first."); return; }
    setBusy(true); setError("");
    try {
      const sample = samples.find((s) => s.declared_market)?.declared_market ?? null;
      const bundle = await api.submit({
        original_request: text, restrictions, requested_job: job, input_class: kind,
        ...(job === "INVESTIGATE_EFFECT" && useMarket && sample ? { declared_market: sample } : {}),
      });
      go(`#/research/${bundle.intake.record_id}`, "start-request");
    } catch (e) {
      setError(e instanceof ApiError ? e.detail : "The request was not saved. Try again.");
      setBusy(false);
    }
  };

  return (
    <div className="stack">
      <div>
        <h1 ref={heading} tabIndex={-1}>Research</h1>
        <p className="lede">Look into a trading idea or a market question on Monad. A study can end without a strategy, and that is still a useful answer.</p>
      </div>

      <form className="panel" onSubmit={submit} aria-labelledby={`${formId}-title`} noValidate>
        <h2 id={`${formId}-title`}>What do you want to find out?</h2>
        <div className="field">
          <label htmlFor={`${formId}-text`}>Your words</label>
          <textarea id={`${formId}-text`} className="input" value={text} onChange={(e) => setText(e.target.value)}
            placeholder="Write it in your own words. A clear rule, a rough hunch or an open question all work."
            aria-describedby={error ? `${formId}-error` : undefined} aria-invalid={error ? true : undefined} />
          {error ? <p id={`${formId}-error`} role="alert" className="error-text">{error}</p> : null}
        </div>

        <fieldset>
          <legend className="legend">What kind of request is this?</legend>
          <div className="choice-list">
            {KINDS.map((k) => (
              <label className="choice" key={k.id}>
                <input type="radio" name={`${formId}-kind`} checked={kind === k.id} onChange={() => setKind(k.id)} />
                <span><strong>{k.label}</strong><br /><span className="muted">{k.hint}</span></span>
              </label>
            ))}
          </div>
          <p className="muted" style={{ marginTop: 8 }}>Job we will keep: <strong>{JOB_LABEL[job]}</strong>. An investigation stays an investigation.</p>
        </fieldset>

        {job === "INVESTIGATE_EFFECT" ? (
          <label className="choice">
            <input type="checkbox" checked={useMarket} onChange={(e) => setUseMarket(e.target.checked)} />
            <span>Use the synthetic fixture market. <span className="muted">Leave this off and we will ask which market.</span></span>
          </label>
        ) : null}

        <fieldset>
          <legend className="legend">Restrictions, in the order you add them</legend>
          {restrictions.length ? (
            <ol className="chips" aria-label="Your restrictions">
              {restrictions.map((r, i) => (
                <li className="chip" key={r}>
                  <span>{i + 1}. {r}</span>
                  <button type="button" aria-label={`Remove restriction: ${r}`} onClick={() => setRestrictions(restrictions.filter((x) => x !== r))}>×</button>
                </li>
              ))}
            </ol>
          ) : <p className="muted">None added.</p>}
          <div className="btn-row" style={{ marginTop: 8 }}>
            {SUPPORTED_RESTRICTIONS.filter((r) => !restrictions.includes(r)).map((r) => (
              <button key={r} type="button" className="btn btn-secondary" onClick={() => addRestriction(r)}>Add “{r}”</button>
            ))}
          </div>
          <div className="field" style={{ marginTop: 12 }}>
            <label htmlFor={`${formId}-custom`}>Another restriction in your words</label>
            <div className="btn-row">
              <input id={`${formId}-custom`} className="input" style={{ flex: "1 1 220px", width: "auto" }} value={custom}
                onChange={(e) => setCustom(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addRestriction(custom); setCustom(""); } }} />
              <button type="button" className="btn btn-secondary" onClick={() => { addRestriction(custom); setCustom(""); }}>Add restriction</button>
            </div>
          </div>
        </fieldset>

        <div className="stack" style={{ gap: 8 }}>
          <p className="muted" id={`${formId}-examples`}>Fixture examples. {fixtureNotice || "The fixture interpreter answers only these."} Picking one fills the form; you can edit it.</p>
          {samples.map((s) => (
            <button key={s.scenario_id} type="button" className="example" aria-describedby={`${formId}-examples`} onClick={() => fill(s)}>
              <span className="eyebrow">{s.label}</span>{s.text}
            </button>
          ))}
        </div>

        <div className="btn-row">
          <button id="start-request" className="btn btn-primary" type="submit" disabled={busy}>{busy ? "Saving your words" : "Prepare request"}</button>
          <span className="muted" style={{ flex: "1 1 260px" }}>Preparing is free. We keep your words and restrictions, ask only what is missing, then show the rules for review. No study runs in this build.</span>
        </div>
      </form>

      <section aria-labelledby="saved-title" className="stack">
        <h2 id="saved-title" style={{ fontSize: 24, margin: 0 }}>Saved requests</h2>
        {loadError ? <p role="alert" className="error-text">{loadError}</p> : null}
        {saved === null && !loadError ? <p className="muted" role="status">Loading saved requests.</p> : null}
        {saved && saved.length === 0 ? <p className="muted">Nothing saved yet. Your requests appear here and stay after you close the page.</p> : null}
        <div className="cards">
          {(saved ?? []).map((r) => {
            const copy = r.published ? OUTCOME_COPY.PUBLISHED : OUTCOME_COPY[r.outcome ?? "INVALID_INPUT"];
            return (
              <button type="button" className="card-open" id={`req-${r.intake_record_id}`} key={r.intake_record_id}
                onClick={() => go(`#/research/${r.intake_record_id}`, `req-${r.intake_record_id}`)}>
                <span className="title">{r.original_request.length > 140 ? `${r.original_request.slice(0, 140)}…` : r.original_request}</span>
                <span className="tags">
                  <span className={`tag tag-${copy.tone}`}>{copy.title}</span>
                  <span className="tag tag-neutral">{CLASS_LABEL[r.input_class]}</span>
                  <span className="tag tag-neutral">{JOB_LABEL[r.requested_job]}</span>
                </span>
                <span className="muted" style={{ fontSize: 13 }}>Saved {formatTime(r.created_at)}</span>
              </button>
            );
          })}
        </div>
      </section>

      <MoeExample />
    </div>
  );
}
