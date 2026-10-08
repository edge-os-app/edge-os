"use client";

import type { Bundle } from "../lib/types";
import { QuestionForm } from "./QuestionForm";

export interface ConversationContext {
  bundle: Bundle;
  busy: boolean;
  answer(questionId: string, choiceId: string): void;
}

/** Contextual conversation. It reads the same saved request and revision as the page. It has no financial tools. */
export function Conversation({ context, idPrefix }: { context: ConversationContext | null; idPrefix: string }) {
  if (!context) {
    return (
      <>
        <h2>Conversation</h2>
        <div className="convo-about">
          <span className="eyebrow">About</span>
          <p style={{ margin: "4px 0 0" }}><strong>Research</strong><br />Your saved requests</p>
        </div>
        <p className="muted">Open a request to see its questions here. This panel reads the same saved records as the page. It never starts research or a trade.</p>
      </>
    );
  }
  const { bundle, busy, answer } = context;
  const { intake, clarifications, head } = bundle;
  const text = intake.content.original_request;
  const labelFor = (qid: string, ref: string) => {
    const choiceId = ref.split(":")[2] ?? "";
    return choiceId === "adopt" ? "Adopted the suggested settings" : `Chose “${choiceId}”`;
  };
  return (
    <>
      <h2>Conversation</h2>
      <div className="convo-about">
        <span className="eyebrow">About this request</span>
        <p style={{ margin: "4px 0 0" }}><strong>{text.length > 90 ? `${text.slice(0, 90)}…` : text}</strong><br />
          <span className="muted">Revision {head.interpretation_revision_id?.slice(0, 8) ?? "none"}</span></p>
      </div>
      <p className="muted" style={{ margin: 0 }}>{bundle.interpreter.notice}</p>
      <div className="stack" role="log" aria-label="Clarification so far">
        {clarifications.map((c) => (
          <div key={c.record_id} className="stack" style={{ gap: 8 }}>
            <div className="msg system"><span className="who">Question</span>{c.content.question}</div>
            <div className="msg user"><span className="who">Your answer</span>{labelFor(c.content.question_id, c.content.answer_ref)}</div>
          </div>
        ))}
        {clarifications.length === 0 ? <p className="muted">No questions answered yet.</p> : null}
      </div>
      {head.outcome === "NEEDS_CLARIFICATION" ? (
        <QuestionForm questions={head.questions} busy={busy} idPrefix={idPrefix} onAnswer={answer} />
      ) : (
        <p className="muted">No question is open for this revision.</p>
      )}
    </>
  );
}
