import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../identity/api";
import { navigate } from "../identity/session";
import { getEvidenceDetail, getNextStep, postFeedback, refreshNextStep } from "./api";
import type { FeedbackDTO, NextStepDTO, NextStepItem } from "./types";
import { KIND_LABEL, actionHref, actionLabel } from "./types";
import "./learning-next.css";

/**
 * /learn — the single next step (T19).
 *
 * The page renders exactly what the server decided: reason, source, the
 * evidence it used and the rule version. It never invents a statistic, never
 * shows a percentage or a ranking, and when the projection is behind it says so
 * instead of silently showing stale advice.
 */

function messageOf(caught: unknown, fallback: string): string {
  if (caught instanceof ApiError) {
    const detail = caught.message.replace(/^[A-Z_]+:\s*/, "");
    if (caught.message.includes("RECOMMENDATION_FEEDBACK_CONFLICT")) {
      return `建议状态已经更新，请刷新后再试。（${detail}）`;
    }
    return detail || fallback;
  }
  if (caught instanceof Error && caught.message) return caught.message;
  return fallback;
}

export function NextStepPage() {
  const [body, setBody] = useState<NextStepDTO | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const [showBasis, setShowBasis] = useState(false);

  const load = useCallback(async () => {
    const next = await getNextStep();
    setBody(next);
    return next;
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const next = await load();
        if (!cancelled) setBody(next);
      } catch (caught) {
        // A failed read must never fall back to a cached "advice".
        if (!cancelled && !(caught instanceof ApiError && caught.status === 401)) {
          setError(messageOf(caught, "暂时读不到下一步建议"));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  const refresh = async () => {
    setBusy("refresh");
    setError(null);
    setNotice(null);
    try {
      const next = await refreshNextStep();
      setBody(next);
      setNotice(
        next.projection
          ? next.projection.created
            ? "已按最新记录整理出新的下一步建议。"
            : "记录没有变化，建议保持不变（重复整理不会重复创建）。"
          : "已整理。",
      );
    } catch (caught) {
      setError(messageOf(caught, "整理失败，可以稍后再试"));
    } finally {
      setBusy(null);
    }
  };

  const feedbackFor = (item: NextStepItem, list: FeedbackDTO[]) =>
    list.find((entry) => entry.subject_key === item.subject_key);

  const act = async (item: NextStepItem, action: "IGNORE" | "RESTORE") => {
    setBusy(`${item.subject_key}:${action}`);
    setError(null);
    try {
      const current = feedbackFor(item, body?.feedback ?? []);
      await postFeedback(item.subject_key, action, current?.revision ?? 0);
      const next = await load();
      setBody(next);
      setNotice(action === "IGNORE" ? "已忽略这条建议；随时可以恢复。" : "已恢复这条建议。");
    } catch (caught) {
      setError(messageOf(caught, "这一步没有成功"));
      try {
        setBody(await load());
      } catch {
        /* the error above is already shown */
      }
    } finally {
      setBusy(null);
    }
  };

  /** Restore straight from the feedback list (the ALL_IGNORED card has no item). */
  const restoreSubject = async (subjectKey: string, revision: number) => {
    setBusy(`${subjectKey}:RESTORE`);
    setError(null);
    try {
      await postFeedback(subjectKey, "RESTORE", revision);
      setBody(await load());
      setNotice("已恢复这条建议。");
    } catch (caught) {
      setError(messageOf(caught, "恢复失败，可以稍后再试"));
      try {
        setBody(await load());
      } catch {
        /* the error above is already shown */
      }
    } finally {
      setBusy(null);
    }
  };

  const openEvidence = async (evidenceId: string) => {
    try {
      const detail = await getEvidenceDetail(evidenceId);
      setEvidence((current) => ({ ...current, [evidenceId]: detail.summary }));
    } catch (caught) {
      setError(messageOf(caught, "无法读取这条依据"));
    }
  };

  const renderItem = (item: NextStepItem, options: { primary: boolean }) => {
    const feedback = feedbackFor(item, body?.feedback ?? []);
    const href = actionHref(item);
    return (
      <section
        className={options.primary ? "next-card next-card-primary" : "next-card"}
        data-testid={options.primary ? "next-primary" : "next-alternative"}
        data-kind={item.kind}
        data-subject={item.subject_key}
        key={item.subject_key}
      >
        <p className="next-meta">
          <span className="next-chip" data-testid="next-kind">
            {KIND_LABEL[item.kind] ?? item.kind}
          </span>
          <span className="next-muted">规则 {item.rule_version}</span>
          {item.effect_verified ? null : (
            <span className="next-muted" data-testid="next-not-verified">
              设计规则，未验证教学效果
            </span>
          )}
        </p>
        <h2 data-testid="next-title">{item.title}</h2>
        <p data-testid="next-reason">{item.reason}</p>
        <p className="next-muted" data-testid="next-source">
          依据来源：
          {item.source.chapter_title
            ? `章节《${item.source.chapter_title}》`
            : item.source.objective_id
              ? `学习目标 ${item.source.objective_id}`
              : item.source.type === "LESSON_SESSION"
                ? "你自己的这节课"
                : String(item.source.type ?? "未知")}
          {item.source.phase ? ` · 阶段 ${item.source.phase}` : ""}
        </p>
        {item.evidence_ids.length > 0 ? (
          <details className="next-evidence" data-testid="next-evidence">
            <summary>查看依据（{item.evidence_ids.length} 条）</summary>
            <ul>
              {item.evidence_ids.map((evidenceId) => (
                <li key={evidenceId}>
                  <code>{evidenceId.slice(0, 8)}</code>
                  <button
                    type="button"
                    className="secondary"
                    data-testid={`next-evidence-open-${evidenceId}`}
                    onClick={() => void openEvidence(evidenceId)}
                  >
                    查看来源
                  </button>
                  {evidence[evidenceId] ? (
                    <span className="next-muted" data-testid="next-evidence-summary">
                      {evidence[evidenceId]}
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          </details>
        ) : (
          <p className="next-muted" data-testid="next-no-evidence">
            这条建议不含学习历史证据（来自课程目录或你自己的课堂状态）。
          </p>
        )}
        <div className="next-actions">
          {href ? (
            <button type="button" data-testid="next-action" onClick={() => navigate(href)}>
              {actionLabel(item)}
            </button>
          ) : null}
          {item.kind !== "ALL_IGNORED" && item.kind !== "NO_CONTENT" ? (
            feedback?.state === "IGNORED" ? (
              <button
                type="button"
                className="secondary"
                data-testid="next-restore"
                disabled={busy !== null}
                onClick={() => void act(item, "RESTORE")}
              >
                恢复这条建议
              </button>
            ) : (
              <button
                type="button"
                className="secondary"
                data-testid="next-ignore"
                disabled={busy !== null}
                onClick={() => void act(item, "IGNORE")}
              >
                先不看这条
              </button>
            )
          ) : null}
        </div>
      </section>
    );
  };

  if (loading) {
    return (
      <main className="next-page" data-testid="next-page">
        <p role="status">正在读取下一步建议…</p>
      </main>
    );
  }

  return (
    <main className="next-page" data-testid="next-page">
      <header className="next-header">
        <p className="next-eyebrow">下一步</p>
        <h1>现在做什么最合适</h1>
        <p className="next-muted" data-testid="next-notice">
          课堂和这里用的是同一个下一步决策；建议会随真实作答、完成状态和你的偏好变化。
        </p>
      </header>

      {error ? (
        <p className="next-error" role="alert" data-testid="next-error">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="next-ok" role="status" data-testid="next-notice-last">
          {notice}
        </p>
      ) : null}

      {body ? (
        <>
          <section className="next-card" data-testid="next-status">
            <p className="next-muted" data-testid="next-state">
              {body.snapshot_state === "CURRENT"
                ? "建议已按最新记录整理。"
                : "建议投影还没跟上最新记录。"}
              {body.cold_start ? "（还没有你的真实学习记录）" : ""}
            </p>
            {body.needs_refresh ? (
              <p data-testid="next-needs-refresh">
                有新的学习记录还没整理；整理只做去重归档，不会凭空生成结论。
              </p>
            ) : null}
            <div className="next-actions">
              <button
                type="button"
                data-testid="next-refresh"
                disabled={busy === "refresh"}
                onClick={() => void refresh()}
              >
                {busy === "refresh" ? "正在整理…" : "重新整理建议"}
              </button>
              <button
                type="button"
                className="secondary"
                data-testid="next-toggle-basis"
                onClick={() => setShowBasis((value) => !value)}
              >
                {showBasis ? "收起判断依据" : "查看判断依据"}
              </button>
              <button
                type="button"
                className="secondary"
                data-testid="next-open-growth"
                onClick={() => navigate("/growth")}
              >
                打开成长记录
              </button>
            </div>
            {showBasis ? (
              <ul className="next-basis" data-testid="next-basis">
                <li>学段 {body.basis.stage} · 年级 {body.basis.grade ?? "未填"}</li>
                <li>真实作答 {body.basis.real_answers} 次（提示/跳过不算掌握）</li>
                <li>使用的证据 {body.basis.evidence_ids.length} 条 · 已确认记忆 {body.basis.active_memory_ids.length} 条</li>
                <li>规则 {body.basis.rule_version} · 阈值 {body.basis.thresholds_version}（未验证效果）</li>
              </ul>
            ) : null}
          </section>

          {renderItem(body.primary, { primary: true })}

          {body.alternatives.length > 0 ? (
            <section data-testid="next-alternatives">
              <h2 className="next-section-title">其它可选内容</h2>
              {body.alternatives.map((item) => renderItem(item, { primary: false }))}
            </section>
          ) : null}

          {body.feedback.length > 0 ? (
            <section className="next-card" data-testid="next-feedback-list">
              <h2>我忽略过的建议</h2>
              <ul className="next-muted">
                {body.feedback.map((entry) => (
                  <li key={entry.subject_key} data-testid="next-feedback-item" data-state={entry.state}>
                    <span>
                      {entry.subject_key} · {entry.state === "IGNORED" ? "已忽略" : "已恢复"} · 修订{" "}
                      {entry.revision}
                    </span>
                    {entry.state === "IGNORED" ? (
                      <button
                        type="button"
                        className="secondary"
                        data-testid="next-feedback-restore"
                        disabled={busy !== null}
                        onClick={() => void restoreSubject(entry.subject_key, entry.revision)}
                      >
                        恢复这条建议
                      </button>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <ul className="next-notes" data-testid="next-honest-notes">
            {body.honest_notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </>
      ) : null}

      <footer className="next-footer">
        <p className="next-muted">
          建议属于你自己的账号；换账号不会看到别人的学习记录。
        </p>
      </footer>
    </main>
  );
}
