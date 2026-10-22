import { fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthValue } from "../lib/auth";
import { App } from "../components/App";

const hoisted = vi.hoisted(() => ({ auth: null as AuthValue | null }));
// The signed-out card is rendered from a fixed auth value so the copy and the button can be checked directly.
vi.mock("../lib/auth", () => ({
  AuthRoot: ({ children }: { children: ReactNode }) => children,
  useAuth: () => hoisted.auth,
}));
vi.mock("../components/Shell", () => ({ Shell: () => null }));

function signedOut(overrides: Partial<AuthValue> = {}): AuthValue {
  return {
    status: "signed-out", fixtureLabel: null, unavailableReason: null, userId: null,
    signInMessage: null, signInSlow: false, explicitSignOut: false,
    login: vi.fn(), logout: vi.fn(), createEmbeddedWallet: null,
    ...overrides,
  };
}

beforeEach(() => { hoisted.auth = signedOut(); });

describe("signed-out card", () => {
  it("shows the builder-approved copy", () => {
    render(<App />);
    expect(screen.getByRole("heading", { level: 2, name: "Sign in to Edge OS" })).toBeInTheDocument();
    expect(screen.getByText("Test a trading idea against real Monad data before you risk money.")).toBeInTheDocument();
    const small = screen.getByText("Signing in doesn't move funds or approve any trade. You set up a trading wallet later, only if you want one.");
    expect(small).toHaveClass("muted");
    expect(screen.queryByText(/Sign in to start|Research on Monad|does not create a wallet/)).toBeNull();
  });

  it("the Sign in button still starts sign-in", () => {
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(hoisted.auth!.login).toHaveBeenCalledTimes(1);
  });
});
