import { saveQuizDraft, submitQuizAnswer, requestQuizHint, saveQuizPosition } from "./api";
import type { QuizAnswer, QuizSessionDTO } from "./types";

/** Shared by inline and full-page practice. Failed writes retain their keys. */
export class QuizRoundPersistence {
  private revisions = new Map<string, number>();
  private writes = new Map<string, Promise<unknown>>();
  private answerKeys = new Map<string, { hash: string; key: string }>();
  private hintKeys = new Map<string, string>();
  private positionWrites = new Map<string, Promise<unknown>>();
  position(session: string, index: number) {
    const pending = (this.positionWrites.get(session) ?? Promise.resolve()).catch(() => undefined)
      .then(() => saveQuizPosition(session,index));
    this.positionWrites.set(session,pending);
    return pending;
  }
  adopt(session: QuizSessionDTO) {
    for (const [id, draft] of Object.entries(session.drafts ?? {}))
      this.revisions.set(`${session.id}:${id}`, draft.revision);
  }
  save(session: string, question: string, answer: QuizAnswer, revision?: number) {
    const slot = `${session}:${question}`;
    const pending = (this.writes.get(slot) ?? Promise.resolve()).catch(() => undefined).then(async () => {
      const result = await saveQuizDraft(session, question, answer, revision ?? this.revisions.get(slot) ?? 0);
      this.revisions.set(slot, result.draft.revision);
      return result;
    });
    this.writes.set(slot, pending);
    return pending;
  }
  async submit(session: string, question: string, answer: QuizAnswer, suppliedKey?: string) {
    const slot = `${session}:${question}`;
    await this.writes.get(slot);
    const hash = JSON.stringify(answer);
    const old = this.answerKeys.get(slot);
    const key = suppliedKey ?? (old?.hash === hash ? old.key : `answer-${crypto.randomUUID()}`);
    this.answerKeys.set(slot, { hash, key });
    const result = await submitQuizAnswer(session, question, answer, key);
    return result;
  }
  async hint(session: string, question: string, level: number, suppliedKey?: string) {
    const slot = `${session}:${question}:${level}`;
    const key = suppliedKey ?? this.hintKeys.get(slot) ?? `hint-${crypto.randomUUID()}`;
    this.hintKeys.set(slot, key);
    const result = await requestQuizHint(session, question, level, key);
    return result;
  }
}
