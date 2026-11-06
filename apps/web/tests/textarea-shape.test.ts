import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/*
 * The base stylesheet gives every `.input` a 999px radius. On a 90px-tall
 * textarea that curve cuts the first line, so the label looks broken and the
 * placeholder starts outside the box. These checks read the CSS source because
 * jsdom does not apply stylesheets, and they state the shape contract:
 * multi-line fields keep a normal token corner, single-line controls stay pills.
 */

type Rule = { selector: string; declarations: Record<string, string>; order: number };

const WEB_ROOT = process.cwd();
const ORGANIC = readFileSync(resolve(WEB_ROOT, "app/organic.css"), "utf8");
const APP = readFileSync(resolve(WEB_ROOT, "app/app.css"), "utf8");

function parse(css: string, firstOrder: number): Rule[] {
  const text = css.replace(/\/\*[\s\S]*?\*\//g, "");
  const rules: Rule[] = [];
  const block = /([^{}]+)\{([^{}]*)\}/g;
  let order = firstOrder;
  let match: RegExpExecArray | null;
  while ((match = block.exec(text))) {
    const selectorGroup = match[1].trim();
    if (!selectorGroup || selectorGroup.startsWith("@")) continue;
    const declarations: Record<string, string> = {};
    for (const part of match[2].split(";")) {
      const colon = part.indexOf(":");
      if (colon === -1) continue;
      declarations[part.slice(0, colon).trim()] = part.slice(colon + 1).trim();
    }
    for (const selector of selectorGroup.split(",")) {
      rules.push({ selector: selector.trim(), declarations, order: order++ });
    }
  }
  return rules;
}

const ORGANIC_RULES = parse(ORGANIC, 0);
const APP_RULES = parse(APP, ORGANIC_RULES.length + 1);
const ALL_RULES = [...ORGANIC_RULES, ...APP_RULES];

type Element = { tag: string; classes: string[] };

const TEXTAREA: Element = { tag: "textarea", classes: ["input"] };
const SINGLE_LINE_INPUT: Element = { tag: "input", classes: ["input"] };

function lastCompound(selector: string): string {
  const parts = selector.split(/\s+|>/).filter(Boolean);
  return parts[parts.length - 1] ?? "";
}

function appliesTo(selector: string, element: Element): boolean {
  const parts = selector.split(/\s+|>/).filter(Boolean);
  // Ancestor-scoped rules need page context. This contract is about the base
  // shape of a control, so only consider rules that match the control alone.
  if (parts.length !== 1) return false;
  const compound = lastCompound(selector);
  if (!compound || compound.includes("::")) return false;
  if (/:not\(\s*textarea\s*\)/.test(compound) && element.tag === "textarea") return false;

  const tag = compound.match(/^[a-zA-Z]+/);
  if (tag && tag[0].toLowerCase() !== element.tag) return false;

  const required = [...compound.matchAll(/\.([a-zA-Z0-9_-]+)/g)].map((m) => m[1]);
  if (!required.every((name) => element.classes.includes(name))) return false;

  const states = (compound.match(/:[a-zA-Z-]+/g) ?? []).filter((p) => p !== ":not");
  return states.length === 0;
}

function declarationsFor(element: Element, property: string): { value: string; order: number }[] {
  return ALL_RULES
    .filter((rule) => appliesTo(rule.selector, element) && rule.declarations[property] !== undefined)
    .map((rule) => ({ value: rule.declarations[property], order: rule.order }))
    .sort((a, b) => a.order - b.order);
}

function tokens(): Record<string, string> {
  const found: Record<string, string> = {};
  for (const rule of ALL_RULES) {
    for (const [property, value] of Object.entries(rule.declarations)) {
      if (property.startsWith("--radius")) found[property] = value;
    }
  }
  return found;
}

function radiusPixels(value: string): number {
  const token = /^var\((--[a-zA-Z0-9-]+)\)$/.exec(value);
  if (token) return radiusPixels(tokens()[token[1]] ?? "0");
  const px = /^([\d.]+)px$/.exec(value);
  if (px) return Number(px[1]);
  return Number.POSITIVE_INFINITY;
}

function effective(element: Element, property: string): string {
  const values = declarationsFor(element, property);
  return values.length ? values[values.length - 1].value : "";
}

describe("multi-line input shape", () => {
  it("does not give a textarea a pill radius", () => {
    const radii = declarationsFor(TEXTAREA, "border-radius").map((entry) => entry.value);
    expect(radii.length).toBeGreaterThan(0);
    expect(radii.every((value) => !value.includes("999") && !value.includes("50%"))).toBe(true);
  });

  it("gives a textarea a normal token corner that cannot cut the first line", () => {
    const radius = radiusPixels(effective(TEXTAREA, "border-radius"));
    const minHeight = Number.parseFloat(effective(TEXTAREA, "min-height"));
    expect(radius).toBeLessThanOrEqual(24);
    expect(minHeight).toBeGreaterThanOrEqual(90);
    expect(radius).toBeLessThanOrEqual(minHeight / 2);
  });

  it("keeps the corner smaller than the inline padding so text starts inside the box", () => {
    const radius = radiusPixels(effective(TEXTAREA, "border-radius"));
    const paddingInline = Number.parseFloat(effective(TEXTAREA, "padding-inline"));
    expect(paddingInline).toBeGreaterThan(0);
    expect(radius).toBeLessThanOrEqual(paddingInline + 16);
  });

  it("keeps single-line inputs, buttons, tags and segments as pills", () => {
    expect(effective(SINGLE_LINE_INPUT, "border-radius")).toBe("999px");
    for (const element of [
      { tag: "button", classes: ["btn"] },
      { tag: "span", classes: ["tag"] },
      { tag: "div", classes: ["seg"] },
    ]) {
      expect(effective(element, "border-radius")).toBe("999px");
    }
  });

  it("keeps the textarea rule in the base sheet, not only inside a narrow media query", () => {
    const applicable = ALL_RULES.filter(
      (rule) => appliesTo(rule.selector, TEXTAREA) && rule.declarations["border-radius"] !== undefined,
    );
    expect(applicable.some((rule) => rule.selector.includes("textarea"))).toBe(true);
  });
});
