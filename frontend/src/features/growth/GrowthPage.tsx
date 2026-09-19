import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../identity/api";
import { navigate } from "../identity/session";
import {
  getEvidenceDetail,
  getGrowthOverview,
  listMemories,
  postMemoryAction,
  reprojectGrowth,
} from "./api";
import type {
  EvidenceDetailDTO,
  GrowthOverviewDTO,
  MemoryAction,
  MemoryDTO,
} from "./types";
import { ACTION_LABEL, LEVEL_LABEL, MEMORY_STATUS_LABEL } from "./types";
import "./growth.css";

/**
 * Growth page (T18 K4/K6/K7/K10/K11).
 *
 * Everything shown here comes from the server's owner-scoped read model: real
 * counts, qualitative observations with the evidence they were derived from,
 * and student-owned memories. There is no mastery percentage, no streak, no
 * IQ/personality wording, and no statistic that the API did not return.
 */

function messageOf(caught: unknown, fallback: string): string {
  if (caught instanceof ApiError) {
    // The frozen envelope uses the generic 409 code, so the specific T18 code
    // travels inside the message ("MEMORY_REVISION_CONFLICT: …").
    const detail = caught.message.replace(/^[A-Z_]+:\s*/, "");
    if (caught.message.includes("MEMORY_REVISION_CONFLICT")) {
      return `这条记忆已经被更新过，请刷新后再操作。（${detail}）`;
    }
    if (caught.message.includes("MEMORY_FORGOTTEN")) {
      return `这条记忆已经遗忘，不能再修改。（${detail}）`;
    }
    return detail || fallback;
  }
  if (caught instanceof Error && caught.message) return caught.message;
  return fallback;
}

