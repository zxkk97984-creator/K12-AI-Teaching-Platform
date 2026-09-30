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
  render(<AutomaticMemory />);
  fireEvent.click(await screen.findByLabelText("允许教师使用个人记忆"));
  await waitFor(() =>
    expect(writes[0].body).toMatchObject({
      auto_enabled: true,
      use_enabled: false,
      base_revision: 1,
    }),
  );
});
