import { render, screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ResearchHome } from "../components/ResearchHome";
import { draftKey } from "../lib/draft";

vi.mock("../lib/api", () => ({
  ApiError: class extends Error {},
  api: {
    interpreter: () => Promise.resolve({ interpreter: { kind: "FIXTURE", id: "x", notice: "n" }, samples: [] }),
    list: () => Promise.resolve({ requests: [], has_more: false }),
  },
}));

const draft = JSON.stringify({ text: "my private hunch", kind: "CONCRETE_THESIS", restrictions: ["no leverage"], custom: "", useMarket: false });
const props = { go: vi.fn(), consumeReturn: () => null };

beforeEach(() => window.sessionStorage.clear());

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
});
