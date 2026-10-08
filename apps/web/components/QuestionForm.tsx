"use client";

import { useEffect, useRef, useState } from "react";
import { ORIGIN_LABEL } from "../lib/describe";
import type { FieldEvidence, Question } from "../lib/types";

export interface AnswerProps {
  questions: Question[];
  busy: boolean;
  idPrefix: string;
  onAnswer(questionId: string, choiceId: string, origin?: HTMLElement): void;
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

export function QuestionForm({ questions, busy, idPrefix, onAnswer, onCancel, message }: AnswerProps) {
  if (questions.length === 0) return null;
  return (
    <div className="stack">
      {questions.map((question) => (
        <One key={question.question_id} question={question} busy={busy} idPrefix={idPrefix} onAnswer={onAnswer} />
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

function One({ question, busy, idPrefix, onAnswer }: { question: Question; busy: boolean; idPrefix: string; onAnswer: AnswerProps["onAnswer"] }) {
  const [choice, setChoice] = useState<string>(question.kind === "ADOPT" ? "adopt" : "");
  const base = `${idPrefix}-${question.question_id}`;
  return (
    <form
      onSubmit={(event) => { event.preventDefault(); if (choice && !busy) onAnswer(question.question_id, choice, event.currentTarget); }}
      aria-labelledby={`${base}-title`} className="stack" data-question={question.question_id}>
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
                  <td>{item.summary}</td>
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
  );
}
