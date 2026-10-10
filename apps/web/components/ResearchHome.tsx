"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { CLASS_LABEL, JOB_LABEL, SUPPORTED_RESTRICTIONS, formatTime } from "../lib/describe";
import { draftKey, parseDraft } from "../lib/draft";
import { listTag } from "../lib/interpretation";
import type { InputClass, Job, RequestSummary, Sample } from "../lib/types";
import { MoeExample } from "./MoeExample";

const KINDS: { id: InputClass; job: Job; label: string; hint: string }[] = [
  { id: "LOOSE_INTUITION", job: "CREATE_STRATEGY", label: "Rough hunch", hint: "You noticed something but have no rule yet." },
  { id: "CONCRETE_THESIS", job: "CREATE_STRATEGY", label: "Specific rule or thesis", hint: "You can say when to enter and exit." },
  { id: "BOUNDED_NO_THESIS", job: "INVESTIGATE_EFFECT", label: "No thesis, a bounded question", hint: "You want to look at a market without a view." },
];

const sameForm = (a: { text: string; kind: string; restrictions: string[]; useMarket: boolean }, b: typeof a) =>
  a.text === b.text && a.kind === b.kind && a.useMarket === b.useMarket
  && a.restrictions.length === b.restrictions.length && a.restrictions.every((r, i) => r === b.restrictions[i]);

