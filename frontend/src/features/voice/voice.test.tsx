import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { VoiceComposer } from "./VoiceComposer";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("VoiceComposer", () => {
  it("does not request a microphone when the provider is unavailable", () => {
    const getUserMedia = vi.fn();
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia },
    });
    render(<VoiceComposer preference="INPUT_ONLY" />);
    fireEvent.click(screen.getByTestId("voice-start"));
    expect(getUserMedia).not.toHaveBeenCalled();
    expect(screen.getByTestId("voice-status").textContent).toContain("语音不可用");
    expect(screen.getByTestId("voice-capability").textContent).toContain("未配置");
  });

  it("keeps text fallback available when voice is disabled", () => {
    const onSendText = vi.fn();
    render(<VoiceComposer preference="DISABLED" onSendText={onSendText} />);
    fireEvent.click(screen.getByTestId("voice-start"));
    expect(screen.getByRole("alert").textContent).toContain("文本输入仍然可用");
    expect(screen.getByTestId("voice-tts-state").textContent).toContain("文本不受影响");
  });

  it("renders an editable transcript only after an injected provider returns text", async () => {
    const stream = { getTracks: () => [{ stop: vi.fn() }] } as unknown as MediaStream;
    const recorder = {
      state: "inactive",
      mimeType: "audio/webm",
      start: vi.fn(function (this: { state: string }) { this.state = "recording"; }),
      stop: vi.fn(function (this: { state: string; onstop?: () => void }) {
        this.state = "inactive";
        this.onstop?.();
      }),
      ondataavailable: undefined as ((event: BlobEvent) => void) | undefined,
      onstop: undefined as (() => void) | undefined,
    };
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: { getUserMedia: vi.fn().mockResolvedValue(stream) },
    });
    vi.stubGlobal("MediaRecorder", vi.fn(() => recorder));
    render(
      <VoiceComposer
        preference="INPUT_ONLY"
        capability={{ inputState: "READY", outputState: "UNAVAILABLE", reason: "fixture" }}
        transcribe={vi.fn().mockResolvedValue("可编辑的转写")}
      />,
    );
    fireEvent.click(screen.getByTestId("voice-start"));
    await screen.findByTestId("voice-stop");
    fireEvent.click(screen.getByTestId("voice-stop"));
    expect(await screen.findByDisplayValue("可编辑的转写")).toBeTruthy();
    expect(screen.getByTestId("voice-send-text")).toBeTruthy();
  });
});
