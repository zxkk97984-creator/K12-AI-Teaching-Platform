import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { LookupCards } from "./LookupCards";
import { MessageView } from "./MessageView";
import type { LookupCardDTO } from "./types";
import * as api from "./api";
import { ApiError } from "../identity/api";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const card: LookupCardDTO = {
  id: "lookup:chapter:one", tool: "COURSE_SEARCH", kind: "COURSE", status: "OK",
  title: "认识人工智能", description: "可信课程说明", queried_at: "2026-10-02T00:00:00Z",
  target: { type: "CHAPTER", id: "chapter-one", revision: "1" }, route: "/chapters/chapter-one?revision=1",
};
const show = (cards: LookupCardDTO[], onRetry?: () => void) => render(<MemoryRouter><Routes>
  <Route path="/" element={<LookupCards cards={cards} onRetry={onRetry} />} />
  <Route path="/chapters/:id" element={<p>课程目标已打开</p>} />
</Routes></MemoryRouter>);

describe("trusted lookup cards", () => {
  it("keeps old messages compatible and never displays missing query sections", () => {
    const { container } = render(<MessageView message={{ id: "old", role: "ASSISTANT", content_markdown: "旧回复", created_at: "2026-10-01T00:00:00Z", card: { message_markdown: "旧回复", source_refs: [], evidence_refs: [], warnings: [], fixture: false } }} />);
    expect(screen.getByText("旧回复")).toBeTruthy();
    expect(container.querySelector(".lookup-results")).toBeNull();
  });
  it("rechecks permissions on explicit activation and uses the returned local route", async () => {
    const resolve = vi.spyOn(api, "resolveLookupTarget").mockResolvedValue({ route: card.route! });
    show([{ ...card, route: "https://evil.test" }]);
    expect(resolve).not.toHaveBeenCalled();
    expect(screen.getByText(/当时的记录/)).toBeTruthy();
    const button = screen.getByRole("button", { name: "打开：认识人工智能" });
    button.focus(); expect(document.activeElement).toBe(button);
    fireEvent.click(button);
    await screen.findByText("课程目标已打开");
    expect(resolve).toHaveBeenCalledWith(card.target);
  });
  it("explains expired targets and supports retry after a transient failure", async () => {
    const resolve = vi.spyOn(api, "resolveLookupTarget")
      .mockRejectedValueOnce(new ApiError(404, "NOT_FOUND", "已撤回", null))
      .mockResolvedValueOnce({ route: card.route! });
    show([card]);
    fireEvent.click(screen.getByRole("button", { name: /打开：/ }));
    await screen.findByRole("alert");
    expect(screen.getByRole("alert").textContent).toContain("版本已不可用");
    fireEvent.click(screen.getByRole("button", { name: "重试打开" }));
    await screen.findByText("课程目标已打开");
    expect(resolve).toHaveBeenCalledTimes(2);
  });
  it("separates empty, failed and unavailable states and offers a normal-question retry", () => {
    const retry = vi.fn();
    show(["EMPTY", "FAILED", "UNAVAILABLE"].map((status, index) => ({ ...card, id: String(index), status: status as LookupCardDTO["status"], target: null, description: status })), retry);
    expect(screen.getByText(/课程与资料 · 没有记录/)).toBeTruthy();
    expect(screen.getByText(/课程与资料 · 查询失败/)).toBeTruthy();
    expect(screen.getByText(/课程与资料 · 暂不可用/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重新询问" }));
    expect(retry).toHaveBeenCalledOnce();
  });
  it("renders explanations as inert data and rejects a forged external route", async () => {
    vi.spyOn(api, "resolveLookupTarget").mockResolvedValue({ route: "https://evil.test" });
    const { container } = show([{ ...card, kind: "WRONG_QUESTION", explanation: '<script>alert("secret")</script>' }]);
    fireEvent.click(screen.getByText("查看已释放的解析"));
    expect(container.querySelector("script")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: /打开：/ }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("打开失败"));
  });
});
