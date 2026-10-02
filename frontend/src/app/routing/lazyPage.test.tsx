import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { createLazyPage, scheduleIdlePreloads } from "./lazyPage";

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.useRealTimers(); });

describe("page loading", () => {
  it("retries a recoverable load failure and keeps the outer owner mounted", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    let reject!: (error: Error) => void;
    const loader = vi.fn().mockImplementationOnce(() => new Promise((_, fail) => { reject = fail; }))
      .mockResolvedValue({ default: () => <p>页面已打开</p> });
    const { Page } = createLazyPage(loader, "资料库");
    function Owner() {
      const [draft, setDraft] = useState("");
      return <><input aria-label="外层草稿" value={draft} onChange={e => setDraft(e.target.value)} /><Page /></>;
    }
    render(<Owner />);
    fireEvent.change(screen.getByLabelText("外层草稿"), { target: { value: "保留这段草稿" } });
    expect(screen.getByRole("status").textContent).toContain("正在加载资料库");
    reject(new Error("network failed"));
    expect(await screen.findByRole("alert")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重新加载页面" }));
    expect(await screen.findByText("页面已打开")).toBeTruthy();
    expect((screen.getByLabelText("外层草稿") as HTMLInputElement).value).toBe("保留这段草稿");
    expect(loader).toHaveBeenCalledTimes(2);
  });

  it("shares an idle import with navigation and preserves page state on prop changes", async () => {
    const loader = vi.fn().mockResolvedValue({ default: ({ title }: { title: string }) => {
      const [draft, setDraft] = useState("");
      return <><p>{title}</p><input aria-label="页面草稿" value={draft} onChange={e => setDraft(e.target.value)} /></>;
    } });
    const { Page, preload } = createLazyPage(loader, "章节");
    await preload();
    const view = render(<Page title="第一章" />);
    await screen.findByText("第一章");
    fireEvent.change(screen.getByLabelText("页面草稿"), { target: { value: "未发送" } });
    view.rerender(<Page title="第二章" />);
    expect((screen.getByLabelText("页面草稿") as HTMLInputElement).value).toBe("未发送");
    expect(loader).toHaveBeenCalledTimes(1);
  });

  it("runs idle imports sequentially, survives failure and cancels after navigation", async () => {
    vi.useFakeTimers();
    let resolve!: () => void;
    const first = vi.fn(() => new Promise<void>(done => { resolve = done; }));
    const second = vi.fn().mockRejectedValue(new Error("offline"));
    const third = vi.fn().mockResolvedValue(undefined);
    const cancel = scheduleIdlePreloads([first, second, third]);
    expect(first).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1700);
    expect(first).toHaveBeenCalledTimes(1);
    expect(second).not.toHaveBeenCalled();
    resolve();
    await vi.advanceTimersByTimeAsync(200);
    expect(second).toHaveBeenCalledTimes(1);
    cancel();
    await vi.runAllTimersAsync();
    expect(third).not.toHaveBeenCalled();
  });

  it("does not cache a rejected background preload", async () => {
    const loader = vi.fn().mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue({ default: () => <p>重试成功</p> });
    const { Page, preload } = createLazyPage(loader, "练习");
    await expect(preload()).rejects.toThrow("offline");
    render(<Page />);
    await waitFor(() => expect(screen.getByText("重试成功")).toBeTruthy());
    expect(loader).toHaveBeenCalledTimes(2);
  });
});
