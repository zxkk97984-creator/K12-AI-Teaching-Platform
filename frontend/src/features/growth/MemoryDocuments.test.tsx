import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { MemoryDocuments } from "./MemoryDocuments";

const DOCUMENT_ID = "11111111-1111-1111-1111-111111111111";

type Version = {
  revision: number;
  title: string;
  content_markdown: string;
  action: string;
  created_at: string;
};

let versions: Version[];
let current: { id: string; title: string; is_primary: boolean; category: string; revision: number; ai_enabled: boolean; content_markdown: string; updated_at: string } | null;
let calls: Array<{ path: string; method: string; headers: Headers }>;

const respond = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => {
  versions = [];
  current = null;
  calls = [];
  document.cookie = "sl_csrf=test-token";
  vi.stubGlobal("confirm", vi.fn(() => true));
  vi.stubGlobal("fetch", vi.fn(async (input: string, init?: RequestInit) => {
    const path = String(input);
    const method = init?.method ?? "GET";
    calls.push({ path, method, headers: new Headers(init?.headers) });
    if (path === "/api/v1/growth/documents" && method === "GET") {
      return respond({ items: current ? [current] : [] });
    }
    if (path === "/api/v1/growth/documents" && method === "POST") {
      current = {
        id: DOCUMENT_ID,
        title: "个人记忆.md",
        is_primary: true,
        category: "NOTE",
        revision: 1,
        ai_enabled: true,
        content_markdown: "",
        updated_at: "2026-09-27T00:00:00Z",
      };
      versions = [{ revision: 1, title: current.title, content_markdown: "", action: "CREATE", created_at: current.updated_at }];
      return respond({ ...current, versions });
    }
    if (path === "/api/v1/growth/documents/" + DOCUMENT_ID && method === "GET") {
      return respond({ ...current, versions: [...versions].reverse() });
    }
    if (path === "/api/v1/growth/documents/" + DOCUMENT_ID && method === "PATCH") {
      const patch = JSON.parse(String(init?.body));
      const before = current;
      if (!before || patch.base_revision !== before.revision) return respond({ detail: "文档已被更新" }, 409);
      const updated = {
        ...before,
        revision: before.revision + 1,
        content_markdown: patch.content_markdown,
        ai_enabled: before.ai_enabled,
      };
      current = updated;
      versions.push({ revision: updated.revision, title: updated.title, content_markdown: updated.content_markdown, action: "EDIT", created_at: updated.updated_at });
      return respond({ ...updated, versions: [...versions].reverse() });
    }
    if (path.endsWith("/restore") && method === "POST") {
      const body = JSON.parse(String(init?.body));
      const old = versions.find((item) => item.revision === body.version_revision);
      const before = current;
      if (!before || !old || body.base_revision !== before.revision) return respond({ detail: "版本冲突" }, 409);
      const updated = { ...before, revision: before.revision + 1, content_markdown: old.content_markdown };
      current = updated;
      versions.push({ revision: updated.revision, title: updated.title, content_markdown: updated.content_markdown, action: "RESTORE", created_at: updated.updated_at });
      return respond({ ...updated, versions: [...versions].reverse() });
    }
    const match = path.match(/\/versions\/(\d+)$/);
    if (match) return respond(versions.find((item) => item.revision === Number(match[1])));
    return respond({ detail: "not found" }, 404);
  }));
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("creates an account document, reads it back, and restores without losing versions", async () => {
  const view = render(<MemoryDocuments />);
  fireEvent.click(await screen.findByRole("button", { name: "创建个人记忆文档" }));
  expect(await screen.findByText("账号已保存 · 版本 1")).toBeTruthy();
  expect(current?.ai_enabled).toBe(true);
  expect(screen.queryByText("仅自己可见，默认不提供给 AI 教师")).toBeNull();
  expect(screen.queryByRole("checkbox")).toBeNull();
  expect(calls.find((call) => call.method === "POST")?.headers.get("X-CSRF-Token")).toBe("test-token");

  fireEvent.click(screen.getByRole("button", { name: "编辑 Markdown" }));
  fireEvent.change(screen.getByLabelText("Markdown 内容"), { target: { value: "# 我的记忆\n\n喜欢看图理解。" } });
  fireEvent.click(screen.getByRole("button", { name: "保存文档" }));
  expect(await screen.findByText("文档已保存为版本 2")).toBeTruthy();
  expect(await screen.findByText("喜欢看图理解。")).toBeTruthy();

  view.unmount();
  render(<MemoryDocuments />);
  expect(await screen.findByText("喜欢看图理解。")).toBeTruthy();
  fireEvent.click(screen.getByText("版本记录（2）"));
  fireEvent.click(screen.getAllByRole("button", { name: "查看" })[1]);
  expect(await screen.findByLabelText("版本 1 预览")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "恢复此版本" }));
  await waitFor(() => expect(screen.getByText("已恢复为新版本 3")).toBeTruthy());
  expect(versions.map((item) => item.revision)).toEqual([1, 2, 3]);
  expect(current?.content_markdown).toBe("");
});
