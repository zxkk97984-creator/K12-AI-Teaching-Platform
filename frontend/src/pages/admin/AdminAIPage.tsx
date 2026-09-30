import { useEffect, useState } from "react";
import { memoryRequest } from "../../features/growth/memory-api";
import { useEditingRegistration } from "../../app/editing/EditingGuard";
import type { components } from "../../shared/types/generated/admin";
import "./admin-common.css";
import "./admin-ai.css";

// FastAPI emits model defaults; derive editable shapes from the generated contract.
type Agent = Required<components["schemas"]["AgentDefinition"]>;
type Route = components["schemas"]["RouteDefinition"];
type Capability = Required<components["schemas"]["CapabilityDefinition"]>;
type Configuration = Omit<components["schemas"]["RegistryView"], "data"> & {
  data: Omit<components["schemas"]["RegistryData"], "agents" | "capabilities"> & {
    agents: Agent[];
    capabilities: Capability[];
  };
};
const BASE = "/api/v1/admin/ai";
const STAGES = {
  "*": "全部学段（默认）",
  PRIMARY_LOWER: "小学低年级",
  PRIMARY_UPPER: "小学高年级",
  JUNIOR: "初中",
  SENIOR: "高中",
};
const OPERATIONS = {
  TEACH_TURN: "教学对话",
  CODE_FEEDBACK: "代码反馈",
  QUIZ_DRAFT: "题目生成",
  LESSON_PACKAGE_DRAFT: "课程生成",
  MEMORY_EXTRACT: "个人记忆整理",
};

