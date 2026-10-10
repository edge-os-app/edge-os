"use client";

import { useEffect, useRef, useState } from "react";
import { ORIGIN_LABEL, summarizeValue } from "../lib/describe";
import type { FieldEvidence, Question } from "../lib/types";

export interface AnswerProps {
  questions: Question[];
  busy: boolean;
  idPrefix: string;
  onAnswer(questionId: string, choiceId: string, origin?: HTMLElement): void;
  /** The user's own words. Present only when the interpreter can read them; the fixture interpreter cannot. */
  onReply?(questionId: string, text: string, origin?: HTMLElement): void;
  onCancel?(): void;
  message?: AnswerMessageValue;
}

export type AnswerMessageValue = { kind: "error" | "notice"; text: string; surface: string };

/** Shows a message only on the surface where the person acted, so a failure appears in one place. A conflict notice
 * must outlive the question form: the reload can remove the form, so hosts render this too. */
export function AnswerMessage({ message, surface }: { message?: AnswerMessageValue; surface: string }) {
  const ref = useRef<HTMLParagraphElement>(null);
  const shown = message && message.surface === surface ? message : undefined;
  useEffect(() => { if (shown) ref.current?.scrollIntoView?.({ block: "center" }); }, [shown?.text, shown?.kind]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!shown) return null;
  return shown.kind === "error"
    ? <p role="alert" className="status err" ref={ref} tabIndex={-1}>{shown.text}</p>
    : <p role="status" className="status stop" ref={ref} tabIndex={-1}>{shown.text}</p>;
}

export function QuestionForm({ questions, busy, idPrefix, onAnswer, onReply, onCancel, message }: AnswerProps) {
  if (questions.length === 0) return null;
  return (
    <div className="stack">
      {questions.map((question) => (
        <One key={question.question_id} question={question} busy={busy} idPrefix={idPrefix} onAnswer={onAnswer} onReply={onReply} />
      ))}
      <AnswerMessage message={message} surface={idPrefix} />
      {onCancel ? (
        <div className="btn-row">
          <button type="button" className="btn btn-secondary" onClick={onCancel}>Not now</button>
          <span className="muted">Your words and any answers stay saved.</span>
        </div>
      ) : null}
    </div>
  );
}

const MAX_WORDS = 2000;

function One({ question, busy, idPrefix, onAnswer, onReply }: { question: Question; busy: boolean; idPrefix: string; onAnswer: AnswerProps["onAnswer"]; onReply: AnswerProps["onReply"] }) {
  const [choice, setChoice] = useState<string>(question.kind === "ADOPT" ? "adopt" : "");
  const base = `${idPrefix}-${question.question_id}`;
  if (question.kind === "TEXT") {
    return onReply ? <Words question={question} busy={busy} base={base} onReply={onReply} heading /> : null;
  }
  return (
    <div className="stack" data-question={question.question_id}>
    <form
      onSubmit={(event) => { event.preventDefault(); if (choice && !busy) onAnswer(question.question_id, choice, event.currentTarget); }}
      aria-labelledby={`${base}-title`} className="stack">
      <h3 id={`${base}-title`}>{question.text}</h3>
      {question.kind === "ADOPT" ? (
        <>
          <table className="records">
            <caption className="visually-hidden">Suggested settings awaiting your adoption</caption>
            <thead><tr><th scope="col">Setting</th><th scope="col">Suggestion</th><th scope="col">Source</th></tr></thead>
            <tbody>
              {question.items?.map((item) => (
                <tr key={item.field_name}>
                  <th scope="row">{item.label}</th>
                  <td>{item.value !== undefined ? summarizeValue(item.field_name, item.value) : item.summary}</td>
                  <td>{ORIGIN_LABEL[item.origin as FieldEvidence["origin"]] ?? item.origin}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="muted">Nothing is adopted until you choose to. These settings only describe how a test would run. They grant no permission to trade.</p>
        </>
      ) : (
        <fieldset>
          <legend className="visually-hidden">{question.text}</legend>
          <div className="choice-list">
            {question.options.map((option) => (
              <label className="choice" key={option.id}>
                <input type="radio" name={base} value={option.id} checked={choice === option.id}
                  onChange={() => setChoice(option.id)} />
                <span>{option.label}</span>
              </label>
            ))}
          </div>
        </fieldset>
      )}
      <div className="btn-row">
        <button type="submit" className="btn btn-primary" disabled={!choice} aria-disabled={busy || undefined}>
          {busy ? "Saving…" : question.kind === "ADOPT" ? "Adopt these settings" : "Save my answer"}
        </button>
      </div>
    </form>
    {question.kind === "CHOICE" && onReply ? <Words question={question} busy={busy} base={base} onReply={onReply} /> : null}
    </div>
  );
}

/** The user's own words for one open question. The interpreter reads them; the user still reviews the result. */
function Words({ question, busy, base, onReply, heading = false }: { question: Question; busy: boolean; base: string; onReply: NonNullable<AnswerProps["onReply"]>; heading?: boolean }) {
  const [words, setWords] = useState("");
  const label = heading ? question.text : "Or say it in your own words";
  return (
    <form className="stack" data-question={`${question.question_id}-words`} aria-labelledby={`${base}-words-label`}
      onSubmit={(event) => { event.preventDefault(); if (words.trim() && !busy) onReply(question.question_id, words, event.currentTarget); }}>
      {heading ? <h3 id={`${base}-words-label`}>{label}</h3> : <label htmlFor={`${base}-words`} id={`${base}-words-label`}>{label}</label>}
      <textarea id={`${base}-words`} className="input" value={words} maxLength={MAX_WORDS} aria-label={heading ? question.text : undefined}
        onChange={(event) => setWords(event.target.value)} aria-describedby={`${base}-words-hint`} />
      <p className="muted" id={`${base}-words-hint`}>The interpreter reads your words. It can misread them, and it cannot replace something you already said. You review the result. Up to {MAX_WORDS.toLocaleString("en-US")} characters.</p>
      <div className="btn-row">
        <button type="submit" className="btn btn-secondary" disabled={!words.trim()} aria-disabled={busy || undefined}>{busy ? "Working…" : "Send my words"}</button>
      </div>
    </form>
  );
}
