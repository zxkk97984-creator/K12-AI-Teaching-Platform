import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { useBeforeUnload, useBlocker, useLocation, useNavigate, type BlockerFunction } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import { ApiError } from "../identity/api";
import {
  cancelCodeRun,
  createCodeRun,
  getCodeDraft,
  getCodeRun,
  requestCodeFeedback,
  saveCodeDraft,
  type CodeWorkspaceScope,
} from "./api";
import { CodeEditor } from "./CodeEditor";
import { CodeLabBackButton } from "./CodeLabBackButton";
import { CodeTaskProblem } from "./CodeTaskProblem";
import { WorkspaceSplitter } from "./WorkspaceSplitter";
import type { CodeDraft, CodeRun, CodeTask } from "./types";

type Props = {
  task: CodeTask;
  draft: CodeDraft;
  initialRun: CodeRun | null;
  runnerAvailable: boolean;
  runnerReason: string;
  userId: string;
  onBack: () => void;
  onPrevious: () => void;
  onHistory: () => void;
  onRunStarted: (runId: string) => void;
};

type Pane = "problem" | "code" | "result";
type Purpose = "EXAMPLE" | "GRADE";
type SaveStatus = "saved" | "unsaved" | "saving" | "failed" | "conflict";
type Recovery = { code: string; baseRevision: number; updatedAt: string };

const SCOPE: CodeWorkspaceScope = { kind: "STANDALONE" };

function recoveryKey(userId: string, task: CodeTask): string {
  return `k12.codelab.recovery.${userId}.${task.task_id}.r${task.revision}.standalone`;
}

function labelForStatus(status: string): string {
  const labels: Record<string, string> = {
    QUEUED: "等待运行",
    RUNNING: "正在运行",
    SUCCEEDED: "代码执行完成",
    FAILED: "代码执行异常",
    TIMEOUT: "运行超时",
    OUTPUT_LIMIT: "输出超过限制",
    UNAVAILABLE: "运行环境不可用",
    SYSTEM_ERROR: "执行服务异常，未形成判分",
    CANCELLED: "已取消",
  };
  return labels[status] ?? status;
}

function formatOutput(value: unknown): string {
  if (typeof value === "string") return JSON.stringify(value);
  return JSON.stringify(value, null, 2) ?? "null";
}

