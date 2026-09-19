import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchHealth } from "./api";

describe("fetchHealth", () => {
  afterEach(() => vi.restoreAllMocks());

  it("returns the local health payload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ status: "ok", request_id: "req-1" }),
      }),
    );
    await expect(fetchHealth("/health/live")).resolves.toEqual({ status: "ok", request_id: "req-1" });
  });
});
