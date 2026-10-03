import { useEffect, useRef, useState, type CSSProperties } from "react";
import { createPortal } from "react-dom";
import { useLocation } from "react-router-dom";
import { createLazyPage } from "../../../app/routing/lazyPage";
import { useConversation } from "../../conversation/ConversationProvider";
import { CompanionHeadAvatar } from "../CompanionAvatar";
import { useCompanionPosition } from "../hooks/useCompanionPosition";
import { useCompanionDisplayMode, type CompanionDisplayMode } from "../hooks/useCompanionDisplayMode";
import { useCompanionPanel, type PanelGesture } from "../hooks/useCompanionPanel";
import { COMPANION_PETS } from "../lib/sprite";
import type { CompanionAiState } from "../types";
import { CompanionSprite } from "./CompanionSprite";
import "../companion.css";
import { useCompanionPet } from "../hooks/useCompanionPet";
import type { CompanionPageContext } from "../openCompanion";
import { useLearningTeacher } from "../LearningTeacherContext";

// The dock and its state stay mounted. Load the conversation renderer only
// when its panel is actually opened, sharing the existing provider/controller.
const ConversationContent = createLazyPage(() => import("../../conversation/ConversationContent").then(m => ({ default: m.ConversationContent })), "对话").Page;
const ConversationCompactOptions = createLazyPage(() => import("../../conversation/ConversationContent").then(m => ({ default: m.ConversationCompactOptions })), "对话设置").Page;