export function ResearchHome({ userId, go, consumeReturn }: { userId: string | null; go: (hash: string, from?: string) => void; consumeReturn: () => string | null }) {
  const heading = useRef<HTMLHeadingElement>(null);
  const formId = useId();
  const [text, setText] = useState("");
  const [kind, setKind] = useState<InputClass>("LOOSE_INTUITION");
  const [restrictions, setRestrictions] = useState<string[]>([]);
  const [custom, setCustom] = useState("");
  const [useMarket, setUseMarket] = useState(false);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [fixtureNotice, setFixtureNotice] = useState("");
  const [fixtureKind, setFixtureKind] = useState("FIXTURE");
  const [samplesError, setSamplesError] = useState(false);
  type FormState = { text: string; kind: InputClass; restrictions: string[]; useMarket: boolean };
  const [undoExample, setUndoExample] = useState<FormState | null>(null);
  const [lastExample, setLastExample] = useState<FormState | null>(null); // what the last example filled in
  const [saved, setSaved] = useState<RequestSummary[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(""); // field validation, shown under the textarea
  const [submitError, setSubmitError] = useState(""); // a failed request, shown beside the button
  const submitMessage = useRef<HTMLParagraphElement>(null);
  const job = KINDS.find((k) => k.id === kind)!.job;

  // Focus returns to the control that opened the request. The saved list loads after mount, so wait for it,
  // and never take focus from a field the person has already moved to.
  const pendingFocus = useRef<string | null>(null);
  useEffect(() => { pendingFocus.current = consumeReturn(); if (!pendingFocus.current) heading.current?.focus(); }, [consumeReturn]);
  useEffect(() => {
    const target = pendingFocus.current;
    if (!target || (saved === null && !loadError)) return;
    pendingFocus.current = null;
    const active = document.activeElement;
    if (active && active !== document.body && active !== heading.current) return; // the person moved on
    (document.getElementById(target) ?? heading.current)?.focus();
  }, [saved, loadError]);

  // `visible` loads show their own error and busy state. A background refresh keeps the list it has.
  const [listBusy, setListBusy] = useState(false);
  const [listFailures, setListFailures] = useState(0);
  const listBusyRef = useRef(false);
  const savedHeading = useRef<HTMLHeadingElement>(null);
  const loadList = useCallback(async (visible: boolean, afterRetry = false) => {
    if (visible) { if (listBusyRef.current) return; listBusyRef.current = true; setListBusy(true); }
    try {
      const r = await api.list();
      setSaved(r.requests); setHasMore(r.has_more); setLoadError("");
      if (afterRetry) setTimeout(() => savedHeading.current?.focus(), 0); // the retry button is gone; keep focus in the section
    } catch (e) {
      if (visible) { setLoadError(e instanceof ApiError ? e.detail : "Saved requests could not be loaded."); setListFailures((n) => n + 1); }
    } finally { if (visible) { listBusyRef.current = false; setListBusy(false); } }
  }, []);
  const refreshList = useCallback(() => { void loadList(false); }, [loadList]);

  // An unsent draft survives a reload or a session that ended. It is kept in this tab for this verified person only,
  // validated before use, and removed on sign-out. `hydrated` keeps the first (empty) render from overwriting it.
  const [hydrated, setHydrated] = useState(false);
  useEffect(() => {
    let raw: string | null = null;
    try { raw = userId ? window.sessionStorage.getItem(draftKey(userId)) : null; } catch { /* storage may be blocked */ }
    const draft = parseDraft(raw);
    if (draft) { setText(draft.text); setKind(draft.kind); setRestrictions(draft.restrictions); setCustom(draft.custom); setUseMarket(draft.useMarket); }
    setHydrated(true);
  }, [userId]);
  useEffect(() => {
    if (!hydrated || !userId) return;
    try { window.sessionStorage.setItem(draftKey(userId), JSON.stringify({ text, kind, restrictions, custom, useMarket })); } catch { /* ignore */ }
  }, [hydrated, userId, text, kind, restrictions, custom, useMarket]);

  useEffect(() => {
    let cancelled = false;
    api.interpreter().then((r) => { if (!cancelled) { setSamples(r.samples); setFixtureNotice(r.interpreter.notice); setFixtureKind(r.interpreter.kind); } })
      .catch(() => { if (!cancelled) setSamplesError(true); });
    void loadList(true);
    return () => { cancelled = true; };
  }, [loadList]);

  const addRestriction = (value: string) => {
    const trimmed = value.trim();
    if (trimmed && !restrictions.includes(trimmed)) setRestrictions([...restrictions, trimmed]);
  };

  const fill = (sample: Sample) => {
    // An example replaces the form. If the person had typed something, keep it for one undo. While the form
    // still shows the previous example unchanged, the person's own words stay the thing to restore.
    const next: FormState = { text: sample.text, kind: sample.input_class, restrictions: sample.restrictions, useMarket: Boolean(sample.declared_market) };
    if (!(undoExample && lastExample && sameForm(lastExample, { text, kind, restrictions, useMarket }))) {
      setUndoExample(text.trim() || restrictions.length ? { text, kind, restrictions, useMarket } : null);
    }
    setLastExample(next);
    setText(next.text); setKind(next.kind); setRestrictions(next.restrictions); setUseMarket(next.useMarket);
  };
  const editedSinceExample = Boolean(lastExample) && !sameForm(lastExample!, { text, kind, restrictions, useMarket });
  const restoreTyped = () => {
    if (!undoExample) return;
    setText(undoExample.text); setKind(undoExample.kind); setRestrictions(undoExample.restrictions); setUseMarket(undoExample.useMarket);
    setUndoExample(null); setLastExample(null);
  };

  useEffect(() => { if (submitError) submitMessage.current?.scrollIntoView({ block: "center" }); }, [submitError]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    if (busy) return;
    if (!text.trim()) { setError("Write your request first."); return; }
    // A restriction that was typed but not yet added is part of the request. Never drop it silently.
    const pending = custom.trim();
    const sent = pending && !restrictions.includes(pending) ? [...restrictions, pending] : restrictions;
    setBusy(true); setError(""); setSubmitError("");
    if (pending) setCustom(""); // added, or already listed: either way it is no longer a loose draft
    if (sent !== restrictions) setRestrictions(sent);
    try {
      const sample = samples.find((s) => s.declared_market)?.declared_market ?? null;
      const bundle = await api.submit({
        original_request: text, restrictions: sent, requested_job: job, input_class: kind,
        ...(job === "INVESTIGATE_EFFECT" && useMarket && sample ? { declared_market: sample } : {}),
      });
      try { if (userId) window.sessionStorage.removeItem(draftKey(userId)); } catch { /* ignore */ }
      go(`#/research/${bundle.intake.record_id}`, "start-request");
    } catch (e) {
      // With no answer from the service the request may still have been saved: say so and refresh the list.
      const unsure = e instanceof ApiError && e.status === 0;
      setSubmitError(unsure ? "The request may have been saved. Check Saved requests below before you send it again."
        : e instanceof ApiError ? e.detail : "The request was not saved. Try again.");
      refreshList();
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
          <p className="muted" style={{ marginTop: 0 }}>Restrictions are saved exactly as you add them here. They are not read out of your words.</p>
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
          <p className="muted" id={`${formId}-examples`}>{fixtureKind === "FIXTURE" ? "Fixture examples." : "Examples."} {fixtureNotice || "The fixture interpreter answers only these."} Picking one fills the form; you can edit it.</p>
          {samplesError ? <p role="status" className="muted">The examples could not be loaded. You can still write your own request.</p> : null}
          {undoExample ? <button type="button" className="btn btn-secondary" onClick={restoreTyped}>Restore what I typed{editedSinceExample ? " (replaces your edits)" : ""}</button> : null}
          {samples.map((s) => (
            <button key={s.scenario_id} type="button" className="example" aria-describedby={`${formId}-examples`} onClick={() => fill(s)}>
              <span className="eyebrow">{s.label}</span>{s.text}
            </button>
          ))}
        </div>

        <div className="btn-row">
          <button id="start-request" className="btn btn-primary" type="submit" aria-disabled={busy || undefined}>{busy ? "Saving your words…" : "Prepare request"}</button>
          <span className="muted" style={{ flex: "1 1 260px" }}>Preparing is free. We keep your words and restrictions, ask only what is missing, then show the rules for review. No study runs in this build.</span>
        </div>
        {submitError ? <p role="alert" className="status err" ref={submitMessage} tabIndex={-1}>{submitError}</p> : null}
      </form>

      <section aria-labelledby="saved-title" className="stack">
        <h2 id="saved-title" ref={savedHeading} tabIndex={-1} style={{ fontSize: 24, margin: 0 }}>Saved requests</h2>
        {loadError ? (
          <div className="btn-row">
            <p role="alert" className="error-text" style={{ margin: 0 }} key={listFailures}>{loadError}</p>
            <button type="button" className="btn btn-secondary" onClick={() => void loadList(true, true)} aria-disabled={listBusy || undefined}>{listBusy ? "Trying again…" : "Try again"}</button>
          </div>
        ) : null}
        {saved === null && !loadError ? <p className="muted" role="status">Loading saved requests.</p> : null}
        {saved && saved.length === 0 ? <p className="muted">Nothing saved yet. Your requests appear here and stay after you close the page.</p> : null}
        {hasMore ? <p className="muted" role="status">Showing your 50 most recent requests. Older ones are saved but not listed here yet.</p> : null}
        <div className="cards">
          {(saved ?? []).map((r) => {
            const copy = listTag(r);
            return (
              <button type="button" className="card-open" id={`req-${r.intake_record_id}`} key={r.intake_record_id}
                onClick={() => go(`#/research/${r.intake_record_id}`, `req-${r.intake_record_id}`)}>
                <span className="title">{r.original_request.length > 140 ? `${r.original_request.slice(0, 140)}…` : r.original_request}</span>
                <span className="tags">
                  <span className={`tag tag-${copy.tone}`} style={{ whiteSpace: "normal" }}>{copy.title}</span>
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
