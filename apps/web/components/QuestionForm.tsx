"use client";

import { useState } from "react";
import { ORIGIN_LABEL } from "../lib/describe";
import type { FieldEvidence, Question } from "../lib/types";

export interface AnswerProps {
  questions: Question[];
  busy: boolean;
  idPrefix: string;
  onAnswer(questionId: string, choiceId: string, origin?: HTMLElement): void;
  onCancel?(): void;
}

export function QuestionForm({ questions, busy, idPrefix, onAnswer, onCancel }: AnswerProps) {
  if (questions.length === 0) return null;
  return (
    <div className="stack">
      {questions.map((question) => (
        <One key={question.question_id} question={question} busy={busy} idPrefix={idPrefix} onAnswer={onAnswer} />
      ))}
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
          {question.kind === "ADOPT" ? "Adopt these settings" : "Save my answer"}
        </button>
      </div>
    </form>
  );
}
