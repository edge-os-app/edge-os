import { act, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Landing from "../app/page";
import AppRoute from "../app/app/page";

const hoisted = vi.hoisted(() => ({ privyLoaded: vi.fn() }));
// The Privy bridge is replaced so a test can tell whether a route tried to start sign-in.
vi.mock("../lib/privy-bridge", () => {
  hoisted.privyLoaded();
  return { default: () => null };
});

type Observer = { callback: IntersectionObserverCallback; observed: Element[] };
let observers: Observer[] = [];

function stubBrowser({ reduceMotion }: { reduceMotion: boolean }) {
  vi.stubGlobal("matchMedia", (query: string) => ({
    matches: reduceMotion && query.includes("prefers-reduced-motion"),
    media: query, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {}, onchange: null, dispatchEvent: () => false,
  }));
  vi.stubGlobal("IntersectionObserver", class {
    state: Observer;
    constructor(callback: IntersectionObserverCallback) { this.state = { callback, observed: [] }; observers.push(this.state); }
    observe(el: Element) { this.state.observed.push(el); }
    unobserve() {}
    disconnect() {}
  });
}

const animate = vi.fn();
beforeEach(() => {
  observers = [];
  animate.mockReset();
  Element.prototype.animate = animate as unknown as typeof Element.prototype.animate;
  vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://api.test");
  delete window.__EDGE_OS_TEST_AUTH__;
});
afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

describe("landing route /", () => {
  it("renders the landing without starting sign-in, even when a session could be injected", async () => {
    stubBrowser({ reduceMotion: false });
    vi.stubEnv("NEXT_PUBLIC_PRIVY_APP_ID", "app-id");
    window.__EDGE_OS_TEST_AUTH__ = { label: "TEST AUTH FIXTURE", getAccessToken: async () => "token" };
    render(<Landing />);
    await act(async () => {});
    expect(screen.getByRole("heading", { level: 1, name: /Test your trade idea/ })).toBeInTheDocument();
    expect(screen.queryByTestId("fixture-banner")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
    expect(hoisted.privyLoaded).not.toHaveBeenCalled();
  });

  it("sends every Enter app link to /app with a plain anchor and keeps the other calls to action", () => {
    stubBrowser({ reduceMotion: true });
    render(<Landing />);
    const enter = screen.getAllByRole("link", { name: "Enter app" });
    expect(enter).toHaveLength(3);
    for (const link of enter) expect(link).toHaveAttribute("href", "/app");
    expect(screen.getByRole("link", { name: "Watch the pitch" })).toHaveAttribute("href", "https://vimeo.com/1235649955");
    const code = screen.getByRole("link", { name: "View the code" });
    expect(code).toHaveAttribute("href", "https://github.com/edge-os-app/edge-os");
    expect(code).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("offers a skip link to the main landmark and one landmark per section", () => {
    stubBrowser({ reduceMotion: true });
    render(<Landing />);
    const skip = screen.getByRole("link", { name: "Skip to content" });
    expect(skip).toHaveAttribute("href", "#main");
    expect(document.getElementById("main")).toBe(screen.getByRole("main"));
    expect(screen.getByRole("banner")).toBeInTheDocument();
    expect(screen.getByRole("contentinfo")).toBeInTheDocument();
    for (const name of ["Ask, check, then go live.", "Answers to the real worries.", "Built on Monad", "An edge needs a reason, not a lucky chart."]) {
      expect(screen.getByRole("heading", { level: 2, name })).toBeInTheDocument();
    }
  });

  it("keeps the permission slip approved by the builder and every example labelled illustrative", () => {
    stubBrowser({ reduceMotion: true });
    render(<Landing />);
    expect(screen.getAllByRole("img", { name: "Stamp: approved by you" })).toHaveLength(1);
    expect(screen.getByText(/Approved by you · Oct 5, 11:00 UTC/)).toBeInTheDocument();
    expect(screen.queryByText(/Signed with your wallet/)).toBeNull();
    expect(screen.getAllByText(/No\. D-002 · Illustrative/)).toHaveLength(2);
    const report = screen.getByRole("figure", { name: /Edge OS report screen.*Illustrative example/ });
    expect(within(report).getByText("Illustrative example")).toBeInTheDocument();
    expect(screen.getByRole("figure", { name: /clarify screen/ })).toBeInTheDocument();
  });

  it("gives informative images alt text and hides decorative art from assistive technology", () => {
    stubBrowser({ reduceMotion: true });
    const { container } = render(<Landing />);
    expect(screen.getByRole("img", { name: /Edge OS agent page for Agent D.*no open positions/ })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Edge OS" })).toHaveAttribute("src", "/landing/lockup.svg");
    for (const image of Array.from(container.querySelectorAll("img"))) expect(image.hasAttribute("alt")).toBe(true);
    const mark = container.querySelector('img[src="/landing/icon.svg"]');
    expect(mark).toHaveAttribute("alt", "");
  });
});

describe("landing motion", () => {
  function revealBlocks() { return Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]")); }
  function stubLayout() {
    vi.spyOn(Element.prototype, "getBoundingClientRect").mockImplementation(function (this: Element) {
      const first = document.querySelector("[data-reveal]");
      const top = this === first ? 10 : 5000;
      return { top, bottom: top + 100, left: 0, right: 100, width: 100, height: 100, x: 0, y: top, toJSON: () => ({}) };
    });
  }

  it("hides only blocks below the fold, then reveals them as they scroll into view", () => {
    stubBrowser({ reduceMotion: false });
    stubLayout();
    render(<Landing />);
    const [inView, ...below] = revealBlocks();
    expect(below.length).toBeGreaterThan(3);
    expect(inView.style.opacity).toBe("");
    for (const block of below) expect(block.style.opacity).toBe("0");

    const target = below[0];
    act(() => observers[0].callback([{ isIntersecting: true, target } as unknown as IntersectionObserverEntry], {} as IntersectionObserver));
    expect(target.style.opacity).toBe("");
    expect(animate).toHaveBeenCalledWith(expect.any(Array), expect.objectContaining({ duration: 650 }));
  });

  it("plays the slip and stamp entrance once on load", () => {
    stubBrowser({ reduceMotion: false });
    stubLayout();
    render(<Landing />);
    const durations = animate.mock.calls.map((call) => (call[1] as { duration: number }).duration);
    expect(durations).toEqual(expect.arrayContaining([900, 380]));
  });

  it("shows all content and runs no animation when the person prefers reduced motion", () => {
    stubBrowser({ reduceMotion: true });
    stubLayout();
    render(<Landing />);
    for (const block of revealBlocks()) expect(block.style.opacity).toBe("");
    expect(animate).not.toHaveBeenCalled();
    expect(observers).toHaveLength(0);
  });
});

describe("app route /app", () => {
  it("still renders the application behind its sign-in gate", async () => {
    stubBrowser({ reduceMotion: true });
    vi.stubEnv("NEXT_PUBLIC_PRIVY_APP_ID", "");
    render(<AppRoute />);
    expect(await screen.findByRole("heading", { name: "Sign-in is unavailable" })).toBeInTheDocument();
    expect(screen.getByText("Sign-in is not configured for this deployment.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { level: 1, name: /Test your trade idea/ })).toBeNull();
  });
});
