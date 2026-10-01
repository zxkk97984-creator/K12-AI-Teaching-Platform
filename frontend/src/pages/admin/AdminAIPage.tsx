import { useEffect, useState } from "react";
import { memoryRequest } from "../../features/growth/memory-api";
import { useEditingRegistration } from "../../app/editing/EditingGuard";
import { AdminDrawer } from "./AdminDrawer";
import { AgentFields, CapabilityFields } from "./AdminAIEditors";
import {
  executionText,
  targetSignature,
  ROLE_LABEL,
  OPERATIONS,
  routeIssues,
  type Agent,
  type Capability,
  type Configuration,
} from "./admin-ai-state";
import { STAGE_LABEL, StatusBadge } from "./admin-labels";
import "./admin-common.css";
import "./admin-ai.css";
const BASE = "/api/v1/admin/ai";
type WorkspaceProof = {
  status: string;
  reason?: string;
  notice?: string;
  checked_at?: string;
  memory?: { both_explicitly_disabled?: boolean };
  plugins: { id?: string; name?: string; version?: string }[];
};
type Editor =
  | { kind: "agent"; index: number; value: Agent }
  | { kind: "capability"; index: number; value: Capability };
export function AdminAIPage() {
  const [config, setConfig] = useState<Configuration | null>(null);
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<"save" | "diagnostic" | null>(null);
  const [tab, setTab] = useState<"agents" | "routes" | "capabilities">(
    "agents",
  );
  const [editor, setEditor] = useState<Editor | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  const [verification, setVerification] = useState<
    Record<string, { proof: WorkspaceProof; fingerprint: string }>
  >({});
  const [signatures, setSignatures] = useState<Record<string, string>>({});
  const dirty = Boolean(config && JSON.stringify(config.data) !== saved);
  const source =
    editor && config
      ? editor.kind === "agent"
        ? config.data.agents[editor.index]
        : config.data.capabilities[editor.index]
      : null;
  const editDirty = Boolean(
    editor && JSON.stringify(editor.value) !== JSON.stringify(source),
  );
  useEditingRegistration("ai-configuration", dirty || editDirty);
  useEffect(() => {
    let active = true;
    setError("");
    void memoryRequest<Configuration>(BASE + "/configuration")
      .then((c) => {
        if (active) {
          setConfig(c);
          setSaved(JSON.stringify(c.data));
        }
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [attempt]);
  useEffect(() => {
    let active = true;
    if (config)
      void Promise.all(
        config.data.agents.map(
          async (a) => [a.id, await targetSignature(a)] as const,
        ),
      )
        .then((entries) => {
          if (active) setSignatures(Object.fromEntries(entries));
        })
        .catch(() => {
          if (active) setSignatures({});
        });
    return () => {
      active = false;
    };
  }, [config?.data.agents]);
  const workspaceFingerprint = (a: Agent) =>
    JSON.stringify([
      executionText(a),
      a.remote_memory_disabled,
      config?.data.capabilities.filter((c) => a.capabilities.includes(c.id)),
    ]);
  const proofState = (a: Agent) => {
    const proof = config?.data.verifications?.[a.id];
    if (!proof) return { text: "未校验", value: "NOT_VERIFIED" };
    if (
      typeof proof.signature !== "string" ||
      !signatures[a.id] ||
      signatures[a.id] !== proof.signature
    )
      return { text: "需要重新核对", value: "STALE" };
    return {
      text: proof.status === "PASSED" ? "连接与协议通过" : "检测未通过",
      value: String(proof.status),
    };
  };
  function closeEditor() {
    if (busy) return;
    if (
      editDirty &&
      !window.confirm("此面板的修改尚未应用到草稿。放弃面板修改并关闭吗？")
    )
      return;
    setEditor(null);
  }
  function applyEditor(nextTab?: "capabilities") {
    if (!editor || !config || busy) return;
    const form = document.getElementById(
      "ai-editor-form",
    ) as HTMLFormElement | null;
    if (form && !form.reportValidity()) return;
    setConfig({
      ...config,
      data: {
        ...config.data,
        agents:
          editor.kind === "agent"
            ? config.data.agents.map((a, i) =>
                i === editor.index ? editor.value : a,
              )
            : config.data.agents,
        capabilities:
          editor.kind === "capability"
            ? config.data.capabilities.map((c, i) =>
                i === editor.index ? editor.value : c,
              )
            : config.data.capabilities,
      },
    });
    setEditor(null);
    setMessage("已应用到页面草稿，请保存全部配置。");
    if (nextTab) setTab(nextTab);
  }
  async function save() {
    if (!config || busy || editDirty) return;
    setBusy("save");
    setError("");
    setMessage("");
    try {
      const c = await memoryRequest<Configuration>(
        BASE + "/configuration",
        "PUT",
        { base_revision: config.revision, data: config.data },
      );
      setConfig(c);
      setSaved(JSON.stringify(c.data));
      setMessage(
        "全部配置已保存。新对话使用最新路由，已有对话继续绑定原教师。",
      );
    } catch (e) {
      setError(
        (e instanceof Error ? e.message : "保存失败") +
          "。草稿已保留，请检查后重试。",
      );
    } finally {
      setBusy(null);
    }
  }
  const diagnosticReason = (a: Agent, binding = false) =>
    busy
      ? "正在处理请求，请稍候"
      : editDirty
        ? "请先将面板修改应用到草稿并保存全部配置"
        : dirty || !config?.persisted
          ? "请先保存全部配置"
          : !a.workspace_id
            ? "尚未填写工作空间 ID"
            : binding && !a.bot_id
              ? "尚未填写 Bot ID"
              : "";
  async function diagnose(
    a: Agent,
    operation: "verify" | "probe" | "prompt-template",
  ) {
    if (
      operation === "prompt-template"
        ? busy || editDirty || dirty
        : diagnosticReason(a, operation === "probe")
    )
      return;
    setBusy("diagnostic");
    setError("");
    setMessage("");
    try {
      const result = await memoryRequest<WorkspaceProof & { prompt?: string }>(
        BASE + "/agents/" + encodeURIComponent(a.id) + "/" + operation,
        operation === "prompt-template" ? "GET" : "POST",
      );
      if (operation === "prompt-template")
        setPrompts((prev) => ({ ...prev, [a.id]: result.prompt ?? "" }));
      if (operation === "verify")
        setVerification((prev) => ({
          ...prev,
          [a.id]: { proof: result, fingerprint: workspaceFingerprint(a) },
        }));
      if (operation === "probe") {
        if (result.status === "PASSED")
          setMessage("真实连接与输出协议测试通过。此结果不代表内容已审校。");
        else
          setError(
            "测试未通过：" + (result.reason || "请检查 Knodo 提示词和绑定"),
          );
        const fresh = await memoryRequest<Configuration>(
          BASE + "/configuration",
        );
        setConfig(fresh);
        setSaved(JSON.stringify(fresh.data));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "诊断失败");
    } finally {
      setBusy(null);
    }
  }
  function addAgent() {
    if (!config || busy) return;
    const value: Agent = {
      id: "teacher-" + crypto.randomUUID(),
      name: "新教师",
      role: "teacher",
      description: "",
      enabled: false,
      bot_id: null,
      workspace_id: null,
      prompt_version: "v1",
      remote_memory_disabled: false,
      capabilities: [],
    };
    const index = config.data.agents.length;
    setConfig({
      ...config,
      data: { ...config.data, agents: [...config.data.agents, value] },
    });
    setEditor({ kind: "agent", index, value });
  }
  function addCapability() {
    if (!config || busy) return;
    const value: Capability = {
      id: "skill-" + crypto.randomUUID(),
      name: "新能力",
      version: "1",
      executor: "KNODO_SKILL",
      plugin_id: null,
      binding_scope: "WORKSPACE",
      handler: null,
      input_contract: "",
      output_contract: "",
      allowed_context: [],
      enabled: true,
    };
    const index = config.data.capabilities.length;
    setConfig({
      ...config,
      data: {
        ...config.data,
        capabilities: [...config.data.capabilities, value],
      },
    });
    setEditor({ kind: "capability", index, value });
  }
  function diagnostics(a: Agent) {
    const record = verification[a.id];
    const stale = record && record.fingerprint !== workspaceFingerprint(a);
    const state = proofState(a);
    const reason = diagnosticReason(a);
    const promptReason = busy
      ? "正在处理请求，请稍候"
      : editDirty || dirty
        ? "请先应用草稿并保存全部配置"
        : "";
    const probeReason = diagnosticReason(a, true);
    return (
      <>
        <div className="admin-ai-diagnostic-status">
          <StatusBadge value={editDirty ? "STALE" : state.value}>
            {editDirty ? "面板配置未保存，需重新核对" : state.text}
          </StatusBadge>
          <span className="admin-help">协议检测与空间插件读取是独立结果</span>
        </div>
        <div className="admin-ai-diagnostic-actions">
          <div>
            <button
              type="button"
              className="admin-button-quiet"
              disabled={Boolean(promptReason)}
              onClick={() => void diagnose(a, "prompt-template")}
            >
              查看配置提示词
            </button>
            {promptReason && <p className="admin-help">{promptReason}</p>}
          </div>
          <div>
            <button
              type="button"
              className="admin-button-quiet"
              disabled={Boolean(reason)}
              onClick={() => void diagnose(a, "verify")}
            >
              核对远端空间插件
            </button>
            {reason && <p className="admin-help">{reason}</p>}
          </div>
          <div>
            <button
              type="button"
              className="admin-button-quiet"
              disabled={Boolean(probeReason)}
              onClick={() => void diagnose(a, "probe")}
            >
              测试连接与输出协议
            </button>
            <p className="admin-help">
              {probeReason || "发送合成消息，仅手动触发"}
            </p>
          </div>
        </div>
        {a.workspace_id && (
          <a
            href={
              "https://knodo.vip/workspaces/" +
              encodeURIComponent(a.workspace_id)
            }
            target="_blank"
            rel="noreferrer"
          >
            打开 Knodo 工作空间 ↗
          </a>
        )}
        {config?.data.verifications?.[a.id] && (
          <p className="admin-help">
            上次协议检测：
            {String(config.data.verifications[a.id].checked_at ?? "时间未知")}
            {config.data.verifications[a.id].reason
              ? " · " + String(config.data.verifications[a.id].reason)
              : ""}
          </p>
        )}
        {record && (
          <div
            className={
              stale || editDirty ? "admin-warning" : "admin-ai-verification"
            }
          >
            <strong>
              {stale || editDirty
                ? "配置已改变，空间插件需要重新核对"
                : record.proof.status === "WORKSPACE_READ_VERIFIED"
                  ? "已读取远端空间插件列表"
                  : "空间插件未核验"}
            </strong>
            <p>{record.proof.notice || record.proof.reason}</p>
            <p>
              远端记忆：
              {!stale &&
              !editDirty &&
              record.proof.memory?.both_explicitly_disabled
                ? "检测时两套均已明确禁用"
                : "当前配置尚未确认"}
            </p>
            {record.proof.plugins.map((p, index) => (
              <p key={p.id ?? index}>
                {p.name ?? p.id} · {p.version ?? "版本未知"}
              </p>
            ))}
          </div>
        )}
        {prompts[a.id] && (
          <details className="admin-technical" open>
            <summary>本地配置提示词模板</summary>
            <p>请粘贴到对应助手；本地模板不表示远端当前内容。</p>
            <textarea
              aria-label={a.name + "配置提示词"}
              readOnly
              value={prompts[a.id]}
              rows={8}
            />
            <button
              type="button"
              className="admin-button-quiet"
              onClick={() =>
                void navigator.clipboard
                  .writeText(prompts[a.id])
                  .then(() => setMessage("提示词已复制。"))
                  .catch(() => setError("自动复制不可用，请选中文本手动复制。"))
              }
            >
              复制提示词
            </button>
          </details>
        )}
      </>
    );
  }
  return (
    <main className="admin-resources admin-ai">
      <header className="admin-page-header">
        <div>
          <h1>AI 教师与能力</h1>
          <p>管理教师分工、学段路由和 Knodo 能力关联。</p>
        </div>
      </header>
      <div className="admin-ai-savebar">
        <div>
          <strong>
            {config
              ? config.persisted
                ? `配置版本 ${config.revision}`
                : "本机初始配置 · 尚未保存"
              : "正在读取配置"}
          </strong>
          <span>
            {busy === "save"
              ? "保存中…"
              : dirty
                ? "有未保存的修改"
                : config?.persisted
                  ? "与服务器配置一致"
                  : "需首次保存"}
          </span>
        </div>
        <button
          disabled={Boolean(busy) || !config || (!dirty && config.persisted)}
          onClick={() => void save()}
        >
          {busy === "save" ? "正在保存…" : "保存全部配置"}
        </button>
      </div>
      {error && (
        <p role="alert" className="admin-error">
          {error}
          {!config && (
            <button
              type="button"
              className="admin-button-quiet"
              onClick={() => setAttempt((v) => v + 1)}
            >
              重试读取
            </button>
          )}
        </p>
      )}
      {message && (
        <p role="status" className="admin-notice">
          {message}
        </p>
      )}
      {!config ? (
        !error && (
          <p role="status" className="admin-muted">
            正在读取配置…
          </p>
        )
      ) : (
        <>
          <nav className="admin-ai-tabs" aria-label="AI 配置分类">
            {(["agents", "routes", "capabilities"] as const).map((key) => (
              <button
                key={key}
                aria-label={
                  {
                    agents: "教师与助手",
                    routes: "学段与任务路由",
                    capabilities: "Skill 与能力",
                  }[key]
                }
                aria-pressed={tab === key}
                className={tab === key ? "is-selected" : "admin-button-quiet"}
                onClick={() => setTab(key)}
              >
                {
                  {
                    agents: "教师与助手",
                    routes: "学段与任务路由",
                    capabilities: "Skill 与能力",
                  }[key]
                }
                <span>{config.data[key].length}</span>
              </button>
            ))}
          </nav>
          <section className="admin-panel">
            {tab === "agents" && (
              <>
                <div className="admin-section-heading">
                  <div>
                    <h2>教师与助手</h2>
                    <p>启用与校验分别记录，绑定 ID 后需主动检测。</p>
                  </div>
                  <button
                    type="button"
                    className="admin-button-quiet"
                    disabled={Boolean(busy)}
                    onClick={addAgent}
                  >
                    新增助手
                  </button>
                </div>
                {config.data.agents.length === 0 ? (
                  <div className="admin-empty">
                    <p>还没有教师或助手。先登记并保存，再配置路由。</p>
                    <button onClick={addAgent}>新增助手</button>
                  </div>
                ) : (
                  <div className="admin-table-wrap">
                    <table className="admin-table admin-ai-table">
                      <thead>
                        <tr>
                          <th>教师 / 助手</th>
                          <th>职责</th>
                          <th>启用状态</th>
                          <th>Knodo 绑定</th>
                          <th>实际校验</th>
                          <th>操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {config.data.agents.map((a, i) => {
                          const state = proofState(a);
                          return (
                            <tr key={a.id}>
                              <td>
                                <strong
                                  className="admin-truncate"
                                  title={a.name}
                                >
                                  {a.name}
                                </strong>
                                <small
                                  className="admin-truncate"
                                  title={a.description}
                                >
                                  {a.description || "暂无简介"}
                                </small>
                              </td>
                              <td>{ROLE_LABEL[a.role]}</td>
                              <td>
                                <StatusBadge>
                                  {a.enabled ? "已启用" : "已停用"}
                                </StatusBadge>
                              </td>
                              <td>
                                <small
                                  className="admin-truncate"
                                  title={a.bot_id ?? undefined}
                                >
                                  Bot：{a.bot_id || "未绑定"}
                                </small>
                                <small>
                                  空间：{a.workspace_id || "未绑定"}
                                </small>
                              </td>
                              <td>
                                <StatusBadge value={state.value}>
                                  {state.text}
                                </StatusBadge>
                              </td>
                              <td>
                                <button
                                  type="button"
                                  className="admin-button-quiet"
                                  disabled={Boolean(busy)}
                                  aria-label={`编辑 ${a.name}`}
                                  onClick={() =>
                                    setEditor({
                                      kind: "agent",
                                      index: i,
                                      value: structuredClone(a),
                                    })
                                  }
                                >
                                  编辑
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
            {tab === "routes" && (
              <>
                <div className="admin-section-heading">
                  <div>
                    <h2>学段与任务路由</h2>
                    <p>
                      具体学段优先于默认规则，同一教师可服务多个学段。最终由服务器校验。
                    </p>
                  </div>
                  <button
                    type="button"
                    className="admin-button-quiet"
                    disabled={Boolean(busy)}
                    onClick={() =>
                      setConfig({
                        ...config,
                        data: {
                          ...config.data,
                          routes: [
                            ...config.data.routes,
                            {
                              operation: "TEACH_TURN",
                              stage: "PRIMARY_LOWER",
                              agent_id:
                                config.data.agents.find(
                                  (a) => a.enabled && a.role === "teacher",
                                )?.id ?? "",
                            },
                          ],
                        },
                      })
                    }
                  >
                    新增路由
                  </button>
                </div>
                {config.data.routes.length === 0 ? (
                  <p className="admin-empty">
                    暂无路由，请新增任务与学段规则。
                  </p>
                ) : (
                  <fieldset disabled={Boolean(busy)}>
                    <div className="admin-table-wrap">
                      <table className="admin-table admin-ai-routes">
                        <thead>
                          <tr>
                            <th>任务</th>
                            <th>学段 / 匹配优先级</th>
                            <th>调用助手</th>
                            <th>检查提示</th>
                            <th>操作</th>
                          </tr>
                        </thead>
                        <tbody>
                          {config.data.routes.map((r, i) => {
                            const issues = routeIssues(
                              r,
                              config.data.routes,
                              config.data.agents,
                            );
                            const change = (patch: Partial<typeof r>) =>
                              setConfig({
                                ...config,
                                data: {
                                  ...config.data,
                                  routes: config.data.routes.map((row, at) =>
                                    at === i ? { ...row, ...patch } : row,
                                  ),
                                },
                              });
                            return (
                              <tr key={i}>
                                <td>
                                  <select
                                    aria-label={`任务 ${i + 1}`}
                                    value={r.operation}
                                    onChange={(e) =>
                                      change({ operation: e.target.value })
                                    }
                                  >
                                    {!OPERATIONS[r.operation] && (
                                      <option value={r.operation}>
                                        {r.operation}（未知任务）
                                      </option>
                                    )}
                                    {Object.entries(OPERATIONS).map(
                                      ([v, n]) => (
                                        <option key={v} value={v}>
                                          {n}
                                        </option>
                                      ),
                                    )}
                                  </select>
                                </td>
                                <td>
                                  <select
                                    aria-label={`学段 ${i + 1}`}
                                    value={r.stage}
                                    onChange={(e) =>
                                      change({
                                        stage: e.target.value as typeof r.stage,
                                      })
                                    }
                                  >
                                    {Object.entries(STAGE_LABEL).map(
                                      ([v, n]) => (
                                        <option key={v} value={v}>
                                          {n}
                                        </option>
                                      ),
                                    )}
                                  </select>
                                  <small>
                                    {r.stage === "*"
                                      ? "默认规则 · 无具体规则时匹配"
                                      : "具体学段 · 优先匹配"}
                                  </small>
                                </td>
                                <td>
                                  <select
                                    aria-label={`调用助手 ${i + 1}`}
                                    value={r.agent_id}
                                    onChange={(e) =>
                                      change({ agent_id: e.target.value })
                                    }
                                  >
                                    <option value="">请选择助手</option>
                                    {!config.data.agents.some(
                                      (a) => a.id === r.agent_id,
                                    ) &&
                                      r.agent_id && (
                                        <option value={r.agent_id}>
                                          {r.agent_id}（失效引用）
                                        </option>
                                      )}
                                    {config.data.agents.map((a) => (
                                      <option key={a.id} value={a.id}>
                                        {a.name}
                                        {!a.enabled ? "（已停用）" : ""} ·{" "}
                                        {ROLE_LABEL[a.role]}
                                      </option>
                                    ))}
                                  </select>
                                </td>
                                <td>
                                  {issues.length ? (
                                    issues.map((issue) => (
                                      <small
                                        className="admin-ai-route-warning"
                                        key={issue}
                                      >
                                        {issue}
                                      </small>
                                    ))
                                  ) : (
                                    <small>
                                      登记规则无明显冲突；保存时服务器继续核验。
                                    </small>
                                  )}
                                </td>
                                <td>
                                  <button
                                    type="button"
                                    className="admin-button-quiet"
                                    onClick={() =>
                                      setConfig({
                                        ...config,
                                        data: {
                                          ...config.data,
                                          routes: config.data.routes.filter(
                                            (_, at) => at !== i,
                                          ),
                                        },
                                      })
                                    }
                                  >
                                    移除
                                  </button>
                                </td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    </div>
                  </fieldset>
                )}
              </>
            )}
            {tab === "capabilities" && (
              <>
                <div className="admin-section-heading">
                  <div>
                    <h2>Skill 与能力</h2>
                    <p>
                      本地登记与远端安装分别管理。实际插件安装、个人技能绑定需在
                      Knodo 完成。
                    </p>
                  </div>
                  <button
                    type="button"
                    className="admin-button-quiet"
                    disabled={Boolean(busy)}
                    onClick={addCapability}
                  >
                    登记能力
                  </button>
                </div>
                {config.data.capabilities.length === 0 ? (
                  <div className="admin-empty">
                    <p>还没有登记能力。登记后可在教师详情中关联。</p>
                    <button onClick={addCapability}>登记首个能力</button>
                  </div>
                ) : (
                  <div className="admin-table-wrap">
                    <table className="admin-table admin-ai-capabilities">
                      <thead>
                        <tr>
                          <th>能力 / 版本</th>
                          <th>本地登记</th>
                          <th>执行与作用范围</th>
                          <th>教师关联</th>
                          <th>远端校验</th>
                          <th>操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {config.data.capabilities.map((c, i) => {
                          const agents = config.data.agents.filter((a) =>
                            a.capabilities.includes(c.id),
                          );
                          const seen =
                            c.binding_scope === "WORKSPACE" &&
                            agents.some(
                              (a) =>
                                verification[a.id]?.fingerprint ===
                                  workspaceFingerprint(a) &&
                                verification[a.id]?.proof.plugins.some(
                                  (p) => p.id === c.plugin_id,
                                ),
                            );
                          return (
                            <tr key={c.id}>
                              <td>
                                <strong
                                  className="admin-truncate"
                                  title={c.name}
                                >
                                  {c.name}
                                </strong>
                                <small>第 {c.version} 版</small>
                              </td>
                              <td>
                                <StatusBadge>
                                  {c.enabled ? "已启用" : "已停用"}
                                </StatusBadge>
                              </td>
                              <td>
                                {c.executor === "BACKEND"
                                  ? "后端受控工具"
                                  : c.binding_scope === "WORKSPACE"
                                    ? "工作空间共享"
                                    : "助手个人技能"}
                                <small>
                                  {c.executor === "KNODO_SKILL" &&
                                  c.binding_scope === "WORKSPACE"
                                    ? "空间内其他教师数量未知"
                                    : ""}
                                </small>
                              </td>
                              <td>
                                {agents.length
                                  ? agents.map((a) => a.name).join("、")
                                  : "尚未关联教师"}
                              </td>
                              <td>
                                <StatusBadge>
                                  {c.executor === "BACKEND"
                                    ? "服务器保存时核验处理器"
                                    : seen
                                      ? "空间列表含绑定 ID"
                                      : "未核对"}
                                </StatusBadge>
                              </td>
                              <td>
                                <button
                                  type="button"
                                  className="admin-button-quiet"
                                  disabled={Boolean(busy)}
                                  aria-label={`编辑 ${c.name}`}
                                  onClick={() =>
                                    setEditor({
                                      kind: "capability",
                                      index: i,
                                      value: structuredClone(c),
                                    })
                                  }
                                >
                                  编辑
                                </button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </>
            )}
          </section>
        </>
      )}
      {editor && config && (
        <AdminDrawer
          busy={Boolean(busy)}
          title={
            editor.kind === "agent" ? "编辑教师与助手" : "编辑 Skill 与能力"
          }
          description="修改先应用到页面草稿；三类配置统一保存到服务器。"
          onClose={closeEditor}
          footer={
            <>
              <span className="admin-help">
                {editDirty ? "面板修改尚未应用" : "关闭面板不会丢失页面草稿"}
              </span>
              <button
                type="button"
                className="admin-button-quiet"
                disabled={Boolean(busy)}
                onClick={closeEditor}
              >
                取消
              </button>
              <button
                type="submit"
                form="ai-editor-form"
                disabled={Boolean(busy)}
              >
                应用到草稿
              </button>
            </>
          }
        >
          {error && (
            <p role="alert" className="admin-error">
              {error}
            </p>
          )}
          <form
            id="ai-editor-form"
            onSubmit={(event) => {
              event.preventDefault();
              applyEditor();
            }}
          >
            <fieldset disabled={Boolean(busy)}>
              {editor.kind === "agent" ? (
                <AgentFields
                  agent={editor.value}
                  capabilities={config.data.capabilities}
                  onChange={(patch) =>
                    setEditor({
                      ...editor,
                      value: { ...editor.value, ...patch },
                    })
                  }
                  diagnostics={diagnostics(editor.value)}
                  onRegister={() => applyEditor("capabilities")}
                />
              ) : (
                <CapabilityFields
                  capability={editor.value}
                  onChange={(patch) =>
                    setEditor({
                      ...editor,
                      value: { ...editor.value, ...patch },
                    })
                  }
                />
              )}
            </fieldset>
          </form>
        </AdminDrawer>
      )}
    </main>
  );
}
