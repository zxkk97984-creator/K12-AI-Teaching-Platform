import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { GrowthPage } from "./GrowthPage";

vi.mock("./MemoryDocuments", () => ({
  MemoryDocuments: () => <section data-testid="growth-documents">个人记忆.md</section>,
}));

vi.mock("./AutomaticMemory", () => ({ AutomaticMemory: () => <section>自动记忆测试入口</section> }));

afterEach(cleanup);

it("keeps handwritten memory beside automatic memory", () => {
  render(<GrowthPage />);
  expect(screen.getByRole("heading", { name: "个人记忆" })).toBeTruthy();
  expect(screen.queryByTestId("growth-documents")).toBeNull();
  fireEvent.click(screen.getByRole("tab", { name: "我写的内容" }));
  expect(screen.getByTestId("growth-documents")).toBeTruthy();
  fireEvent.click(screen.getByRole("tab", { name: "自动记忆" }));
  expect(screen.getByTestId("growth-documents")).toBeTruthy();
  expect(screen.queryByLabelText("学习阶段")).toBeNull();
  expect(screen.queryByLabelText("教师风格")).toBeNull();
  expect(screen.queryByText("学习观察")).toBeNull();
  expect(screen.getByText(/自动整理不会覆盖这里的文字/)).toBeTruthy();
});
