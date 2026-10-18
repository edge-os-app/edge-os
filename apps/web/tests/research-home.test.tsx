import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResearchHome } from "../components/ResearchHome";
import { draftKey } from "../lib/draft";

const mocks = vi.hoisted(() => ({
  list: vi.fn(), submit: vi.fn(), interpreter: vi.fn(),
  samples: [{ scenario_id: "hunch", label: "Rough hunch", text: "SAMPLE TEXT", input_class: "LOOSE_INTUITION", requested_job: "CREATE_STRATEGY", restrictions: ["no leverage"], declared_market: null }],
}));
vi.mock("../lib/api", () => ({
  ApiError: class extends Error { status = 503; detail = "A required service is unavailable. Retry later."; },
  api: {
    interpreter: (...args: unknown[]) => mocks.interpreter(...args),
    list: (...args: unknown[]) => mocks.list(...args),
    submit: (...args: unknown[]) => mocks.submit(...args),
  },
}));

const draft = JSON.stringify({ text: "my private hunch", kind: "CONCRETE_THESIS", restrictions: ["no leverage"], custom: "", useMarket: false });
const props = { go: vi.fn(), consumeReturn: () => null };

beforeEach(() => {
  window.sessionStorage.clear();
  mocks.list.mockReset(); mocks.submit.mockReset(); mocks.interpreter.mockReset();
  mocks.list.mockResolvedValue({ requests: [], has_more: false });
  mocks.interpreter.mockResolvedValue({ interpreter: { kind: "FIXTURE", id: "x", notice: "n" }, samples: mocks.samples });
});

describe("unsent draft", () => {
  it("is restored for the same person, also under StrictMode", async () => {
    window.sessionStorage.setItem(draftKey("user-1"), draft);
    render(<StrictMode><ResearchHome userId="user-1" {...props} /></StrictMode>);
    await waitFor(() => expect((screen.getByLabelText("Your words", { selector: "textarea" }) as HTMLTextAreaElement).value).toBe("my private hunch"));
  });

  it("is never shown to another person in the same tab", async () => {
    window.sessionStorage.setItem(draftKey("user-1"), draft);
    render(<ResearchHome userId="user-2" {...props} />);
    await waitFor(() => expect(screen.getByText("Nothing saved yet. Your requests appear here and stay after you close the page.")).toBeInTheDocument());
    expect((screen.getByLabelText("Your words", { selector: "textarea" }) as HTMLTextAreaElement).value).toBe("");
  });

  it("survives a damaged stored draft without crashing", async () => {
    window.sessionStorage.setItem(draftKey("user-1"), JSON.stringify({ text: "x", kind: "NOT_A_KIND", restrictions: "no" }));
    render(<ResearchHome userId="user-1" {...props} />);
    await waitFor(() => expect(screen.getByRole("heading", { name: "Research", level: 1 })).toBeInTheDocument());
    expect((screen.getByLabelText("Your words", { selector: "textarea" }) as HTMLTextAreaElement).value).toBe("");
  });

  it("a failed retry of the saved list shows the error again and keeps the retry button", async () => {
    const { ApiError } = await import("../lib/api");
    mocks.list.mockRejectedValue(new ApiError(503, "service_unavailable", "A required service is unavailable. Retry later."));
    const user = userEvent.setup();
    render(<ResearchHome userId="user-1" {...props} />);
    const retry = await screen.findByRole("button", { name: "Try again" });
    await user.click(retry);
    await waitFor(() => expect(mocks.list).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("alert")).toBeInTheDocument();           // still an error, never a silent "Loading"
    expect(screen.queryByText("Loading saved requests.")).toBeNull();
    expect(screen.getByRole("button", { name: /Try again|Trying again/ })).toBeInTheDocument();
    mocks.list.mockResolvedValue({ requests: [], has_more: false });  // the service recovers
    await user.click(screen.getByRole("button", { name: /Try again/ }));
    await waitFor(() => expect(screen.getByText(/Nothing saved yet/)).toBeInTheDocument());
  });

  it("a restriction typed but not yet added is sent with the request, not dropped", async () => {
    mocks.submit.mockResolvedValue({ intake: { record_id: "abc" } });
    const user = userEvent.setup();
    render(<ResearchHome userId="user-1" {...props} />);
    await screen.findByText(/Nothing saved yet/);
    await user.click(screen.getByRole("button", { name: /Add “no leverage”/ }));
    await user.type(screen.getByLabelText("Your words", { selector: "textarea" }), "my long typed hunch");
    await user.type(screen.getByLabelText("Another restriction in your words"), "never trade at night");
    await user.click(screen.getByRole("button", { name: "Prepare request" }));
    await waitFor(() => expect(mocks.submit).toHaveBeenCalled());
    expect(mocks.submit.mock.calls[0][0].restrictions).toEqual(["no leverage", "never trade at night"]);
  });

  it("choosing an example over typed words can be undone", async () => {
    const user = userEvent.setup();
    render(<ResearchHome userId="user-1" {...props} />);
    const box = screen.getByLabelText("Your words", { selector: "textarea" }) as HTMLTextAreaElement;
    await user.type(box, "my long typed hunch");
    await user.click(await screen.findByRole("button", { name: /SAMPLE TEXT/ }));
    expect(box.value).toBe("SAMPLE TEXT");
    await user.click(screen.getByRole("button", { name: "Restore what I typed" }));
    expect(box.value).toBe("my long typed hunch");
  });

  it("restoring after two example picks brings back the person's own words, not the first example", async () => {
    mocks.samples.push({ scenario_id: "thesis", label: "Specific thesis", text: "SAMPLE B", input_class: "CONCRETE_THESIS", requested_job: "CREATE_STRATEGY", restrictions: [], declared_market: null });
    const user = userEvent.setup();
    render(<ResearchHome userId="user-1" {...props} />);
    const box = screen.getByLabelText("Your words", { selector: "textarea" }) as HTMLTextAreaElement;
    await user.type(box, "my long typed hunch");
    await user.click(await screen.findByRole("button", { name: /SAMPLE TEXT/ }));
    await user.click(screen.getByRole("button", { name: /SAMPLE B/ }));
    await user.click(screen.getByRole("button", { name: /Restore what I typed/ }));
    expect(box.value).toBe("my long typed hunch");
    mocks.samples.pop();
  });

  it("says plainly when restoring will replace edits made to an example", async () => {
    const user = userEvent.setup();
    render(<ResearchHome userId="user-1" {...props} />);
    const box = screen.getByLabelText("Your words", { selector: "textarea" }) as HTMLTextAreaElement;
    await user.type(box, "typed first");
    await user.click(await screen.findByRole("button", { name: /SAMPLE TEXT/ }));
    expect(screen.getByRole("button", { name: "Restore what I typed" })).toBeInTheDocument();
    await user.type(box, " plus my edit");
    expect(screen.getByRole("button", { name: /replaces your edits/ })).toBeInTheDocument();
  });

  it("ignores a second press of Try again while a retry runs, and moves focus to the list heading when it works", async () => {
    const { ApiError } = await import("../lib/api");
    mocks.list.mockRejectedValueOnce(new ApiError(503, "service_unavailable", "A required service is unavailable. Retry later."));
    let release: (v: unknown) => void = () => {};
    mocks.list.mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    const user = userEvent.setup();
    render(<ResearchHome userId="user-1" {...props} />);
    const retry = await screen.findByRole("button", { name: "Try again" });
    await user.click(retry);
    await user.click(screen.getByRole("button", { name: /Trying again/ }));
    await user.click(screen.getByRole("button", { name: /Trying again/ }));
    expect(mocks.list).toHaveBeenCalledTimes(2); // the first load and one retry
    release({ requests: [], has_more: false });
    await waitFor(() => expect(screen.getByText(/Nothing saved yet/)).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "Saved requests" })).toHaveFocus();
  });
});

