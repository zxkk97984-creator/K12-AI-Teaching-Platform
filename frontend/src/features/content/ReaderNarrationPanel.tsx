import type { useChapterNarration } from "./useChapterNarration";

type ReaderNarrator = ReturnType<typeof useChapterNarration>;
const labels = {
  idle: "点击播放，听一听本章内容。", loading: "正在准备语音…", speaking: "正在朗读", paused: "朗读已暂停",
  ended: "朗读已结束。", unavailable: "当前浏览器没有可用的朗读声音，可用已配置中文声音的 Edge／Chrome 打开，或选择其他声音。",
  error: "朗读播放失败，请重试或选择其他声音。",
};

export function ReaderNarrationPanel({ narrator, onReadChapter }: { narrator: ReaderNarrator; onReadChapter: () => void }) {
  const status = narrator.message || narrator.notice || labels[narrator.status];
  const failed = Boolean(narrator.message) || narrator.status === "error" || narrator.status === "unavailable";
  return <section id="reader-narration" className="reader-narration" aria-label="课文朗读" data-pet-avoid>
    <div className="reader-narration-heading"><h2>课文朗读</h2><span>系统语音</span></div>
    <div className="reader-narration-controls">
      <button type="button" className="reader-narration-play" disabled={narrator.status === "loading"} onClick={() => {
        if (narrator.status === "speaking") narrator.pause();
        else if (narrator.status === "paused") narrator.resume();
        else onReadChapter();
      }}>{narrator.status === "loading" ? "准备语音…" : narrator.status === "speaking" ? "暂停朗读" : narrator.status === "paused" ? "继续朗读" : "播放本章"}</button>
      <button type="button" disabled={!narrator.active} onClick={narrator.stop}>停止朗读</button>
      <label>语速<select aria-label="课文朗读语速" value={narrator.rate} onChange={(event) => narrator.setRate(Number(event.target.value))}>
        <option value="0.8">0.8 倍</option><option value="1">1 倍</option><option value="1.2">1.2 倍</option><option value="1.5">1.5 倍</option>
      </select></label>
      <a className="reader-narration-settings" href="/settings#settings-narration-voice">朗读声音设置 →</a>
    </div>
    <p className="reader-narration-status" role={failed ? "alert" : "status"}>{status}{narrator.total > 0 && (narrator.active || narrator.status === "ended") ? ` · ${narrator.scope === "selection" ? "选中文字" : "本章"} · 第 ${narrator.position + 1} / ${narrator.total} 句` : ""}</p>
    {narrator.active && narrator.segment ? <p className="reader-narration-excerpt">{narrator.segment.text}</p> : null}
    <p className="reader-narration-note">{narrator.status === "unavailable" ? "" : `${narrator.voiceNotice} · `}继续朗读会从当前句开始，声音与语速从下一句起生效；代码示例请对照正文查看。</p>
  </section>;
}
