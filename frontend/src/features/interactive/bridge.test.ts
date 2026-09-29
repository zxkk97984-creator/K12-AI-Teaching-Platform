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
});
