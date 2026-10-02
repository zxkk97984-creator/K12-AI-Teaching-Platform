import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConversationController } from "./controller";
import * as api from "./api";
import { listCourses } from "../content/api";
import { ApiError } from "../identity/api";
import type { RunDTO, SessionDetail } from "./types";
vi.mock("./api", () => ({
  listSessions: vi.fn(),
  getSession: vi.fn(),
  createSession: vi.fn(),
  createTurn: vi.fn(),
  cancelRun: vi.fn(),
  getRun: vi.fn(),
  subscribeRun: vi.fn(),
}));
vi.mock("../content/api", () => ({ listCourses: vi.fn() }));
const detail = (id = "a") =>
  ({
    id,
    chapter_id: `chapter-${id}`,
    chapter_title: id,
    messages: [],
  }) as unknown as SessionDetail;
const run = (status: RunDTO["status"] = "RUNNING") =>
  ({ id: "run-a", session_id: "a", status }) as RunDTO;
const deferred = <T>() => {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => {
    resolve = r;
  });
  return { promise, resolve };
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getSession).mockImplementation(async (id) => detail(id));
  vi.mocked(api.listSessions).mockResolvedValue([]);
  vi.mocked(listCourses).mockResolvedValue({ items: [] });
  vi.mocked(api.subscribeRun).mockReturnValue({ close: vi.fn() });
  vi.mocked(api.createTurn).mockResolvedValue({ run: run() });
});
describe("shared conversation ownership", () => {
  it("deduplicates loading and double-click sends and owns one subscription", async () => {
    const c = new ConversationController();
    await Promise.all([c.initialize(), c.initialize()]);
    expect(api.listSessions).toHaveBeenCalledTimes(1);
    await c.select("a");
    c.setDraft("explain");
    await Promise.all([c.send(), c.send()]);
    expect(api.createTurn).toHaveBeenCalledTimes(1);
    expect(api.subscribeRun).toHaveBeenCalledTimes(1);
    c.dispose();
  });
  it("rejects a stale selection response", async () => {
    const c = new ConversationController();
    const slow = deferred<SessionDetail>();
    vi.mocked(api.getSession).mockImplementation((id) =>
      id === "a" ? slow.promise : Promise.resolve(detail(id)),
    );
    const a = c.select("a");
    await c.select("b");
    slow.resolve(detail("a"));
    await a;
    expect(c.getSnapshot().detail?.id).toBe("b");
    c.dispose();
  });
  it("resumes an accepted run after loading a session without sending it again", async () => {
    const c = new ConversationController();
    vi.mocked(api.getSession).mockResolvedValue({ ...detail(), active_run_id: "run-a" });
    vi.mocked(api.getRun).mockResolvedValue({ ...run(), draft_markdown: "已经生成的一部分" });

    await c.select("a");

    expect(api.getRun).toHaveBeenCalledWith("run-a");
    expect(api.subscribeRun).toHaveBeenCalledTimes(1);
    expect(api.createTurn).not.toHaveBeenCalled();
    expect(c.getSnapshot().run?.draft_markdown).toBe("已经生成的一部分");
    c.dispose();
  });
  it("keeps the composer blocked until a failed run restoration can be retried", async () => {
    const c = new ConversationController();
    vi.mocked(api.getSession).mockResolvedValue({ ...detail(), active_run_id: "run-a" });
    vi.mocked(api.getRun)
      .mockRejectedValueOnce(new Error("暂时无法读取运行"))
      .mockResolvedValueOnce(run());

    await c.select("a");
    expect(c.getSnapshot().selecting).toBe(true);
    expect(c.getSnapshot().error).toContain("暂时无法读取运行");
    c.setDraft("不要重复发送");
    await c.send();
    expect(api.createTurn).not.toHaveBeenCalled();

    await c.reconnect();
    expect(c.getSnapshot().selecting).toBe(false);
    expect(c.getSnapshot().run?.id).toBe("run-a");
    expect(api.subscribeRun).toHaveBeenCalledOnce();
    c.dispose();
  });
  it("clears account state and ignores a late accepted turn after logout", async () => {
    const c = new ConversationController();
    await c.select("a");
    const request = deferred<{ run: RunDTO }>();
    vi.mocked(api.createTurn).mockReturnValue(request.promise);
    c.setDraft("private draft");
    const send = c.send();
    c.dispose();
    request.resolve({ run: run() });
    await send;
    expect(c.getSnapshot().detail).toBeNull();
    expect(c.getSnapshot().draft).toBe("");
    expect(api.subscribeRun).not.toHaveBeenCalled();
  });
  it("reuses idempotency on an uncertain send and never resends on reconnect", async () => {
    const c = new ConversationController();
    await c.select("a");
    c.setDraft("same question");
    vi.mocked(api.createTurn).mockRejectedValueOnce(new Error("network"));
    await c.send();
    await c.send();
    expect(vi.mocked(api.createTurn).mock.calls[0][2]).toBe(
      vi.mocked(api.createTurn).mock.calls[1][2],
    );
    vi.mocked(api.getRun).mockResolvedValue(run("SUCCEEDED"));
    await c.reconnect();
    expect(api.createTurn).toHaveBeenCalledTimes(2);
    expect(c.getSnapshot().run?.status).toBe("SUCCEEDED");
    c.dispose();
  });
  it("keeps an in-flight run across session selection and cancels the owning run", async () => {
    const c = new ConversationController();
    await c.select("a");
    c.setDraft("hello");
    await c.send();
    await c.select("b");
    c.setDraft("second");
    await c.send();
    expect(api.createTurn).toHaveBeenCalledTimes(1);
    vi.mocked(api.cancelRun).mockResolvedValue(run("CANCELLED"));
    await c.cancel();
    expect(api.cancelRun).toHaveBeenCalledWith("run-a");
    expect(c.getSnapshot().detail?.id).toBe("b");
    c.dispose();
  });
  it("keeps a dropped stream as a quiet polling state and clears it on completion", async () => {
    vi.useFakeTimers();
    const c = new ConversationController();
    vi.mocked(api.subscribeRun).mockReturnValue({ close: vi.fn() });
    vi.mocked(api.getRun).mockResolvedValue(run("SUCCEEDED"));
    await c.select("a");
    c.setDraft("hello");
    await c.send();
    const callback = vi.mocked(api.subscribeRun).mock.calls[0][1];

    callback.onError?.();
    expect(c.getSnapshot().error).toBeNull();
    expect(c.getSnapshot().transport).toBe("polling");

    // Events from the closed stream cannot overwrite a newer poll result.
    callback.onUpdate(run("SUCCEEDED"));
    expect(c.getSnapshot().run?.status).toBe("RUNNING");
    await vi.advanceTimersByTimeAsync(2100);
    expect(c.getSnapshot().error).toBeNull();
    expect(c.getSnapshot().run?.status).toBe("SUCCEEDED");
    expect(c.getSnapshot().transport).toBeNull();
    c.dispose();
    vi.useRealTimers();
  });

  it("polls instead of abandoning the run when the stream drops", async () => {
    // A dropped stream does not mean the run stopped: the server keeps going
    // and the result is persisted, so the client must keep reading it.
    vi.useFakeTimers();
    const c = new ConversationController();
    vi.mocked(api.subscribeRun).mockReturnValue({ close: vi.fn() });
    vi.mocked(api.getRun).mockResolvedValue(run("RUNNING"));
    await c.select("a");
    c.setDraft("hello");
    await c.send();
    const callback = vi.mocked(api.subscribeRun).mock.calls[0][1];

    callback.onError?.();
    vi.mocked(api.getRun).mockResolvedValue(run("SUCCEEDED"));
    await vi.advanceTimersByTimeAsync(2100);

    expect(api.getRun).toHaveBeenCalled();
    expect(c.getSnapshot().run?.status).toBe("SUCCEEDED");
    expect(c.getSnapshot().error).toBeNull();
    c.dispose();
    vi.useRealTimers();
  });

  it("updates the same provisional answer through SSE and polling", async () => {
    vi.useFakeTimers();
    const c = new ConversationController();
    await c.select("a");
    c.setDraft("hello");
    await c.send();
    const callback = vi.mocked(api.subscribeRun).mock.calls[0][1];
    callback.onUpdate({ ...run(), draft_markdown: "第一句" });
    expect(c.getSnapshot().run?.draft_markdown).toBe("第一句");

    callback.onError?.();
    vi.mocked(api.getRun).mockResolvedValue({ ...run(), draft_markdown: "第一句，第二句" });
    await vi.advanceTimersByTimeAsync(2100);
    expect(c.getSnapshot().run?.draft_markdown).toBe("第一句，第二句");
    expect(api.createTurn).toHaveBeenCalledTimes(1);
    c.dispose();
    vi.useRealTimers();
  });

  it("unblocks the composer when a vanished run cannot be polled", async () => {
    vi.useFakeTimers();
    const c = new ConversationController();
    await c.select("a");
    c.setDraft("hello");
    await c.send();
    const callback = vi.mocked(api.subscribeRun).mock.calls[0][1];
    vi.mocked(api.getRun).mockRejectedValue(new ApiError(404, "NOT_FOUND", "运行不存在", null));

    callback.onError?.();
    await vi.advanceTimersByTimeAsync(2100);

    expect(c.getSnapshot().run).toBeNull();
    expect(c.getSnapshot().transport).toBeNull();
    expect(c.getSnapshot().error).toContain("已不存在");
    c.dispose();
    vi.useRealTimers();
  });

  it("closes the subscription on dispose and ignores late events", async () => {
    const c = new ConversationController();
    const close = vi.fn();
    vi.mocked(api.subscribeRun).mockReturnValue({ close });
    await c.select("a");
    c.setDraft("hello");
    await c.send();
    const callback = vi.mocked(api.subscribeRun).mock.calls[0][1];
    c.dispose();
    callback.onUpdate(run("SUCCEEDED"));
    expect(close).toHaveBeenCalledOnce();
    expect(c.getSnapshot().run).toBeNull();
    c.trackRun(run());
    expect(api.subscribeRun).toHaveBeenCalledTimes(1);
  });
});

