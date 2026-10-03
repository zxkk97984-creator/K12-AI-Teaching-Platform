import { useEffect, useId, useLayoutEffect, useRef, useState, type KeyboardEvent, type RefObject } from "react";
import { createPortal } from "react-dom";
import { useConversation } from "./ConversationProvider";
import { useAccount } from "../identity/AccountContext";
import { BrowserVoiceInput } from "../voice/BrowserVoiceInput";
import "./composer.css";

type Props = {
  compact?: boolean; inputId: string; inputRef: RefObject<HTMLTextAreaElement | null>;
  draft: string; busy: boolean; sending: boolean; contextLabel?: string; maxLength?: number;
  onDraft: (value: string) => void; onVoice: (value: string) => void; onSend: () => void;
};

export function ConversationComposer({ inputId, inputRef, draft, busy, sending, contextLabel, compact = false, maxLength = 8000, onDraft, onVoice, onSend }: Props) {
  const account = useAccount();
  const { detail, selecting, controller, reference } = useConversation();
  const stage = account?.profile?.stage;
  const inputEnabled = !account || ["INPUT_ONLY", "INPUT_AND_OUTPUT"].includes(account.preferences?.voice_preference ?? "DISABLED");
  const [menuOpen, setMenuOpen] = useState(false);
  const [position, setPosition] = useState({left:12,top:12,width:280});
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const menuId = useId();

  useEffect(() => {
    const element = inputRef.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${Math.min(element.scrollHeight, compact ? 96 : 112)}px`;
  }, [compact, draft, inputRef]);
  useEffect(() => {
    if (busy) setMenuOpen(false);
  },[busy]);
  useLayoutEffect(() => {
    const element = menu.current;
    if (!menuOpen || !element || !trigger.current) return;
    const bounds = trigger.current.getBoundingClientRect();
    const width = Math.min(280,window.innerWidth - 24);
    element.showPopover?.();
    const height = element.getBoundingClientRect().height;
    setPosition({width,left:Math.max(12,Math.min(bounds.left,window.innerWidth - width - 12)),top:Math.max(12,bounds.top - height - 10)});
    element.querySelector<HTMLButtonElement>('button:not(:disabled)')?.focus({preventScroll:true});
    const outside = (event: PointerEvent) => {
      if (event.target instanceof Node && !element.contains(event.target) && !trigger.current?.contains(event.target)) setMenuOpen(false);
    };
    const closeOnMove = () => setMenuOpen(false);
    document.addEventListener("pointerdown",outside,true);
    window.addEventListener("resize",closeOnMove);
    window.addEventListener("scroll",closeOnMove,true);
    return () => {
      document.removeEventListener("pointerdown",outside,true);
      window.removeEventListener("resize",closeOnMove);
      window.removeEventListener("scroll",closeOnMove,true);
      if (element.hidePopover && element.matches(":popover-open")) element.hidePopover();
    };
  },[menuOpen]);
  const menuKeys = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape" || event.key === "Tab") {
      event.preventDefault(); event.stopPropagation(); setMenuOpen(false);
      if (event.key === "Tab" && !event.shiftKey) inputRef.current?.focus();
      else trigger.current?.focus();
      return;
    }
    if (!["ArrowDown","ArrowUp","Home","End"].includes(event.key)) return;
    event.preventDefault();
    const items = Array.from(menu.current?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)') ?? []);
    const index = items.indexOf(document.activeElement as HTMLButtonElement);
    const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
    items[next]?.focus();
  };
  const choose = (action: "practice" | "explain") => {
    setMenuOpen(false);
    if (action === "practice") controller.preparePractice();
    else if (!controller.getSnapshot().draft.trim() && reference) controller.setDraft(`请结合「${reference}」解释当前内容`);
    inputRef.current?.focus();
  };
  return <>
    <form className={`conv-composer conv-composer--tools${compact ? " conv-composer--compact" : ""}`} data-stage={stage} onSubmit={event => { event.preventDefault(); if (!busy && draft.trim()) onSend(); }}>
      {!compact && contextLabel ? <div className="conv-composer-context"><span>{contextLabel}</span></div> : null}
      {compact ? <label className="sr-only" htmlFor={inputId}>想对老师说什么</label> : <div className="conv-composer-heading od-row"><label className="k12-composer-label od-fill" htmlFor={inputId}>想对老师说什么</label><span className="conv-keyboard-hint">Enter 发送 · Shift + Enter 换行</span></div>}
      <div className="conv-input-line od-row">
        <button ref={trigger} className="conv-compose-add" type="button" aria-label="更多学习操作" title="更多学习操作" aria-haspopup="menu" aria-expanded={menuOpen} aria-controls={menuOpen ? menuId : undefined} disabled={busy} onClick={() => setMenuOpen(value => !value)} onKeyDown={event => { if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setMenuOpen(true); } }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true"><path d="M12 5v14M5 12h14" /></svg>
        </button>
        <textarea ref={inputRef} id={inputId} maxLength={maxLength} value={draft} onChange={event => onDraft(event.target.value)} onKeyDown={event => {
          if (event.nativeEvent.isComposing || event.keyCode === 229) return;
          if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); if (!busy && draft.trim()) onSend(); }
        }} placeholder={compact ? "提问…" : "输入你的问题…"} title={compact ? [contextLabel ?? (reference ? `当前参考：${reference}` : undefined),"Enter 发送 · Shift + Enter 换行"].filter(Boolean).join(" · ") : undefined} rows={1} />
        <div className="conv-composer-actions">
          <BrowserVoiceInput compact={compact} scopeKey={`${account?.user.id ?? "guest"}:${detail?.id ?? "new"}:${selecting}`} draft={draft} onDraft={onVoice} enabled={inputEnabled} disabled={busy} />
          <button className="conv-send-icon" data-testid="send-turn" disabled={busy || !draft.trim()} type="submit" aria-label="发送" title={sending ? "正在发送…" : "发送"} aria-busy={sending}>
            <svg width="23" height="23" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5m-6 6 6-6 6 6" /></svg>
          </button>
        </div>
      </div>
      {!compact ? <p className="conv-composer-hint">AI 回答请结合课程核对。</p> : null}
    </form>
    {menuOpen && createPortal(<div ref={menu} id={menuId} className="conv-compose-menu" data-stage={stage} role="menu" aria-label="学习操作" popover="manual" style={position} onKeyDown={menuKeys}>
      <p className="conv-compose-menu-context" title={reference ?? undefined}>{reference ? `参考：${reference}` : "学习小助手"}</p>
      <button type="button" role="menuitem" onClick={() => choose("practice")}><span className="conv-compose-menu-icon" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M5 4h11l3 3v13H5zM15 4v4h4M8 12h8m-8 4h5" /></svg></span><span>生成练习<small>选择题数，边聊边练</small></span></button>
      <button type="button" role="menuitem" disabled={!reference} onClick={() => choose("explain")} title={!reference ? "打开学习内容后，可请老师解释" : undefined}><span className="conv-compose-menu-icon" aria-hidden="true"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d="M9 18h6m-5 3h4M8 14a6 6 0 1 1 8 0c-1 1-1 2-1 4H9c0-2 0-3-1-4" /></svg></span><span>解释这里<small>把当前内容讲清楚</small></span></button>
    </div>,document.body)}
  </>;
}
