import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../features/identity/api";
import { navigate } from "../../features/identity/session";
import { CodeEditor } from "../../features/codelab/CodeEditor";
import {
  cancelCodeRun,
  createCodeRun,
  getCodeDraft,
  listCodeTasks,
  requestCodeFeedback,
  saveCodeDraft,
} from "../../features/codelab/api";
import type { CodeRun, CodeTask } from "../../features/codelab/types";
import "../../features/codelab/codelab.css";

function taskFromUrl(tasks: CodeTask[]): CodeTask | null {
  const requested = new URLSearchParams(window.location.search).get("task");
  return tasks.find((task) => task.task_id === requested) ?? tasks[0] ?? null;
}

export function CodeLabPage() {
  const [tasks, setTasks] = useState<CodeTask[]>([]);
  const [task, setTask] = useState<CodeTask | null>(null);
  const [code, setCode] = useState("");
  const [run, setRun] = useState<CodeRun | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const taskNotice = useMemo(
    () => task && (task.status === "DRAFT" || task.review_status !== "HUMAN_REVIEWED")
      ? "本任务仍是本地草稿/未完成人工审校；运行结果仅用于开发验证。"
      : null,
    [task],
  );

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const body = await listCodeTasks();
        if (cancelled) return;
        setTasks(body.items);
        const selected = taskFromUrl(body.items);
        setTask(selected);
        if (selected) setCode((await getCodeDraft(selected.task_id, selected.revision)).code);
      } catch (caught) {
        if (!cancelled) setError(caught instanceof ApiError ? caught.message : "无法加载编程任务");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  async function selectTask(next: CodeTask) {
    setTask(next);
    setRun(null);
    setError(null);
    try {
      setCode((await getCodeDraft(next.task_id, next.revision)).code);
      navigate(`/code?task=${encodeURIComponent(next.task_id)}`);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "无法加载草稿");
    }
  }

  async function save() {
    if (!task) return;
    setBusy(true);
    setError(null);
    try {
      await saveCodeDraft(task.task_id, task.revision, code);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "保存草稿失败");
    } finally {
      setBusy(false);
    }
  }

  async function runCode() {
    if (!task) return;
    setBusy(true);
    setError(null);
    try {
      const response = await createCodeRun(task.task_id, task.revision, code, crypto.randomUUID());
      setRun(response.run);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "提交运行失败");
    } finally {
      setBusy(false);
    }
  }

  if (loading) return <main className="codelab-page">正在加载编程任务…</main>;
  return (
    <main className="codelab-page" data-testid="codelab-page">
      <header className="codelab-header">
        <div>
          <p className="eyebrow">CodeLab · 编程实践</p>
          <h1>把思路写成可运行的函数</h1>
          <p className="codelab-muted">运行、可信判分、AI反馈和文本课程状态彼此分开显示。</p>
        </div>
        <button type="button" className="secondary" onClick={() => navigate("/courses")}>返回课程</button>
      </header>
      {error ? <p className="codelab-error" role="alert">{error}</p> : null}
      {taskNotice ? <p className="codelab-notice" data-testid="codelab-notice">{taskNotice}</p> : null}
      <div className="codelab-layout">
        <aside className="codelab-card" aria-label="编程任务列表">
          <p className="eyebrow">任务</p>
          <div className="codelab-task-list">
            {tasks.map((item) => (
              <button
                key={`${item.task_id}:${item.revision}`}
                type="button"
                data-active={item.task_id === task?.task_id}
                onClick={() => void selectTask(item)}
              >
                <strong>{item.title}</strong>
                <span className="codelab-meta"> · r{item.revision} · {item.chapter_binding.stage}</span>
              </button>
            ))}
          </div>
        </aside>
        <section className="codelab-card" aria-label="代码编辑器">
          {task ? (
            <>
              <h2>{task.title}</h2>
              <p>{task.description}</p>
              <p className="codelab-meta">入口：{task.entrypoint} · 章节：{task.chapter_binding.course_slug}/{task.chapter_binding.chapter_slug}</p>
              <CodeEditor value={code} onChange={setCode} />
              <div className="codelab-actions">
                <button type="button" className="secondary" onClick={() => void save()} disabled={busy}>保存草稿</button>
                <button type="button" onClick={() => void runCode()} disabled={busy}>运行这份代码</button>
                {run && (run.status === "QUEUED" || run.status === "RUNNING") ? (
                  <button type="button" className="secondary" onClick={() => void cancelCodeRun(run.id)}>取消运行</button>
                ) : null}
              </div>
            </>
          ) : <p className="codelab-muted">当前没有可用任务。</p>}
        </section>
      </div>
      {run ? (
        <section className="codelab-card codelab-result" data-testid="codelab-result">
          <div className="codelab-result__head">
            <div>
              <p className="eyebrow">运行结果</p>
              <h2>{run.status}</h2>
            </div>
            <span className="codelab-meta">代码快照：{run.code_hash.slice(0, 12)}</span>
          </div>
          <p>可信正确性：{run.correctness_status} · 确定性分数：{run.deterministic_score ?? "未验证"}</p>
          <p>AI反馈：{run.feedback_status === "READY" ? "已返回（fixture）" : "未配置/未请求"}</p>
          {run.result?.observations?.map((observation, index) => (
            <div key={`${String(observation.case_id)}-${index}`}>
              <p className="codelab-meta">{String(observation.case_id)} · {String(observation.execution_status)}</p>
              {observation.stdout ? <pre>{String(observation.stdout)}</pre> : null}
              {observation.stderr ? <pre>{String(observation.stderr)}</pre> : null}
            </div>
          ))}
          <div className="codelab-actions">
            <button
              type="button"
              className="secondary"
              disabled={run.feedback_status === "READY"}
              onClick={async () => {
                const response = await requestCodeFeedback(run.id);
                setRun(response.run);
              }}
            >
              请求代码反馈
            </button>
          </div>
          {run.feedback?.summary ? <p className="codelab-notice">{run.feedback.summary}</p> : null}
        </section>
      ) : null}
    </main>
  );
}
