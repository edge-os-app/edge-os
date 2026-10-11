"use client";

import { FIELD_LABEL, summarizeValue } from "../lib/describe";
import type { Bundle, Clarification } from "../lib/types";
import { AnswerMessage, QuestionForm } from "./QuestionForm";

export interface ConversationContext {
  bundle: Bundle;
  busy: boolean;
  message?: { kind: "error" | "notice"; text: string; surface: string };
  answer(questionId: string, choiceId: string, origin?: HTMLElement): void;
  reply(questionId: string, text: string, origin?: HTMLElement): void;
}

/** Contextual conversation. It reads the same saved request and revision as the page. It has no financial tools. */
export function Conversation({ context, idPrefix, showTitle = true }: { context: ConversationContext | null; idPrefix: string; showTitle?: boolean }) {
  const title = showTitle ? <h2 tabIndex={-1} data-focus-target>Conversation</h2> : null;
  if (!context) {
    return (
      <>
        {title}
        <div className="convo-about">
          <span className="eyebrow">About</span>
          <p style={{ margin: "4px 0 0" }}><strong>Research</strong><br />Your saved requests</p>
        </div>
        <p className="muted">Open a request to see its questions here. This panel reads the same saved records as the page. It never starts research or a trade.</p>
      </>
    );
  }
  const { bundle, busy, answer, reply, message } = context;
  const { intake, clarifications, head } = bundle;
  const text = intake.content.original_request;
  // Say what the answer changed, in the words of the saved record, not the internal choice ID.
  const labelFor = (c: Clarification) => {
    const result = bundle.interpretations.find((i) => i.content.interpretation_revision_id === c.resulting_revision_id);
    return c.changed_fields.map((name) => {
      const item = result?.content.field_evidence.find((f) => f.field_name === name);
      const label = FIELD_LABEL[name] ?? name;
      return item && item.state === "KNOWN" && c.question_id !== "adopt-suggested-settings" ? `${label}: ${summarizeValue(name, item.value)}` : label;
    });
  };
  return (
    <>
      {title}
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
            <div className="msg user"><span className="who">{c.content.question_id === "adopt-suggested-settings" ? "You adopted" : "Your answer"}</span>{labelFor(c.content).join("; ")}</div>
          </div>
        ))}
        {clarifications.length === 0 ? <p className="muted">No questions answered yet.</p> : null}
      </div>
      {head.outcome === "NEEDS_CLARIFICATION" ? (
        <QuestionForm questions={head.questions} busy={busy} idPrefix={idPrefix} onAnswer={answer}
          onReply={bundle.interpreter.kind === "FIXTURE" ? undefined : reply} message={message} />
      ) : (
        <>
          <AnswerMessage message={message} surface={idPrefix} />
          <p className="muted">No question is open for this revision.</p>
        </>
      )}
    </>
  );
}
