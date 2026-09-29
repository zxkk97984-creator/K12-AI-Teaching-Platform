import { listCourses } from "../content/api";
import { ApiError } from "../identity/api";
import type { ChapterSummaryDTO } from "../content/types";
import * as api from "./api";
import type { RunDTO, SceneSnapshot, SessionDetail, SessionSummary } from "./types";

export const isTerminal = (run: RunDTO) =>
  ["SUCCEEDED", "FAILED", "CANCELLED", "STALE"].includes(run.status);
export const STATUS_TEXT: Record<RunDTO["status"], string> = {
  QUEUED: "等待老师回复…",
  RUNNING: "正在生成…",
  SUCCEEDED: "已完成",
  FAILED: "生成失败，请稍后重试",
  CANCELLED: "已取消",
  STALE: "结果已过期，请重新选择课程",
};
export interface ConversationState {
  sessions: SessionSummary[];
  chapters: ChapterSummaryDTO[];
  detail: SessionDetail | null;
  draft: string;
  run: RunDTO | null;
  loading: boolean;
  selecting: boolean;
  sending: boolean;
  transport: "stream" | "polling" | null;
  error: string | null;
}
const initial = (): ConversationState => ({
  sessions: [],
  chapters: [],
  detail: null,
  draft: "",
  run: null,
  loading: false,
  selecting: false,
  sending: false,
  transport: null,
  error: null,
});

