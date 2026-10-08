"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { CLASS_LABEL, FIELD_LABEL, JOB_LABEL, ORIGIN_LABEL, OUTCOME_COPY, formatTime, shortId, summarizeValue } from "../lib/describe";
import type { Bundle, Finding, Strategy } from "../lib/types";
import type { ConversationContext } from "./Conversation";
import { QuestionForm } from "./QuestionForm";
import { RulesReview } from "./RulesReview";

interface Props {
  id: string;
  go(hash: string, from?: string): void;
  setContext(ctx: ConversationContext | null): void;
  openConversation(event: React.MouseEvent<HTMLButtonElement>): void;
}

function pendingKeys(draftId: string): { operation_id: string; idempotency_key: string } {
  const storageKey = `edge-os:publication:${draftId}`;
  try {
    const stored = window.sessionStorage.getItem(storageKey);
    if (stored) return JSON.parse(stored);
  } catch { /* storage may be blocked; a new key is safe because the root slot is unique */ }
  const keys = { operation_id: crypto.randomUUID(), idempotency_key: `ui-${crypto.randomUUID()}` };
  try { window.sessionStorage.setItem(storageKey, JSON.stringify(keys)); } catch { /* ignore */ }
  return keys;
}

export function RequestPage({ id, go, setContext, openConversation }: Props) {
  const heading = useRef<HTMLHeadingElement>(null);
  const stateHeading = useRef<HTMLHeadingElement>(null);
  const errorBanner = useRef<HTMLParagraphElement>(null);
  const focusSurface = useRef<HTMLElement | null | undefined>(undefined); // undefined: nothing pending
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [verified, setVerified] = useState<null | boolean>(null);
  const [opened, setOpened] = useState<"loading" | "loaded">("loading");

  useEffect(() => {
    let cancelled = false;
    api.get(id).then((b) => { if (!cancelled) { setBundle(b); setOpened("loaded"); } })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof ApiError && e.status === 404 ? "This request was not found." : "The request could not be loaded."); });
    return () => { cancelled = true; };
  }, [id]);

  useEffect(() => { if (bundle) heading.current?.focus(); }, [bundle === null]); // eslint-disable-line react-hooks/exhaustive-deps

  const reload = useCallback(async (): Promise<boolean> => {
    try { setBundle(await api.get(id)); return true; }
    catch { setError("The saved request could not be reloaded. Reload the page to see its current state."); return false; }
  }, [id]);

  const answer = useCallback(async (questionId: string, choiceId: string, origin?: HTMLElement) => {
    if (!bundle?.head.interpretation_revision_id) return;
    // Remember which surface took the answer. After the state change, focus stays there.
    const surface = origin?.closest<HTMLElement>("[data-focus-surface]") ?? null;
    setBusy(true); setError(""); setNotice("");
    try {
      setBundle(await api.answer(id, { previous_revision_id: bundle.head.interpretation_revision_id, question_id: questionId, choice_id: choiceId }));
      focusSurface.current = surface; // the answered form is gone; the layout effect lands focus on the new state
    } catch (e) {
      if (e instanceof ApiError && e.code === "parent_revision_conflict") {
        setNotice("This request changed elsewhere. It was reloaded. Check the question and answer again.");
        await reload();
      } else setError(e instanceof ApiError ? e.detail : "Your answer was not saved.");
    } finally { setBusy(false); }
  }, [bundle, id, reload]);

  // A failure must be visible where the user acted, not above the fold. Focus stays on the pressed button.
  useEffect(() => { if (error) errorBanner.current?.scrollIntoView({ block: "center", behavior: "auto" }); }, [error]);

  // Runs right after the new state commits, before paint: focus stays inside the surface that took the answer.
  useLayoutEffect(() => {
    if (focusSurface.current === undefined) return;
    const surface = focusSurface.current;
    focusSurface.current = undefined;
    const inside = surface?.querySelector<HTMLElement>("[data-focus-target]") ?? null; // main-page forms carry no surface: they land on the state heading
    (inside ?? stateHeading.current)?.focus();
  }, [bundle]);

  useEffect(() => {
    setContext(bundle ? { bundle, busy, answer } : null);
    return () => setContext(null);
  }, [bundle, busy, answer, setContext]);

  const revision = bundle?.revisions[0];
  useEffect(() => {
    if (!revision) { setVerified(null); return; }
    let cancelled = false;
    api.revision(revision.strategy_id, revision.revision_id)
      .then((r) => { if (!cancelled) setVerified(r.stored_hash_matches_content && r.content_sha256 === revision.content_sha256); })
      .catch(() => { if (!cancelled) setVerified(false); });
    return () => { cancelled = true; };
  }, [revision?.revision_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const publish = async () => {
    if (busy || !bundle?.head.draft_id) return;
    const draft = bundle.drafts.find((d) => d.record_id === bundle.head.draft_id);
    if (!draft) return;
    const keys = pendingKeys(draft.record_id);
    setBusy(true); setError(""); setNotice("");
    focusSurface.current = null; // the Save button disappears; the layout effect lands focus on the new state
    try {
      await api.publish(draft.content.strategy_id, { ...keys, expected_parent_revision_id: null, draft_id: draft.record_id, strategy: draft.content.source_syntax });
      await reload();
    } catch (e) {
      focusSurface.current = undefined;
      if (e instanceof ApiError && e.code === "parent_revision_conflict") {
        focusSurface.current = null;
        if (await reload()) setNotice("A revision of this rule was already saved. The saved record is shown.");
      } else if (e instanceof ApiError && e.status === 0) {
        setError("We could not confirm the save. Press save again. It reuses the same key, so it cannot create a second revision.");
      } else setError(e instanceof ApiError ? e.detail : "The revision was not saved.");
    } finally { setBusy(false); }
  };

  if (!bundle) {
    return (
      <div className="stack">
        <h1 ref={heading} tabIndex={-1}>Request</h1>
        {error ? (
          <section className="panel" role="alert"><h2>{error}</h2>
            <button className="btn btn-secondary" type="button" onClick={() => go("#/research")}>Back to Research</button></section>
        ) : <p role="status" aria-busy="true" className="muted">Opening saved request.</p>}
      </div>
    );
  }

  const intake = bundle.intake.content;
  const head = bundle.head;
  const outcome = revision ? "PUBLISHED" : head.outcome ?? "INVALID_INPUT";
  const copy = OUTCOME_COPY[outcome];
  const headOutcome = bundle.outcomes.find((o) => o.interpretation_revision_id === head.interpretation_revision_id)?.record.content
    ?? bundle.outcomes[bundle.outcomes.length - 1]?.record.content;
  const draft = bundle.drafts.find((d) => d.record_id === head.draft_id);
  const interp = bundle.interpretations.find((i) => i.content.interpretation_revision_id === head.interpretation_revision_id);
  const findings: Finding[] = headOutcome?.findings ?? [];
  const stopped = ["UNSUPPORTED", "UNRESOLVED", "INVALID_INPUT"].includes(outcome);

  return (
    <div className="stack">
      <div>
        <h1 ref={heading} tabIndex={-1}>Your request</h1>
        <p className="muted" style={{ marginTop: 0 }}>Saved request {shortId(bundle.intake.record_id)}</p>
        <div className="btn-row">
          <button className="btn btn-secondary" type="button" onClick={() => go("#/research", `req-${id}`)}>All requests</button>
          <button className="btn btn-secondary convo-button" type="button" onClick={openConversation}>Conversation</button>
        </div>
      </div>

      <section className="panel" aria-labelledby="words-title">
        <h2 id="words-title">Your words</h2>
        <p className="words" data-testid="original-request">{intake.original_request}</p>
        <dl className="kv">
          <dt>Kind</dt><dd>{CLASS_LABEL[intake.input_class]}</dd>
          <dt>Job kept</dt><dd>{JOB_LABEL[intake.requested_job]}</dd>
          <dt>Restrictions</dt>
          <dd>{intake.restrictions.length ? (<ol className="chips" aria-label="Saved restrictions">{intake.restrictions.map((r, i) => (<li className="chip" style={{ paddingRight: 12 }} key={r}>{i + 1}. {r}</li>))}</ol>) : "None"}</dd>
          <dt>Saved</dt><dd>{formatTime(bundle.intake.created_at)}</dd>
        </dl>
      </section>

      {notice ? <p role="status" className="status ok">{notice}</p> : null}
      {error ? <p role="alert" className="status err" ref={errorBanner} tabIndex={-1}>{error}</p> : null}

      <section className={`status ${outcome === "PUBLISHED" || outcome === "COMPILED" ? "ok" : stopped ? "stop" : ""}`} aria-labelledby="state-title" data-testid="outcome" data-outcome={outcome}>
        <p className="visually-hidden" role="status">{copy.title}</p>
        <h2 id="state-title" ref={stateHeading} tabIndex={-1}><span className={`tag tag-${copy.tone}`} style={{ marginRight: 8 }}>{copy.title}</span></h2>
        {outcome === "NEEDS_CLARIFICATION" && <p>We need {head.questions.length === 1 ? "one answer" : "a few answers"} before the rules can be reviewed. Nothing is guessed. Answer here or in the conversation.</p>}
        {outcome === "COMPILED" && <p>These rules came from your words and the settings you adopted. Check them, then save. Saving makes an immutable revision. It does not show the rules work.</p>}
        {outcome === "PUBLISHED" && <p>This revision is saved. Reopening it later shows the same record from storage.</p>}
        {stopped && (
          <>
            {findings.map((f) => (<p key={f.path + f.code}>{f.detail}</p>))}
            <p>Your words, restrictions and the reason are saved. {outcome === "UNRESOLVED" ? "No study ran, and no signal or strategy was created." : "No strategy was created."}</p>
          </>
        )}
      </section>

      {outcome === "NEEDS_CLARIFICATION" && (
        <section className="panel" aria-labelledby="q-title">
          <h2 id="q-title">What we need from you</h2>
          <QuestionForm questions={head.questions} busy={busy} idPrefix="main" onAnswer={answer} onCancel={() => go("#/research", `req-${id}`)} />
        </section>
      )}

      {(outcome === "COMPILED" || outcome === "PUBLISHED") && draft && (
        <section className="panel" aria-labelledby="rules-title">
          <h2 id="rules-title">Rules to review</h2>
          <RulesReview strategy={draft.content.source_syntax as Strategy} />
          <p className="muted">Compiling gives reviewable rules. It is not evidence they work, and it grants no permission to trade.</p>
          {outcome === "COMPILED" && (
            <div className="btn-row">
              <button className="btn btn-primary" type="button" onClick={publish} aria-disabled={busy || undefined}>{busy ? "Saving" : "Save this revision"}</button>
              <button className="btn btn-secondary" type="button" onClick={() => go("#/research", `req-${id}`)}>Not now</button>
            </div>
          )}
        </section>
      )}

      {revision && (
        <section className="panel" aria-labelledby="rev-title" data-testid="revision">
          <h2 id="rev-title">Saved revision</h2>
          <dl className="kv">
            <dt>Revision ID</dt><dd className="mono" data-testid="revision-id">{revision.revision_id}</dd>
            <dt>Strategy ID</dt><dd className="mono">{revision.strategy_id}</dd>
            <dt>Content hash</dt><dd className="mono">{revision.content_sha256}</dd>
            <dt>Meaning manifest hash</dt><dd className="mono">{revision.manifest_sha256}</dd>
            <dt>Saved</dt><dd>{formatTime(revision.created_at)}</dd>
            <dt>Stored copy</dt><dd>{verified === null ? "Checking" : verified ? "Read back from the database. Its hash matches." : "Could not be confirmed."}</dd>
          </dl>
        </section>
      )}

      <details>
        <summary>Where each setting came from</summary>
        {interp ? (
          <table className="records">
            <thead><tr><th scope="col">Setting</th><th scope="col">Meaning</th><th scope="col">Source</th><th scope="col">Status</th></tr></thead>
            <tbody>
              {interp.content.field_evidence.map((f) => (
                <tr key={f.field_name}>
                  <th scope="row">{FIELD_LABEL[f.field_name] ?? f.field_name}</th>
                  <td>{f.state === "KNOWN" ? summarizeValue(f.field_name, f.value) : "Missing. We will ask."}</td>
                  <td>{ORIGIN_LABEL[f.origin]}</td>
                  <td>{f.state !== "KNOWN" ? "Needs your answer" : f.adoption === "PENDING" ? "Awaiting your adoption" : f.adoption === "ADOPTED" ? "Adopted" : "Stated"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <p className="muted">No interpretation was made for this request.</p>}
      </details>

      <details>
        <summary>Record details</summary>
        <dl className="kv">
          <dt>Request</dt><dd className="mono">{bundle.intake.record_id}</dd>
          <dt>Current revision</dt><dd className="mono">{head.interpretation_revision_id ?? "none"}</dd>
          <dt>Revisions in history</dt><dd>{bundle.interpretations.length}</dd>
          <dt>Interpreter</dt><dd>{bundle.interpreter.kind} · {bundle.interpreter.id}</dd>
          <dt>Opened</dt><dd>{opened === "loaded" ? "Read from the database just now" : ""}</dd>
        </dl>
      </details>
    </div>
  );
}
