import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { GrowthPage } from "./GrowthPage";

vi.mock("./MemoryDocuments", () => ({
  MemoryDocuments: () => <section data-testid="growth-documents">个人记忆.md</section>,
}));

afterEach(cleanup);

it("keeps personal memory focused on the Markdown document", () => {
  render(<GrowthPage />);
  expect(screen.getByRole("heading", { name: "个人记忆" })).toBeTruthy();
  expect(screen.getByTestId("growth-documents")).toBeTruthy();
  expect(screen.queryByLabelText("学习阶段")).toBeNull();
  expect(screen.queryByLabelText("教师风格")).toBeNull();
  expect(screen.queryByText("学习观察")).toBeNull();
  expect(screen.getByText(/当前版本会供 AI 教师参考/)).toBeTruthy();
});
