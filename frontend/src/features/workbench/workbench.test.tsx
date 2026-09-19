import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../identity/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../identity/api")>();
  return { ...actual, getMe: vi.fn(), logout: vi.fn() };
});

import { ApiError, getMe } from "../identity/api";
import { WorkbenchShell } from "./WorkbenchShell";
import { densityForStage } from "./density";
import { WorkbenchPage } from "../../pages/workbench/WorkbenchPage";
import type { MeResponse, Stage } from "../identity/types";

const getMeMock = vi.mocked(getMe);

function studentMe(
  overrides: { stage?: Stage; grade?: number | null; onboarded?: boolean } = {},
): MeResponse {
  const { stage = "JUNIOR", grade = 8, onboarded = true } = overrides;
  return {
    user: {
      id: "00000000-0000-0000-0000-000000000001",
      username: "synthetic.student",
      role: "student",
      is_active: true,
    },
    profile: {
      stage: onboarded ? stage : null,
      grade: onboarded ? grade : null,
      revision: 3,
      onboarding_completed: onboarded,
    },
    preferences: {
      preferred_style: "VISUAL",
      interests: ["算法"],
      proactive_guidance_enabled: true,
      voice_preference: "DISABLED",
      profile_revision: 3,
    },
  };
}

const adminMe: MeResponse = {
  user: {
    id: "00000000-0000-0000-0000-0000000000aa",
    username: "synthetic.admin",
    role: "admin",
    is_active: true,
  },
  profile: null,
  preferences: null,
};

function text(node: HTMLElement | null): string {
  return node?.textContent ?? "";
}

beforeEach(() => {
  getMeMock.mockReset();
});

afterEach(() => {
  cleanup();
  document.title = "";
});

describe("workbench shell honesty", () => {
  it("shows the four regions with explicit not-connected states and no fake statistics", () => {
    render(<WorkbenchShell me={studentMe()} />);

    const shell = screen.getByTestId("workbench-shell");
    expect(shell.getAttribute("data-density")).toBe("compact");
    expect(text(screen.getByTestId("stage-summary"))).toContain("初中（7–9年级） · 8 年级");
    expect(text(screen.getByTestId("chapter-navigation"))).toContain("归属任务：T08");
    expect(text(screen.getByTestId("activity-slot"))).toContain("归属任务：T14");
    expect(text(screen.getByTestId("lesson-canvas"))).toContain("归属任务：T08");

    const body = text(shell);
    for (const forbidden of ["学习天数", "正确率", "连续打卡", "示例回复", "正在生成"]) {
      expect(body).not.toContain(forbidden);
    }
    expect(screen.queryByRole("link", { name: "课程" })).toBeNull();
    expect(screen.getByText("课程").getAttribute("aria-disabled")).toBe("true");
  });

  it("keeps the teacher area disabled without simulated replies", () => {
    render(<WorkbenchShell me={studentMe()} />);
    const teacherPanel = screen.getByRole("tabpanel", { name: "教师" });
    const capabilityPanel = within(teacherPanel).getByTestId("teacher-capability");
    expect(text(capabilityPanel)).toContain("教师未启用");
    expect(capabilityPanel.getAttribute("data-state")).toBe("disabled");
    // No simulated conversation surface: no message list, no fake speaker lines.
    expect(within(teacherPanel).queryAllByRole("article")).toHaveLength(0);
    expect(within(teacherPanel).queryAllByRole("log")).toHaveLength(0);
    expect(text(teacherPanel)).not.toMatch(/老师：|Tutor：|正在生成…|生成中/);
    expect(text(teacherPanel)).toContain("已记录偏好：图示讲解");
  });

  it("renders no fake chapters inside the chapter navigation", () => {
    render(<WorkbenchShell me={studentMe()} />);
    const nav = screen.getByRole("navigation", { name: "章节导航" });
    expect(within(nav).queryAllByRole("listitem")).toHaveLength(0);
    expect(text(within(nav).getByTestId("chapter-navigation"))).toContain("不展示任何占位课程");
  });

  it("gives low grades a spacious density and fewer simultaneous panels", () => {
    render(<WorkbenchShell me={studentMe({ stage: "PRIMARY_LOWER", grade: 2 })} />);
    expect(screen.getByTestId("workbench-shell").getAttribute("data-density")).toBe("spacious");
    expect(screen.queryByTestId("compact-panels")).toBeNull();
    expect(text(screen.getByTestId("lesson-canvas"))).toContain("课程内容尚未接通");
  });

  it("keeps compact density panels for junior students", () => {
    render(<WorkbenchShell me={studentMe()} />);
    expect(screen.getByTestId("compact-panels")).not.toBeNull();
  });

  it("moves between workbench tabs with the keyboard", () => {
    render(<WorkbenchShell me={studentMe()} />);
    const canvasTab = screen.getByRole("tab", { name: "学习内容" });
    const teacherTab = screen.getByRole("tab", { name: "教师" });
    expect(canvasTab.getAttribute("aria-selected")).toBe("true");
    canvasTab.focus();
    fireEvent.keyDown(canvasTab, { key: "ArrowRight" });
    expect(teacherTab.getAttribute("aria-selected")).toBe("true");
    expect(document.activeElement).toBe(teacherTab);
    fireEvent.keyDown(teacherTab, { key: "ArrowLeft" });
    expect(canvasTab.getAttribute("aria-selected")).toBe("true");
  });
});

