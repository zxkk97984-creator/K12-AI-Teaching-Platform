import { afterEach, describe, expect, it, vi } from "vitest";

import { ApiError } from "../identity/api";
import { getChapter, listCourses, postPageContext } from "./api";
import type { ChapterDetailDTO } from "./types";

afterEach(() => {
  vi.restoreAllMocks();
  document.cookie = "sl_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => JSON.stringify(body),
  };
}

describe("content api client", () => {
  it("unwraps the course list and surfaces the error envelope", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse(200, { items: [] }));
    vi.stubGlobal("fetch", fetchMock);
    await expect(listCourses()).resolves.toEqual({ items: [] });

    fetchMock.mockResolvedValueOnce(
      jsonResponse(503, {
        error: { code: "SERVICE_UNAVAILABLE", message: "数据库尚未就绪", request_id: "req-x" },
      }),
    );
    await expect(listCourses()).rejects.toMatchObject({
      status: 503,
      message: "数据库尚未就绪",
      requestId: "req-x",
    });
  });

  it("sends the double-submit CSRF header on writes and keeps the session cookie", async () => {
    document.cookie = "sl_csrf=csrf-token-123";
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse(200, { chapter_id: "x" }));
    vi.stubGlobal("fetch", fetchMock);
    await postPageContext({ chapter_id: "11111111-1111-1111-1111-111111111111", revision: 1 });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = init.headers as Headers;
    expect(headers.get("X-CSRF-Token")).toBe("csrf-token-123");
    expect(init.credentials).toBe("same-origin");
    expect(init.method).toBe("POST");
  });

  it("treats 404 as a real, readable error and informs the identity listener on 401", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        jsonResponse(404, { error: { code: "NOT_FOUND", message: "章节不可用" } }),
      )
      .mockResolvedValueOnce(
        jsonResponse(401, { error: { code: "UNAUTHORIZED", message: "登录已失效" } }),
      );
    vi.stubGlobal("fetch", fetchMock);
    const unauthorized = vi.fn();
    window.addEventListener("identity:unauthorized", unauthorized);

    const notFound = await getChapter("unknown").catch((error: unknown) => error);
    expect(notFound).toBeInstanceOf(ApiError);
    expect(notFound).toMatchObject({ status: 404, message: "章节不可用" });

    const expired = await getChapter("unknown").catch((error: unknown) => error);
    expect(expired).toMatchObject({ status: 401 });
    expect(unauthorized).toHaveBeenCalledTimes(1);
    window.removeEventListener("identity:unauthorized", unauthorized);
  });

  it("keeps the generated content DTO typing available to callers", () => {
    const revision: ChapterDetailDTO["revision"] = 1;
    expect(revision).toBe(1);
  });
});
