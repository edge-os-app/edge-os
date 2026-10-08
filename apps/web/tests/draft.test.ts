import { beforeEach, describe, expect, it } from "vitest";
import { clearClientState, draftKey, parseDraft } from "../lib/draft";

beforeEach(() => window.sessionStorage.clear());

describe("unsent draft storage", () => {
  const good = JSON.stringify({ text: "a hunch", kind: "LOOSE_INTUITION", restrictions: ["no leverage"], custom: "x", useMarket: true });

  it("accepts a well-formed draft", () => {
    expect(parseDraft(good)).toEqual({ text: "a hunch", kind: "LOOSE_INTUITION", restrictions: ["no leverage"], custom: "x", useMarket: true });
  });

  it.each([
    ["not json", "{"], ["an unknown kind", JSON.stringify({ text: "a", kind: "SOMETHING", restrictions: [] })],
    ["restrictions that are not strings", JSON.stringify({ text: "a", kind: "LOOSE_INTUITION", restrictions: [1] })],
    ["a missing text", JSON.stringify({ kind: "LOOSE_INTUITION", restrictions: [] })], ["nothing", null],
  ])("drops %s instead of trusting it", (_name, raw) => { expect(parseDraft(raw as string | null)).toBeNull(); });

  it("keys the draft by the verified person", () => {
    expect(draftKey("user-1")).not.toBe(draftKey("user-2"));
  });

  it("removes everything this app stored when a person signs out, and nothing else", () => {
    window.sessionStorage.setItem(draftKey("user-1"), good);
    window.sessionStorage.setItem("edge-os:publication:abc", "{}");
    window.sessionStorage.setItem("other-app:keep", "1");
    clearClientState();
    expect(window.sessionStorage.getItem(draftKey("user-1"))).toBeNull();
    expect(window.sessionStorage.getItem("edge-os:publication:abc")).toBeNull();
    expect(window.sessionStorage.getItem("other-app:keep")).toBe("1");
  });
});
