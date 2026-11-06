import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/*
 * jsdom does not apply stylesheets or do layout, so these checks read the CSS source.
 * They state the rule only. A real browser measurement proves the scrolling behavior.
 */

const APP = readFileSync(resolve(process.cwd(), "app/app.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

type CssRule = { media: string; declarations: Record<string, string> };

function rulesFor(target: string): CssRule[] {
  const rules: CssRule[] = [];
  let media = "";
  for (const match of APP.matchAll(/@media\s+([^{]+?)\s*\{|([^{}]+)\{([^{}]*)\}|\}/g)) {
    const [token, condition, selectors, body] = match;
    if (condition !== undefined) media = condition;
    else if (token === "}") media = "";
    else if (selectors.split(",").some((selector) => selector.trim() === target)) {
      const parts = body.split(";").filter((part) => part.includes(":"));
      rules.push({
        media,
        declarations: Object.fromEntries(parts.map((part) => {
          const colon = part.indexOf(":");
          return [part.slice(0, colon).trim(), part.slice(colon + 1).trim()];
        })),
      });
    }
  }
  return rules;
}

const sidebarRules = () => rulesFor(".sidebar");

describe("side bar position rules", () => {
  it("sets the sticky declarations in the rule above the 760px phone rule", () => {
    expect(sidebarRules().find((rule) => rule.media === "(width > 760px)")?.declarations).toEqual({
      position: "sticky",
      top: "0",
      height: "100dvh",
      "overflow-y": "auto",
    });
  });

  it("has no other side bar rule that sets a position, height or overflow", () => {
    const others = sidebarRules().filter((rule) => rule.media !== "(width > 760px)");
    expect(others.map((rule) => rule.media)).toEqual(["", "(max-width: 760px)"]);
    expect(Object.keys(others[1].declarations).sort()).toEqual(["gap", "padding"]);
    for (const property of ["position", "top", "height", "overflow", "overflow-y"]) {
      expect(others[0].declarations).not.toHaveProperty(property);
    }
  });
});

describe("right column position rules", () => {
  it("sets the sticky declarations in the rule above the 1180px rule that hides the column", () => {
    expect(rulesFor(".convo-desktop")).toEqual([
      { media: "(max-width: 1180px)", declarations: { display: "none" } },
      { media: "(width > 1180px)", declarations: { position: "sticky", top: "0", height: "100dvh", "overflow-y": "auto" } },
    ]);
  });

  it("leaves the conversation rules that the sheet uses without a position, height or overflow", () => {
    expect(rulesFor(".sheet .convo")).toEqual([{ media: "", declarations: { border: "0", "min-height": "100%" } }]);
    const shared = rulesFor(".convo");
    expect(shared.map((rule) => rule.media)).toEqual([""]);
    for (const property of ["position", "top", "height", "overflow", "overflow-y"]) {
      expect(shared[0].declarations).not.toHaveProperty(property);
    }
  });
});
