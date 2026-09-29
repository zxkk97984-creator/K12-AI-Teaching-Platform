import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../identity/api";
import { getChapter, getReadingState, postPageContext, postReadingEvent } from "./api";
import type { ChapterDetailDTO, ReadingEventRequest, ReadingStateDTO } from "./types";

export type ReaderState =
  | { kind: "loading" }
  | { kind: "ready"; chapter: ChapterDetailDTO }
  | { kind: "error"; status: number | null; message: string; requestId: string | null };

export type PageContextView = {
  sourceId: string;
  revision: number;
  blockId: string | null;
  sectionKey: string | null;
  selectedText: string | null;
  selectedChars: number;
  updatedAt: number;
};

export function newEventId(prefix: string): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function errorState(reason: unknown): ReaderState {
  if (reason instanceof ApiError) {
    return { kind: "error", status: reason.status, message: reason.message, requestId: reason.requestId };
  }
  return {
    kind: "error",
    status: null,
    message: reason instanceof Error ? reason.message : "未知错误",
    requestId: null,
  };
}

/**
 * Loads one chapter revision plus the reader's own last position, and keeps the
 * page context server-validated. Behaviour events are best-effort: a failed
 * event must never break reading, and no event records mastery.
 */
export function useReader(chapterId: string, requestedRevision?: number) {
  const [state, setState] = useState<ReaderState>({ kind: "loading" });
  const [resume, setResume] = useState<ReadingStateDTO | null>(null);
  const [context, setContext] = useState<PageContextView | null>(null);
  const [contextError, setContextError] = useState<string | null>(null);
  const sentEvents = useRef<Set<string>>(new Set());
  const visitKey = useRef<string | null>(null);
  const visitId = useRef<string | null>(null);
  const positionTimer = useRef<number | null>(null);
  const pendingPosition = useRef<string | null>(null);
  const lastPosition = useRef<string | null>(null);
  const positionSequence = useRef(0);
  const stateRef = useRef<ReaderState>(state);
  stateRef.current = state;

  // Leaving or switching a chapter must never keep the previous selection.
  useEffect(() => {
    const key = `${chapterId}:${requestedRevision ?? "latest"}`;
    if (visitKey.current === key) return;
    visitKey.current = key;
    visitId.current = newEventId(`visit-${chapterId.replace(/-/g, "").slice(0, 8)}`);
    setResume(null);
    setContext(null);
    setContextError(null);
    sentEvents.current = new Set();
    pendingPosition.current = null;
    lastPosition.current = null;
    positionSequence.current = 0;
    if (positionTimer.current !== null) window.clearTimeout(positionTimer.current);
    positionTimer.current = null;
  }, [chapterId, requestedRevision]);

  const sendEvent = useCallback(async (payload: ReadingEventRequest) => {
    try {
      await postReadingEvent(payload);
    } catch {
      /* behaviour records are best effort */
    }
  }, []);

  useEffect(() => {
    let active = true;
    setState({ kind: "loading" });
    Promise.all([
      getChapter(chapterId, requestedRevision),
      getReadingState(chapterId, requestedRevision).catch(() => null),
    ])
      .then(([chapter, readingState]) => {
        if (!active) return;
        setState({ kind: "ready", chapter });
        if (readingState) setResume(readingState);
        void sendEvent({
          client_event_id: `${visitId.current ?? newEventId("visit")}-enter`,
          chapter_id: chapter.chapter_id,
          revision: chapter.revision,
          event_kind: "ENTER",
          section_key: null,
          block_id: null,
          selected_text_length: null,
        });
      })
      .catch((reason: unknown) => {
        if (active) setState(errorState(reason));
      });
    return () => {
      active = false;
    };
  }, [chapterId, requestedRevision, sendEvent]);

  const selectText = useCallback(
    async (blockId: string | null, rawText: string) => {
      const current = stateRef.current;
      if (current.kind !== "ready") return;
      const chapter = current.chapter;
      try {
        const validated = await postPageContext({
          chapter_id: chapter.chapter_id,
          revision: chapter.revision,
          block_id: blockId,
          selected_text: rawText,
        });
        setContext({
          sourceId: validated.source_id,
          revision: validated.revision,
          blockId: validated.block_id,
          sectionKey: validated.section_key,
          selectedText: validated.selected_text,
          selectedChars: validated.selected_text_chars,
          updatedAt: Date.now(),
        });
        setContextError(null);
      const clientEventId = `select-${visitId.current ?? "visit"}-${
        validated.block_id ?? "chapter"
      }-${Math.min(validated.selected_text_chars, 9999)}`;
        if (!sentEvents.current.has(clientEventId)) {
          sentEvents.current.add(clientEventId);
          void sendEvent({
            client_event_id: clientEventId,
            chapter_id: chapter.chapter_id,
            revision: chapter.revision,
            event_kind: "SELECT_TEXT",
            block_id: validated.block_id,
            selected_text_length: validated.selected_text_chars,
          });
        }
      } catch (reason: unknown) {
        setContext(null);
        setContextError(reason instanceof Error ? reason.message : "选中文字校验失败");
      }
    },
    [sendEvent],
  );

  const clearContext = useCallback(() => {
    setContext(null);
    setContextError(null);
  }, []);

  const recordPosition = useCallback(
    (blockId: string | null) => {
      const current = stateRef.current;
      if (current.kind !== "ready" || !blockId) return;
      const chapter = current.chapter;
      if (lastPosition.current === blockId) return;
      pendingPosition.current = blockId;
      if (positionTimer.current !== null) window.clearTimeout(positionTimer.current);
      positionTimer.current = window.setTimeout(() => {
        const nextBlock = pendingPosition.current;
        if (!nextBlock || lastPosition.current === nextBlock) return;
        lastPosition.current = nextBlock;
        positionSequence.current += 1;
        const clientEventId = `position-${visitId.current ?? "visit"}-${positionSequence.current}-${nextBlock}`;
        void sendEvent({
          client_event_id: clientEventId,
          chapter_id: chapter.chapter_id,
          revision: chapter.revision,
          event_kind: "BLOCK_VIEW",
          block_id: nextBlock,
          section_key: null,
          selected_text_length: null,
        });
      }, 250);
    },
    [sendEvent],
  );

  return { state, resume, context, contextError, selectText, clearContext, recordPosition };
}