export function AdminAIPage() {
  const [config, setConfig] = useState<Configuration | null>(null);
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [tab, setTab] = useState<"agents" | "routes" | "capabilities">(
    "agents",
  );
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  const [verification, setVerification] = useState<
    Record<
      string,
      {
        status: string;
        reason?: string;
        notice?: string;
        checked_at?: string;
        memory?: {
          both_explicitly_disabled?: boolean;
          legacy_enabled?: boolean | null;
          plugin_enabled?: boolean | null;
        };
        plugins: { id?: string; name?: string; version?: string }[];
      }
    >
  >({});
  const dirty = Boolean(config && JSON.stringify(config.data) !== saved);
  useEditingRegistration("ai-configuration", dirty);
  useEffect(() => {
    let active = true;
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
  }, []);
  const changeAgent = (index: number, patch: Partial<Agent>) =>
    setConfig(
      (c) =>
        c && {
          ...c,
          data: {
            ...c.data,
            agents: c.data.agents.map((a, i) =>
              i === index ? { ...a, ...patch } : a,
            ),
          },
        },
    );
  const changeRoute = (index: number, patch: Partial<Route>) =>
    setConfig(
      (c) =>
        c && {
          ...c,
          data: {
            ...c.data,
            routes: c.data.routes.map((a, i) =>
              i === index ? { ...a, ...patch } : a,
            ),
          },
        },
    );
  const changeCap = (index: number, patch: Partial<Capability>) =>
    setConfig(
      (c) =>
        c && {
          ...c,
          data: {
            ...c.data,
            capabilities: c.data.capabilities.map((a, i) =>
              i === index ? { ...a, ...patch } : a,
            ),
          },
        },
    );
  const save = async () => {
    if (!config) return;
    setBusy(true);
    setError("");
    try {
      const c = await memoryRequest<Configuration>(
        BASE + "/configuration",
        "PUT",
        { base_revision: config.revision, data: config.data },
      );
      setConfig(c);
      setSaved(JSON.stringify(c.data));
      setMessage(
        "配置已保存，新对话会使用最新默认路由。已有对话继续绑定原教师。",
      );
      setVerification({});
    } catch (e) {
      setError(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };
  return (
    <main className="admin-resources admin-ai">
      <header className="admin-page-header">
        <div>
          <p className="admin-eyebrow">教学配置</p>
          <h1>AI 教师与能力</h1>
          <p>管理教师分工、学段路由，以及与 Knodo 的能力关联。</p>
        </div>
        <button
          disabled={busy || !config || (!dirty && config.persisted)}
          onClick={() => void save()}
        >
          {busy ? "正在保存…" : "保存配置"}
        </button>
      </header>
      {error && (
        <p role="alert" className="admin-ai-error">
          {error}
        </p>
      )}
      {message && (
        <p role="status" className="admin-ai-notice">
          {message}
        </p>
      )}
      {!config ? (
        <p>正在读取配置…</p>
      ) : (
        <>
          <div className="admin-ai-status">
            <span>
              {config.persisted
                ? `配置版本 ${config.revision}`
                : "尚未保存 · 从本机配置初始化"}
            </span>
            <span>{dirty ? "有未保存的修改" : "当前修改已保存"}</span>
          </div>
          <nav className="admin-ai-tabs" aria-label="AI 配置分类">
            {(["agents", "routes", "capabilities"] as const).map((key) => (
              <button
                key={key}
                className={tab === key ? "" : "admin-button-quiet"}
                aria-pressed={tab === key}
                onClick={() => setTab(key)}
              >
                {
                  {
                    agents: "教师与助手",
                    routes: "学段与任务路由",
                    capabilities: "Skill 与能力",
                  }[key]
                }
              </button>
            ))}
          </nav>
          {tab === "agents" && (
            <section>
              <div className="admin-section-heading">
                <div>
                  <h2>教师与助手</h2>
                  <p>
                    提示词、模型与实际 Skill 内容在 Knodo
                    中管理。填写绑定后，再设置默认路由。
                  </p>
                </div>
                <button
                  className="admin-button-quiet"
                  onClick={() =>
                    setConfig({
                      ...config,
                      data: {
                        ...config.data,
                        agents: [
                          ...config.data.agents,
                          {
                            id: "teacher-" + Date.now(),
                            name: "新教师",
                            role: "teacher",
                            description: "",
                            enabled: false,
                            bot_id: null,
                            workspace_id: null,
                            prompt_version: "v1",
                            remote_memory_disabled: false,
                            capabilities: [],
                          },
                        ],
                      },
                    })
                  }
                >
                  新增助手
                </button>
              </div>
              <div className="admin-ai-list">
                {config.data.agents.map((a, i) => (
                  <article key={i} className="admin-ai-card">
                    <div className="admin-section-heading">
                      <h3>{a.name}</h3>
                      <label>
                        <input
                          type="checkbox"
                          checked={a.enabled}
                          onChange={(e) =>
                            changeAgent(i, { enabled: e.target.checked })
                          }
                        />{" "}
                        启用
                      </label>
                    </div>
                    <div className="admin-ai-fields">
                      <label>
                        稳定标识
                        <input
                          value={a.id}
                          onChange={(e) =>
                            changeAgent(i, { id: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        显示名称
                        <input
                          value={a.name}
                          onChange={(e) =>
                            changeAgent(i, { name: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        职责
                        <select
                          value={a.role}
                          onChange={(e) =>
                            changeAgent(i, {
                              role: e.target.value as Agent["role"],
                            })
                          }
                        >
                          <option value="teacher">学生教师</option>
                          <option value="designer">教研制作</option>
                          <option value="memory">内部记忆整理</option>
                        </select>
                      </label>
                      <label>
                        提示词版本
                        <input
                          value={a.prompt_version}
                          onChange={(e) =>
                            changeAgent(i, { prompt_version: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        Knodo Bot ID
                        <input
                          value={a.bot_id ?? ""}
                          onChange={(e) =>
                            changeAgent(i, { bot_id: e.target.value || null })
                          }
                          autoComplete="off"
                        />
                      </label>
                      <label>
                        工作空间 ID
                        <input
                          value={a.workspace_id ?? ""}
                          onChange={(e) =>
                            changeAgent(i, {
                              workspace_id: e.target.value || null,
                            })
                          }
                          autoComplete="off"
                        />
                      </label>
                    </div>
                    <label>
                      简介
                      <textarea
                        value={a.description}
                        onChange={(e) =>
                          changeAgent(i, { description: e.target.value })
                        }
                        maxLength={1000}
                      />
                    </label>
                    <label className="admin-ai-check">
                      <input
                        type="checkbox"
                        checked={a.remote_memory_disabled}
                        onChange={(e) =>
                          changeAgent(i, {
                            remote_memory_disabled: e.target.checked,
                          })
                        }
                      />{" "}
                      已在 Knodo 核对并关闭共享空间的自动记忆采集和召回
                    </label>
                    <fieldset>
                      <legend>登记的能力关联</legend>
                      {config.data.capabilities.length ? (
                        config.data.capabilities.map((cap) => (
                          <label key={cap.id} className="admin-ai-check">
                            <input
                              type="checkbox"
                              checked={a.capabilities.includes(cap.id)}
                              onChange={(e) =>
                                changeAgent(i, {
                                  capabilities: e.target.checked
                                    ? [...a.capabilities, cap.id]
                                    : a.capabilities.filter(
                                        (id) => id !== cap.id,
                                      ),
                                })
                              }
                            />{" "}
                            {cap.name}
                          </label>
                        ))
                      ) : (
                        <small>在“Skill 与能力”中登记后可关联。</small>
                      )}
                    </fieldset>
                    <div className="admin-ai-links">
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
                      <button
                        className="admin-button-quiet"
                        disabled={
                          busy || dirty || !config.persisted || !a.workspace_id
                        }
                        onClick={() => {
                          setBusy(true);
                          void memoryRequest<(typeof verification)[string]>(
                            BASE +
                              "/agents/" +
                              encodeURIComponent(a.id) +
                              "/verify",
                            "POST",
                          )
                            .then((v) =>
                              setVerification((prev) => ({
                                ...prev,
                                [a.id]: v,
                              })),
                            )
                            .catch((e: Error) => setError(e.message))
                            .finally(() => setBusy(false));
                        }}
                      >
                        核对远端空间插件
                      </button>
                    </div>
                    <button
                      className="admin-button-quiet"
                      disabled={dirty}
                      onClick={() =>
                        void memoryRequest<{ prompt: string }>(
                          BASE +
                            "/agents/" +
                            encodeURIComponent(a.id) +
                            "/prompt-template",
                        )
                          .then((result) =>
                            setPrompts((prev) => ({
                              ...prev,
                              [a.id]: result.prompt,
                            })),
                          )
                          .catch((e: Error) => setError(e.message))
                      }
                    >
                      查看可复制的配置提示词
                    </button>
                    {prompts[a.id] && (
                      <div>
                        <p>
                          本地模板，请粘贴到 Knodo
                          对应助手的系统提示词；不会自动覆盖远端。
                        </p>
                        <textarea
                          aria-label={a.name + "配置提示词"}
                          value={prompts[a.id]}
                          readOnly
                          rows={10}
                        />
                        <button
                          className="admin-button-quiet"
                          onClick={() =>
                            void navigator.clipboard
                              .writeText(prompts[a.id])
                              .then(() => setMessage("配置提示词已复制"))
                              .catch(() =>
                                setError("自动复制不可用，请选中文本手动复制"),
                              )
                          }
                        >
                          复制提示词
                        </button>
                      </div>
                    )}
                    <button
                      className="admin-button-quiet"
                      disabled={
                        busy ||
                        dirty ||
                        !config.persisted ||
                        !a.bot_id ||
                        !a.workspace_id
                      }
                      onClick={() => {
                        setBusy(true);
                        setError("");
                        void memoryRequest<{ status: string; reason?: string }>(
                          BASE +
                            "/agents/" +
                            encodeURIComponent(a.id) +
                            "/probe",
                          "POST",
                        )
                          .then(async (proof) => {
                            setMessage(
                              proof.status === "PASSED"
                                ? "真实连接与输出协议测试通过，可以配置路由。"
                                : "测试未通过：" +
                                    (proof.reason ||
                                      "请检查 Knodo 提示词和绑定"),
                            );
                            const fresh = await memoryRequest<Configuration>(
                              BASE + "/configuration",
                            );
                            setConfig(fresh);
                            setSaved(JSON.stringify(fresh.data));
                          })
                          .catch((e: Error) => setError(e.message))
                          .finally(() => setBusy(false));
                      }}
                    >
                      测试连接与输出协议（合成消息）
                    </button>
                    {verification[a.id] && (
                      <div className="admin-ai-verification">
                        <strong>
                          {verification[a.id].status ===
                          "WORKSPACE_READ_VERIFIED"
                            ? "已读取远端空间插件"
                            : "尚未核验"}
                        </strong>
                        <p>
                          {verification[a.id].notice ||
                            verification[a.id].reason}
                        </p>
                        {verification[a.id].memory && (
                          <p>
                            远端记忆：
                            {verification[a.id].memory?.both_explicitly_disabled
                              ? "两套均已明确禁用"
                              : "尚未确认全部禁用，请在 Knodo 检查"}
                          </p>
                        )}
                        {verification[a.id].plugins.map((p, j) => (
                          <p key={p.id ?? j}>
                            {p.name ?? p.id} · {p.version ?? "版本未提供"}
                          </p>
                        ))}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            </section>
          )}
          {tab === "routes" && (
            <section>
              <div className="admin-section-heading">
                <div>
                  <h2>学段与任务路由</h2>
                  <p>
                    具体学段优先于全部学段。小学低年级和高年级可指向同一位教师。
                  </p>
                </div>
                <button
                  className="admin-button-quiet"
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
                              config.data.agents.find((a) => a.enabled)?.id ??
                              "",
                          },
                        ],
                      },
                    })
                  }
                >
                  新增路由
                </button>
              </div>
              {config.data.routes.map((r, i) => (
                <div key={i} className="admin-ai-route">
                  <label>
                    任务
                    <select
                      value={r.operation}
                      onChange={(e) =>
                        changeRoute(i, { operation: e.target.value })
                      }
                    >
                      {Object.entries(OPERATIONS).map(([v, n]) => (
                        <option key={v} value={v}>
                          {n}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    学段
                    <select
                      value={r.stage}
                      onChange={(e) =>
                        changeRoute(i, { stage: e.target.value as Route["stage"] })
                      }
                    >
                      {Object.entries(STAGES).map(([v, n]) => (
                        <option key={v} value={v}>
                          {n}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    调用助手
                    <select
                      value={r.agent_id}
                      onChange={(e) =>
                        changeRoute(i, { agent_id: e.target.value })
                      }
                    >
                      <option value="">请选择</option>
                      {config.data.agents
                        .filter((a) => a.enabled)
                        .map((a) => (
                          <option key={a.id} value={a.id}>
                            {a.name}
                          </option>
                        ))}
                    </select>
                  </label>
                  <button
                    className="admin-button-quiet"
                    onClick={() =>
                      setConfig({
                        ...config,
                        data: {
                          ...config.data,
                          routes: config.data.routes.filter(
                            (_, index) => index !== i,
                          ),
                        },
                      })
                    }
                  >
                    移除路由
                  </button>
                </div>
              ))}
            </section>
          )}
          {tab === "capabilities" && (
            <section>
              <div className="admin-section-heading">
                <div>
                  <h2>Skill 与能力</h2>
                  <p>
                    此处登记关联。实际插件安装、个人技能绑定和停用需要在 Knodo
                    完成，空间插件会影响空间内所有教师。
                  </p>
                </div>
                <button
                  className="admin-button-quiet"
                  onClick={() =>
                    setConfig({
                      ...config,
                      data: {
                        ...config.data,
                        capabilities: [
                          ...config.data.capabilities,
                          {
                            id: "skill-" + Date.now(),
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
                          },
                        ],
                      },
                    })
                  }
                >
                  登记能力
                </button>
              </div>
              <div className="admin-ai-list">
                {config.data.capabilities.map((c, i) => (
                  <article key={i} className="admin-ai-card">
                    <h3>{c.name}</h3>
                    <div className="admin-ai-fields">
                      <label>
                        能力标识
                        <input
                          value={c.id}
                          onChange={(e) => changeCap(i, { id: e.target.value })}
                        />
                      </label>
                      <label>
                        名称
                        <input
                          value={c.name}
                          onChange={(e) =>
                            changeCap(i, { name: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        版本
                        <input
                          value={c.version}
                          onChange={(e) =>
                            changeCap(i, { version: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        执行方式
                        <select
                          value={c.executor}
                          onChange={(e) =>
                            changeCap(i, {
                              executor: e.target
                                .value as Capability["executor"],
                            })
                          }
                        >
                          <option value="KNODO_SKILL">Knodo Skill</option>
                          <option value="BACKEND">后端受控工具</option>
                        </select>
                      </label>
                      {c.executor === "KNODO_SKILL" ? (
                        <>
                          <label>
                            Plugin ID
                            <input
                              value={c.plugin_id ?? ""}
                              onChange={(e) =>
                                changeCap(i, {
                                  plugin_id: e.target.value || null,
                                })
                              }
                            />
                          </label>
                          <label>
                            挂载位置
                            <select
                              value={c.binding_scope}
                              onChange={(e) =>
                                changeCap(i, {
                                  binding_scope: e.target
                                    .value as Capability["binding_scope"],
                                })
                              }
                            >
                              <option value="WORKSPACE">
                                工作空间（共享）
                              </option>
                              <option value="ASSISTANT">助手个人技能</option>
                            </select>
                          </label>
                        </>
                      ) : (
                        <label>
                          已安装的处理器标识
                          <input
                            value={c.handler ?? ""}
                            onChange={(e) =>
                              changeCap(i, { handler: e.target.value || null })
                            }
                          />
                        </label>
                      )}
                      <label>
                        输入契约
                        <input
                          value={c.input_contract}
                          onChange={(e) =>
                            changeCap(i, { input_contract: e.target.value })
                          }
                        />
                      </label>
                      <label>
                        输出契约
                        <input
                          value={c.output_contract}
                          onChange={(e) =>
                            changeCap(i, { output_contract: e.target.value })
                          }
                        />
                      </label>
                    </div>
                    <fieldset>
                      <legend>本地调用允许的上下文</legend>
                      {(["course", "conversation", "personal_memory"] as const).map(
                        (value) => (
                          <label key={value} className="admin-ai-check">
                            <input
                              type="checkbox"
                              checked={c.allowed_context.includes(value)}
                              onChange={(e) =>
                                changeCap(i, {
                                  allowed_context: e.target.checked
                                    ? [...c.allowed_context, value]
                                    : c.allowed_context.filter(
                                        (v) => v !== value,
                                      ),
                                })
                              }
                            />
                            {
                              {
                                course: "课程",
                                conversation: "当前对话",
                                personal_memory: "相关个人记忆",
                              }[value]
                            }
                          </label>
                        ),
                      )}
                    </fieldset>
                    <label>
                      <input
                        type="checkbox"
                        checked={c.enabled}
                        onChange={(e) =>
                          changeCap(i, { enabled: e.target.checked })
                        }
                      />{" "}
                      启用本地能力登记
                    </label>
                  </article>
                ))}
              </div>
            </section>
          )}
        </>
      )}
    </main>
  );
}
