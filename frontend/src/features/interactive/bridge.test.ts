import { describe, expect, it } from "vitest";
import { validatedMessage } from "./bridge";

const frame = {} as Window;
const expected = { instanceId: "instance-1", sessionId: "session-1", revisionId: "version-1" };
const good = {
  source: frame, origin: "null",
  data: { channel: "k12-interactive-v1", instance_id: "instance-1", session_id: "session-1", revision_id: "version-1", message_id: "event-1", type: "checkpoint", payload: { game_state: { level: 2 } } },
};

describe("sandbox message boundary", () => {
  it("accepts only the current frame, instance, activity and version", () => {
    expect(validatedMessage(good, frame, expected)?.type).toBe("checkpoint");
    expect(validatedMessage({ ...good, source: {} as Window }, frame, expected)).toBeNull();
    expect(validatedMessage({ ...good, origin: "http://127.0.0.1" }, frame, expected)).toBeNull();
    expect(validatedMessage(good, frame, { ...expected, instanceId: "replacement" })).toBeNull();
    expect(validatedMessage(good, frame, { ...expected, revisionId: "version-2" })).toBeNull();
  });
  it("rejects unknown messages and oversized payloads", () => {
    expect(validatedMessage({ ...good, data: { ...good.data, type: "navigate" } }, frame, expected)).toBeNull();
    expect(validatedMessage({ ...good, data: { ...good.data, payload: { state: "x".repeat(65536) } } }, frame, expected)).toBeNull();
  });
  it('requires explicit supported workspace registration and typed experiment data', () => {
    const message = (type: string, payload: unknown) => validatedMessage({...good, data: {...good.data, type, payload}}, frame, expected);
    expect(message('workspace_ready', {version: 1, commands: ['scene', 'reset']})).not.toBeNull();
    expect(message('workspace_ready', {version: 1, commands: ['navigate']})).toBeNull();
    expect(message('workspace_ready', {version: 2, commands: []})).toBeNull();
    expect(message('checkpoint', {game_state: ['invalid']})).toBeNull();
    expect(message('activity_state', {scene_id: 'first', game_state: {}, hint: '观察变化'})).not.toBeNull();
    expect(message('activity_state', {scene_id: 'first', game_state: {}, hint: 123})).toBeNull();
    expect(message('scene_changed', {scene_id: {id: 'first'}})).toBeNull();
  });
});
