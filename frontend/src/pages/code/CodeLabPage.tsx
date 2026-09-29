import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { ApiError } from "../../features/identity/api";
import { useAccount } from "../../features/identity/AccountContext";
import {
  favoriteCodeTask,
  getCodeDraft,
  getCodeRun,
  getCodeTask,
  getRunnerStatus,
  listCodeRuns,
  listCodeTasks,
  unfavoriteCodeTask,
} from "../../features/codelab/api";
import { CodeLabBank } from "../../features/codelab/CodeLabBank";
import { CodeLabBackButton } from "../../features/codelab/CodeLabBackButton";
import { CodeLabHistory, CodeLabHistoryDetail } from "../../features/codelab/CodeLabHistory";
import { CodeLabWorkspace } from "../../features/codelab/CodeLabWorkspace";
import type { CodeDraft, CodeRunDetail, CodeRunSummary, CodeTask } from "../../features/codelab/types";
import "../../features/codelab/codelab.css";

const PAGE_SIZE = 10;
type Tab = "bank" | "favorites" | "history";

function tabFrom(params: URLSearchParams): Tab {
  const value = params.get("tab");
  return value === "favorites" || value === "history" ? value : "bank";
}

function pageFrom(params: URLSearchParams, key = "page"): number {
  const value = Number(params.get(key) ?? "1");
  return Number.isSafeInteger(value) && value > 0 ? value : 1;
}

function validPageValue(value: string | null): boolean {
  if (value === null) return true;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0;
}

function errorMessage(caught: unknown, fallback: string): string {
  if (caught instanceof ApiError) return caught.message;
  if (caught instanceof Error && caught.message) return caught.message;
  return fallback;
}

