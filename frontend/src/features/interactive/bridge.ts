export const CHANNEL = "k12-interactive-v1";
export type BridgeMessage = {
  channel: string; instance_id: string; session_id: string; revision_id: string;
  message_id: string; type: string; payload: unknown;
};
const TYPES = new Set(["ready", "scene_changed", "request_narration", "checkpoint", "complete", "ask_teacher", "error", "workspace_ready", "activity_state", "command_result"]);
export const WORKSPACE_COMMANDS = ["scene", "pause", "reset", "complete", "demonstrate"] as const;
export type WorkspaceCommand = typeof WORKSPACE_COMMANDS[number];
export type PlaybackStep = { scene_id: string; prompt_id: string };
export function isObject(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
export function validatedMessage(
  event: Pick<MessageEvent, "source" | "origin" | "data">,
  frameWindow: Window | null | undefined,
  expected: { instanceId: string; sessionId: string; revisionId: string },
): BridgeMessage | null {
  if (!frameWindow || event.source !== frameWindow || event.origin !== "null" || !isObject(event.data)) return null;
  const data = event.data;
  if (data.channel !== CHANNEL || data.instance_id !== expected.instanceId || data.session_id !== expected.sessionId || data.revision_id !== expected.revisionId) return null;
  if (typeof data.message_id !== "string" || data.message_id.length < 1 || data.message_id.length > 100 || typeof data.type !== "string" || !TYPES.has(data.type)) return null;
  try { if (new TextEncoder().encode(JSON.stringify(data.payload ?? null)).length > 65536) return null; }
  catch { return null; }
  const p = isObject(data.payload) ? data.payload : {};
  if (data.type === "scene_changed" && (typeof p.scene_id !== "string" || !/^[A-Za-z0-9_-]{1,100}$/.test(p.scene_id))) return null;
  if (data.type === "request_narration" && (typeof p.prompt_id !== "string" || !/^[A-Za-z0-9_-]{1,100}$/.test(p.prompt_id))) return null;
  if (data.type === "checkpoint" && !isObject(p.game_state)) return null;
  if (data.type === "complete" && !isObject(p.game_result)) return null;
  if (data.type === "workspace_ready") {
    if (p.version !== 1 || !Array.isArray(p.commands) || p.commands.length > WORKSPACE_COMMANDS.length || p.commands.some(c => !WORKSPACE_COMMANDS.includes(c as WorkspaceCommand))) return null;
    if (p.playback_steps !== undefined && (!p.commands.includes('demonstrate') || !Array.isArray(p.playback_steps) || p.playback_steps.length < 1 || p.playback_steps.length > 100 || p.playback_steps.some(step => !isObject(step) || typeof step.scene_id !== 'string' || typeof step.prompt_id !== 'string' || !/^[A-Za-z0-9_-]{1,100}$/.test(step.scene_id) || !/^[A-Za-z0-9_-]{1,100}$/.test(step.prompt_id)))) return null;
  }
  if (data.type === "activity_state" && (typeof p.scene_id !== "string" || typeof p.hint !== "string" || p.hint.length > 500 || !isObject(p.game_state))) return null;
  if (data.type === "command_result" && (typeof p.ok !== "boolean" || (p.error !== undefined && (typeof p.error !== "string" || p.error.length > 500)))) return null;
  return data as BridgeMessage;
}
