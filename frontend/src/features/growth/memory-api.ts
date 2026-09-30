import { ensureCsrfToken } from "../identity/api";
import type { components } from "../../shared/types/generated/learning";

export async function memoryRequest<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = await ensureCsrfToken();
  const response = await fetch(path, {
    method,
    headers,
    credentials: "same-origin",
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.error?.message ?? data?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : Array.isArray(detail)
          ? detail
              .map((item: { msg?: string }) => item.msg ?? "字段不合法")
              .join("；")
          : "请求失败，请稍后重试",
    );
  }
  return data as T;
}

export type MemoryItem = components["schemas"]["MemoryItemView"];
export type MemoryOverview = components["schemas"]["MemoryOverviewView"];
export const CATEGORY_LABELS: Record<string, string> = {
  PREFERENCE: "交流偏好",
  INTEREST: "兴趣爱好",
  GOAL: "长期目标",
  PLAN: "计划安排",
  EXPERIENCE: "个人经历",
  LEARNING: "学习情况",
};
