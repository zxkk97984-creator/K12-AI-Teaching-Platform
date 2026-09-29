import { describe, expect, it } from "vitest";
import { buildQuestionDocument, validatePlayerMessage } from "./IsolatedQuestionPlayer";
import type { QuizQuestionDTO } from "./types";

const question: QuizQuestionDTO = {
  id: "question-1", question_key: "q1", position: 0, type: "SINGLE_CHOICE",
  stem: "选哪一个？", source_refs: [], hint_limit: 2, hints_used: 0, hints: [],
  attempts_used: 0, max_attempts: 2,
  options: [{ key: "A", text: "甲" }, { key: "B", text: "乙" }],
};

function playerEvent(data: unknown, origin = "null", source: Window | null = window) {
  return new MessageEvent("message", { data, origin, source });
}

const envelope = {
  channel: "k12-quiz-player-v1", token: "token-1", sessionId: "session-1",
  questionId: "question-1", type: "submit", data: "A",
};

describe("sandboxed question player boundary", () => {
  it("accepts only the current opaque frame and a valid answer", () => {
    expect(validatePlayerMessage(playerEvent(envelope), window, "token-1", "session-1", question)?.data).toBe("A");
    expect(validatePlayerMessage(playerEvent(envelope, location.origin), window, "token-1", "session-1", question)).toBeNull();
    expect(validatePlayerMessage(playerEvent(envelope), null, "token-1", "session-1", question)).toBeNull();
    expect(validatePlayerMessage(playerEvent(envelope), window, "wrong", "session-1", question)).toBeNull();
    expect(validatePlayerMessage(playerEvent({ ...envelope, sessionId: "other" }), window, "token-1", "session-1", question)).toBeNull();
    expect(validatePlayerMessage(playerEvent({ ...envelope, data: "not-an-option" }), window, "token-1", "session-1", question)).toBeNull();
    expect(validatePlayerMessage(playerEvent({ ...envelope, type: "complete", data: { score: 100 } }), window, "token-1", "session-1", question)).toBeNull();
  });

  it("requires an exact ordering permutation and JSON booleans", () => {
    const ordering: QuizQuestionDTO = { ...question, type: "ORDERING", items: [{ key: "x", text: "一" }, { key: "y", text: "二" }] };
    expect(validatePlayerMessage(playerEvent({ ...envelope, data: ["y", "x"] }), window, "token-1", "session-1", ordering)).not.toBeNull();
    expect(validatePlayerMessage(playerEvent({ ...envelope, data: ["x", "x"] }), window, "token-1", "session-1", ordering)).toBeNull();
    const trueFalse: QuizQuestionDTO = { ...question, type: "TRUE_FALSE" };
    expect(validatePlayerMessage(playerEvent({ ...envelope, data: false }), window, "token-1", "session-1", trueFalse)).not.toBeNull();
    expect(validatePlayerMessage(playerEvent({ ...envelope, data: "FALSE" }), window, "token-1", "session-1", trueFalse)).toBeNull();
  });

  it("escapes structured text before inserting it into fixed srcdoc", () => {
    const document = buildQuestionDocument({
      channel: "k12-quiz-player-v1", token: "token-1", sessionId: "session-1",
      questionId: "question-1", parentOrigin: location.origin, type: "SINGLE_CHOICE",
      stem: "</script><script>alert(1)</script>", options: question.options ?? [], items: [], value: null, disabled: false, hintDisabled: false,
    });
    expect(document).not.toContain("allow-same-origin");
    expect(document).toContain("connect-src 'none'");
    expect(document).not.toContain("</script><script>alert(1)</script>");
    expect(document).toContain("\\u003c/script>");
  });
});
