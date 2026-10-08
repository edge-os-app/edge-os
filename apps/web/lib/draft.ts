import type { InputClass } from "./types";

export const STORAGE_PREFIX = "edge-os:";
const DRAFT_PREFIX = `${STORAGE_PREFIX}research-draft:`;
const KINDS: InputClass[] = ["LOOSE_INTUITION", "CONCRETE_THESIS", "BOUNDED_NO_THESIS"];

export interface Draft { text: string; kind: InputClass; restrictions: string[]; custom: string; useMarket: boolean }

/** A draft belongs to one verified person. Another person in the same tab never sees it. */
export function draftKey(userId: string): string { return `${DRAFT_PREFIX}${userId}`; }

/** Accepts only a well-formed draft. A damaged or foreign value is dropped, never trusted. */
export function parseDraft(raw: string | null): Draft | null {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw) as Partial<Draft>;
    if (typeof value.text !== "string" || !KINDS.includes(value.kind as InputClass)) return null;
    if (!Array.isArray(value.restrictions) || !value.restrictions.every((r) => typeof r === "string")) return null;
    return { text: value.text, kind: value.kind as InputClass, restrictions: value.restrictions,
      custom: typeof value.custom === "string" ? value.custom : "", useMarket: value.useMarket === true };
  } catch { return null; }
}

/** Everything this app keeps in the tab (drafts, retry keys) is removed on an explicit sign-out. */
export function clearClientState(): void {
  try {
    const keys: string[] = [];
    for (let i = 0; i < window.sessionStorage.length; i++) {
      const key = window.sessionStorage.key(i);
      if (key && key.startsWith(STORAGE_PREFIX)) keys.push(key);
    }
    keys.forEach((key) => window.sessionStorage.removeItem(key));
  } catch { /* storage may be blocked */ }
}
