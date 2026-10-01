import { webcrypto } from "node:crypto";
import { afterEach, expect, it, vi } from "vitest";
import { targetSignature, routeIssues, type Agent } from "./admin-ai-state";
const agent: Agent = {
  id: "primary",
  name: "教师",
  role: "teacher",
  bot_id: "bot-primary",
  workspace_id: "shared-space",
  prompt_version: '版本😀, "v1"\n',
  capabilities: ["skill-one", "skill-two"],
  description: "",
  enabled: true,
  remote_memory_disabled: true,
};
afterEach(() => vi.unstubAllGlobals());
it("matches the backend Python signature including Unicode, escapes, separators and array order", async () => {
  vi.stubGlobal("crypto", webcrypto);
  // Expected digest produced by backend target_signature / Python json.dumps.
  expect(await targetSignature(agent)).toBe("b51a9fa8f74aaa841764");
  expect(
    await targetSignature({
      ...agent,
      name: "新显示名称",
      description: "新说明",
    }),
  ).toBe(await targetSignature(agent));
  expect(await targetSignature({ ...agent, bot_id: "different" })).not.toBe(
    await targetSignature(agent),
  );
});
it("flags duplicate and invalid draft routes without restricting a teacher to a single stage", () => {
  const routes = [
    {
      operation: "TEACH_TURN",
      stage: "PRIMARY_LOWER" as const,
      agent_id: "primary",
    },
    {
      operation: "TEACH_TURN",
      stage: "PRIMARY_UPPER" as const,
      agent_id: "primary",
    },
  ];
  expect(routeIssues(routes[0], routes, [agent])).toEqual([]);
  expect(routeIssues(routes[0], [...routes, routes[0]], [agent])).toContain(
    "同一任务和学段规则重复",
  );
  expect(
    routeIssues(routes[0], routes, [{ ...agent, enabled: false }]),
  ).toContain("助手已停用");
  expect(
    routeIssues({ ...routes[0], agent_id: "unknown" }, routes, [agent]),
  ).toContain("助手引用不存在");
});