it("offers a fresh validated reply once, ignoring drafts, failures, repeat receipts and restored history", async () => {
  const card = { message_markdown: "解释正文", source_refs: [], evidence_refs: [], warnings: [], fixture: true };
  const completed = { ...run("SUCCEEDED"), card, result_message_id: "message-a" };
  const c = new ConversationController();
  await c.select("a");
  expect(c.claimReplyNarration(completed)).toBe(false);
  c.setDraft("新问题"); await c.send();
  expect(c.claimReplyNarration({ ...completed, status: "RUNNING" })).toBe(false);
  expect(c.claimReplyNarration({ ...completed, status: "FAILED" })).toBe(false);
  expect(c.claimReplyNarration({ ...completed, card: null })).toBe(false);
  expect(c.claimReplyNarration(completed)).toBe(true);
  expect(c.claimReplyNarration(completed)).toBe(false);
  c.dispose();
  const restored = new ConversationController();
  vi.mocked(api.getSession).mockResolvedValue({ ...detail(), active_run_id: "run-a" });
  vi.mocked(api.getRun).mockResolvedValue(completed);
  await restored.select("a");
  expect(restored.claimReplyNarration(completed)).toBe(false);
  restored.dispose();
});

it("does not read a completed reply after switching away and reopening history", async () => {
  const c = new ConversationController(); await c.select("a"); c.setDraft("新问题"); await c.send(); await c.select("b");
  const completed = { ...run("SUCCEEDED"), card: { message_markdown: "正文", source_refs: [], evidence_refs: [], warnings: [], fixture: true }, result_message_id: "message-a" };
  expect(c.claimReplyNarration(completed)).toBe(false);
  await c.select("a");
  expect(c.claimReplyNarration(completed)).toBe(false);
  c.dispose();
});

it("does not offer an idempotent accepted result for automatic narration", async () => {
  const completed = { ...run("SUCCEEDED"), idempotent_replay: true, card: { message_markdown: "正文", source_refs: [], evidence_refs: [], warnings: [], fixture: true }, result_message_id: "m" };
  vi.mocked(api.createTurn).mockResolvedValue({ run: completed });
  const c = new ConversationController(); await c.select("a"); c.setDraft("question"); await c.send();
  expect(c.claimReplyNarration(completed)).toBe(false); c.dispose();
});
