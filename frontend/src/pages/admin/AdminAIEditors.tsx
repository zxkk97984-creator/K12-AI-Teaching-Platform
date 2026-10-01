import type { ReactNode } from "react";
import { ROLE_LABEL, type Agent, type Capability } from "./admin-ai-state";
export function AgentFields({
  agent: a,
  capabilities,
  onChange,
  diagnostics,
  onRegister,
}: {
  agent: Agent;
  capabilities: Capability[];
  onChange: (patch: Partial<Agent>) => void;
  diagnostics: ReactNode;
  onRegister: () => void;
}) {
  return (
    <>
      <section className="admin-form-section">
        <h3>基础信息</h3>
        <div className="admin-form-grid">
          <label>
            显示名称
            <input
              value={a.name}
              required
              maxLength={80}
              onChange={(e) => onChange({ name: e.target.value })}
            />
          </label>
          <label>
            职责
            <select
              value={a.role}
              onChange={(e) =>
                onChange({ role: e.target.value as Agent["role"] })
              }
            >
              {Object.entries(ROLE_LABEL).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="admin-form-wide">
            简介
            <textarea
              value={a.description}
              maxLength={1000}
              rows={2}
              onChange={(e) => onChange({ description: e.target.value })}
            />
          </label>
        </div>
        <label className="admin-check">
          <input
            type="checkbox"
            checked={a.enabled}
            onChange={(e) => onChange({ enabled: e.target.checked })}
          />
          启用此教师 / 助手
        </label>
        <p className="admin-help">
          启用状态仅控制本地可用性，连接状态见下方诊断。
        </p>
      </section>
      <section className="admin-form-section">
        <h3>Knodo 绑定</h3>
        <div className="admin-form-grid">
          <label>
            Knodo Bot ID
            <input
              value={a.bot_id ?? ""}
              autoComplete="off"
              pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,127}"
              onChange={(e) => onChange({ bot_id: e.target.value || null })}
            />
          </label>
          <label>
            工作空间 ID
            <input
              value={a.workspace_id ?? ""}
              autoComplete="off"
              pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,127}"
              onChange={(e) =>
                onChange({ workspace_id: e.target.value || null })
              }
            />
          </label>
          <label>
            提示词版本
            <input
              value={a.prompt_version}
              maxLength={80}
              onChange={(e) => onChange({ prompt_version: e.target.value })}
            />
          </label>
        </div>
        <p className="admin-help">
          填写 ID 后仍需保存并主动测试。模型、提示词和插件在 Knodo 管理。
        </p>
      </section>
      <fieldset className="admin-form-section">
        <legend>能力关联</legend>
        {capabilities.length ? (
          capabilities.map((cap) => (
            <label key={cap.id} className="admin-check">
              <input
                type="checkbox"
                checked={a.capabilities.includes(cap.id)}
                onChange={(e) =>
                  onChange({
                    capabilities: e.target.checked
                      ? [...a.capabilities, cap.id]
                      : a.capabilities.filter((id) => id !== cap.id),
                  })
                }
              />
              <span>
                {cap.name}{" "}
                <small className="admin-muted">
                  {cap.enabled ? "" : "（本地登记已停用）"} ·{" "}
                  {cap.binding_scope === "WORKSPACE"
                    ? "工作空间共享"
                    : "助手个人"}
                </small>
              </span>
            </label>
          ))
        ) : (
          <div className="admin-empty">
            <p>尚未登记能力。先应用教师草稿，再去登记能力。</p>
            <button
              type="button"
              className="admin-button-quiet"
              onClick={onRegister}
            >
              应用草稿并登记能力
            </button>
          </div>
        )}
        {a.capabilities
          .filter((id) => !capabilities.some((cap) => cap.id === id))
          .map((id) => (
            <p className="admin-error" key={id}>
              未登记的能力引用：{id}
            </p>
          ))}
      </fieldset>
      <section className="admin-form-section">
        <h3>人工安全确认</h3>
        <label className="admin-check">
          <input
            type="checkbox"
            checked={a.remote_memory_disabled}
            onChange={(e) =>
              onChange({ remote_memory_disabled: e.target.checked })
            }
          />
          <span>我已在 Knodo 核对并关闭共享空间的自动记忆采集和召回</span>
        </label>
        <p className="admin-help">
          这是人工确认记录，不会远程修改设置，也不代表系统已检测。共享空间内其他教师可能同时受影响。
        </p>
      </section>
      <section className="admin-form-section">
        <h3>连接与输出协议诊断</h3>
        {diagnostics}
      </section>
      <details className="admin-technical">
        <summary>稳定标识</summary>
        <label>
          稳定标识
          <input value={a.id} readOnly />
        </label>
        <p>用于路由和会话引用，保持不变；可选中文本复制。</p>
      </details>
    </>
  );
}
export function CapabilityFields({
  capability: c,
  onChange,
}: {
  capability: Capability;
  onChange: (patch: Partial<Capability>) => void;
}) {
  return (
    <>
      <section className="admin-form-section">
        <h3>本地登记</h3>
        <div className="admin-form-grid">
          <label>
            名称
            <input
              value={c.name}
              required
              maxLength={80}
              onChange={(e) => onChange({ name: e.target.value })}
            />
          </label>
          <label>
            版本
            <input
              value={c.version}
              maxLength={64}
              onChange={(e) => onChange({ version: e.target.value })}
            />
          </label>
        </div>
        <label className="admin-check">
          <input
            type="checkbox"
            checked={c.enabled}
            onChange={(e) => onChange({ enabled: e.target.checked })}
          />
          启用本地能力登记
        </label>
        <p className="admin-help">本地登记不会安装或启用远端插件。</p>
      </section>
      <section className="admin-form-section">
        <h3>执行与作用范围</h3>
        <div className="admin-form-grid">
          <label>
            执行方式
            <select
              value={c.executor}
              onChange={(e) =>
                onChange({ executor: e.target.value as Capability["executor"] })
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
                  pattern="[A-Za-z0-9][A-Za-z0-9_-]{0,127}"
                  onChange={(e) =>
                    onChange({ plugin_id: e.target.value || null })
                  }
                />
              </label>
              <label>
                挂载位置
                <select
                  value={c.binding_scope}
                  onChange={(e) =>
                    onChange({
                      binding_scope: e.target
                        .value as Capability["binding_scope"],
                    })
                  }
                >
                  <option value="WORKSPACE">工作空间（共享）</option>
                  <option value="ASSISTANT">助手个人技能</option>
                </select>
              </label>
            </>
          ) : (
            <label>
              已安装的处理器标识
              <input
                value={c.handler ?? ""}
                maxLength={80}
                onChange={(e) => onChange({ handler: e.target.value || null })}
              />
            </label>
          )}
        </div>
        <p className="admin-help">
          空间插件影响该空间内的教师。远端安装及个人绑定请在 Knodo
          核对；本页不能检测助手个人技能。
        </p>
      </section>
      <fieldset className="admin-form-section">
        <legend>本地调用允许的上下文</legend>
        {(["course", "conversation", "personal_memory"] as const).map(
          (value) => (
            <label key={value} className="admin-check">
              <input
                type="checkbox"
                checked={c.allowed_context.includes(value)}
                onChange={(e) =>
                  onChange({
                    allowed_context: e.target.checked
                      ? [...c.allowed_context, value]
                      : c.allowed_context.filter((v) => v !== value),
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
        <p className="admin-help">仅允许业务调用按现有权限提供这些上下文。</p>
      </fieldset>
      <details className="admin-technical">
        <summary>契约与稳定标识</summary>
        <div className="admin-form-grid">
          <label>
            输入契约
            <input
              value={c.input_contract}
              maxLength={100}
              onChange={(e) => onChange({ input_contract: e.target.value })}
            />
          </label>
          <label>
            输出契约
            <input
              value={c.output_contract}
              maxLength={100}
              onChange={(e) => onChange({ output_contract: e.target.value })}
            />
          </label>
          <label className="admin-form-wide">
            能力标识
            <input value={c.id} readOnly />
          </label>
        </div>
        <p>契约是协议名称字符串；标识用于教师引用，保持不变。</p>
      </details>
    </>
  );
}
