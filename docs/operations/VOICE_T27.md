# T27 voice boundary

The local build exposes a reusable `VoiceComposer` state boundary but does not
claim an ASR/TTS provider is ready.

- `backend/app/modules/voice/capability.py` returns `UNAVAILABLE` for both
  input and output until a separately authorized provider is configured.
- `frontend/src/features/voice/VoiceComposer.tsx` requests `getUserMedia`
  only after an explicit click and only when the capability says `READY`.
  Permission rejection, cancellation, transcription failure, and unmount all
  release tracks and leave text input available.
- Transcription is injected as a provider function and the returned text is
  editable before the caller sends it. TTS has no browser speechSynthesis
  fallback; unavailable/failed TTS never blocks text.
- Fixtures test state transitions only. They do not upload audio or establish
  real provider readiness. T05 identity settings remain the source of the
  persisted voice preference; this task does not rebuild that settings flow.

When a real provider is authorized, the adapter must implement the injected
transcribe contract, preserve the explicit consent boundary, and add separate
live evidence. Knodo web UI voice controls are not treated as an API contract.