describe("densityForStage", () => {
  it("maps the four stages to two densities", () => {
    expect(densityForStage("PRIMARY_LOWER")).toBe("spacious");
    expect(densityForStage("PRIMARY_UPPER")).toBe("spacious");
    expect(densityForStage("JUNIOR")).toBe("compact");
    expect(densityForStage("SENIOR")).toBe("compact");
    expect(densityForStage(null)).toBe("compact");
  });
});

describe("workbench page states", () => {
  it("renders the real shell for an authenticated student", async () => {
    getMeMock.mockResolvedValue(studentMe());
    render(<WorkbenchPage />);
    expect(text(screen.getByRole("status"))).toContain("正在读取学习档案…");
    const shell = await screen.findByTestId("workbench-shell");
    expect(shell).not.toBeNull();
    expect(text(screen.getByTestId("stage-summary"))).toContain("初中（7–9年级） · 8 年级");
    expect(document.title).toBe("教学工作台 · 霜铃 K12");
  });

  it("shows a real 503 error state with request id and retries", async () => {
    getMeMock.mockRejectedValueOnce(
      new ApiError(503, "SERVICE_UNAVAILABLE", "数据库尚未就绪", "req-503"),
    );
    render(<WorkbenchPage />);
    const alert = await screen.findByRole("alert");
    expect(text(alert)).toContain("暂时无法打开工作台");
    expect(text(alert)).toContain("数据库尚未就绪");
    expect(text(alert)).toContain("req-503");

    getMeMock.mockResolvedValueOnce(studentMe());
    fireEvent.click(screen.getByRole("button", { name: "重新加载" }));
    expect(await screen.findByTestId("workbench-shell")).not.toBeNull();
    expect(getMeMock).toHaveBeenCalledTimes(2);
  });

  it("asks for onboarding instead of inventing a stage", async () => {
    getMeMock.mockResolvedValue(studentMe({ onboarded: false }));
    render(<WorkbenchPage />);
    const note = await screen.findByTestId("needs-stage");
    expect(text(note)).toContain("先完成学段选择");
    const link = within(note).getByRole("link", { name: /去选择学段/ });
    expect(link.getAttribute("href")).toBe("/onboarding");
  });

  it("keeps administrators out of the student workbench", async () => {
    getMeMock.mockResolvedValue(adminMe);
    render(<WorkbenchPage />);
    const notice = await screen.findByTestId("admin-notice");
    expect(text(notice)).toContain("管理端能力");
    expect(screen.queryByTestId("workbench-shell")).toBeNull();
  });
});
