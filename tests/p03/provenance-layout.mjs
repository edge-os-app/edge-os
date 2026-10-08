import { expect } from "@playwright/test";

export async function openProvenanceAndMeasure(page, expectedMeaning) {
  const disclosure = page.locator("details").filter({
    has: page.getByText("Where each setting came from", { exact: true }),
  });
  await disclosure.locator("summary").click();
  const table = disclosure.locator("table.records");
  const entry = table.getByRole("row").filter({
    has: page.getByRole("rowheader", { name: "Entry rule" }),
  });
  await expect(entry.locator("td").nth(0)).toContainText(expectedMeaning);
  await expect(entry.locator("td").nth(1)).toHaveText("You said");
  await expect(entry.locator("td").nth(2)).toHaveText("Stated");
  await expect(table.getByRole("columnheader", { name: "Source" })).toBeVisible();
  await expect(table.getByRole("columnheader", { name: "Status" })).toBeVisible();

  const measure = await table.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const cells = [...element.querySelectorAll("th, td")].map((cell) => {
      const cellRect = cell.getBoundingClientRect();
      return { text: cell.textContent.trim(), left: cellRect.left, right: cellRect.right,
        width: cell.clientWidth, scrollWidth: cell.scrollWidth };
    });
    return {
      viewport: window.innerWidth,
      document: document.documentElement.scrollWidth,
      tableLeft: rect.left,
      tableRight: rect.right,
      cells,
    };
  });
  return measure;
}

export function expectProvenanceFits(measure) {
  expect(measure.document, JSON.stringify(measure)).toBeLessThanOrEqual(measure.viewport);
  expect(measure.tableLeft, JSON.stringify(measure)).toBeGreaterThanOrEqual(0);
  expect(measure.tableRight, JSON.stringify(measure)).toBeLessThanOrEqual(measure.viewport);
  expect(measure.cells.every((cell) => cell.left >= 0 && cell.right <= measure.viewport
    && cell.scrollWidth <= cell.width + 1), JSON.stringify(measure)).toBe(true);
}
