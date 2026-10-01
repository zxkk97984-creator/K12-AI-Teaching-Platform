import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { ChapterMarkdown } from "./ChapterMarkdown";

afterEach(cleanup);
describe("imported lecture formatting", () => {
  it("renders tables, code and formulas while treating HTML examples as text", () => {
    const text = "## 示例\n\n| 变量 | 数值 |\n| --- | --- |\n| n | 3 |\n\n```html\n<script>alert(1)</script>\n```\n\n公式：$x^2 + y^2$";
    const { container } = render(<ChapterMarkdown text={text} />);
    expect(screen.getByRole("table")).toBeTruthy();
    expect(screen.getByText("<script>alert(1)</script>")).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector(".katex")).toBeTruthy();
  });
});
