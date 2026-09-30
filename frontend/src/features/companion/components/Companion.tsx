import { useEffect, useRef, useState, type CSSProperties } from "react";
import { useLocation } from "react-router-dom";
import { ConversationCompactOptions, ConversationContent } from "../../conversation/ConversationContent";
import { useConversation } from "../../conversation/ConversationProvider";
import { CompanionHeadAvatar } from "../CompanionAvatar";
import { useCompanionPosition } from "../hooks/useCompanionPosition";
import { placePanel, type PanelRect } from "../lib/geometry";
import { COMPANION_PETS } from "../lib/sprite";
import type { CompanionAiState } from "../types";
import { CompanionSprite } from "./CompanionSprite";
import "../companion.css";
import { useCompanionPet } from "../hooks/useCompanionPet";
import type { CompanionPageContext } from "../openCompanion";

export function Companion({ userId }: { userId: string }) {
  const [pet, selectPet] = useCompanionPet(userId);
  const [open, setOpen] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [petError, setPetError] = useState("");
  const [narration, setNarration] = useState<{ speaking: boolean; subtitle: string }>({ speaking: false, subtitle: "" });
  const [narrowViewport, setNarrowViewport] = useState(() => window.innerWidth <= 767);
  const [rect, setRect] = useState<PanelRect | null>(null);
  const dock = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const location = useLocation();
  const codeSurface = location.pathname === "/code";
  const position = useCompanionPosition(userId, codeSurface ? ".codelab-pet-slot" : undefined);
  const { controller, run, sending, draft, error } = useConversation();
  const autoMinimized = useRef(false);
  const minimizedBeforeAuto = useRef(false);
  const chapterId = location.pathname.startsWith("/chapters/")
    ? location.pathname.split("/")[2]
    : undefined;
  const sessionId = ["/lessons", "/conversations"].includes(location.pathname)
    ? new URLSearchParams(location.search).get("session")
    : null;
  useEffect(() => {
    if (sessionId) void controller.select(sessionId);
  }, [sessionId, controller]);
  useEffect(() => {
    const show = (event: Event) => {
      const context = (event as CustomEvent<CompanionPageContext>).detail;
      if (context) {
        controller.setPageContext({
          page_type: context.page_type,
          visible_section: context.visible_section?.slice(0, 200),
          selected_text: context.selected_text?.slice(0, 4000),
          content_kind: context.content_kind,
          content_id: context.content_id,
          content_version: context.content_version,
          section_index: context.section_index,
          knowledge_points: context.knowledge_points?.slice(0, 12),
          activity_type: context.activity_type,
          quiz_session_id: context.quiz_session_id,
          question_id: context.question_id,
          interactive_session_id: context.interactive_session_id,
          interactive_scene_id: context.interactive_scene_id,
          interactive_prompt_id: context.interactive_prompt_id,
        });
        if (context.conversationId) {
          void controller.select(context.conversationId).then(() => {
            if (context.suggestedQuestion && !controller.getSnapshot().draft.trim())
              controller.setDraft(context.suggestedQuestion);
          });
          setOpen(true);
          setMinimized(false);
          setOptionsOpen(false);
          return;
        }
        const activeChapter = controller.getSnapshot().detail?.chapter_id;
        const needsNewSession = context.chapterId
          ? activeChapter !== context.chapterId
          : Boolean(activeChapter);
        if (needsNewSession) {
          void controller.start(context.chapterId).then(() => {
            if (context.suggestedQuestion && !controller.getSnapshot().draft.trim())
              controller.setDraft(context.suggestedQuestion);
          });
        } else if (context.suggestedQuestion && !controller.getSnapshot().draft.trim()) {
          controller.setDraft(context.suggestedQuestion);
        }
      }
      setOpen(true);
      setMinimized(false);
      setOptionsOpen(false);
    };
    window.addEventListener("companion:open", show);
    return () => window.removeEventListener("companion:open", show);
  }, [controller]);
  useEffect(() => {
    const update = (event: Event) => setNarration((event as CustomEvent<{ speaking: boolean; subtitle: string }>).detail);
    window.addEventListener("companion:narration", update);
    return () => window.removeEventListener("companion:narration", update);
  }, []);
  useEffect(() => { controller.setPageContext(null); }, [controller, location.pathname, location.search]);
  useEffect(() => { setOpen(false); setOptionsOpen(false); }, [location.pathname]);
  useEffect(() => {
    const update = () => setNarrowViewport(window.innerWidth <= 767);
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);
  const readingSurface = location.pathname === "/resources" || location.pathname.startsWith("/books/");
  const mobileConversation = narrowViewport && location.pathname.startsWith("/conversations");
  useEffect(() => {
    const shouldMinimize = readingSurface || mobileConversation || narrowViewport || codeSurface;
    if (shouldMinimize && !autoMinimized.current) {
      minimizedBeforeAuto.current = minimized;
      autoMinimized.current = true;
    }
    if (shouldMinimize && !open && !minimized) setMinimized(true);
    if (!shouldMinimize && autoMinimized.current) {
      autoMinimized.current = false;
      setMinimized(minimizedBeforeAuto.current);
    }
  }, [readingSurface, mobileConversation, narrowViewport, codeSurface, open, minimized]);
  useEffect(() => {
    if (!open) return;
    const update = () => {
      if (dock.current)
        setRect(placePanel(dock.current.getBoundingClientRect()));
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [open, position.position]);
  useEffect(() => {
    if (!open || !rect) return;
    panel.current?.querySelector<HTMLButtonElement>('button[aria-label="收起对话"]')?.focus();
    // Only focus on opening, not on drag/resize.
  }, [open, Boolean(rect)]);
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape" && open) {
        setOpen(false);
        setOptionsOpen(false);
        dock.current?.focus();
      }
    };
    window.addEventListener("keydown", close);
    return () => window.removeEventListener("keydown", close);
  }, [open]);
  let state: CompanionAiState = narration.speaking ? "speaking" : "idle";
  if (!narration.speaking && (sending || run?.status === "QUEUED" || run?.status === "RUNNING"))
    state = "thinking";
  else if (!narration.speaking && (error || run?.status === "FAILED" || run?.status === "STALE"))
    state = "confused";
  else if (draft && !narration.speaking) state = "listening";
  else if (!narration.speaking && run?.status === "SUCCEEDED") state = "happy";
  const close = () => {
    setOpen(false);
    setOptionsOpen(false);
    dock.current?.focus();
  };
  return (
    <>
      <div
        className="companion-dock"
        data-testid="companion-dock"
        data-minimized={minimized}
        style={{
          left: position.position.x,
          top: position.position.y,
          "--codelab-pet-left": `${position.position.x}px`,
          "--codelab-pet-top": `${position.position.y}px`,
        } as CSSProperties}
      >
        {!minimized ? (
          <button
            className="companion-minimize"
            aria-label="最小化桌宠"
            onClick={() => {
              setMinimized(true);
              setOpen(false);
              setOptionsOpen(false);
            }}
          >
            −
          </button>
        ) : null}
        <button
          ref={dock}
          className="companion-toggle"
          aria-label={`打开${pet.displayName}学习助手`}
          aria-expanded={open}
          aria-controls="companion-panel"
          onPointerDown={position.pointerDown}
          onPointerMove={position.pointerMove}
          onPointerUp={position.pointerUp}
          onPointerCancel={position.pointerCancel}
          onKeyDown={position.keyDown}
          onClick={() => {
            if (!position.wasDragged()) {
              setMinimized(false);
              if (open) setOptionsOpen(false);
              setOpen((v) => !v);
            }
          }}
        >
          {minimized ? (
            <CompanionHeadAvatar pet={pet} size={54} />
          ) : (
            <>
              <CompanionSprite
                petId={pet.id}
                state={position.movement ?? state}
              />
              <span className="companion-name">{narration.speaking ? `${pet.displayName}正在朗读` : `${pet.displayName} · 问问老师`}</span>
            </>
          )}
        </button>
      </div>
      {open && rect ? (
        <aside
          ref={panel}
          id="companion-panel"
          className="companion-panel"
          aria-label={`${pet.displayName}对话面板`}
          role="dialog"
          aria-modal="false"
          style={rect}
        >
          <header className="companion-panel-header od-row">
            <span className="companion-panel-avatar" aria-hidden="true"><CompanionSprite petId={pet.id} state="idle" size={40} /></span>
            <div className="od-field od-fill"><strong>{pet.displayName}</strong><span>{state === "thinking" ? "正在整理思路…" : "你的随身学习伙伴"}</span></div>
            <div className="companion-panel-tools od-row">
              <button type="button" className="secondary" aria-label="新建对话" title="新建对话" disabled={Boolean(sending) || state === "thinking"} onClick={() => { setOptionsOpen(false); void controller.start(); }}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg></button>
              <button type="button" className="secondary" aria-label="更多选项" title={optionsOpen ? "收起更多选项" : "更多选项"} aria-expanded={optionsOpen} aria-controls="companion-extra-options" onClick={() => setOptionsOpen((value) => !value)}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h.01M12 12h.01M19 12h.01" strokeWidth="3" /></svg></button>
              <a href={controller.getSnapshot().detail ? `/conversations?session=${controller.getSnapshot().detail!.id}` : "/conversations"} aria-label="打开完整对话" title="打开完整对话" onClick={() => { setOpen(false); setOptionsOpen(false); }}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 3h7v7M21 3l-11 11M10 3H3v18h18v-7" /></svg></a>
              <button type="button" className="secondary" aria-label="收起对话" title="收起对话" onClick={close}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button>
            </div>
          </header>
          <div id="companion-extra-options" className="companion-extra-options" hidden={!optionsOpen} style={optionsOpen ? undefined : { display: "none" }}>
            {optionsOpen ? <><label className="companion-picker">选择学习伙伴<select value={pet.id} onChange={(event) => { setPetError(""); void selectPet(event.target.value).then(() => setOptionsOpen(false)).catch((caught) => setPetError(caught instanceof Error ? caught.message : "桌宠选择未保存")); }}>{COMPANION_PETS.map((p) => <option key={p.id} value={p.id}>{p.displayName}</option>)}</select></label>
              {petError && <p role="alert">{petError}</p>}
              <ConversationCompactOptions chapterId={chapterId} onSelect={() => setOptionsOpen(false)} /></> : null}
          </div>
          <ConversationContent chapterId={chapterId} compact />
          <footer className="companion-panel-footer">AI 回答请结合课程核对</footer>
        </aside>
      ) : null}
    </>
  );
}