/** One owner-scoped controller, one run subscription; no conversation content in storage. */
export class ConversationController {
  private state = initial();
  private disposed = false;
  activate = () => {
    this.disposed = false;
  };
  private listeners = new Set<() => void>();
  private epoch = 0;
  private selection = 0;
  private selectingId: string | null = null;
  private initialized = false;
  private subscription: api.RunSubscription | null = null;
  private followVersion = 0;
  private pending: { session: string; message: string; key: string } | null =
    null;
  private pageContext: (Partial<SceneSnapshot> & { route: string }) | null = null;
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private patch(patch: Partial<ConversationState>) {
    this.state = { ...this.state, ...patch };
    this.listeners.forEach((fn) => fn());
  }
  private fail(error: unknown) {
    this.patch({
      error: error instanceof Error ? error.message : "请求失败，请重试",
    });
  }
  private sceneSnapshot(detail: SessionDetail): SceneSnapshot {
    const route = `${window.location.pathname}${window.location.search}`.slice(0, 240);
    const pageType = window.location.pathname.startsWith("/code")
      ? "codelab"
      : window.location.pathname.startsWith("/practice")
        ? "practice"
        : window.location.pathname.startsWith("/chapters/")
          ? "chapter_reader"
          : "conversation";
    const selected = window.getSelection?.()?.toString().trim().slice(0, 4000) || null;
    const pageContext = this.pageContext?.route === route ? this.pageContext : null;
    return {
      route,
      page_type: pageContext?.page_type ?? pageType,
      chapter_id: detail.chapter_id,
      chapter_title: detail.chapter_title,
      selected_text: pageContext?.selected_text ?? selected,
      content_kind: pageContext?.content_kind,
      content_id: pageContext?.content_id,
      content_version: pageContext?.content_version,
      section_index: pageContext?.section_index,
      visible_section: pageContext?.visible_section,
      knowledge_points: pageContext?.knowledge_points,
      quiz_session_id: pageContext?.quiz_session_id,
      question_id: pageContext?.question_id,
      interactive_session_id: pageContext?.interactive_session_id,
      interactive_scene_id: pageContext?.interactive_scene_id,
      interactive_prompt_id: pageContext?.interactive_prompt_id,
      activity_type: pageContext?.activity_type ?? pageType,
    };
  }
  setPageContext = (context: Partial<SceneSnapshot> | null) => {
    this.pageContext = context
      ? { ...context, route: `${window.location.pathname}${window.location.search}`.slice(0, 240) }
      : null;
  };
  setDraft = (draft: string) => this.patch({ draft });
  initialize = async () => {
    if (this.initialized) return;
    this.initialized = true;
    const epoch = this.epoch;
    this.patch({ loading: true, error: null });
    const [sessions, courses] = await Promise.allSettled([
      api.listSessions(),
      listCourses(),
    ]);
    if (epoch !== this.epoch) return;
    this.patch({
      loading: false,
      ...(sessions.status === "fulfilled" ? { sessions: sessions.value } : {}),
      ...(courses.status === "fulfilled"
        ? { chapters: courses.value.items.flatMap((c) => c.chapters) }
        : {}),
    });
    if (sessions.status === "rejected" || courses.status === "rejected") {
      this.initialized = false;
      this.fail(
        sessions.status === "rejected"
          ? sessions.reason
          : courses.status === "rejected"
            ? courses.reason
            : null,
      );
    }
  };
  select = async (id: string) => {
    if (
      (this.state.detail?.id === id && !this.state.selecting) ||
      this.selectingId === id
    )
      return;
    this.selectingId = id;
    const epoch = this.epoch,
      selection = ++this.selection;
    this.patch({ detail: null, draft: "", selecting: true, error: null });
    try {
      const detail = await api.getSession(id);
      // A refreshed page has no in-memory run. Recover the accepted run from
      // the owner-scoped session before enabling the composer again.
      let activeRun: RunDTO | null = null;
      let restoreError: unknown = null;
      if (detail.active_run_id && (!this.state.run || isTerminal(this.state.run))) {
        try {
          activeRun = await api.getRun(detail.active_run_id);
        } catch (error) {
          if (error instanceof ApiError && error.status === 404) detail.active_run_id = null;
          else restoreError = error;
        }
      }
      if (epoch === this.epoch && selection === this.selection) {
        this.selectingId = null;
        this.patch({ detail, selecting: Boolean(restoreError) });
        if (activeRun && (!this.state.run || isTerminal(this.state.run))) this.follow(activeRun);
        if (restoreError) this.fail(restoreError);
      }
    } catch (error) {
      if (epoch === this.epoch && selection === this.selection) {
        this.selectingId = null;
        this.patch({ selecting: false });
        this.fail(error);
      }
    }
  };
  start = async (chapterId?: string, idempotencyKey?: string) => {
    if (this.state.selecting) return;
    const epoch = this.epoch;
    this.patch({ selecting: true, error: null });
    try {
      const session = await api.createSession(chapterId, idempotencyKey);
      if (epoch !== this.epoch) return;
      this.patch({
        sessions: [
          session,
          ...this.state.sessions.filter((s) => s.id !== session.id),
        ],
        selecting: false,
      });
      await this.select(session.id);
      return this.state.detail?.id === session.id ? session.id : undefined;
    } catch (error) {
      if (epoch === this.epoch) {
        this.patch({ selecting: false });
        this.fail(error);
      }
    }
  };
  private async refresh(id: string, epoch: number) {
    try {
      const [detail, sessions] = await Promise.all([
        api.getSession(id),
        api.listSessions(),
      ]);
      if (epoch !== this.epoch) return;
      this.patch({
        sessions,
        ...(this.state.detail?.id === id ? { detail } : {}),
      });
    } catch (error) {
      if (epoch === this.epoch) this.fail(error);
    }
  }
  setExternalBusy = (sending: boolean) => {
    if (!this.disposed) this.patch({ sending });
  };
  trackRun = (run: RunDTO) => {
    if (this.disposed) return;
    if (this.state.run?.id === run.id && this.subscription) return;
    this.follow(run);
  };
  private follow(run: RunDTO) {
    this.subscription?.close();
    this.subscription = null;
    const epoch = this.epoch;
    const version = ++this.followVersion;
    // A new run supersedes any earlier stream problem: the note belongs to the
    // run it describes, not to the session for the rest of its life.
    this.patch({ run, transport: isTerminal(run) ? null : "stream", error: null });
    if (isTerminal(run)) {
      void this.refresh(run.session_id, epoch);
      return;
    }
    this.subscription = api.subscribeRun(run.id, {
      onUpdate: (update) => {
        if (epoch !== this.epoch || version !== this.followVersion || this.state.transport === "polling") return;
        // Reaching a terminal state is the evidence that the connection
        // worked, so any "connection lost" note is no longer true.
        this.patch({ run: update, transport: isTerminal(update) ? null : "stream", error: null });
        if (isTerminal(update)) {
          this.subscription?.close();
          this.subscription = null;
          void this.refresh(update.session_id, epoch);
          window.dispatchEvent(new Event("learning:updated"));
        }
      },
      onError: () => {
        // The accepted run keeps generating on the server. Its latest draft is
        // stored with the run, so polling can continue the same answer.
        if (epoch !== this.epoch || version !== this.followVersion || this.state.transport === "polling") return;
        this.subscription?.close();
        this.subscription = null;
        this.patch({ transport: "polling" });
        this.pollRun(run.id, epoch, version);
      },
    });
  }