describe("preparation copy follows the configured interpreter", () => {
  const note = () => screen.getByText(/^Preparing/).textContent ?? "";

  it("says a live release can cost money and starts no study or trade", async () => {
    mocks.interpreter.mockResolvedValue({ interpreter: { kind: "HERMES_LIVE_RELEASE", id: "rel-1", notice: "live notice" }, samples: mocks.samples });
    render(<ResearchHome userId="user-1" {...props} />);
    await waitFor(() => expect(note()).toMatch(/cost/i));
    expect(note()).not.toMatch(/\bfree\b/i);
    expect(note()).not.toMatch(/no study runs in this build/i);
    expect(note()).toMatch(/does not start a study/i);
    expect(note()).toMatch(/authorize a trade/i);
  });

  it("keeps the fixture interpreter clearly a fixture and not a paid call", async () => {
    render(<ResearchHome userId="user-1" {...props} />);
    await waitFor(() => expect(mocks.interpreter).toHaveBeenCalled());
    await waitFor(() => expect(note()).toMatch(/fixture/i));
    expect(note()).not.toMatch(/\bfree\b/i);
    expect(note()).not.toMatch(/may incur a model cost/i);
  });

  it("uses neutral words when the interpreter did not answer", async () => {
    mocks.interpreter.mockRejectedValue(new Error("offline"));
    render(<ResearchHome userId="user-1" {...props} />);
    await waitFor(() => expect(screen.getByText(/examples could not be loaded/i)).toBeInTheDocument());
    expect(note()).not.toMatch(/\bfree\b/i);
    expect(note()).not.toMatch(/may incur a model cost/i);
    expect(note()).not.toMatch(/fixture/i);
  });

  it("never calls preparing free while the interpreter configuration is still unknown", async () => {
    mocks.interpreter.mockReturnValue(new Promise(() => {}));
    render(<ResearchHome userId="user-1" {...props} />);
    await screen.findByText(/Nothing saved yet/);
    expect(note()).not.toMatch(/\bfree\b/i);
    expect(note()).not.toMatch(/may incur a model cost/i);
    expect(note()).not.toMatch(/fixture/i);
  });
});
