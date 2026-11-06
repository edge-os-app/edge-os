import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

/*
 * jsdom does not apply stylesheets or do layout, so these checks read the CSS source.
 * They state the rule only. A real browser measurement proves the scrolling behavior.
 */

const APP = readFileSync(resolve(process.cwd(), "app/app.css"), "utf8").replace(/\/\*[\s\S]*?\*\//g, "");

function mediaBlock(condition: string): string {
  const start = APP.indexOf(`@media ${condition} {`);
  if (start === -1) return "";
  const end = APP.indexOf("\n}", start);
  return APP.slice(start, end);
}

function sidebarDeclarations(css: string): Record<string, string> {
  const body = css.match(/(?:^|[\s}])\.sidebar\s*\{([^}]*)\}/)?.[1] ?? "";
  return Object.fromEntries(body.split(";").filter((part) => part.includes(":")).map((part) => {
    const colon = part.indexOf(":");
    return [part.slice(0, colon).trim(), part.slice(colon + 1).trim()];
  }));
}

describe("side bar position", () => {
  it("stays in the window and scrolls by itself above the 760px phone rule", () => {
    expect(sidebarDeclarations(mediaBlock("(width > 760px)"))).toEqual({
      position: "sticky",
      top: "0",
      height: "100dvh",
      "overflow-y": "auto",
    });
  });

  it("adds no position rule to the base or phone layout", () => {
    const phone = sidebarDeclarations(mediaBlock("(max-width: 760px)"));
    expect(Object.keys(phone).sort()).toEqual(["gap", "padding"]);
    const base = sidebarDeclarations(APP.slice(0, APP.indexOf("@media")));
    expect(base).not.toHaveProperty("position");
    expect(base).not.toHaveProperty("height");
  });
});