  /**
   * Fallback for a dropped event stream: poll the run until it reaches a
   * terminal state. Bounded, so a run that never finishes cannot poll forever.
   */
  private pollRun(runId: string, epoch: number, version: number) {
    const intervalMs = 2000;
    const maxAttempts = 150;
    let attempt = 0;
    const tick = async () => {
      if (epoch !== this.epoch || version !== this.followVersion || this.state.run?.id !== runId) return;
      if (attempt >= maxAttempts) {
        this.patch({ transport: null, error: "暂时无法继续读取回复，请重新读取状态。" });
        return;
      }
      attempt += 1;
      try {
        const run = await api.getRun(runId);
        if (epoch !== this.epoch || version !== this.followVersion) return;
        if (isTerminal(run)) {
          this.patch({ run, transport: null, error: null });
          void this.refresh(run.session_id, epoch);
          window.dispatchEvent(new Event("learning:updated"));
          return;
        }
        this.patch({ run, error: null });
      } catch (error) {
        if (epoch !== this.epoch || version !== this.followVersion) return;
        if (error instanceof ApiError && error.status === 404) {
          this.patch({ run: null, transport: null, error: "这次回复已不存在，请重新提问。" });
          return;
        }
      }
      window.setTimeout(() => void tick(), intervalMs);
    };
    window.setTimeout(() => void tick(), intervalMs);
  }
  send = async () => {
    const { detail, draft, sending, selecting, run } = this.state;
    if (!draft.trim() || sending || selecting || (run && !isTerminal(run)))
      return;
    // A free conversation can start directly from the empty state. Creating
    // the session first keeps the existing turn/run lifecycle and means the
    // first question is persisted exactly like subsequent turns.
    if (!detail) {
      const message = draft.trim();
      const epoch = this.epoch;
      const creationKey = `k12-session-${crypto.randomUUID()}`;
      const id = await this.start(undefined, creationKey);
      if (!id || epoch !== this.epoch) return;
      this.setDraft(message);
      await this.send();
      return;
    }
    const epoch = this.epoch,
      message = draft.trim();
    if (
      !this.pending ||
      this.pending.session !== detail.id ||
      this.pending.message !== message
    )
      this.pending = { session: detail.id, message, key: crypto.randomUUID() };
    this.patch({ sending: true, error: null });
    try {
      const result = await api.createTurn(
        detail.id,
        message,
        this.pending.key,
        (detail.conversation_type ?? detail.type) === "FREE" ? "FREE" : "LESSON",
        this.sceneSnapshot(detail),
      );
      if (epoch !== this.epoch) return;
      this.pending = null;
      this.patch({
        ...(this.state.detail?.id === detail.id ? { draft: "" } : {}),
        sending: false,
      });
      this.follow(result.run);
      await this.refresh(detail.id, epoch);
    } catch (error) {
      if (epoch === this.epoch) {
        this.patch({ sending: false });
        this.fail(error);
      }
    }
  };
  cancel = async () => {
    const { run } = this.state;
    if (!run || isTerminal(run)) return;
    const epoch = this.epoch;
    try {
      const updated = await api.cancelRun(run.id);
      if (epoch === this.epoch) this.follow(updated);
    } catch (error) {
      if (epoch === this.epoch) this.fail(error);
    }
  };
  rename = async (sessionId: string, title: string) => {
    await api.updateSession(sessionId, { title });
    await this.reconnect();
  };
  archive = async (sessionId: string) => {
    await api.updateSession(sessionId, { archived: true });
    if (this.state.detail?.id === sessionId) this.clearSelection();
    await this.reconnect();
  };
  remove = async (sessionId: string) => {
    await api.deleteSession(sessionId);
    if (this.state.detail?.id === sessionId) this.clearSelection();
    await this.reconnect();
  };
  clearSelection = () => {
    this.epoch++;
    this.followVersion++;
    this.subscription?.close();
    this.subscription = null;
    this.pending = null;
    this.patch({ detail: null, draft: "", run: null, transport: null, selecting: false, sending: false });
  };
  reconnect = async () => {
    const epoch = this.epoch;
    this.patch({ error: null });
    try {
      if (this.state.run) {
        const run = await api.getRun(this.state.run.id);
        if (epoch === this.epoch) this.follow(run);
      } else if (this.state.detail?.active_run_id) {
        try {
          const run = await api.getRun(this.state.detail.active_run_id);
          if (epoch === this.epoch) this.follow(run);
        } catch (error) {
          if (!(error instanceof ApiError) || error.status !== 404) throw error;
          // The run vanished between reading the session and retrying it.
          // Stop blocking the composer; the next detail refresh will confirm.
          if (epoch === this.epoch) this.patch({ run: null, transport: null });
        }
      }
      if (this.state.detail) await this.refresh(this.state.detail.id, epoch);
      const sessions = await api.listSessions();
      if (epoch === this.epoch) this.patch({ sessions, selecting: false });
      await this.initialize();
    } catch (error) {
      if (epoch === this.epoch) this.fail(error);
    }
  };
  dispose = () => {
    this.disposed = true;
    this.epoch++;
    this.followVersion++;
    this.selection++;
    this.subscription?.close();
    this.subscription = null;
    this.initialized = false;
    this.pending = null;
    this.selectingId = null;
    this.patch(initial());
  };
}
