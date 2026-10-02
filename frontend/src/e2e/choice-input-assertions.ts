import { expect, type Page } from "@playwright/test";

export async function expectCompactChoices(page: Page) {
  const inputs = page.locator('input[type="checkbox"], input[type="radio"]');
  expect(await inputs.count()).toBeGreaterThan(0);
  const boxes = await inputs.evaluateAll((elements) => elements.map((element) => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return {
      label: element.getAttribute("aria-label") || element.closest("label")?.textContent?.trim(),
      width: rect.width, height: rect.height,
      opacity: style.opacity, padding: style.padding,
      borderWidth: style.borderWidth, appearance: style.appearance,
      switch: element.getAttribute("role") === "switch",
    };
  }));
  for (const box of boxes) {
    if (box.width === 0 && box.height === 0) continue;
    expect(box.padding, box.label).toBe("0px");
    if (box.opacity === "0") {
      // Grade and pet cards intentionally hide their native radio.
      expect(box.width, box.label).toBeLessThanOrEqual(1);
      expect(box.height, box.label).toBeLessThanOrEqual(1);
    } else if (box.switch) {
      expect(box.width, box.label).toBeCloseTo(44, 0);
      expect(box.height, box.label).toBeCloseTo(24, 0);
      expect(box.appearance, box.label).toBe("none");
    } else {
      expect(box.width, box.label).toBeGreaterThanOrEqual(16);
      expect(box.width, box.label).toBeLessThanOrEqual(20);
      expect(box.height, box.label).toBeCloseTo(box.width, 0);
      expect(box.borderWidth, box.label).toBe("0px");
      expect(box.appearance, box.label).toBe("auto");
    }
  }
}
