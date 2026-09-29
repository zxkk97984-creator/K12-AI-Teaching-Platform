import { useCallback, useEffect, useRef, useState } from "react";
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
  const [isMobile, setIsMobile] = useState(false);
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
    if (!recoveryReady) return;
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
  }, [code, draftRevision, recoveryReady, savedCode, task, userId]);

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
  useBeforeUnload((event) => {
    if (!hasUnsavedChanges) return;
    event.preventDefault();
    event.returnValue = "";
  });

  useEffect(() => {
    if (blocker.state !== "blocked") return;
    let active = true;
    const leave = async () => {
      const saveBeforeLeave = window.confirm("当前代码还没有同步到服务器。确定先保存并离开吗？取消会留在当前页面。" );
      if (!saveBeforeLeave) {
        blocker.reset();
        return;
      }
      const saved = await saveLatest();
      if (!active) return;
      if (saved) {
        blocker.proceed();
      } else if (window.confirm("草稿未保存。确定放弃未保存修改并离开吗？")) {
        blocker.proceed();
      } else {
        blocker.reset();
      }
    };
    void leave();
    return () => { active = false; };
  }, [blocker, saveLatest]);

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
    if (!conflictDraft) return;
    const confirmed = window.confirm("将使用当前编辑内容覆盖服务器上的新草稿。继续吗？");
    if (!confirmed) return;
    try {
      const response = await saveCodeDraft(
        task.task_id,
        task.revision,
        latestCode.current,
        undefined,
        SCOPE,
        conflictDraft.revision_number ?? 0,
      );
      draftRevisionRef.current = response.revision_number ?? 0;
      savedCodeRef.current = latestCode.current;
      setSavedCode(latestCode.current);
      setSavedAt(response.updated_at);
      setDraftRevision(draftRevisionRef.current);
      setConflictDraft(null);
      setSaveStatus("saved");
      setSaveError("");
    } catch (caught) {
      setSaveError(caught instanceof Error ? caught.message : "覆盖保存失败");
      setSaveStatus("conflict");
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
    if (!runnerAvailable || busyPurpose || anyRunning || conflictDraft) return;
    setRunError("");
    if (!(await saveLatest())) {
      setRunError("草稿尚未成功保存，请先解决保存问题，再运行这份代码。");
      return;
    }
    const snapshot = latestCode.current;
    setBusyPurpose(purpose);
    try {
      const response = await createCodeRun(
        task.task_id,
        task.revision,
        snapshot,
        crypto.randomUUID(),
        undefined,
        purpose,
        SCOPE,
      );
      updateRun(response.run);
      onRunStarted(response.run.id);
      setActiveResult(purpose);
      setMobilePane("result");
    } catch (caught) {
      setRunError(caught instanceof Error ? caught.message : "提交运行失败");
    } finally {
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
  const taskSourceLabel = task.is_test_fixture ? "合成练习" : taskNeedsReview ? "草稿／未完成人工审校" : "课程编程任务";

  return (
    <main className="codelab-page" data-testid="codelab-workspace">
      <RunPoller run={examplesRun} onUpdate={updatePolledRun} onError={setRunError} />
      <RunPoller run={gradeRun} onUpdate={updatePolledRun} onError={setRunError} />
      <header className="codelab-page-header">
        <div>
          <CodeLabBackButton onClick={onPrevious} />
          <p className="eyebrow">{task.chapter_binding.stage === "JUNIOR" ? "初中编程入门" : "高中编程与算法"}</p>
          <h1>{task.title}</h1>
          <p className="codelab-muted">{taskSourceLabel} · r{task.revision} · {task.catalog.tags.join(" · ")}</p>
        </div>
        <div className="codelab-header-actions">
          <button type="button" className="secondary" onClick={onHistory}>本题记录</button>
          <button type="button" className="secondary" onClick={onBack}>返回题库</button>
        </div>
      </header>
      {taskNeedsReview ? (
        <p className="codelab-notice" role="status">{task.is_test_fixture ? "合成练习内容，尚未人工审校。" : "本任务尚未完成人工审校。"} 运行使用真实 runner；正式判分只依据服务端可信用例。</p>
      ) : null}
      <p className={runnerAvailable ? "codelab-status" : "codelab-error"} role="status">{runnerReason}</p>
      {isMobile ? (
        <nav className="codelab-mobile-panes" aria-label="编程工作区">
          {([
            ["problem", "题目"],
            ["code", "代码"],
            ["result", "结果"],
          ] as const).map(([pane, label]) => (
            <button key={pane} type="button" aria-pressed={mobilePane === pane} onClick={() => setMobilePane(pane)}>
              {label}
            </button>
          ))}
        </nav>
      ) : null}
      <div className="codelab-workspace-grid">
        <section
          className="codelab-panel codelab-problem-panel"
          hidden={isMobile && mobilePane !== "problem"}
          aria-label="题目说明"
          data-testid="codelab-problem"
        >
          <div className="codelab-panel-heading">
            <p className="eyebrow">题目说明</p>
            <span className={`codelab-difficulty codelab-difficulty--${task.catalog.difficulty?.toLowerCase() ?? "unknown"}`}>
              {task.catalog.difficulty === "EASY" ? "入门" : task.catalog.difficulty === "MEDIUM" ? "基础" : task.catalog.difficulty === "HARD" ? "进阶" : "未标注难度"}
            </span>
          </div>
          <p>{task.description}</p>
          <dl className="codelab-contract">
            <div><dt>函数签名</dt><dd><code>{task.entrypoint}</code></dd></div>
            <div><dt>语言</dt><dd>Python · function-json.v1</dd></div>
          </dl>
          <section className="codelab-io-contract" aria-label="输入输出范围">
            <h2>输入与输出范围</h2>
            <details>
              <summary>查看输入字段、类型与合法范围</summary>
              <pre>{formatOutput(task.io_contract.input_schema)}</pre>
            </details>
            <details>
              <summary>查看返回值类型</summary>
              <pre>{formatOutput(task.io_contract.output_schema)}</pre>
            </details>
          </section>
          {task.course_link ? (
            <section className="codelab-course-link">
              <p className="eyebrow">关联课程</p>
              <h2>{task.course_link.course_title}</h2>
              <p>{task.course_link.chapter_title}</p>
              {task.course_link.available && task.course_link.href ? <a href={task.course_link.href}>打开关联章节</a> : <span>当前不可打开</span>}
            </section>
          ) : <p className="codelab-muted">这道题目前没有可访问的课程章节链接。</p>}
          <section className="codelab-examples" aria-label="公开示例">
            <h2>公开示例</h2>
            {task.examples.map((example, index) => (
              <details key={`${task.task_id}-example-${index}`}>
                <summary>示例 {index + 1}</summary>
                <dl>
                  <div><dt>输入</dt><dd><pre>{formatOutput(example.input)}</pre></dd></div>
                  <div><dt>预期输出</dt><dd><pre>{formatOutput(example.output)}</pre></dd></div>
                </dl>
              </details>
            ))}
          </section>
        </section>

        <div className="codelab-workspace-right">
          <section
            className="codelab-panel codelab-code-panel"
            hidden={isMobile && mobilePane !== "code"}
            aria-label="代码编辑器"
            data-testid="codelab-code-pane"
          >
            <div className="codelab-panel-heading">
              <div><p className="eyebrow">Python 编辑器</p><span className="codelab-save-status" role="status" data-state={saveStatus}>
                {saveStatus === "saved" ? `草稿已保存${savedAt ? ` · ${new Date(savedAt).toLocaleString()}` : ""}` : saveStatus === "saving" ? "正在保存草稿…" : saveStatus === "conflict" ? "检测到其他窗口修改" : saveStatus === "failed" ? "保存失败" : "有尚未保存的代码"}
              </span></div>
              <button type="button" className="secondary" onClick={() => void saveLatest()} disabled={saveStatus === "saving" || code === savedCode}>保存草稿</button>
            </div>
            <CodeEditor value={code} onChange={(value) => { setCode(value); setSaveStatus("unsaved"); }} ariaLabel={`${task.title} 的 Python 代码`} />
            <div className="codelab-actions">
              <button type="button" className="secondary" onClick={() => void submitRun("EXAMPLE")} disabled={!runnerAvailable || Boolean(busyPurpose) || anyRunning || Boolean(conflictDraft)}>
                {busyPurpose === "EXAMPLE" || exampleRunning ? "运行中…" : "运行示例"}
              </button>
              <button type="button" onClick={() => void submitRun("GRADE")} disabled={!runnerAvailable || Boolean(busyPurpose) || anyRunning || Boolean(conflictDraft)}>
                {busyPurpose === "GRADE" || gradeRunning ? "提交中…" : "提交判题"}
              </button>
              {anyRunning ? <button type="button" className="secondary" onClick={() => void cancelRun()} disabled={cancelBusy}>{cancelBusy ? "正在取消…" : "取消运行"}</button> : null}
              <button type="button" className="secondary" onClick={() => { void navigator.clipboard?.writeText(code).catch(() => setRunError("无法访问剪贴板，请用编辑器快捷键复制。")); }}>复制代码</button>
            </div>
            {saveError ? <p className="codelab-error" role="alert">{saveError}</p> : null}
            {!storageAvailable ? <p className="codelab-muted" role="status">本浏览器不允许本标签页恢复副本；服务端草稿保存仍可使用。</p> : null}
            {runError ? <p className="codelab-error" role="alert">{runError}</p> : null}
            {conflictDraft ? (
              <div className="codelab-conflict" role="alert">
                <p>另一个窗口已经更新了服务器草稿。当前编辑内容仍保留。</p>
                <button type="button" className="secondary" onClick={applyServerDraft}>使用服务器版本</button>
                <button type="button" onClick={() => void overwriteServerDraft()}>用当前内容覆盖</button>
              </div>
            ) : null}
            {recovery ? (
              <div className="codelab-recovery" role="status">
                <p>本标签页发现尚未同步的代码（{new Date(recovery.updatedAt).toLocaleString()}）。</p>
                {recovery.baseRevision !== draft.revision_number ? <p>服务器版本已变化；恢复后仍要先解决草稿冲突。</p> : null}
                <button type="button" onClick={() => { setCode(recovery.code); latestCode.current = recovery.code; setRecovery(null); setSaveStatus("unsaved"); }}>恢复本地代码</button>
                <button type="button" className="secondary" onClick={() => { window.sessionStorage.removeItem(recoveryKey(userId, task)); setRecovery(null); }}>使用服务器草稿</button>
              </div>
            ) : null}
          </section>

          <section
            className="codelab-panel codelab-result-panel"
            hidden={isMobile && mobilePane !== "result"}
            aria-label="运行与判题结果"
            data-testid="codelab-result-panel"
          >
            <div className="codelab-panel-heading">
              <div><p className="eyebrow">结果</p><span className="codelab-muted">公开运行、可信判分和 AI 建议分开展示</span></div>
              {anyRunning ? <span role="status">{labelForStatus(currentRun?.status ?? "RUNNING")}</span> : null}
            </div>
            <div className="codelab-result-tabs" role="tablist" aria-label="选择结果类型">
              <button type="button" role="tab" aria-selected={activeResult === "EXAMPLE"} onClick={() => setActiveResult("EXAMPLE")}>示例运行</button>
              <button type="button" role="tab" aria-selected={activeResult === "GRADE"} onClick={() => setActiveResult("GRADE")}>正式判题</button>
            </div>
            {currentRun ? (
              <div className="codelab-result-body" data-testid={`codelab-result-${activeResult.toLowerCase()}`}>
                <p className="codelab-result-status"><strong>{labelForStatus(currentRun.status)}</strong><span>· {currentRun.code_hash === "" ? "" : `代码快照 ${currentRun.code_hash.slice(0, 12)}`}</span></p>
                {currentRun.code !== code ? <p className="codelab-notice">以下结果对应上次运行的代码快照；当前编辑内容尚未判定。</p> : null}
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
                    <p><strong>可信判定：{currentRun.correctness_status}</strong> · 得分 {scoreLabel}</p>
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
          </section>
        </div>
      </div>
    </main>
  );
}