export function Companion({ userId }: { userId: string }) {
  const [pet, selectPet] = useCompanionPet(userId);
  const [open, setOpen] = useState(false);
  const [displayMode, setDisplayMode] = useCompanionDisplayMode(userId);
  const minimized = displayMode === "compact";
  const [optionsOpen, setOptionsOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [petError, setPetError] = useState("");
  const [narration, setNarration] = useState<{ speaking: boolean; subtitle: string }>({ speaking: false, subtitle: "" });
  const dock = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLElement>(null);
  const location = useLocation();
  const previousPath = useRef(location.pathname);
  const codeSurface = location.pathname === "/code";
  const interactiveSurface = location.pathname.startsWith("/interactive/");
  const headerSurface = !interactiveSurface && !codeSurface;
  const compactAtHeader = minimized && headerSurface;
  const learningTeacher = useLearningTeacher();
  const [learningContext, setLearningContext] = useState("");

  const position = useCompanionPosition(userId, minimized ? codeSurface ? ".codelab-pet-slot" : headerSurface ? ".app-pet-slot" : undefined : undefined, compactAtHeader ? ".app-sidebar, .k12-mobile-nav, .k12-mobile-settings, [data-pet-avoid], .page-toolbar, .history-records, .practice-session, .practice-detail-header, .od-library-tools, .interactive-filters, .interactive-card, .library-book-card, .settings-panel, .memory-tabs, .app-topbar-title, .app-topbar-account, .conv-composer, .conv-quick-prompts" : undefined);
  const panelPosition = useCompanionPanel(open, dock, position.position);
  const { rect } = panelPosition;
  const panelPointerEvents = { onPointerMove: panelPosition.pointerMove, onPointerUp: panelPosition.pointerEnd, onPointerCancel: panelPosition.pointerEnd, onLostPointerCapture: panelPosition.pointerEnd };
  const { controller, run, sending, draft, error } = useConversation();
  useEffect(() => { void controller.initialize(); }, [controller]);
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
      if (location.pathname.startsWith("/interactive/")) {
        setLearningContext(learningTeacher.beforeOpen(context?.interactive_prompt_id ?? undefined) ?? "");
        setOpen(true);
        setOptionsOpen(false);
        return;
      }
      if (context) {
        controller.setPageContext({
          chapter_id:context.chapter_id ?? context.chapterId, chapter_title:context.chapter_title, chapter_revision:context.chapter_revision,
          content_block_id:context.content_block_id,
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
        if (context.conversationId && !controller.getSnapshot().detail) {
          void controller.select(context.conversationId).then(() => {
            if (context.suggestedQuestion && !controller.getSnapshot().draft.trim())
              controller.setDraft(context.suggestedQuestion);
          });
          setOpen(true);
          setOptionsOpen(false);
          return;
        }
        // Page context changes within one free conversation.
        if (context.suggestedQuestion && !controller.getSnapshot().draft.trim())
          controller.setDraft(context.suggestedQuestion);

      }
      setOpen(true);
      setOptionsOpen(false);
    };
    window.addEventListener("companion:open", show);
    return () => window.removeEventListener("companion:open", show);
  }, [controller, learningTeacher, location.pathname]);
  useEffect(() => {
    learningTeacher.setVisible(open && interactiveSurface);
    return () => learningTeacher.setVisible(false);
  }, [open, interactiveSurface, learningTeacher]);
  useEffect(() => {
    const update = (event: Event) => setNarration((event as CustomEvent<{ speaking: boolean; subtitle: string }>).detail);
    window.addEventListener("companion:narration", update);
    return () => window.removeEventListener("companion:narration", update);
  }, []);
  useEffect(() => { controller.setPageContext(null); }, [controller, location.pathname, location.search]);
  useEffect(() => {
    if (previousPath.current === location.pathname) return;
    previousPath.current = location.pathname;
    // Keep the dialogue visible and continuous during navigation.
    setOptionsOpen(false);
  }, [location.pathname, pinned]);
  const hasRect = Boolean(rect);
  useEffect(() => {
    const element = panel.current;
    if (!open || !pinned || !element?.showPopover) return;
    // A manual popover uses the browser's top layer, above ordinary page overlays.
    element.showPopover();
    return () => { if (element.matches(":popover-open")) element.hidePopover(); };
  }, [open, pinned, hasRect]);
  useEffect(() => {
    if (!open || !rect) return;
    panel.current?.querySelector<HTMLButtonElement>('button[aria-label="收起对话"]')?.focus();
    // Only focus on opening, not on drag/resize.
  }, [open, hasRect]);
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key === "Escape" && open && !document.querySelector("dialog:modal")) {
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
      {interactiveSurface && position.dragging ? <div className="companion-drag-shield" aria-hidden="true" /> : null}
      <div
        className="companion-dock"
        data-testid="companion-dock"
        data-compact={compactAtHeader}
        data-minimized={minimized}
        style={{
          left: position.position.x,
          top: position.position.y,
          "--interactive-pet-left": `${position.position.x}px`,
          "--interactive-pet-top": `${position.position.y}px`,
          "--codelab-pet-left": `${position.position.x}px`,
          "--codelab-pet-top": `${position.position.y}px`,
        } as CSSProperties}
      >
        {!minimized ? (
          <button
            type="button"
            className="companion-minimize"
            aria-label="缩小桌宠"
            title="缩成头像"
            onClick={() => {
              setDisplayMode("compact");
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
              if (interactiveSurface && !open) setLearningContext(learningTeacher.beforeOpen() ?? "");
              if (open) setOptionsOpen(false);
              setOpen((v) => !v);
            }
          }}
        >
          {minimized ? (
            <CompanionHeadAvatar pet={pet} size={codeSurface ? 36 : headerSurface ? 38 : 54} />
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
      {open && rect ? createPortal(
        <aside
          ref={panel}
          id="companion-panel"
          className={`companion-panel${interactiveSurface ? " companion-panel--learning" : ""}`}
          data-pinned={pinned}
          data-adjusting={panelPosition.active}
          popover={pinned ? "manual" : undefined}
          aria-label={`${pet.displayName}对话面板`}
          role="dialog"
          aria-modal="false"
          style={rect}
        >
          <header className="companion-panel-header od-row" title="拖动标题栏移动弹窗"
            onPointerDown={(event) => panelPosition.pointerDown(event, "move")}
            {...panelPointerEvents}>
            <span className="companion-panel-avatar" aria-hidden="true"><CompanionSprite petId={pet.id} state="idle" size={40} /></span>
            <div className="od-field od-fill"><strong>{pet.displayName}</strong><span>{state === "thinking" ? "正在整理思路…" : "你的随身学习伙伴"}</span></div>
            <div className="companion-panel-tools od-row">
              <button type="button" className="secondary companion-pin" aria-label={pinned ? "取消置顶" : "置顶对话"} title={pinned ? "取消置顶" : "置顶对话：保持在页面前面"} aria-pressed={pinned} onClick={() => setPinned((value) => !value)}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M9 3h6M9 3v6l-3 4v2h12v-2l-3-4V3M12 15v6" /></svg></button>
              <button type="button" className="secondary" aria-label="新建对话" title="新建对话" disabled={Boolean(sending) || state === "thinking"} onClick={() => { setOptionsOpen(false); void controller.start(); }}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg></button>
              <button type="button" className="secondary" aria-label="更多选项" title={optionsOpen ? "收起更多选项" : "更多选项"} aria-expanded={optionsOpen} aria-controls="companion-extra-options" onClick={() => setOptionsOpen((value) => !value)}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M5 12h.01M12 12h.01M19 12h.01" strokeWidth="3" /></svg></button>
              <a href={controller.getSnapshot().detail ? `/conversations?session=${controller.getSnapshot().detail!.id}` : "/conversations"} aria-label="打开完整对话" title="打开完整对话" onClick={() => { setOpen(false); setOptionsOpen(false); }}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M14 3h7v7M21 3l-11 11M10 3H3v18h18v-7" /></svg></a>
              <button type="button" className="secondary" aria-label="收起对话" title="收起对话" onClick={close}><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="m6 6 12 12M6 18 18 6" /></svg></button>
            </div>
          </header>
          {interactiveSurface && learningContext ? <p className="companion-learning-context">结合：{learningContext}</p> : null}
          <div id="companion-extra-options" className="companion-extra-options" hidden={!optionsOpen} style={optionsOpen ? undefined : { display: "none" }}>
            {optionsOpen ? <label className="companion-picker companion-display-picker">桌宠显示<select aria-label="桌宠显示方式" value={displayMode} onChange={event => setDisplayMode(event.target.value as CompanionDisplayMode)}><option value="compact">头像模式</option><option value="full">全身形象</option></select></label> : null}
            {optionsOpen ? <ConversationCompactOptions chapterId={chapterId} onSelect={() => setOptionsOpen(false)} partnerSettings={<><label className="companion-picker">选择学习伙伴<select value={pet.id} onChange={(event) => { setPetError(""); void selectPet(event.target.value).then(() => setOptionsOpen(false)).catch((caught) => setPetError(caught instanceof Error ? caught.message : "桌宠选择未保存")); }}>{COMPANION_PETS.map((p) => <option key={p.id} value={p.id}>{p.displayName}</option>)}</select></label>{petError && <p role="alert">{petError}</p>}</>} /> : null}
          </div>
          <ConversationContent chapterId={chapterId} compact learningWorkspace={interactiveSurface} beforeSend={interactiveSurface ? learningTeacher.beforeSend : undefined} />
          {(["n", "s", "e", "w", "ne", "nw", "sw"] as PanelGesture[]).map((direction) => <div key={direction} aria-hidden="true" className={`companion-resize companion-resize--${direction}`}
            onPointerDown={(event) => panelPosition.pointerDown(event, direction)} {...panelPointerEvents} />)}
          <button type="button" className="companion-resize companion-resize--se" aria-label="调整对话窗口大小" title="拖动调整大小；方向键也可调整"
            onPointerDown={(event) => panelPosition.pointerDown(event, "se")} {...panelPointerEvents}
            onKeyDown={(event) => {
              const change: Record<string, [number, number]> = { ArrowRight: [24, 0], ArrowLeft: [-24, 0], ArrowDown: [0, 24], ArrowUp: [0, -24] };
              if (change[event.key]) { event.preventDefault(); panelPosition.resizeBy(...change[event.key]); }
            }}><svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d="m3 9 6-6M7 9l2-2" /></svg></button>
        </aside>
      , document.body) : null}
    </>
  );
}
