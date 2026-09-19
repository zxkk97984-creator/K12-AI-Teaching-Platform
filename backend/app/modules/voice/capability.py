from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

VoiceState = Literal["UNAVAILABLE", "READY"]


@dataclass(frozen=True)
class VoiceCapability:
    input_state: VoiceState
    output_state: VoiceState
    reason: str
    provider: str | None = None

    @property
    def ready(self) -> bool:
        return self.input_state == "READY" or self.output_state == "READY"

    def as_public(self) -> dict[str, str | bool | None]:
        return {
            "input_state": self.input_state,
            "output_state": self.output_state,
            "ready": self.ready,
            "provider": self.provider,
            "reason": self.reason,
        }


def local_voice_capability() -> VoiceCapability:
    """Return the honest local state until an authorized ASR/TTS provider exists."""

    return VoiceCapability(
        input_state="UNAVAILABLE",
        output_state="UNAVAILABLE",
        reason="尚未配置经过授权的 ASR/TTS provider；文本学习仍然可用。",
    )
