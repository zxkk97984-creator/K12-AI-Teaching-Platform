import type { components } from "../../shared/types/generated/admin";
export type Agent = Required<components["schemas"]["AgentDefinition"]>;
export type Capability = Required<
  components["schemas"]["CapabilityDefinition"]
>;
export type Route = components["schemas"]["RouteDefinition"];
export type Configuration = Omit<
  components["schemas"]["RegistryView"],
  "data"
> & {
  data: Omit<
    components["schemas"]["RegistryData"],
    "agents" | "capabilities"
  > & { agents: Agent[]; capabilities: Capability[] };
};
export const ROLE_LABEL = {
  teacher: "学生教师",
  designer: "教研制作",
  memory: "内部记忆整理",
};
export const OPERATIONS: Record<string, string> = {
  TEACH_TURN: "教学对话",
  CODE_FEEDBACK: "代码反馈",
  QUIZ_DRAFT: "题目生成",
  LESSON_PACKAGE_DRAFT: "课程生成",
  MEMORY_EXTRACT: "个人记忆整理",
};
export const OPERATION_ROLE: Record<string, Agent["role"]> = {
  TEACH_TURN: "teacher",
  CODE_FEEDBACK: "teacher",
  QUIZ_DRAFT: "designer",
  LESSON_PACKAGE_DRAFT: "designer",
  MEMORY_EXTRACT: "memory",
};
const EXECUTION_KEYS = [
  "bot_id",
  "capabilities",
  "id",
  "prompt_version",
  "role",
  "workspace_id",
] as const;
// Matches Python json.dumps(sort_keys=True, ensure_ascii=True), including spaces.
function pythonJSON(value: unknown): string {
  if (Array.isArray(value)) return "[" + value.map(pythonJSON).join(", ") + "]";
  return JSON.stringify(value ?? null).replace(
    /[\u007f-\uffff]/g,
    (char) => "\\u" + char.charCodeAt(0).toString(16).padStart(4, "0"),
  );
}
export function executionText(agent: Agent): string {
  return (
    "{" +
    EXECUTION_KEYS.map(
      (key) => JSON.stringify(key) + ": " + pythonJSON(agent[key]),
    ).join(", ") +
    "}"
  );
}
export async function targetSignature(agent: Agent) {
  const bytes = await crypto.subtle.digest(
    "SHA-256",
    new TextEncoder().encode(executionText(agent)),
  );
  return Array.from(new Uint8Array(bytes), (byte) =>
    byte.toString(16).padStart(2, "0"),
  )
    .join("")
    .slice(0, 20);
}
export function routeIssues(
  route: Route,
  routes: Route[],
  agents: Agent[],
): string[] {
  const issues: string[] = [];
  if (
    routes.filter(
      (r) => r.operation === route.operation && r.stage === route.stage,
    ).length > 1
  )
    issues.push("同一任务和学段规则重复");
  const agent = agents.find((a) => a.id === route.agent_id);
  if (!agent) return [...issues, "助手引用不存在"];
  if (!agent.enabled) issues.push("助手已停用");
  if (agent.role !== OPERATION_ROLE[route.operation])
    issues.push("助手职责与任务不匹配");
  if (!agent.bot_id || !agent.workspace_id) issues.push("助手尚未填写完整绑定");
  if (
    agent.id !== "legacy-tutor" &&
    agent.role !== "designer" &&
    !agent.remote_memory_disabled
  )
    issues.push("尚未人工确认远端记忆关闭");
  return issues;
}
