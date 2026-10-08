import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { QuestionForm } from "../components/QuestionForm";
import type { Question } from "../lib/types";

const choice: Question = { question_id: "choose-entry", kind: "CHOICE", field_name: "entry", text: "What should count as a rise for the entry rule?",
  options: [{ id: "a", label: "Up 1% over 15 minutes" }, { id: "b", label: "Up 2% over 15 minutes" }] };
const adopt: Question = { question_id: "adopt-suggested-settings", kind: "ADOPT", text: "Review the suggested settings. Adopt them to continue.",
  options: [{ id: "adopt", label: "Adopt these settings" }],
  items: [{ field_name: "sizing", label: "Sizing", summary: "Fixed 100 quote units per entry", origin: "AGENT_PROPOSED", question: "q?" }] };

describe("question form", () => {
  it("answers with the keyboard: arrow to a choice, Enter to submit", async () => {
    const onAnswer = vi.fn(); const user = userEvent.setup();
    render(<QuestionForm questions={[choice]} busy={false} idPrefix="t" onAnswer={onAnswer} />);
    expect(screen.getByRole("button", { name: "Save my answer" })).toBeDisabled();
    await user.tab(); await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: /Up 2%/ })).toBeChecked();
    await user.keyboard("{Enter}");
    expect(onAnswer).toHaveBeenCalledWith("choose-entry", "b", expect.any(HTMLFormElement)); // the form says which surface answered
  });

  it("shows every suggested setting with its source before adoption", async () => {
    const onAnswer = vi.fn(); const user = userEvent.setup();
    render(<QuestionForm questions={[adopt]} busy={false} idPrefix="t" onAnswer={onAnswer} />);
    expect(screen.getByRole("row", { name: /Sizing.*Fixed 100 quote units.*Suggested/ })).toBeInTheDocument();
    expect(screen.getByText(/grant no permission to trade/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Adopt these settings" }));
    expect(onAnswer).toHaveBeenCalledWith("adopt-suggested-settings", "adopt", expect.any(HTMLFormElement));
  });

  it("shows a failure inside the form that was submitted, and says it is working while busy", () => {
    const { rerender } = render(<QuestionForm questions={[adopt]} busy idPrefix="t" onAnswer={vi.fn()} />);
    expect(screen.getByRole("button", { name: /Saving/ })).toHaveAttribute("aria-disabled", "true");
    const failure = { kind: "error" as const, surface: "t", text: "A required service is unavailable. Retry later." };
    rerender(<QuestionForm questions={[adopt]} busy={false} idPrefix="t" onAnswer={vi.fn()} message={failure} />);
    expect(screen.getByRole("alert")).toHaveTextContent("unavailable");
    expect(screen.getByRole("button", { name: "Adopt these settings" })).toBeInTheDocument();
    rerender(<QuestionForm questions={[adopt]} busy={false} idPrefix="t" onAnswer={vi.fn()} message={{ kind: "notice", surface: "t", text: "This request changed elsewhere." }} />);
    expect(screen.getByRole("status")).toHaveTextContent("changed elsewhere");
    // another surface acted: this form stays quiet, so a failure is announced once
    rerender(<QuestionForm questions={[adopt]} busy={false} idPrefix="t" onAnswer={vi.fn()} message={{ ...failure, surface: "sheet" }} />);
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("offers a way out that keeps the work", async () => {
    const onCancel = vi.fn(); const user = userEvent.setup();
    render(<QuestionForm questions={[choice]} busy={false} idPrefix="t" onAnswer={vi.fn()} onCancel={onCancel} />);
    await user.click(screen.getByRole("button", { name: "Not now" }));
    expect(onCancel).toHaveBeenCalled();
    expect(screen.getByText(/stay saved/)).toBeInTheDocument();
  });

  it("ignores a second answer while a save is in flight, without dropping keyboard focus", async () => {
    const onAnswer = vi.fn(); const user = userEvent.setup();
    render(<QuestionForm questions={[adopt]} busy idPrefix="t" onAnswer={onAnswer} />);
    const button = screen.getByRole("button", { name: /Saving/ });
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).not.toBeDisabled(); // a disabled button would lose focus on a failed save
    button.focus();
    await user.keyboard("{Enter}");
    expect(onAnswer).not.toHaveBeenCalled();
    expect(button).toHaveFocus();
  });
});
