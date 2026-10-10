"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { CLASS_LABEL, FIELD_LABEL, JOB_LABEL, ORIGIN_LABEL, OUTCOME_COPY, formatTime, shortId, summarizeValue } from "../lib/describe";
import { FAILURE_COPY, RETRY_BLOCKED, sourceQuote, systemFailure } from "../lib/interpretation";
import type { Bundle, Finding, Strategy } from "../lib/types";
import type { ConversationContext } from "./Conversation";
import { InterpretationAttempts } from "./InterpretationAttempts";
import { AnswerMessage, QuestionForm } from "./QuestionForm";
import { RulesReview } from "./RulesReview";
import { InvestigationReview } from "./InvestigationReview";
import { SpotReplayPanel } from "./SpotReplayPanel";

interface Props {
  id: string;
  sourceRecordId?: string;
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

export function RequestPage({ id, sourceRecordId, go, setContext, openConversation }: Props) {
  const heading = useRef<HTMLHeadingElement>(null);
  const stateHeading = useRef<HTMLHeadingElement>(null);
  const errorBanner = useRef<HTMLParagraphElement>(null);
  const focusSurface = useRef<HTMLElement | null | undefined>(undefined); // undefined: nothing pending
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [work, setWork] = useState(""); // what the interpreter is doing now, announced to assistive technology
  const [answerMessage, setAnswerMessage] = useState<{ kind: "error" | "notice"; text: string; surface: string } | undefined>(undefined);
  const [verified, setVerified] = useState<null | boolean>(null);
  const [opened, setOpened] = useState<"loading" | "loaded">("loading");

  const [attempt, setAttempt] = useState(0);
  const [retrying, setRetrying] = useState(false);
  useEffect(() => {
    let cancelled = false;
    api.get(id).then((b) => { if (!cancelled) { setBundle(b); setOpened("loaded"); setError(""); } })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof ApiError && e.status === 404 ? "This request was not found." : "The request could not be loaded."); })
      .finally(() => { if (!cancelled) setRetrying(false); });
    return () => { cancelled = true; };
  }, [id, attempt]);

  useEffect(() => { if (bundle) heading.current?.focus(); }, [bundle === null]); // eslint-disable-line react-hooks/exhaustive-deps

  const reload = useCallback(async (quiet = false): Promise<boolean> => {
    try { setBundle(await api.get(id)); return true; }
    catch { if (!quiet) setError("The saved request could not be reloaded. Reload the page to see its current state."); return false; }
  }, [id]);

  const respond = useCallback(async (questionId: string, body: { choice_id: string } | { answer_text: string }, origin?: HTMLElement) => {
    if (!bundle?.head.interpretation_revision_id) return;
    // Remember which surface took the answer. After the state change, focus stays there.
    const surface = origin?.closest<HTMLElement>("[data-focus-surface]") ?? null;
    const surfaceName = surface?.dataset.focusSurface ?? "main";
    setBusy(true); setAnswerMessage(undefined);
    setWork("answer_text" in body ? "The interpreter is reading your words. This can take a few seconds." : "Saving your answer.");
    try {
      setBundle(await api.answer(id, { previous_revision_id: bundle.head.interpretation_revision_id, question_id: questionId, ...body }));
      focusSurface.current = surface; // the answered form is gone; the layout effect lands focus on the new state
    } catch (e) {
      if (e instanceof ApiError && e.code === "parent_revision_conflict") {
        focusSurface.current = surface; // after the reload commits, focus lands in this surface
        if (await reload(true)) setAnswerMessage({ kind: "notice", surface: surfaceName, text: "This request changed elsewhere. It was reloaded. Check the current state before you answer again." });
        else {
          focusSurface.current = undefined;
          setAnswerMessage({ kind: "error", surface: surfaceName, text: "This request changed elsewhere and the saved copy could not be reloaded. Reload the page before you answer again." });
        }
      } else if (e instanceof ApiError && e.status === 0) {
        await reload(true); // the service may have saved the answer or an attempt: show what is saved
        setAnswerMessage({ kind: "error", surface: surfaceName, text: "We could not confirm what happened. The saved request was reloaded. Check its attempts before you answer again." });
      } else setAnswerMessage({ kind: "error", surface: surfaceName, text: e instanceof ApiError ? e.detail : "Your answer was not saved." });
    } finally { setBusy(false); setWork(""); }
  }, [bundle, id, reload]);
  const answer = useCallback((questionId: string, choiceId: string, origin?: HTMLElement) => respond(questionId, { choice_id: choiceId }, origin), [respond]);
  const reply = useCallback((questionId: string, text: string, origin?: HTMLElement) => respond(questionId, { answer_text: text }, origin), [respond]);

  // Explicit retry of the interpreter. It starts a separate attempt and never replays an unknown one.
  const retryInterpretation = async () => {
    if (busy || !bundle || !bundle.head.retry.allowed) return;
    setBusy(true); setError(""); setNotice(""); setAnswerMessage(undefined);
    setWork("Trying the interpreter again. This can take a few seconds.");
    focusSurface.current = null; // the retry button may disappear; focus lands on the new state
    try {
      setBundle(await api.retryInterpretation(id, bundle.head.retry.retry_of));
    } catch (e) {
      focusSurface.current = undefined;
      await reload(true);
      setError(e instanceof ApiError && e.status !== 0 ? `${e.detail} The saved request was reloaded.`
        : "We could not confirm what happened. The saved request was reloaded. Check its attempts before you try again.");
    } finally { setBusy(false); setWork(""); }
  };

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
    setContext(bundle ? { bundle, busy, answer, reply, message: answerMessage } : null);
    return () => setContext(null);
  }, [bundle, busy, answer, reply, answerMessage, setContext]);

  const revision = bundle?.revisions[0];
  useEffect(() => {
    if (!revision) { setVerified(null); return; }
    let cancelled = false;
    api.revision(revision.strategy_id, revision.revision_id)
      .then((r) => { if (!cancelled) setVerified(r.stored_hash_matches_content && r.stored_manifest_hash_matches_content && r.content_sha256 === revision.content_sha256); })
      .catch(() => { if (!cancelled) setVerified(false); });
    return () => { cancelled = true; };
  }, [revision?.revision_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const publish = async () => {
    if (busy || !bundle?.head.draft_id) return;
    const draft = bundle.drafts.find((d) => d.record_id === bundle.head.draft_id);
    if (!draft) return;
    const keys = pendingKeys(draft.record_id);
    setBusy(true); setError(""); setNotice("");
    setAnswerMessage(undefined); // an earlier conflict notice must not outlive the next action
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
          <section className="panel"><h2 role="alert" key={attempt}>{error}</h2>
            <div className="btn-row">
              {error !== "This request was not found." ? <button className="btn btn-primary" type="button" onClick={() => { if (!retrying) { setRetrying(true); setAttempt((n) => n + 1); } }} aria-disabled={retrying || undefined}>{retrying ? "Trying again…" : "Try again"}</button> : null}
              <button className="btn btn-secondary" type="button" onClick={() => go("#/research")}>Back to Research</button>
            </div></section>
        ) : <p role="status" aria-busy="true" className="muted">Opening saved request.</p>}
      </div>
    );
  }

  const intake = bundle.intake.content;
  const sourceIsInBundle = sourceRecordId != null && [
    bundle.intake.record_id,
    ...bundle.interpretations.map((item) => item.record_id),
    ...bundle.outcomes.map((item) => item.record.record_id),
    ...bundle.clarifications.map((item) => item.record_id),
    ...bundle.drafts.map((item) => item.record_id),
    ...bundle.publications.map((item) => item.record_id),
  ].includes(sourceRecordId);
  const head = bundle.head;
  const outcome = revision ? "PUBLISHED" : head.outcome ?? "INVALID_INPUT";
  const copy = OUTCOME_COPY[outcome];
  const headOutcome = bundle.outcomes.find((o) => o.interpretation_revision_id === head.interpretation_revision_id)?.record.content
    ?? bundle.outcomes[bundle.outcomes.length - 1]?.record.content;
  const draft = bundle.drafts.find((d) => d.record_id === head.draft_id);
  const interp = bundle.interpretations.find((i) => i.content.interpretation_revision_id === head.interpretation_revision_id);
  const findings: Finding[] = headOutcome?.findings ?? [];
  const stopped = ["UNSUPPORTED", "UNRESOLVED", "INVALID_INPUT"].includes(outcome);
  const failure = outcome === "INVALID_INPUT" ? systemFailure(findings) : null; // the interpreter failed; the idea was not judged
  const usesWords = bundle.interpreter.kind !== "FIXTURE";
  const lastAttempt = bundle.attempts[bundle.attempts.length - 1];

  return (
    <div className="stack">
      <div>
        <h1 ref={heading} tabIndex={-1}>Your request</h1>
        <p className="muted" style={{ marginTop: 0 }}>Saved request {shortId(bundle.intake.record_id)}</p>
        {sourceRecordId && (sourceIsInBundle
          ? <p role="status">Opened source record <code>{sourceRecordId}</code>.</p>
          : <p role="alert">The saved request opened, but source record <code>{sourceRecordId}</code> is not in this detail. Context is unchanged.</p>)}
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
        <p className="visually-hidden" role="status">{failure ? FAILURE_COPY[failure].title : copy.title}</p>
        <h2 id="state-title" ref={stateHeading} tabIndex={-1}><span className={`tag tag-${copy.tone}`} style={{ marginRight: 8 }}>{failure ? FAILURE_COPY[failure].title : copy.title}</span></h2>
        {outcome === "NEEDS_CLARIFICATION" && <p>We need {head.questions.length === 1 ? "one answer" : "a few answers"} before the rules can be reviewed. Nothing is guessed. Answer here or in the conversation.</p>}
        {outcome === "COMPILED" && <p>These rules came from your words and the settings you adopted. Check them, then save. Saving makes an immutable revision. It does not show the rules work.</p>}
        {outcome === "PUBLISHED" && <p>This revision is saved. Reopening it later shows the same record from storage.</p>}
        {failure ? (
          <>
            <p>{FAILURE_COPY[failure].lead}</p>
            <p data-testid="failure-detail">{findings[0]?.detail}</p>
            <p>Your words and restrictions are saved. No strategy was created.</p>
            {head.retry.allowed ? (
              <div className="btn-row">
                <button className="btn btn-primary" type="button" onClick={retryInterpretation} aria-disabled={busy || undefined}>{busy ? "Trying again…" : "Try the interpreter again"}</button>
                <span className="muted">A retry is a separate attempt. The earlier attempt stays in the list below.</span>
              </div>
            ) : <p className="muted" data-testid="retry-blocked">{RETRY_BLOCKED[head.retry.reason ?? ""] ?? "A retry is not available."}</p>}
          </>
        ) : null}
        {stopped && !failure && (
          <>
            {findings.map((f) => {
              const field = f.path.match(/^\/field_evidence\/([^/]+)/)?.[1];
              return <p key={f.path + f.code}>{field ? <><strong>{FIELD_LABEL[field] ?? field.replaceAll("_", " ")}:</strong> </> : null}{f.detail}</p>;
            })}
            <p>Your words, restrictions and the reason are saved. {outcome === "UNRESOLVED" ? "No study ran, and no signal or strategy was created." : "No strategy was created."}</p>
          </>
        )}
      </section>

      {intake.requested_job === "INVESTIGATE_EFFECT" ? <InvestigationReview intakeId={id}
        interpretationRevisionId={head.interpretation_revision_id} /> : null}

      {/* The region is always on the page, so assistive technology announces the text when it changes. */}
      <p role="status" aria-live="polite" aria-busy={work ? true : undefined} className={work ? "status stop" : "visually-hidden"} data-testid="working">{work}</p>

      {head.reply ? (
        <section className="status stop" aria-labelledby="reply-title" data-testid="reply-state" data-reply={head.reply.state}>
          <h2 id="reply-title" style={{ fontSize: 18 }}>{head.reply.state === "REJECTED" ? "Your last reply could not be used" : head.reply.state === "UNCERTAIN" ? "We do not know if your last reply was read" : "Your last reply was not read"}</h2>
          <p>{head.reply.state === "REJECTED" && head.reply.reason_code === "reply_changed_nothing"
            ? "Your reply matched what is already saved, so nothing changed. Say what you want to change, or choose an option."
            : head.reply.state === "REJECTED"
            ? `The interpreter's reading broke a rule (${head.reply.reason_code?.replaceAll("_", " ")}), so none of it was used. Your saved meaning did not change.`
            : head.reply.state === "UNCERTAIN" ? "The interpreter may or may not have read it. Nothing was retried and your saved meaning did not change."
              : "A system failure stopped the interpreter. Your saved meaning did not change."}</p>
          {head.retry.allowed ? (
            <div className="btn-row">
              <button className="btn btn-secondary" type="button" onClick={retryInterpretation} aria-disabled={busy || undefined}>{busy ? "Trying again…" : "Try this reply again"}</button>
              <span className="muted">You can also choose an option or write something different.</span>
            </div>
          ) : <p className="muted">{RETRY_BLOCKED[head.retry.reason ?? ""] ?? ""}</p>}
        </section>
      ) : null}

      {outcome === "NEEDS_CLARIFICATION" && (
        <section className="panel" aria-labelledby="q-title">
          <h2 id="q-title">What we need from you</h2>
          <QuestionForm questions={head.questions} busy={busy} idPrefix="main" onAnswer={answer} onReply={usesWords ? reply : undefined} message={answerMessage} onCancel={() => go("#/research", `req-${id}`)} />
        </section>
      )}

      {outcome !== "NEEDS_CLARIFICATION" ? <AnswerMessage message={answerMessage} surface="main" /> : null}

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

      {revision && draft && <SpotReplayPanel strategy={draft.content.source_syntax as Strategy}
        strategyId={revision.strategy_id} strategyRevisionId={revision.revision_id} />}

      <InterpretationAttempts attempts={bundle.attempts} lateResults={bundle.late_results}
        open={Boolean(failure) || Boolean(head.reply) || (lastAttempt !== undefined && lastAttempt.status !== "COMPLETED")} />

      <details>
        <summary>Where each setting came from</summary>
        {interp ? (
          <table className="records">
            <thead><tr><th scope="col">Setting</th><th scope="col">Meaning</th><th scope="col">Source</th><th scope="col">Status</th></tr></thead>
            <tbody>
              {interp.content.field_evidence.map((f) => (
                <tr key={f.field_name}>
                  <th scope="row">{FIELD_LABEL[f.field_name] ?? f.field_name}</th>
                  <td>{f.state === "KNOWN" ? summarizeValue(f.field_name, f.value)
                    : f.state === "CONFLICTING" ? <>Two statements that disagree:<ol>{(f.conflicts ?? []).map((c, i) => <li key={i}>{summarizeValue(f.field_name, c.value)}</li>)}</ol></>
                      : "Missing. We will ask."}</td>
                  <td>{f.state === "MISSING" ? "Not stated yet" : ORIGIN_LABEL[f.origin]}{sourceQuote(f.source_ref, intake.original_request) ? <><br /><span className="muted">{`\u201c${sourceQuote(f.source_ref, intake.original_request)}\u201d`}</span></> : null}</td>
                  <td>{f.state === "CONFLICTING" ? "Conflict: needs your answer" : f.state !== "KNOWN" ? "Needs your answer" : f.adoption === "PENDING" ? "Awaiting your adoption" : f.adoption === "ADOPTED" ? "Adopted" : "Stated"}</td>
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
          {lastAttempt ? <>
            <dt>Model and route</dt><dd>{lastAttempt.identity.model} · {lastAttempt.identity.route} · {lastAttempt.identity.runtime_label}</dd>
            <dt>Latest request hash</dt><dd className="mono">{lastAttempt.identity.task_sha256.slice(0, 16)}</dd>
          </> : null}
          <dt>Opened</dt><dd>{opened === "loaded" ? "Read from the database just now" : ""}</dd>
        </dl>
      </details>
    </div>
  );
}