export function GrowthPage() {
  const [overview, setOverview] = useState<GrowthOverviewDTO | null>(null);
  const [memories, setMemories] = useState<MemoryDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [openEvidence, setOpenEvidence] = useState<Record<string, EvidenceDetailDTO | "loading">>({});
  const [editing, setEditing] = useState<{ id: string; value: string } | null>(null);

  const load = useCallback(async () => {
    const [body, memoryBody] = await Promise.all([getGrowthOverview(), listMemories()]);
    setOverview(body);
    setMemories(memoryBody.items);
    return body;
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const body = await load();
        if (!cancelled) setOverview(body);
      } catch (caught) {
        if (!cancelled && !(caught instanceof ApiError && caught.status === 401)) {
          setError(messageOf(caught, "无法读取成长记录"));
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  const reproject = async () => {
    setBusy("projection");
    setError(null);
    setNotice(null);
    try {
      const body = await reprojectGrowth();
      setOverview(body);
      setMemories(body.memories);
      setNotice(
        body.projection
          ? `已完成整理：新增依据 ${body.projection.evidence.inserted} 条、` +
              `观察 ${body.projection.observations.created} 条、记忆候选 ${body.projection.memories.created} 条。` +
              "（重复整理不会重复计数）"
          : "已完成整理。",
      );
    } catch (caught) {
      setError(messageOf(caught, "整理失败，请稍后再试"));
    } finally {
      setBusy(null);
    }
  };

  const act = async (memory: MemoryDTO, action: MemoryAction, extra: { statement?: string } = {}) => {
    setBusy(`${memory.id}:${action}`);
    setError(null);
    try {
      const updated = await postMemoryAction(memory.id, action, memory.revision, extra);
      setMemories((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setEditing(null);
      setNotice(`已${ACTION_LABEL[action]}：「${updated.statement}」`);
      // The overview mirrors the same facts; re-read it instead of guessing.
      setOverview(await getGrowthOverview());
    } catch (caught) {
      setError(messageOf(caught, "这一步没有成功"));
      if (caught instanceof ApiError && caught.status === 409) {
        try {
          setOverview(await getGrowthOverview());
          const refreshed = await listMemories();
          setMemories(refreshed.items);
        } catch {
          /* the error above is already shown */
        }
      }
    } finally {
      setBusy(null);
    }
  };

  const showEvidence = async (evidenceId: string) => {
    setOpenEvidence((current) => ({ ...current, [evidenceId]: "loading" }));
    try {
      const detail = await getEvidenceDetail(evidenceId);
      setOpenEvidence((current) => ({ ...current, [evidenceId]: detail }));
    } catch (caught) {
      setError(messageOf(caught, "无法读取这条依据"));
      setOpenEvidence((current) => {
        const next = { ...current };
        delete next[evidenceId];
        return next;
      });
    }
  };

  if (loading) {
    return (
      <main className="growth-page" data-testid="growth-page">
        <p role="status">正在读取成长记录…</p>
      </main>
    );
  }

  return (
    <main className="growth-page" data-testid="growth-page">
      <header className="growth-header">
        <p className="growth-eyebrow">成长</p>
        <h1>我的学习记录与依据</h1>
        <p className="growth-muted" data-testid="growth-notice">
          这里只展示服务器上真实发生过的作答与活动。记录条数不是学习效果，也不会生成掌握度百分比。
        </p>
      </header>

      {error ? (
        <p className="growth-error" role="alert" data-testid="growth-error">
          {error}
        </p>
      ) : null}
      {notice ? (
        <p className="growth-notice" role="status" data-testid="growth-notice-last">
          {notice}
        </p>
      ) : null}

      <section className="growth-card" data-testid="growth-evidence">
        <h2>证据整理</h2>
        <p className="growth-muted">{overview?.counts_not_effect_notice}</p>
        {overview?.needs_projection ? (
          <p data-testid="growth-needs-projection">
            有新的学习记录还没有整理。整理只会把已发生的事实去重归档，不会新增任意结论。
          </p>
        ) : (
          <p className="growth-muted" data-testid="growth-projection-fresh">
            已经是最新整理结果；重复整理不会改变已确认的事实。
          </p>
        )}
        <div className="growth-actions">
          <button
            type="button"
            data-testid="growth-reproject"
            disabled={busy === "projection"}
            onClick={() => void reproject()}
          >
            {busy === "projection" ? "正在整理…" : overview?.needs_projection ? "整理我的证据" : "重新整理（幂等）"}
          </button>
          <button
            type="button"
            className="secondary"
            data-testid="growth-back-lessons"
            onClick={() => navigate("/lessons")}
          >
            回到课堂
          </button>
        </div>
      </section>

      <section className="growth-card" data-testid="growth-summary">
        <h2>真实记录</h2>
        <ul className="growth-counts">
          <li data-testid="growth-real-answers">
            真实作答 <strong>{overview?.real_answers ?? 0}</strong> 次
          </li>
          <li data-testid="growth-correct-answers">
            其中答对 <strong>{overview?.correct_answers ?? 0}</strong> 次
          </li>
          <li data-testid="growth-evidence-total">
            已归档依据 <strong>{overview?.evidence_total ?? 0}</strong> 条
          </li>
        </ul>
        {overview?.insufficient_evidence ? (
          <p className="growth-muted" data-testid="growth-insufficient">
            记录还很少，仍需观察；现在不会给出任何结论。
          </p>
        ) : null}
        <p className="growth-muted">{overview?.no_percentage_notice}</p>
      </section>

      <section className="growth-card" data-testid="growth-observations">
        <h2>定性观察</h2>
        {overview && overview.observations.length > 0 ? (
          <ul className="growth-observation-list">
            {overview.observations.map((observation) => (
              <li key={observation.id} data-testid="growth-observation" data-level={observation.level}>
                <p className="growth-level">
                  <span className="growth-chip">{LEVEL_LABEL[observation.level]}</span>
                  <span className="growth-muted">规则 {observation.rule_version}</span>
                </p>
                <p data-testid="growth-statement">{observation.statement}</p>
                <p className="growth-muted" data-testid="growth-basis-counts">
                  依据：真实作答 {observation.basis.answered} 次 · 答对 {observation.basis.correct} 次 ·
                  覆盖 {observation.basis.distinct_questions} 道不同题 · 查看提示{" "}
                  {observation.basis.hints_viewed} 次
                </p>
                <p className="growth-muted">{observation.notice}</p>
                <details>
                  <summary data-testid="growth-basis-toggle">查看依据</summary>
                  <ul className="growth-evidence-list">
                    {observation.basis.evidence_ids.map((evidenceId) => {
                      const detail = openEvidence[evidenceId];
                      return (
                        <li key={evidenceId} data-testid="growth-evidence-item">
                          <code>{evidenceId.slice(0, 8)}</code>
                          <button
                            type="button"
                            className="secondary"
                            data-testid={`growth-evidence-open-${evidenceId}`}
                            onClick={() => void showEvidence(evidenceId)}
                          >
                            查看来源
                          </button>
                          {detail === "loading" ? <span className="growth-muted">读取中…</span> : null}
                          {detail && detail !== "loading" ? (
                            <span className="growth-evidence-detail" data-testid="growth-evidence-detail">
                              {detail.summary} · 来源{" "}
                              {detail.source_ref.question_id
                                ? `题目 ${String(detail.source_ref.question_id).slice(0, 8)}`
                                : String(detail.source_ref.lesson_event_kind ?? detail.source_kind)}
                              · 记录于 {detail.observed_at.slice(0, 19)}
                            </span>
                          ) : null}
                        </li>
                      );
                    })}
                  </ul>
                </details>
              </li>
            ))}
          </ul>
        ) : (
          <p className="growth-muted" data-testid="growth-observations-empty">
            还没有足够的记录可以观察；先去做一节课或一组练习，这里会出现真实依据。
          </p>
        )}
      </section>

      <section className="growth-card" data-testid="growth-memories">
        <h2>我的记忆（可随时修改或遗忘）</h2>
        <p className="growth-muted">
          只有你确认的记忆才会进入教学上下文；候选、有疑问和已遗忘都不会被使用。
        </p>
        {memories.length === 0 ? (
          <p className="growth-muted" data-testid="growth-memories-empty">
            还没有候选记忆。系统只会根据你的真实记录提出建议，而且必须由你确认。
          </p>
        ) : (
          <ul className="growth-memory-list">
            {memories.map((memory) => (
              <li
                key={memory.id}
                data-testid="growth-memory"
                data-status={memory.status}
                data-memory-id={memory.id}
              >
                <p className="growth-level">
                  <span className="growth-chip">{MEMORY_STATUS_LABEL[memory.status]}</span>
                  <span className="growth-muted">
                    修订 {memory.revision} · 注入状态{" "}
                    {memory.injection_status === "INJECTED" ? "会作为教学参考" : "不会注入"}
                  </span>
                </p>
                <p data-testid="growth-memory-statement">{memory.statement}</p>
                {memory.status === "REMOVED" && memory.local_withdrawal_notice ? (
                  <p className="growth-muted" data-testid="growth-memory-withdrawal">
                    {memory.local_withdrawal_notice}
                  </p>
                ) : (
                  <p className="growth-muted" data-testid="growth-memory-note">
                    {memory.injection_note}
                  </p>
                )}

                {editing?.id === memory.id ? (
                  <div className="growth-edit">
                    <label>
                      修改这条记忆
                      <textarea
                        value={editing.value}
                        maxLength={400}
                        data-testid="growth-memory-edit-input"
                        onChange={(event) =>
                          setEditing({ id: memory.id, value: event.target.value })
                        }
                      />
                    </label>
                    <div className="growth-actions">
                      <button
                        type="button"
                        data-testid="growth-memory-edit-save"
                        disabled={busy !== null || editing.value.trim().length < 2}
                        onClick={() => void act(memory, "EDIT", { statement: editing.value })}
                      >
                        保存修改
                      </button>
                      <button type="button" className="secondary" onClick={() => setEditing(null)}>
                        取消
                      </button>
                    </div>
                  </div>
                ) : (
                  <div className="growth-actions">
                    {memory.status !== "ACTIVE" && memory.status !== "REMOVED" ? (
                      <button
                        type="button"
                        data-testid="growth-memory-confirm"
                        disabled={busy !== null}
                        onClick={() => void act(memory, "CONFIRM")}
                      >
                        确认这条记忆
                      </button>
                    ) : null}
                    {memory.status !== "DISPUTED" && memory.status !== "REMOVED" ? (
                      <button
                        type="button"
                        className="secondary"
                        data-testid="growth-memory-dispute"
                        disabled={busy !== null}
                        onClick={() => void act(memory, "DISPUTE")}
                      >
                        我有疑问
                      </button>
                    ) : null}
                    {memory.status !== "REMOVED" ? (
                      <>
                        <button
                          type="button"
                          className="secondary"
                          data-testid="growth-memory-edit"
                          disabled={busy !== null}
                          onClick={() => setEditing({ id: memory.id, value: memory.statement })}
                        >
                          修改
                        </button>
                        <button
                          type="button"
                          className="secondary"
                          data-testid="growth-memory-forget"
                          disabled={busy !== null}
                          onClick={() => void act(memory, "FORGET")}
                        >
                          遗忘
                        </button>
                      </>
                    ) : null}
                  </div>
                )}

                <details>
                  <summary data-testid="growth-memory-history-toggle">操作历史</summary>
                  <ol className="growth-history">
                    {memory.history.map((event) => (
                      <li key={event.id} data-testid="growth-history-event">
                        {ACTION_LABEL[event.action]}（修订 {event.from_revision} → {event.to_revision}）
                        {event.statement_before && event.statement_after
                        && event.statement_before !== event.statement_after ? (
                          <span className="growth-muted">
                            ：由「{event.statement_before}」改为「{event.statement_after}」
                          </span>
                        ) : null}
                      </li>
                    ))}
                  </ol>
                </details>
              </li>
            ))}
          </ul>
        )}
      </section>

      <footer className="growth-footer">
        <p className="growth-muted">
          这些记录属于你自己的账号；换账号后不会看到别人的记录，后端也会拒绝读取。
        </p>
      </footer>
    </main>
  );
}
