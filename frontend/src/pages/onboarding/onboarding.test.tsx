import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const navigate = vi.fn();
vi.mock("../../features/identity/session", () => ({
  navigate: (path: string) => navigate(path),
}));
vi.mock("../../features/identity/api", async () => {
  const actual = await vi.importActual<typeof import("../../features/identity/api")>(
    "../../features/identity/api",
  );
  return { ...actual, getMe: vi.fn(), patchProfile: vi.fn(), patchPreferences: vi.fn() };
});

import * as identity from "../../features/identity/api";
import { OnboardingPage } from "./OnboardingPage";

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("OnboardingPage", () => {
  it("lets an in-progress Chinese composition finish instead of submitting", async () => {
    // R28: the interests field is free text inside a form, so Enter during IME
    // composition must not fire the submit.
    vi.mocked(identity.getMe).mockResolvedValue({
      user: { id: "u1", username: "合成学生", role: "student", is_active: true },
      profile: { stage: "JUNIOR", grade: 8, revision: 1, onboarding_completed: false },
      preferences: {
        preferred_style: "VISUAL",
        interests: [],
        proactive_guidance_enabled: true,
        voice_preference: "DISABLED",
        profile_revision: 1,
      },
    } as never);
    vi.mocked(identity.patchProfile).mockResolvedValue({ profile: { revision: 2 } } as never);
    vi.mocked(identity.patchPreferences).mockResolvedValue({} as never);

    render(<OnboardingPage />);
    const interests = await screen.findByLabelText(/兴趣/);

    fireEvent.keyDown(interests, { key: "Enter", keyCode: 229, isComposing: true });
    fireEvent.submit(interests.closest("form")!);
    // The composition keystroke itself must not have triggered a save.
    await waitFor(() => expect(identity.patchPreferences).not.toHaveBeenCalled());

    fireEvent.keyDown(interests, { key: "Enter", keyCode: 13 });
    fireEvent.submit(interests.closest("form")!);
    await waitFor(() => expect(identity.patchPreferences).toHaveBeenCalled());
  });
});
