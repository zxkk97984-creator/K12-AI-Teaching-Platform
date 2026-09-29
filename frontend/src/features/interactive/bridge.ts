export const CHANNEL = "k12-interactive-v1";
export type BridgeMessage = {
  channel: string; instance_id: string; session_id: string; revision_id: string;
  message_id: string; type: string; payload: unknown;
};
const TYPES = new Set(["ready", "scene_changed", "request_narration", "checkpoint", "complete", "ask_teacher", "error"]);
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
  try { if (JSON.stringify(data.payload ?? null).length > 65536) return null; }
  catch { return null; }
  return data as BridgeMessage;
}
