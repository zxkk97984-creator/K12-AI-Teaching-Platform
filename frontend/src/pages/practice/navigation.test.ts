import { describe, expect, it } from "vitest";
import { historyLocation, practiceReturn } from "./navigation";

describe("practice navigation boundaries", () => {
  it("keeps list filters while rejecting external or mutating return targets", () => {
    expect(practiceReturn("/practice?view=history&type=questions&favorite=1")).toBe("/history?type=questions&favorite=1");
    for (const value of ["//evil.test", "https://evil.test", "/practice?chapter=id&start=1", "/login", "/admin/ai", "/workbench#bad", "/history?start=1", "/history?returnTo=https://evil.test"]) expect(practiceReturn(value)).toBeNull();
  });
  it("keeps history filters and migrates old links without starting a lesson", () => {
    expect(practiceReturn("/resources")).toBe("/resources");
    expect(practiceReturn("/resources?start=1")).toBeNull();
    expect(practiceReturn("/resources?returnTo=https://evil.test")).toBeNull();
    expect(practiceReturn("/history?type=interactive&status=completed")).toBe("/practice?status=completed");
    expect(historyLocation(new URLSearchParams("view=history&type=games&chapter=old&start=1"))).toBe("/practice");
  });
  it("moves personal quiz bookmarks to history while retaining active filters", () => {
    expect(practiceReturn("/practice?type=questions&favorite=1")).toBe("/history?type=questions&favorite=1");
    expect(practiceReturn("/practice?tab=teacher")).toBe("/history?type=questions");
    expect(practiceReturn("/practice?tab=active")).toBe("/history?status=active&type=questions");
  });
  it("keeps search text as data in safe history return links", () => {
    const target = `/history?type=questions&status=completed&q=${encodeURIComponent("Python 条件 & 循环")}`;
    expect(practiceReturn(target)).toBe(target);
    expect(practiceReturn(`${target}&start=1`)).toBeNull();
    expect(historyLocation(new URLSearchParams("type=questions&q=+Python+"))).toBe("/history?type=questions&q=Python");
    expect(historyLocation(new URLSearchParams("q=all"))).toBe("/history?q=all");
    expect(historyLocation(new URLSearchParams("q=0"))).toBe("/history?q=0");
  });
});
