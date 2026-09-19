import { afterEach, describe, expect, it, vi } from "vitest";
import { ensureCsrfToken } from "./api";

describe("identity api", () => {
  afterEach(() => vi.restoreAllMocks());

  it("uses a same-origin CSRF token", async () => {
    document.cookie = "sl_csrf=csrf-1; path=/";
    await expect(ensureCsrfToken()).resolves.toBe("csrf-1");
  });

  it("reports a structured server error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: false,
      status: 401,
      text: async () => JSON.stringify({ error: { code: "UNAUTHORIZED", message: "登录已失效", request_id: "r1" } }),
    }));
    const { getMe } = await import("./api");
    await expect(getMe()).rejects.toMatchObject({ status: 401, code: "UNAUTHORIZED", requestId: "r1" });
  });
});
