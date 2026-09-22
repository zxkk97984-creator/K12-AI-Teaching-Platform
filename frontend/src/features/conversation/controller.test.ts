import { beforeEach, describe, expect, it, vi } from "vitest";
import { ConversationController } from "./controller";
import * as api from "./api";
import { listCourses } from "../content/api";
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
  it("clears a dropped-connection note once the run reaches a terminal state", async () => {
    // Regression: the note used to persist for the rest of the session, so a
    // run that finished normally still showed "connection lost".
    const c = new ConversationController();
    vi.mocked(api.subscribeRun).mockReturnValue({ close: vi.fn() });
    await c.select("a");
    c.setDraft("hello");
    await c.send();
    const callback = vi.mocked(api.subscribeRun).mock.calls[0][1];

    callback.onError?.();
    expect(c.getSnapshot().error).toContain("实时连接中断");

    callback.onUpdate(run("SUCCEEDED"));
    expect(c.getSnapshot().error).toBeNull();
    expect(c.getSnapshot().run?.status).toBe("SUCCEEDED");
    c.dispose();
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
    await vi.advanceTimersByTimeAsync(3100);

    expect(api.getRun).toHaveBeenCalled();
    expect(c.getSnapshot().run?.status).toBe("SUCCEEDED");
    expect(c.getSnapshot().error).toBeNull();
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