export function CodeLabPage() {
  const account = useAccount();
  const stage = account?.profile?.stage;
  const userId = account?.user.id ?? "anonymous";
  const location = useLocation();
  const navigate = useNavigate();
  const params = useMemo(() => new URLSearchParams(location.search), [location.search]);
  const tab = tabFrom(params);
  const taskId = params.get("task");
  const revisionParam = params.get("revision");
  const runParam = params.get("run");
  const restoreParam = params.get("restore_run");
  const historyDetailMode = tab === "history" && params.get("view") === "record" && Boolean(runParam);
  const workspaceMode = Boolean(taskId) && !historyDetailMode;
  const bankPage = pageFrom(params);
  const historyPage = pageFrom(params, "history_page");
  const bankQuery = params.get("q") ?? "";
  const category = params.get("category") ?? "";
  const difficulty = params.get("difficulty") ?? "";
  const progress = params.get("progress") ?? "";
  const historyQuery = params.get("history_q") ?? "";
  const purpose = params.get("purpose") ?? "";
  const scopeKind = params.get("scope_kind") ?? "";

  const [queryDraft, setQueryDraft] = useState(bankQuery);
  const [historyQueryDraft, setHistoryQueryDraft] = useState(historyQuery);
  const [tasks, setTasks] = useState<CodeTask[]>([]);
  const [taskTotal, setTaskTotal] = useState(0);
  const [facets, setFacets] = useState<{ categories: string[]; difficulties: string[] }>({ categories: [], difficulties: [] });
  const [bankLoading, setBankLoading] = useState(false);
  const [bankError, setBankError] = useState("");
  const [bankAttempt, setBankAttempt] = useState(0);
  const [favoritePending, setFavoritePending] = useState<string | null>(null);
  const [favoriteError, setFavoriteError] = useState("");
  const [historyRows, setHistoryRows] = useState<CodeRunSummary[]>([]);
  const [historyTotal, setHistoryTotal] = useState(0);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [historyAttempt, setHistoryAttempt] = useState(0);
  const [detail, setDetail] = useState<CodeRunDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [workspaceTask, setWorkspaceTask] = useState<CodeTask | null>(null);
  const [workspaceDraft, setWorkspaceDraft] = useState<CodeDraft | null>(null);
  const [workspaceRun, setWorkspaceRun] = useState<CodeRunDetail | null>(null);
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [workspaceError, setWorkspaceError] = useState("");
  const [runnerAvailable, setRunnerAvailable] = useState(false);
  const [runnerReason, setRunnerReason] = useState("正在检查真实 runner…");
  const loadedWorkspaceKey = useMemo(
    () => `${stage ?? ""}:${userId}:${taskId ?? ""}:${revisionParam ?? "latest"}`,
    [revisionParam, stage, taskId, userId],
  );
  const loadedWorkspaceRef = useRef("");

  useEffect(() => {
    const next = new URLSearchParams(location.search);
    let changed = false;
    const removeInvalid = (key: string, accepted: readonly string[]) => {
      const value = next.get(key);
      if (value !== null && !accepted.includes(value)) {
        next.delete(key);
        changed = true;
      }
    };
    removeInvalid("tab", ["bank", "favorites", "history"]);
    removeInvalid("category", ["PYTHON_BASICS", "DATA_PROCESSING", "ALGORITHMS"]);
    removeInvalid("difficulty", ["EASY", "MEDIUM", "HARD"]);
    removeInvalid("progress", ["NOT_STARTED", "IN_PROGRESS", "PASSED"]);
    removeInvalid("purpose", ["EXAMPLE", "GRADE"]);
    removeInvalid("scope_kind", ["STANDALONE", "CHAPTER", "LESSON", "QUIZ"]);
    for (const key of ["page", "history_page"]) {
      if (!validPageValue(next.get(key))) {
        next.delete(key);
        changed = true;
      }
    }
    if (next.get("view") === "record" && !next.has("run")) {
      next.delete("view");
      changed = true;
    }
    if (changed) {
      const value = next.toString();
      navigate({ pathname: "/code", search: value ? `?${value}` : "" }, { replace: true });
    }
  }, [location.search, navigate]);

  useEffect(() => setQueryDraft(bankQuery), [bankQuery]);
  useEffect(() => setHistoryQueryDraft(historyQuery), [historyQuery]);

  const updateSearch = useCallback((update: (next: URLSearchParams) => void, replace = true) => {
    const next = new URLSearchParams(location.search);
    update(next);
    const value = next.toString();
    navigate({ pathname: "/code", search: value ? `?${value}` : "" }, { replace });
  }, [location.search, navigate]);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setRunnerReason("正在检查真实 runner…");
    void getRunnerStatus().then((status) => {
      if (!active) return;
      setRunnerAvailable(status.available);
      setRunnerReason(status.reason);
    }).catch((caught) => {
      if (!active) return;
      setRunnerAvailable(false);
      setRunnerReason(errorMessage(caught, "无法读取真实 runner 状态"));
    });
    return () => {
      active = false;
      controller.abort();
    };
  }, [stage, userId]);

  useEffect(() => {
    if (workspaceMode || tab === "history" || !stage) return undefined;
    const controller = new AbortController();
    let active = true;
    setBankLoading(true);
    setBankError("");
    setFavoriteError("");
    void listCodeTasks({
      q: bankQuery,
      category: category || undefined,
      difficulty: difficulty || undefined,
      progress: progress || undefined,
      favorite_only: tab === "favorites",
      limit: PAGE_SIZE,
      offset: (bankPage - 1) * PAGE_SIZE,
      signal: controller.signal,
    }).then((response) => {
      if (!active) return;
      setTasks(response.items);
      setTaskTotal(response.total);
      setFacets(response.facets);
      const lastPage = Math.max(1, Math.ceil(response.total / PAGE_SIZE));
      if (bankPage > lastPage) {
        updateSearch((next) => {
          if (lastPage > 1) next.set("page", String(lastPage));
          else next.delete("page");
        });
      }
    }).catch((caught) => {
      if (active && !controller.signal.aborted) setBankError(errorMessage(caught, "题库暂时无法读取"));
    }).finally(() => { if (active) setBankLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [bankAttempt, bankPage, bankQuery, category, difficulty, progress, stage, tab, updateSearch, userId, workspaceMode]);

  useEffect(() => {
    if (tab !== "history" || historyDetailMode || !stage) return undefined;
    const controller = new AbortController();
    let active = true;
    setHistoryLoading(true);
    setHistoryError("");
    void listCodeRuns({
      q: historyQuery,
      task_id: params.get("task_id") ?? undefined,
      purpose: purpose === "EXAMPLE" || purpose === "GRADE" ? purpose : undefined,
      scope_kind: ["STANDALONE", "CHAPTER", "LESSON", "QUIZ"].includes(scopeKind)
        ? scopeKind as "STANDALONE" | "CHAPTER" | "LESSON" | "QUIZ"
        : undefined,
      limit: PAGE_SIZE,
      offset: (historyPage - 1) * PAGE_SIZE,
      signal: controller.signal,
    }).then((response) => {
      if (!active) return;
      setHistoryRows(response.items);
      setHistoryTotal(response.total);
      const lastPage = Math.max(1, Math.ceil(response.total / PAGE_SIZE));
      if (historyPage > lastPage) {
        updateSearch((next) => {
          if (lastPage > 1) next.set("history_page", String(lastPage));
          else next.delete("history_page");
        });
      }
    }).catch((caught) => {
      if (active && !controller.signal.aborted) setHistoryError(errorMessage(caught, "练习记录暂时无法读取"));
    }).finally(() => { if (active) setHistoryLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [historyAttempt, historyDetailMode, historyPage, historyQuery, params, purpose, scopeKind, stage, tab, updateSearch, userId]);

  useEffect(() => {
    if (!historyDetailMode || !runParam) return undefined;
    const controller = new AbortController();
    let active = true;
    setDetail(null);
    setDetailLoading(true);
    setDetailError("");
    void getCodeRun(runParam, controller.signal).then((response) => {
      if (active) setDetail(response);
    }).catch((caught) => {
      if (active && !controller.signal.aborted) setDetailError(errorMessage(caught, "历史记录无法读取"));
    }).finally(() => { if (active) setDetailLoading(false); });
    return () => { active = false; controller.abort(); };
  }, [historyDetailMode, runParam, stage, userId]);

  useEffect(() => {
    if (!workspaceMode || !taskId || !stage) {
      loadedWorkspaceRef.current = "";
      setWorkspaceTask(null);
      setWorkspaceDraft(null);
      setWorkspaceRun(null);
      setWorkspaceError("");
      return undefined;
    }
    if (loadedWorkspaceRef.current === loadedWorkspaceKey && workspaceTask && workspaceDraft) {
      return undefined;
    }
    loadedWorkspaceRef.current = loadedWorkspaceKey;
    const controller = new AbortController();
    let active = true;
    setWorkspaceTask(null);
    setWorkspaceDraft(null);
    setWorkspaceRun(null);
    setWorkspaceLoading(true);
    setWorkspaceError("");
    void (async () => {
      try {
        const requestedRun = runParam ? await getCodeRun(runParam, controller.signal) : null;
        if (requestedRun && requestedRun.run.task_id !== taskId) {
          throw new Error("运行记录与当前题目不匹配，已停止展示结果。");
        }
        const restoreRun = restoreParam && restoreParam !== runParam
          ? await getCodeRun(restoreParam, controller.signal)
          : null;
        if (restoreRun && restoreRun.run.task_id !== taskId) {
          throw new Error("历史快照与当前题目不匹配，无法恢复。");
        }
        const selectedRevision = revisionParam
          ? Number(revisionParam)
          : requestedRun?.run.task_revision;
        const selected = await getCodeTask(taskId, selectedRevision, controller.signal);
        if (
          requestedRun &&
          (requestedRun.run.task_id !== selected.task_id || requestedRun.run.task_revision !== selected.revision)
        ) {
          throw new Error("运行记录与当前题目版本不匹配，已停止展示结果。");
        }
        const savedDraft = await getCodeDraft(selected.task_id, selected.revision, { kind: "STANDALONE" }, controller.signal);
        if (!active) return;
        setWorkspaceTask(selected);
        setWorkspaceDraft(savedDraft);
        setWorkspaceRun(restoreRun ?? requestedRun);
      } catch (caught) {
        if (active && !controller.signal.aborted) setWorkspaceError(errorMessage(caught, "无法打开这道编程题"));
      } finally {
        if (active) setWorkspaceLoading(false);
      }
    })();
      return () => { active = false; controller.abort(); };
  }, [loadedWorkspaceKey, revisionParam, runParam, restoreParam, stage, taskId, userId, workspaceDraft, workspaceMode, workspaceTask]);

  useEffect(() => {
    if (!workspaceMode || !taskId || !runParam) return undefined;
    const controller = new AbortController();
    let active = true;
    void getCodeRun(runParam, controller.signal).then((response) => {
      if (!active) return;
      if (
        response.run.task_id !== taskId ||
        (revisionParam && response.run.task_revision !== Number(revisionParam))
      ) {
        setWorkspaceRun(null);
        setWorkspaceError("运行记录与当前题目版本不匹配，已停止展示结果。");
        return;
      }
      setWorkspaceRun(response);
      setWorkspaceError("");
    }).catch((caught) => {
      if (active && !controller.signal.aborted) setWorkspaceError(errorMessage(caught, "无法读取运行记录"));
    });
    return () => { active = false; controller.abort(); };
  }, [revisionParam, runParam, taskId, workspaceMode]);

  function setTab(nextTab: Tab) {
    updateSearch((next) => {
      next.set("tab", nextTab);
      next.delete("task");
      next.delete("revision");
      next.delete("run");
      next.delete("view");
      next.delete("restore_run");
      next.delete("page");
      next.delete("history_page");
      if (nextTab !== "history") next.delete("task_id");
    });
  }

  function openTask(task: CodeTask) {
    updateSearch((next) => {
      next.set("task", task.task_id);
      next.set("revision", String(task.revision));
      next.delete("run");
      next.delete("view");
      next.delete("restore_run");
    }, false);
  }

  function backToBank() {
    updateSearch((next) => {
      next.delete("task");
      next.delete("revision");
      next.delete("run");
      next.delete("view");
      next.delete("restore_run");
      if (!next.has("tab")) next.set("tab", "bank");
    });
  }

  function returnToPreviousPage() {
    const historyIndex = window.history.state?.idx;
    if (typeof historyIndex === "number" && historyIndex > 0) {
      navigate(-1);
      return;
    }

    if (document.referrer) {
      const previous = new URL(document.referrer);
      const previousPath = `${previous.pathname}${previous.search}`;
      if (previous.origin === window.location.origin && previousPath !== `${location.pathname}${location.search}`) {
        navigate(previousPath);
        return;
      }
    }
    navigate("/workbench");
  }

  function openHistory() {
    const currentTaskId = taskId;
    updateSearch((next) => {
      next.set("tab", "history");
      next.delete("task");
      next.delete("revision");
      next.delete("run");
      next.delete("view");
      next.delete("restore_run");
      next.delete("page");
      if (currentTaskId) next.set("task_id", currentTaskId);
    });
  }

  function openHistoryDetail(runId: string) {
    updateSearch((next) => {
      next.set("tab", "history");
      next.set("view", "record");
      next.set("run", runId);
      next.delete("task");
      next.delete("revision");
      next.delete("restore_run");
    }, false);
  }

  const runStarted = useCallback((runId: string) => {
    updateSearch((next) => next.set("run", runId));
  }, [updateSearch]);

  async function continueFromHistory(restoreSnapshot: boolean) {
    if (!detail) return;
    try {
      const current = await getCodeTask(detail.run.task_id);
      if (restoreSnapshot && current.revision !== detail.run.task_revision) {
        setDetailError("这份历史代码属于已归档版本，只能只读查看或复制；请先从当前题目版本继续练习。");
        return;
      }
      updateSearch((next) => {
        next.set("task", current.task_id);
        next.set("revision", String(current.revision));
        if (restoreSnapshot) next.set("restore_run", detail.run.id);
        else next.delete("restore_run");
        next.delete("view");
        next.delete("run");
        next.set("tab", "bank");
      }, false);
    } catch (caught) {
      setDetailError(errorMessage(caught, "无法打开当前版本的题目"));
    }
  }

  async function toggleFavorite(task: CodeTask) {
    if (favoritePending) return;
    setFavoritePending(task.task_id);
    setFavoriteError("");
    try {
      if (task.is_favorite) await unfavoriteCodeTask(task.task_id);
      else await favoriteCodeTask(task.task_id);
      setBankAttempt((attempt) => attempt + 1);
    } catch (caught) {
      setFavoriteError(errorMessage(caught, "收藏状态未保存，请重试。"));
    } finally {
      setFavoritePending(null);
    }
  }

  if (workspaceMode) {
    if (workspaceLoading) return <main className="codelab-page"><CodeLabBackButton onClick={returnToPreviousPage} /><p role="status">正在读取题目和独立练习草稿…</p></main>;
    if (workspaceError || !workspaceTask || !workspaceDraft) {
      return <main className="codelab-page"><CodeLabBackButton onClick={returnToPreviousPage} /><h1>无法打开这道题</h1><p className="codelab-error" role="alert">{workspaceError || "题目暂时无法读取"}</p><button type="button" className="secondary" onClick={backToBank}>返回题库</button></main>;
    }
    return (
      <CodeLabWorkspace
        key={`${workspaceTask.task_id}:${workspaceTask.revision}`}
        task={workspaceTask}
        draft={workspaceDraft}
        initialRun={workspaceRun?.run ?? null}
        runnerAvailable={runnerAvailable}
        runnerReason={runnerReason}
        userId={userId}
        onBack={backToBank}
        onPrevious={returnToPreviousPage}
        onHistory={openHistory}
        onRunStarted={runStarted}
      />
    );
  }

  if (historyDetailMode) {
    return (
      <CodeLabHistoryDetail
        detail={detail}
        loading={detailLoading}
        error={detailError}
        onBack={openHistory}
        onPrevious={returnToPreviousPage}
        onContinue={() => void continueFromHistory(false)}
        onRestore={() => void continueFromHistory(true)}
      />
    );
  }

  if (tab === "history") {
    return (
      <CodeLabHistory
        items={historyRows}
        total={historyTotal}
        offset={(historyPage - 1) * PAGE_SIZE}
        limit={PAGE_SIZE}
        loading={historyLoading}
        error={historyError}
        query={historyQueryDraft}
        taskFilter={params.get("task_id") ?? ""}
        purpose={purpose}
        scopeKind={scopeKind}
        actionError={detailError}
        onQueryChange={setHistoryQueryDraft}
        onPurpose={(value) => updateSearch((next) => { if (value) next.set("purpose", value); else next.delete("purpose"); next.delete("history_page"); })}
        onScopeKind={(value) => updateSearch((next) => { if (value) next.set("scope_kind", value); else next.delete("scope_kind"); next.delete("history_page"); })}
        onSearch={() => updateSearch((next) => { const value = historyQueryDraft.trim(); if (value) next.set("history_q", value); else next.delete("history_q"); next.delete("history_page"); })}
        onPage={(page) => updateSearch((next) => { if (page > 1) next.set("history_page", String(page)); else next.delete("history_page"); })}
        onClear={() => { setHistoryQueryDraft(""); updateSearch((next) => { next.delete("history_q"); next.delete("purpose"); next.delete("scope_kind"); next.delete("history_page"); next.delete("task_id"); }); }}
        onRetry={() => setHistoryAttempt((attempt) => attempt + 1)}
        onOpen={openHistoryDetail}
        onTab={setTab}
        onPrevious={returnToPreviousPage}
      />
    );
  }

  return (
    <CodeLabBank
      stage={stage ?? undefined}
      tab={tab}
      tasks={tasks}
      total={taskTotal}
      offset={(bankPage - 1) * PAGE_SIZE}
      limit={PAGE_SIZE}
      page={bankPage}
      query={queryDraft}
      category={category}
      difficulty={difficulty}
      progress={progress}
      categories={facets.categories}
      difficulties={facets.difficulties}
      loading={bankLoading}
      error={bankError}
      favoritePending={favoritePending}
      actionError={favoriteError}
      onQueryChange={setQueryDraft}
      onSearch={() => updateSearch((next) => { const value = queryDraft.trim(); if (value) next.set("q", value); else next.delete("q"); next.delete("page"); })}
      onCategory={(value) => updateSearch((next) => { if (value) next.set("category", value); else next.delete("category"); next.delete("page"); })}
      onDifficulty={(value) => updateSearch((next) => { if (value) next.set("difficulty", value); else next.delete("difficulty"); next.delete("page"); })}
      onProgress={(value) => updateSearch((next) => { if (value) next.set("progress", value); else next.delete("progress"); next.delete("page"); })}
      onPage={(page) => updateSearch((next) => { if (page > 1) next.set("page", String(page)); else next.delete("page"); })}
      onClear={() => { setQueryDraft(""); updateSearch((next) => { next.delete("q"); next.delete("category"); next.delete("difficulty"); next.delete("progress"); next.delete("page"); }); }}
      onRetry={() => setBankAttempt((attempt) => attempt + 1)}
      onToggleFavorite={(task) => void toggleFavorite(task)}
      onOpenTask={openTask}
      onTab={setTab}
      onPrevious={returnToPreviousPage}
    />
  );
}
