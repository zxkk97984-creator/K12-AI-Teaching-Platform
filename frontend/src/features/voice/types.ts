import type { VoicePreference } from "../identity/types";

export type VoiceInteractionState =
  | "IDLE"
  | "REQUESTING_PERMISSION"
  | "RECORDING"
  | "TRANSCRIBING"
  | "READY_TO_SEND"
  | "CANCELLED"
  | "ERROR";

export type VoiceCapability = {
  inputState: "UNAVAILABLE" | "READY";
  outputState: "UNAVAILABLE" | "READY";
  reason: string;
  provider?: string | null;
};

export const LOCAL_VOICE_CAPABILITY: VoiceCapability = {
  inputState: "UNAVAILABLE",
  outputState: "UNAVAILABLE",
  reason: "尚未配置经过授权的 ASR/TTS provider；文本学习仍然可用。",
  provider: null,
};

export type VoiceComposerProps = {
  preference: VoicePreference;
  capability?: VoiceCapability;
  transcribe?: (audio: Blob) => Promise<string>;
  onSendText?: (text: string) => void;
};
