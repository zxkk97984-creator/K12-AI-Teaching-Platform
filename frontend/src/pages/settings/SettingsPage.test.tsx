import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import * as identityApi from "../../features/identity/api";
import type { MeResponse } from "../../features/identity/types";
import { SettingsPage } from "./SettingsPage";

const me: MeResponse = {
  user: { id: "11111111-1111-1111-1111-111111111111", username: "student", role: "student", is_active: true },
  profile: { stage: "PRIMARY_LOWER", grade: 2, revision: 0, onboarding_completed: true, nickname: null, avatar_url: null },
  preferences: { preferred_style: "EXAMPLE", teacher_style: "AUTO", companion_pet_id: "shuangling", interests: [], proactive_guidance_enabled: true, voice_preference: "DISABLED", profile_revision: 0 },
};

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("saves nickname, exact grade, matching stage and teacher style", async () => {
  vi.spyOn(identityApi, "getMe").mockResolvedValue(me);
  const updatedProfile: MeResponse = {
    ...me,
    profile: { ...me.profile!, stage: "SENIOR", grade: 10, nickname: "小星", revision: 1 },
    preferences: { ...me.preferences!, profile_revision: 1 },
  };
  const patchProfile = vi.spyOn(identityApi, "patchProfile").mockResolvedValue(updatedProfile);
  const patchPreferences = vi.spyOn(identityApi, "patchPreferences").mockResolvedValue({
    ...updatedProfile,
    preferences: { ...updatedProfile.preferences!, teacher_style: "SOCRATIC", profile_revision: 2 },
  });
  render(<SettingsPage />);
  await screen.findByRole("heading", { name: "设置你的学习空间" });
  fireEvent.change(screen.getByLabelText(/昵称/), { target: { value: "小星" } });
  fireEvent.click(screen.getByRole("radio", { name: "高一" }));
  fireEvent.change(screen.getByLabelText("教师风格"), { target: { value: "SOCRATIC" } });
  fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
  await waitFor(() => expect(patchProfile).toHaveBeenCalledWith({ base_revision: 0, nickname: "小星", stage: "SENIOR", grade: 10 }));
  await waitFor(() => expect(patchPreferences).toHaveBeenCalledWith(expect.objectContaining({
    base_revision: 1, teacher_style: "SOCRATIC", preferred_style: "EXAMPLE",
  })));
  expect(await screen.findByText(/已保存到当前账号/)).toBeTruthy();
  expect(document.querySelector(".settings-current-grade")?.textContent).toBe("高一");
});

it("keeps a changed teacher style visible when saving fails", async () => {
  vi.spyOn(identityApi, "getMe").mockResolvedValue(me);
  vi.spyOn(identityApi, "patchPreferences").mockRejectedValue(new identityApi.ApiError(409, "REVISION_CONFLICT", "档案已更新", null));
  render(<SettingsPage />);
  const style = await screen.findByLabelText("教师风格") as HTMLSelectElement;
  fireEvent.change(style, { target: { value: "GENTLE" } });
  fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
  expect((await screen.findByRole("alert")).textContent).toContain("档案已更新");
  expect(style.value).toBe("GENTLE");
});

it("restores six pet images and saves the selected companion on this account", async () => {
  vi.spyOn(identityApi, "getMe").mockResolvedValue(me);
  const patchProfile = vi.spyOn(identityApi, "patchProfile");
  const patchPreferences = vi.spyOn(identityApi, "patchPreferences").mockResolvedValue({
    ...me,
    profile: { ...me.profile!, revision: 1 },
    preferences: { ...me.preferences!, companion_pet_id: "anya", profile_revision: 1 },
  });
  render(<SettingsPage />);
  const picker = await screen.findByRole("group", { name: "选择桌宠形象" });
  expect(within(picker).getAllByRole("radio")).toHaveLength(6);
  fireEvent.click(within(picker).getByRole("radio", { name: "阿尼亚" }));
  expect(screen.getByText("已选择阿尼亚，保存设置后生效。")).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
  await waitFor(() => expect(patchPreferences).toHaveBeenCalledWith(expect.objectContaining({
    base_revision: 0,
    companion_pet_id: "anya",
  })));
  expect(patchProfile).not.toHaveBeenCalled();
  expect(await screen.findByText("当前陪伴你的是阿尼亚。")).toBeTruthy();
});

it("shows server-confirmed avatar and allows account-level removal", async () => {
  vi.spyOn(identityApi, "getMe").mockResolvedValue(me);
  const withAvatar: MeResponse = {
    ...me,
    profile: { ...me.profile!, avatar_url: "/api/v1/me/avatar?v=hash", revision: 1 },
    preferences: { ...me.preferences!, profile_revision: 1 },
  };
  const upload = vi.spyOn(identityApi, "uploadAvatar").mockResolvedValue(withAvatar);
  const remove = vi.spyOn(identityApi, "deleteAvatar").mockResolvedValue(me);
  render(<SettingsPage />);
  await screen.findByRole("heading", { name: "设置你的学习空间" });
  fireEvent.change(document.querySelector("#settings-avatar-file")!, { target: { files: [new File(["png"], "portrait.png", { type: "image/png" })] } });
  await waitFor(() => expect(upload).toHaveBeenCalledOnce());
  expect(await screen.findByText("头像已保存到当前账号。")).toBeTruthy();
  expect(document.querySelector(".settings-profile .account-avatar img")?.getAttribute("src")).toBe("/api/v1/me/avatar?v=hash");
  fireEvent.click(screen.getByRole("button", { name: "移除头像" }));
  await waitFor(() => expect(remove).toHaveBeenCalledOnce());
  expect(await screen.findByText("头像已移除。")).toBeTruthy();
});
