import { useEffect, useRef } from "react";
import { useConversation } from "../conversation/ConversationProvider";
import { useAccount } from "../identity/AccountContext";
import { useNarration } from "../interactive/useNarration";
import { replyNarrationText } from "./replyNarration";
export function useReplyAutoNarration() {
  const account = useAccount();
  const { controller, run, detail } = useConversation();
  const initialCompletedRun = useRef(run?.status === "SUCCEEDED" ? run.id : null);
  const voice = useNarration(() => "");
  const { play, stop } = voice;
  useEffect(() => { stop(); return stop; }, [detail?.id, account?.user.id, stop]);
  useEffect(() => {
    if (!run || !controller.claimReplyNarration(run)) return;
    if (initialCompletedRun.current === run.id) return;
    // Consume completion even when disabled: enabling a setting must not replay history.
    if (!account?.preferences?.auto_read_replies || !voice.outputEnabled) return;
    const text = replyNarrationText(run.card!.message_markdown);
    if (text) void play({ id: `reply-${run.result_message_id}`, scene_id: "reply", text, audio: null, trigger: "MANUAL" }, { automatic: true });
  }, [controller, run, detail?.id, account?.preferences?.auto_read_replies, voice.outputEnabled, play]);
  return { ...voice, notice: voice.notice || (voice.status === "error" ? "自动朗读被阻止或播放失败，可用回复旁的按钮手动重试。" : voice.status === "unavailable" ? voice.voiceNotice : "") };
}
