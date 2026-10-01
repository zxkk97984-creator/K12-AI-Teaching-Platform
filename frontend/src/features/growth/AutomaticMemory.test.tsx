import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AutomaticMemory } from "./AutomaticMemory";
import type { MemoryOverview } from "./memory-api";
let data: MemoryOverview;
let writes: { path: string; body: Record<string, unknown> }[];
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
  writes = [];
  data = {
    total: 1,
    offset: 0,
    has_more: false,
    settings: { auto_enabled: true, use_enabled: true, revision: 1 },
    content_revision: 1,
    last_updated_at: null,
    summary_markdown: "- 喜欢天文",
    notice: "仅供个性化参考",
    tasks: [],
    items: [
      {
        id: "memory-1",
        key: "interest:astronomy",
        category: "INTEREST",
        statement: "喜欢天文",
        status: "ACTIVE",
        manual: false,
        revision: 1,
        valid_until: null,
        updated_at: "2026-09-29T00:00:00Z",
        sources: [],
      },
    ],
  };
  document.cookie = "sl_csrf=memory-test";
  vi.stubGlobal("confirm", () => true);
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: string, init?: RequestInit) => {
      const path = String(input);
      if (init?.method && init.method !== "GET") {
        const body = JSON.parse(String(init.body));
        writes.push({ path, body });
        if (path.endsWith("/settings"))
          data.settings = {
            ...data.settings,
            use_enabled: body.use_enabled,
            revision: 2,
          };
        if (body.action === "EDIT")
          data.items[0] = {
            ...data.items[0],
            statement: body.statement,
            manual: true,
            revision: 2,
          };
        if (body.action === "FORGET")
          data.items[0] = { ...data.items[0], status: "REMOVED", revision: 3 };
      }
      return new Response(JSON.stringify(data), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("edits and forgets an automatic item while keeping a visible control", async () => {
  render(<AutomaticMemory />);
  fireEvent.click(
    await screen.findByRole("button", { name: "更正" }),
  );
  fireEvent.change(screen.getByLabelText("更正记忆"), {
    target: { value: "现在更喜欢生物" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存更正" }));
  await waitFor(() =>
    expect(writes[0].body).toMatchObject({
      action: "EDIT",
      base_revision: 1,
      statement: "现在更喜欢生物",
    }),
  );
  await screen.findByText("由你维护");
  fireEvent.click(screen.getByRole("button", { name: "遗忘" }));
  await waitFor(() =>
    expect(writes[1].body).toMatchObject({
      action: "FORGET",
      base_revision: 2,
    }),
  );
  await waitFor(() => expect(screen.queryByText("现在更喜欢生物")).toBeNull());
  fireEvent.click(screen.getByLabelText("显示已遗忘的条目"));
  expect(await screen.findByRole("button", { name: "重新记住" })).toBeTruthy();
});
it("can stop recall without disabling automatic collection", async () => {
  render(<AutomaticMemory settingsOpen />);
  fireEvent.click(await screen.findByLabelText("用于 AI 辅导"));
  await waitFor(() =>
    expect(writes[0].body).toMatchObject({
      auto_enabled: true,
      use_enabled: false,
      base_revision: 1,
    }),
  );
});

it("distinguishes empty memory from filter misses and hides unnecessary pagination", async () => {
  data.items = [];
  data.total = 0;
  render(<AutomaticMemory />);
  expect(await screen.findByText("还没有自动记忆")).toBeTruthy();
  expect(screen.queryByLabelText("记忆分页")).toBeNull();
  fireEvent.change(screen.getByRole("searchbox"), { target: { value: "不存在" } });
  expect(await screen.findByText("没有找到匹配的记忆")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "清除筛选" }));
  expect(await screen.findByText("还没有自动记忆")).toBeTruthy();
});
it("restores the real setting after a rejected update", async () => {
  const fetchBefore = globalThis.fetch;
  vi.stubGlobal("fetch", vi.fn((input: string, init?: RequestInit) => {
    if (String(input).endsWith("/settings")) return Promise.resolve(new Response(JSON.stringify({ detail: "更新失败" }), { status: 503 }));
    return fetchBefore(input, init);
  }));
  render(<AutomaticMemory settingsOpen />);
  fireEvent.click(await screen.findByLabelText("用于 AI 辅导"));
  await waitFor(() => expect((screen.getByLabelText("用于 AI 辅导") as HTMLInputElement).checked).toBe(true));
  expect(screen.getAllByText("更新失败").length).toBeGreaterThan(0);
  expect(writes).toHaveLength(0);
});

it("shows loading failure with retry instead of claiming there is no memory", async () => {
  const fetchBefore = globalThis.fetch;
  let fail = true;
  vi.stubGlobal("fetch", vi.fn((input: string, init?: RequestInit) => fail
    ? Promise.resolve(new Response(JSON.stringify({ detail: "读取失败" }), { status: 503 }))
    : fetchBefore(input, init)));
  render(<AutomaticMemory />);
  expect(await screen.findByText("读取失败")).toBeTruthy();
  expect(screen.queryByText("还没有自动记忆")).toBeNull();
  fail = false;
  fireEvent.click(screen.getByRole("button", { name: "重新读取" }));
  expect(await screen.findByText("喜欢天文")).toBeTruthy();
  expect(screen.queryByText("读取失败")).toBeNull();
});