function RunPoller({
  run,
  onUpdate,
  onError,
}: {
  run: CodeRun | null;
  onUpdate: (requestedRunId: string, run: CodeRun) => void;
  onError: (message: string) => void;
}) {
  const updateRef = useRef(onUpdate);
  const errorRef = useRef(onError);
  updateRef.current = onUpdate;
  errorRef.current = onError;

  useEffect(() => {
    if (!run || !["QUEUED", "RUNNING"].includes(run.status)) return undefined;
    let cancelled = false;
    let timer = 0;
    const poll = async () => {
      await new Promise<void>((resolve) => {
        timer = window.setTimeout(resolve, 800);
      });
      if (cancelled) return;
      try {
        const next = await getCodeRun(run.id);
        if (cancelled) return;
        updateRef.current(run.id, next.run);
        if (["QUEUED", "RUNNING"].includes(next.run.status)) void poll();
      } catch (caught) {
        if (!cancelled) errorRef.current(caught instanceof Error ? caught.message : "读取运行状态失败");
      }
    };
    void poll();
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [run?.id, run?.status]);
  return null;
}

export function CodeLabWorkspace({
  task,
  draft,
  initialRun,
  runnerAvailable,
  runnerReason,
  userId,
  onBack,
  onPrevious,
  onHistory,
  onRunStarted,
}: Props) {
  const location = useLocation();
  const navigate = useNavigate();
  const [code, setCode] = useState(draft.code);
  const [savedCode, setSavedCode] = useState(draft.code);
  const [draftRevision, setDraftRevision] = useState(draft.revision_number ?? 0);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");
  const [savedAt, setSavedAt] = useState<string | null>(draft.updated_at);
  const [conflictDraft, setConflictDraft] = useState<CodeDraft | null>(null);
  const [saveError, setSaveError] = useState("");
  const [recovery, setRecovery] = useState<Recovery | null>(null);
  const [recoveryReady, setRecoveryReady] = useState(false);
  const [storageAvailable, setStorageAvailable] = useState(true);
  const [examplesRun, setExamplesRun] = useState<CodeRun | null>(
    initialRun?.purpose === "EXAMPLE" ? initialRun : null,
  );
  const [gradeRun, setGradeRun] = useState<CodeRun | null>(
    initialRun?.purpose === "GRADE" ? initialRun : null,
  );
  const initialRunRef = useRef(initialRun?.id ?? null);
  const [activeResult, setActiveResult] = useState<Purpose>(initialRun?.purpose ?? "EXAMPLE");
  const [busyPurpose, setBusyPurpose] = useState<Purpose | null>(null);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [feedbackError, setFeedbackError] = useState("");
  const [runError, setRunError] = useState("");
  const [mobilePane, setMobilePane] = useState<Pane>("problem");
  const [isMobile, setIsMobile] = useState(() => window.matchMedia("(max-width: 1023px)").matches);
  const [problemPercent, setProblemPercent] = useState(38);
  const [resultPercent, setResultPercent] = useState(30);
  const [resultExpanded, setResultExpanded] = useState(true);
  const [focusMode, setFocusMode] = useState(false);
  const focusButtonRef = useRef<HTMLButtonElement>(null);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const rightRef = useRef<HTMLDivElement>(null);
  const submittingRef = useRef(false);
  const overwritingRef = useRef(false);
  const [cancelBusy, setCancelBusy] = useState(false);
  const latestCode = useRef(code);
  const savedCodeRef = useRef(savedCode);
  const draftRevisionRef = useRef(draftRevision);
  const savingRef = useRef<Promise<boolean> | null>(null);
  const hasUnsavedChanges = code !== savedCode || saveStatus === "saving" || saveStatus === "conflict";
  latestCode.current = code;
  savedCodeRef.current = savedCode;
  draftRevisionRef.current = draftRevision;

  useEffect(() => {
    const media = window.matchMedia("(max-width: 1023px)");
    const update = () => setIsMobile(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!focusMode) return;
    const exitOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      event.preventDefault();
      event.stopPropagation();
      setFocusMode(false);
      focusButtonRef.current?.focus();
    };
    document.addEventListener("keydown", exitOnEscape);
    return () => document.removeEventListener("keydown", exitOnEscape);
  }, [focusMode]);

  useEffect(() => {
    if (!initialRun || initialRunRef.current === initialRun.id) return;
    initialRunRef.current = initialRun.id;
    if (initialRun.purpose === "EXAMPLE") setExamplesRun(initialRun);
    else setGradeRun(initialRun);
    setActiveResult(initialRun.purpose ?? "EXAMPLE");
  }, [initialRun]);

  useEffect(() => {
    const key = recoveryKey(userId, task);
    try {
      const raw = window.sessionStorage.getItem(key);
      if (raw) {
        const parsed = JSON.parse(raw) as Recovery;
        if (
          typeof parsed.code === "string" &&
          Number.isInteger(parsed.baseRevision) &&
          typeof parsed.updatedAt === "string" &&
          parsed.code !== draft.code
        ) {
          setRecovery(parsed);
        } else {
          window.sessionStorage.removeItem(key);
        }
      }
    } catch {
      setStorageAvailable(false);
    } finally {
      setRecoveryReady(true);
    }
  }, [draft.code, task, userId]);

  useEffect(() => {
    if (!recoveryReady || recovery) return;
    const key = recoveryKey(userId, task);
    try {
      if (code !== savedCode) {
        const value: Recovery = {
          code,
          baseRevision: draftRevision,
          updatedAt: new Date().toISOString(),
        };
        window.sessionStorage.setItem(key, JSON.stringify(value));
      } else {
        window.sessionStorage.removeItem(key);
      }
    } catch {
      setStorageAvailable(false);
    }
  }, [code, draftRevision, recovery, recoveryReady, savedCode, task, userId]);

  const saveLatest = useCallback(async (): Promise<boolean> => {
    if (conflictDraft) return false;
    if (savingRef.current) {
      const previous = await savingRef.current;
      if (!previous) return false;
      if (savedCodeRef.current === latestCode.current) return true;
    }
    const snapshot = latestCode.current;
    if (snapshot === savedCodeRef.current) return true;
    setSaveStatus("saving");
    setSaveError("");
    const pending = (async () => {
      try {
        const response = await saveCodeDraft(
          task.task_id,
          task.revision,
          snapshot,
          undefined,
          SCOPE,
          draftRevisionRef.current,
        );
        draftRevisionRef.current = response.revision_number ?? draftRevisionRef.current;
        savedCodeRef.current = snapshot;
        setSavedAt(response.updated_at);
        setDraftRevision(draftRevisionRef.current);
        setSavedCode(snapshot);
        setSaveStatus(latestCode.current === snapshot ? "saved" : "unsaved");
        return true;
      } catch (caught) {
        const message = caught instanceof Error ? caught.message : "保存草稿失败";
        setSaveError(message);
        if (caught instanceof ApiError && caught.status === 409) {
          try {
            const latest = await getCodeDraft(task.task_id, task.revision, { kind: "STANDALONE" });
            setConflictDraft(latest);
          } catch {
            setConflictDraft(null);
          }
          setSaveStatus("conflict");
        } else {
          setSaveStatus("failed");
        }
        return false;
      }
    })();
    savingRef.current = pending;
    const ok = await pending;
    if (savingRef.current === pending) savingRef.current = null;
    if (ok && savedCodeRef.current !== latestCode.current) return saveLatest();
    return ok;
  }, [conflictDraft, task.revision, task.task_id]);

  useEffect(() => {
    if (!hasUnsavedChanges || conflictDraft || saveStatus === "failed") return undefined;
    const timer = window.setTimeout(() => void saveLatest(), 1000);
    return () => window.clearTimeout(timer);
  }, [code, conflictDraft, hasUnsavedChanges, saveLatest, saveStatus]);

  const shouldBlock = useCallback<BlockerFunction>(
    ({ currentLocation, nextLocation }) => {
      if (!hasUnsavedChanges) return false;
      const current = new URLSearchParams(currentLocation.search);
      const next = new URLSearchParams(nextLocation.search);
      const sameWorkspace =
        currentLocation.pathname === nextLocation.pathname &&
        currentLocation.pathname === "/code" &&
        current.get("task") === next.get("task") &&
        current.get("revision") === next.get("revision") &&
        current.get("view") === next.get("view");
      return !sameWorkspace;
    },
    [hasUnsavedChanges],
  );
  const blocker = useBlocker(shouldBlock);
  const blockerRef = useRef(blocker);
  const saveLatestRef = useRef(saveLatest);
  blockerRef.current = blocker;
  saveLatestRef.current = saveLatest;
  const blockedLocationKey = blocker.state === "blocked" ? blocker.location.key : null;
  useBeforeUnload((event) => {
    if (!hasUnsavedChanges) return;
    event.preventDefault();
    event.returnValue = "";
  });

  useEffect(() => {
    if (!blockedLocationKey) return;
    let active = true;
    const currentBlocker = () => {
      const current = blockerRef.current;
      return active && current.state === "blocked" && current.location.key === blockedLocationKey ? current : null;
    };
    const leave = async () => {
      const saveBeforeLeave = window.confirm("当前代码还没有同步到服务器。确定先保存并离开吗？取消会留在当前页面。" );
      if (!saveBeforeLeave) {
        currentBlocker()?.reset();
        return;
      }
      const saved = await saveLatestRef.current();
      const current = currentBlocker();
      if (!current) return;
      if (saved) {
        current.proceed();
      } else if (window.confirm("草稿未保存。确定放弃未保存修改并离开吗？")) {
        current.proceed();
      } else {
        current.reset();
      }
    };
    void leave();
    return () => { active = false; };
  }, [blockedLocationKey]);

  const applyServerDraft = () => {
    if (!conflictDraft) return;
    setCode(conflictDraft.code);
    latestCode.current = conflictDraft.code;
    savedCodeRef.current = conflictDraft.code;
    draftRevisionRef.current = conflictDraft.revision_number ?? 0;
    setSavedCode(conflictDraft.code);
    setSavedAt(conflictDraft.updated_at);
    setDraftRevision(draftRevisionRef.current);
    setConflictDraft(null);
    setSaveStatus("saved");
    setSaveError("");
  };

  const overwriteServerDraft = async () => {
    if (!conflictDraft || overwritingRef.current) return;
    const confirmed = window.confirm("将使用当前编辑内容覆盖服务器上的新草稿。继续吗？");
    if (!confirmed) return;
    overwritingRef.current = true;
    setSaveStatus("saving");
    const snapshot = latestCode.current;
    try {
      const response = await saveCodeDraft(
        task.task_id,
        task.revision,
        snapshot,
        undefined,
        SCOPE,
        conflictDraft.revision_number ?? 0,
      );
      draftRevisionRef.current = response.revision_number ?? 0;
      savedCodeRef.current = snapshot;
      setSavedCode(snapshot);
      setSavedAt(response.updated_at);
      setDraftRevision(draftRevisionRef.current);
      setConflictDraft(null);
      setSaveStatus(latestCode.current === snapshot ? "saved" : "unsaved");
      setSaveError("");
    } catch (caught) {
      setSaveError(caught instanceof Error ? caught.message : "覆盖保存失败");
      setSaveStatus("conflict");
    } finally {
      overwritingRef.current = false;
    }
  };

  const exampleRunning = examplesRun ? ["QUEUED", "RUNNING"].includes(examplesRun.status) : false;
  const gradeRunning = gradeRun ? ["QUEUED", "RUNNING"].includes(gradeRun.status) : false;
  const anyRunning = exampleRunning || gradeRunning;

  const updateRun = useCallback((next: CodeRun) => {
    if (next.purpose === "EXAMPLE") setExamplesRun(next);
    else setGradeRun(next);
  }, []);

  const updatePolledRun = useCallback((requestedRunId: string, next: CodeRun) => {
    if (next.id !== requestedRunId) return;
    const update = (previous: CodeRun | null) => {
      if (!previous || previous.id !== requestedRunId) return previous;
      if (["SUCCEEDED", "FAILED", "TIMEOUT", "OUTPUT_LIMIT", "UNAVAILABLE", "SYSTEM_ERROR", "CANCELLED"].includes(previous.status)) {
        return previous;
      }
      return next;
    };
    if (next.purpose === "EXAMPLE") setExamplesRun(update);
    else setGradeRun(update);
  }, []);

  async function submitRun(purpose: Purpose) {
    if (!runnerAvailable || submittingRef.current || anyRunning || conflictDraft) return;
    submittingRef.current = true;
    setBusyPurpose(purpose);
    setRunError("");
    setResultExpanded(true);
    setActiveResult(purpose);
    try {
      if (!(await saveLatest())) {
        setRunError("草稿尚未成功保存，请先解决保存问题，再运行这份代码。");
        return;
      }
      const response = await createCodeRun(
        task.task_id, task.revision, latestCode.current, crypto.randomUUID(),
        undefined, purpose, SCOPE,
      );
      updateRun(response.run);
      onRunStarted(response.run.id);
      setMobilePane("result");
    } catch (caught) {
      setRunError(caught instanceof Error ? caught.message : "提交运行失败");
    } finally {
      submittingRef.current = false;
      setBusyPurpose(null);
    }
  }

  async function cancelRun() {
    const run = examplesRun && exampleRunning ? examplesRun : gradeRun && gradeRunning ? gradeRun : null;
    if (!run || cancelBusy) return;
    setCancelBusy(true);
    setRunError("");
    try {
      const response = await cancelCodeRun(run.id);
      updateRun(response.run);
    } catch (caught) {
      setRunError(caught instanceof Error ? caught.message : "取消请求失败");
    } finally {
      setCancelBusy(false);
    }
  }

  async function requestFeedback() {
    if (!gradeRun?.feedback_eligible || feedbackBusy) return;
    setFeedbackBusy(true);
    setFeedbackError("");
    try {
      const response = await requestCodeFeedback(gradeRun.id);
      setGradeRun(response.run);
      if (response.run.feedback_status === "FAILED") {
        setFeedbackError(response.run.feedback?.summary ?? "AI 建议暂时不可用，可以重试。");
      } else if (response.reason) {
        setFeedbackError(response.reason);
      }
    } catch (caught) {
      setFeedbackError(caught instanceof Error ? caught.message : "AI 建议暂时不可用，可以重试。");
    } finally {
      setFeedbackBusy(false);
    }
  }

  function downloadOrCopyHistoryCode() {
    const url = new URLSearchParams(location.search);
    const restoreRun = url.get("restore_run");
    if (!restoreRun) return;
    const run = initialRun;
    if (run?.id !== restoreRun || run.task_id !== task.task_id) {
      setRunError("历史代码与当前题目版本不匹配，无法恢复。");
      return;
    }
    if (!window.confirm("将用这次历史代码替换当前独立练习草稿。原历史记录和课堂记录不会改变。继续吗？")) {
      url.delete("restore_run");
      navigate({ pathname: location.pathname, search: `?${url.toString()}` }, { replace: true });
      return;
    }
    setCode(run.code);
    latestCode.current = run.code;
    setMobilePane("code");
    url.delete("restore_run");
    navigate({ pathname: location.pathname, search: `?${url.toString()}` }, { replace: true });
  }

  useEffect(() => {
    downloadOrCopyHistoryCode();
    // The explicit restore is tied to the original, read-only run snapshot.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialRun?.id, task.task_id, task.revision]);

  const currentRun = activeResult === "EXAMPLE" ? examplesRun : gradeRun;
  const grade = gradeRun?.result?.grading;
  const scoreLabel = gradeRun?.deterministic_score == null
    ? "尚无可信分数"
    : `${gradeRun.deterministic_score} / 70`;
  const taskNeedsReview = task.is_test_fixture || task.status === "DRAFT" || task.review_status !== "HUMAN_REVIEWED";

  const saveLabel = saveStatus === "saved" ? "草稿已保存" : saveStatus === "saving" ? "正在保存草稿…" : saveStatus === "conflict" ? "检测到其他窗口修改" : saveStatus === "failed" ? "保存失败" : "有尚未保存的代码";
  const layoutStyle = { "--problem-percent": problemPercent, "--result-percent": resultPercent } as CSSProperties;

  return (
    <main className="codelab-page codelab-workspace" data-testid="codelab-workspace" data-focus-mode={focusMode} style={layoutStyle}>
      <RunPoller run={examplesRun} onUpdate={updatePolledRun} onError={setRunError} />
      <RunPoller run={gradeRun} onUpdate={updatePolledRun} onError={setRunError} />
      <header className="codelab-workspace-toolbar">
        <div className="codelab-workspace-title"><h1>{task.title}</h1><span className="codelab-difficulty">{task.catalog.difficulty === "EASY" ? "入门" : task.catalog.difficulty === "MEDIUM" ? "基础" : task.catalog.difficulty === "HARD" ? "进阶" : "未标注"}</span></div>
        <div className="codelab-header-actions">
          <span className={`codelab-runner-badge${runnerAvailable ? " is-ready" : ""}`} role="status" title={runnerReason}>{runnerAvailable ? runnerReason : "runner 不可用"}</span>
          <button
            ref={focusButtonRef}
            type="button"
            className="secondary codelab-focus-toggle"
            aria-pressed={focusMode}
            aria-keyshortcuts={focusMode ? "Escape" : undefined}
            title={focusMode ? "退出专注模式（Esc）" : "收起导航与悬浮老师，专心编程"}
            onClick={() => setFocusMode((value) => !value)}
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={focusMode ? "M9 3v6H3m12-6v6h6M9 21v-6H3m12 6v-6h6" : "M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6"} /></svg>
            {focusMode ? "退出专注" : "专注模式"}
            {focusMode ? <kbd>Esc</kbd> : null}
          </button>
          <CodeLabBackButton onClick={onPrevious} />
          <button type="button" className="secondary" onClick={onBack}>返回题库</button>
          <button type="button" className="secondary" onClick={onHistory}>本题记录</button>
        </div>
      </header>
      {taskNeedsReview ? <p className="codelab-notice codelab-review-notice" role="status">{task.is_test_fixture ? "合成练习 · 尚未人工审校" : "尚未完成人工审校"} · 正式判分依据服务端可信用例</p> : null}
      {!runnerAvailable ? <p className="codelab-error" role="alert">{runnerReason}</p> : null}
      {isMobile ? <nav className="codelab-mobile-panes" aria-label="编程工作区">
        {([["problem", "题目"], ["code", "代码"], ["result", "结果"]] as const).map(([pane, label]) => <button key={pane} type="button" aria-pressed={mobilePane === pane} onClick={() => setMobilePane(pane)}>{label}</button>)}
      </nav> : null}
      <div className="codelab-workspace-grid" ref={workspaceRef}>
        <section className="codelab-panel codelab-problem-panel" hidden={isMobile && mobilePane !== "problem"} aria-label="题目说明" data-testid="codelab-problem">
          <CodeTaskProblem task={task} />
        </section>
        {!isMobile ? <WorkspaceSplitter container={workspaceRef} axis="x" value={problemPercent} onChange={setProblemPercent} label="调整题目与编辑器宽度" min={32} max={46} /> : null}
        <div className={`codelab-workspace-right${!resultExpanded ? " is-result-collapsed" : ""}`} ref={rightRef} hidden={isMobile && mobilePane === "problem"}>
          <section className="codelab-panel codelab-code-panel" hidden={isMobile && mobilePane !== "code"} aria-label="代码编辑器" data-testid="codelab-code-pane">
            <div className="codelab-panel-heading"><p className="eyebrow">Python 编辑器</p><button type="button" className="secondary" onClick={() => { void navigator.clipboard?.writeText(code).catch(() => setRunError("无法访问剪贴板，请用编辑器快捷键复制。")); }}>复制代码</button></div>
            <CodeEditor fillParent readOnly={Boolean(recovery)} value={code} onChange={(value) => { setCode(value); setSaveStatus(value === savedCodeRef.current ? "saved" : "unsaved"); }} ariaLabel={`${task.title} 的 Python 代码`} />
          </section>
          {!isMobile && resultExpanded ? <WorkspaceSplitter container={rightRef} axis="y" reverse value={resultPercent} onChange={setResultPercent} label="调整结果面板高度" min={22} max={48} /> : null}
          <section className="codelab-panel codelab-result-panel" hidden={isMobile && mobilePane !== "result"} aria-label="运行与判题结果" data-testid="codelab-result-panel">
            <div className="codelab-panel-heading">
              <p className="eyebrow">结果 <span className="codelab-muted">{currentRun ? labelForStatus(currentRun.status) : "等待运行"}</span></p>
              {!isMobile ? <button type="button" className="secondary codelab-result-toggle" aria-expanded={resultExpanded} onClick={() => setResultExpanded((value) => !value)}>{resultExpanded ? "折叠结果" : "展开结果"}</button> : null}
            </div>
            <div className="codelab-result-tabs" role="tablist" aria-label="选择结果类型">
              <button type="button" role="tab" aria-selected={activeResult === "EXAMPLE"} onClick={() => setActiveResult("EXAMPLE")}>示例运行</button>
              <button type="button" role="tab" aria-selected={activeResult === "GRADE"} onClick={() => setActiveResult("GRADE")}>正式判题</button>
            </div>
            <div className="codelab-result-scroll" hidden={!isMobile && !resultExpanded}>
            {currentRun ? (
              <div className="codelab-result-body" data-testid={`codelab-result-${activeResult.toLowerCase()}`}>
                <p className="codelab-result-status"><strong>{labelForStatus(currentRun.status)}</strong><span>· {currentRun.code_hash === "" ? "" : `代码快照 ${currentRun.code_hash.slice(0, 12)}`}</span></p>
                {currentRun.code !== code ? <p className="codelab-notice">以下结果对应上次运行的代码快照；当前编辑内容尚未判定。</p> : null}
                {activeResult === "EXAMPLE" && currentRun.result?.error ? <p className="codelab-error" role="alert">{currentRun.result.error}</p> : null}
                {activeResult === "EXAMPLE" ? (
                  <>
                    <p>此结果只执行公开示例，不代表正式判题。</p>
                    {currentRun.result?.observations?.map((item, index) => (
                      <article className="codelab-observation" key={`${String(item.case_id)}-${index}`}>
                        <h3>示例 {index + 1} · {labelForStatus(String(item.execution_status ?? ""))}</h3>
                        {item.input !== undefined ? <dl><div><dt>输入</dt><dd><pre>{formatOutput(item.input)}</pre></dd></div><div><dt>公开预期</dt><dd><pre>{formatOutput(item.expected_output)}</pre></dd></div><div><dt>实际返回</dt><dd><pre>{formatOutput(item.actual_output)}</pre></dd></div></dl> : null}
                        {item.stdout ? <details><summary>查看标准输出</summary><pre>{String(item.stdout)}</pre></details> : null}
                        {item.stderr ? <pre>{String(item.stderr)}</pre> : null}
                      </article>
                    ))}
                  </>
                ) : (
                  <>
                    <p><strong>可信判定：{currentRun.correctness_status}（{({ PASSED: "通过", PARTIAL: "部分通过", FAILED: "未通过", NOT_VERIFIED: "未形成判分" } as Record<string, string>)[currentRun.correctness_status] ?? currentRun.correctness_status}）</strong> · 得分 {scoreLabel}</p>
                    {currentRun.result?.error ? <p className="codelab-error" role="alert">{currentRun.result.error}</p> : null}
                    {currentRun.result?.observations?.filter((item) => item.stderr || item.error).map((item, index) => <details key={`error-${index}`}><summary>执行错误 {index + 1}</summary><pre>{String(item.stderr ?? item.error)}</pre></details>)}
                    {grade?.groups?.length ? <ul className="codelab-grade-groups">{grade.groups.map((group, index) => <li key={`${String(group.id)}-${index}`}>{String(group.name ?? group.id)}：{String(group.score ?? "—")} / {String(group.max_score ?? "—")} · 通过 {String(group.passed ?? 0)} · 失败 {String(group.failed ?? 0)}</li>)}</ul> : null}
                    <div className="codelab-feedback">
                      <h3>AI 代码建议</h3>
                      {gradeRun?.feedback?.source ? <p>来源：{gradeRun.feedback.source === "KNODO" ? "Knodo" : "本地 fixture 合成反馈"} · 不改变可信成绩</p> : null}
                      {gradeRun?.feedback?.summary ? <ReactMarkdown>{gradeRun.feedback.summary}</ReactMarkdown> : <p>{gradeRun?.feedback_eligible ? "尚未请求 AI 建议。" : gradeRun?.feedback_unavailable_reason === "AI_DISABLED" ? "当前未启用 AI 反馈。" : "需要有效的正式判分结果才能请求 AI 建议。"}</p>}
                      {feedbackError ? <p className="codelab-error" role="alert">{feedbackError}</p> : null}
                      {gradeRun?.feedback_eligible ? <button type="button" className="secondary" onClick={() => void requestFeedback()} disabled={feedbackBusy || gradeRun.feedback_status === "READY"}>{feedbackBusy ? "正在请求建议…" : gradeRun.feedback_status === "FAILED" || gradeRun.feedback_status === "STALE" ? "重试 AI 建议" : gradeRun.feedback_status === "READY" ? "建议已返回" : "请求 AI 建议"}</button> : null}
                    </div>
                  </>
                )}
              </div>
            ) : (
              <div className="codelab-result-empty"><h2>{activeResult === "EXAMPLE" ? "运行公开示例" : "提交正式判题"}</h2><p>{activeResult === "EXAMPLE" ? "查看代码在公开示例下的真实运行输出。" : "提交后，服务端可信测试会给出正式判定和 70 分制成绩。"}</p></div>
            )}
            </div>
          </section>
        </div>
      </div>
      <div className="codelab-workspace-alerts" aria-label="草稿与执行提示">
        {saveError ? <p className="codelab-error" role="alert">{saveError}</p> : null}
        {runError ? <p className="codelab-error" role="alert">{runError}</p> : null}
        {!storageAvailable ? <p className="codelab-muted" role="status">本浏览器无法保留标签页恢复副本；服务端草稿仍可保存。</p> : null}
        {conflictDraft ? <div className="codelab-conflict" role="alert"><p>另一个窗口已经更新了服务器草稿。当前编辑内容仍保留。</p><button type="button" className="secondary" disabled={saveStatus === "saving"} onClick={applyServerDraft}>使用服务器版本</button><button type="button" disabled={saveStatus === "saving"} onClick={() => void overwriteServerDraft()}>用当前内容覆盖</button></div> : null}
        {recovery ? <div className="codelab-recovery" role="status"><p>本标签页发现尚未同步的代码（{new Date(recovery.updatedAt).toLocaleString()}）。</p>{recovery.baseRevision !== (draft.revision_number ?? 0) ? <p>服务器版本已变化，恢复后需要解决草稿冲突。</p> : null}<button type="button" onClick={() => {
          setCode(recovery.code); latestCode.current = recovery.code;
          if (recovery.baseRevision !== (draft.revision_number ?? 0)) { setConflictDraft(draft); setSaveStatus("conflict"); }
          else setSaveStatus("unsaved");
          setRecovery(null); setMobilePane("code");
        }}>恢复本地代码</button><button type="button" className="secondary" onClick={() => { window.sessionStorage.removeItem(recoveryKey(userId, task)); setRecovery(null); }}>使用服务器草稿</button></div> : null}
      </div>
      <footer className="codelab-workspace-actions">
        <span className="codelab-save-status" role="status" data-state={saveStatus} title={savedAt ? `保存于 ${new Date(savedAt).toLocaleString()}` : undefined}>{saveLabel}</span>
        <button type="button" className="secondary codelab-save-button" onClick={() => void saveLatest()} disabled={saveStatus === "saving" || code === savedCode}>保存草稿</button>
        <div className="codelab-actions">
          <button type="button" className="secondary" onClick={() => void submitRun("EXAMPLE")} disabled={!runnerAvailable || Boolean(busyPurpose) || anyRunning || Boolean(conflictDraft)}>{busyPurpose === "EXAMPLE" || exampleRunning ? "运行中…" : "运行示例"}</button>
          <button type="button" onClick={() => void submitRun("GRADE")} disabled={!runnerAvailable || Boolean(busyPurpose) || anyRunning || Boolean(conflictDraft)}>{busyPurpose === "GRADE" || gradeRunning ? "提交中…" : "提交判题"}</button>
          {anyRunning ? <button type="button" className="secondary" onClick={() => void cancelRun()} disabled={cancelBusy}>{cancelBusy ? "正在取消…" : "取消运行"}</button> : null}
        </div>
      </footer>
    </main>
  );
}
