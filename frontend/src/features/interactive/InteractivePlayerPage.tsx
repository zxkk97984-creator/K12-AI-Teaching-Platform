import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { openCompanion } from "../companion/openCompanion";
import { useAccount } from "../identity/AccountContext";
import { patchPreferences } from "../identity/api";
import {
  completeInteractive, getInteractive, getInteractiveDocument, getInteractiveSession,
  listInteractive, saveInteractive, startInteractive, type InteractiveDetail, type InteractiveManifest,
  type InteractivePrompt, type InteractiveSession,
} from "./api";
import { useNarration } from "./useNarration";
import { CHANNEL, isObject, validatedMessage } from "./bridge";
import "./interactive.css";

export function InteractivePlayerPage() {
  const { resourceId = "" } = useParams();
  const account = useAccount();
  const stage = account?.profile?.stage;
  const [detail, setDetail] = useState<InteractiveDetail | null>(null);
  const [documentHtml, setDocumentHtml] = useState("");
  const [latestRevisionId, setLatestRevisionId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saveStatus, setSaveStatus] = useState<"ready" | "saving" | "saved" | "unsaved">("ready");
  const [saveError, setSaveError] = useState("");
  const [started, setStarted] = useState(false);
  const [large, setLarge] = useState(false);
  const [voiceEnabled, setVoiceEnabled] = useState(() => account?.preferences?.voice_preference === "OUTPUT_ONLY" || account?.preferences?.voice_preference === "INPUT_AND_OUTPUT");
  const [sceneId, setSceneId] = useState<string | null>(null);
  const [retryIndex, setRetryIndex] = useState(0);
  const frame = useRef<HTMLIFrameElement>(null);
  const instanceId = useRef(crypto.randomUUID());
  const sessionRef = useRef<InteractiveSession | null>(null);
  const pending = useRef<{ scene_id?: string | null; game_state?: Record<string, unknown> | null; complete?: boolean; game_result?: Record<string, unknown>; source?: "SDK_REPORTED" | "USER_CONFIRMED" } | null>(null);
  const checkpointBatch = useRef<{ gameState: Record<string, unknown>; messageIds: string[] } | null>(null);
  const checkpointTimer = useRef<number | null>(null);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const narrator = useNarration((prompt) => `/api/v1/interactive/sessions/${sessionRef.current?.id}/audio/${encodeURIComponent(prompt.id)}`);
  const manifest = detail?.manifest;
  const catalogRoute = detail?.resource.purpose === "GAME" ? "/practice" : stage?.startsWith("PRIMARY") ? "/animations" : "/activities";
  const currentScene = manifest?.scenes.find((item) => item.id === sceneId) ?? manifest?.scenes[0];
  const prompts = manifest?.prompts.filter((item) => item.scene_id === currentScene?.id) ?? [];

  useEffect(() => {
    let alive = true;
    setLoading(true); setError(""); setDetail(null); setDocumentHtml("");
    setStarted(false); setSaveStatus("ready"); pending.current = null;
    if (checkpointTimer.current !== null) window.clearTimeout(checkpointTimer.current);
    checkpointTimer.current = null; checkpointBatch.current = null;
    sessionRef.current = null;
    instanceId.current = crypto.randomUUID();
    void (async () => {
      const [content, catalog] = await Promise.all([getInteractive(resourceId), listInteractive()]);
      if (!alive) return;
      setLatestRevisionId(content.revision_id);
      const recent = catalog.items.find((item) => item.id === content.id);
      if (recent?.activity_status === "COMPLETED" && recent.session_id) {
        const activity = await getInteractiveSession(recent.session_id);
        if (!alive || activity.session.stage !== stage) return;
        sessionRef.current = activity.session;
        setDetail(activity);
        setSceneId(activity.session.current_scene_id ?? activity.manifest.scenes[0]?.id ?? null);
        return;
      }
      const session = await startInteractive(content.id);
      const [activity, document] = await Promise.all([getInteractiveSession(session.id), getInteractiveDocument(session.id)]);
      if (!alive || activity.session.stage !== stage || document.revision_id !== activity.session.revision_id) return;
      sessionRef.current = activity.session;
      setDetail(activity); setDocumentHtml(document.document_html);
      setSceneId(activity.session.current_scene_id ?? activity.manifest.scenes[0]?.id ?? null);
    })().catch((caught) => { if (alive) setError(caught instanceof Error ? caught.message : "内容暂时无法打开"); })
      .finally(() => { if (alive) setLoading(false); });
    return () => {
      alive = false; narrator.stop();
      if (checkpointTimer.current !== null) window.clearTimeout(checkpointTimer.current);
      checkpointTimer.current = null; checkpointBatch.current = null;
    };
  // narrator.stop has stable identity. Stage changes discard the old iframe and pending context.
  }, [resourceId, stage, retryIndex, narrator.stop]);

  const post = useCallback((type: string, messageId: string, payload: unknown = null) => {
    const session = sessionRef.current;
    if (!session || !frame.current?.contentWindow) return;
    frame.current.contentWindow.postMessage({
      channel: CHANNEL, instance_id: instanceId.current, session_id: session.id,
      revision_id: session.revision_id, message_id: messageId, type, payload,
    }, "*");
  }, []);

  const persist = useCallback((patch: NonNullable<typeof pending.current>) => {
    pending.current = patch;
    setSaveStatus("saving"); setSaveError("");
    const task = queue.current.catch(() => undefined).then(async () => {
      const session = sessionRef.current;
      if (!session) throw new Error("活动尚未就绪");
      const body = {
        base_revision: session.base_revision,
        event_id: crypto.randomUUID(),
        scene_id: patch.scene_id ?? session.current_scene_id,
        ...(patch.game_state === undefined ? {} : { game_state: patch.game_state }),
      };
      const saved = patch.complete
        ? await completeInteractive(session.id, { ...body, game_result: patch.game_result, source: patch.source })
        : await saveInteractive(session.id, body);
      sessionRef.current = saved;
      setDetail((previous) => previous ? { ...previous, session: saved } : previous);
      setSceneId(saved.current_scene_id);
      if (saved.status === "COMPLETED") setStarted(false);
      if (pending.current === patch) pending.current = null;
      setSaveStatus(pending.current || checkpointBatch.current ? "saving" : "saved");
      return saved;
    }).catch((caught) => {
      setSaveStatus("unsaved"); setSaveError(caught instanceof Error ? caught.message : "保存失败");
      throw caught;
    });
    queue.current = task;
    return task;
  }, []);

  const flushCheckpoint = useCallback((): Promise<InteractiveSession | null> => {
    if (checkpointTimer.current !== null) window.clearTimeout(checkpointTimer.current);
    checkpointTimer.current = null;
    const batch = checkpointBatch.current;
    checkpointBatch.current = null;
    if (!batch) return Promise.resolve(null);
    return persist({ game_state: batch.gameState }).then((saved) => {
      for (const messageId of batch.messageIds) post("saved", messageId, saved);
      return saved;
    }).catch((caught) => {
      for (const messageId of batch.messageIds) post("save_failed", messageId, {
        message: caught instanceof Error ? caught.message : "检查点未保存",
      });
      throw caught;
    });
  }, [persist, post]);

  const askTeacher = useCallback((promptId?: string) => {
    const session = sessionRef.current;
    if (!session || !manifest) return;
    openCompanion({
      page_type: "INTERACTIVE", activity_type: detail?.resource.purpose,
      content_kind: "INTERACTIVE", content_id: session.resource_id,
      content_version: session.revision_id, interactive_session_id: session.id,
      interactive_scene_id: sceneId, interactive_prompt_id: promptId,
      visible_section: currentScene?.title ?? manifest.title,
      knowledge_points: manifest.knowledge_points,
      suggestedQuestion: `请结合「${manifest.title}」中${currentScene?.title ?? "当前场景"}，给我一点讲解。`,
    });
  }, [currentScene?.title, detail?.resource.purpose, manifest, sceneId]);

  const playPrompt = useCallback(async (prompt: InteractivePrompt) => {
    if (!voiceEnabled) { setSaveError("朗读已关闭，请先点击“开启朗读”。字幕仍可查看。"); return false; }
    return narrator.play(prompt);
  }, [narrator, voiceEnabled]);

  useEffect(() => {
    if (!manifest || !detail) return;
    const onMessage = (event: MessageEvent) => {
      const session = sessionRef.current;
      if (!session) return;
      const message = validatedMessage(event, frame.current?.contentWindow, {
        instanceId: instanceId.current, sessionId: session.id, revisionId: session.revision_id,
      });
      if (!message) return;
      const payload = isObject(message.payload) ? message.payload : {};
      const reply = (type: "saved" | "save_failed", value: unknown) => post(type, message.message_id, value);
      if (message.type === "ready") return;
      if (!started) { reply("save_failed", { message: "请先点击开始学习" }); return; }
      if (message.type === "request_narration") {
        const prompt = manifest.prompts.find((item) => item.id === payload.prompt_id && item.scene_id === (sceneId ?? manifest.scenes[0]?.id));
        if (!prompt) { reply("save_failed", { message: "当前场景没有这个问题" }); return; }
        void playPrompt(prompt).then((accepted) => reply(accepted ? "saved" : "save_failed", { message: accepted ? "正在尝试朗读" : "没有可用的朗读声音" }));
        return;
      }
      if (message.type === "ask_teacher") { askTeacher(); reply("saved", { opened: true }); return; }
      if (message.type === "scene_changed") {
        if (typeof payload.scene_id !== "string" || !manifest.scenes.some((item) => item.id === payload.scene_id)) { reply("save_failed", { message: "场景不存在" }); return; }
        narrator.stop();
        void flushCheckpoint().then(() => persist({ scene_id: payload.scene_id as string })).then((saved) => {
          reply("saved", saved);
          const prompt = manifest.prompts.find((item) => item.scene_id === payload.scene_id && item.trigger === "SCENE_ENTER");
          if (prompt) void playPrompt(prompt);
        }).catch((caught) => reply("save_failed", { message: caught instanceof Error ? caught.message : "场景未保存" }));
        return;
      }
      if (message.type === "checkpoint" || message.type === "complete") {
        if (message.type === "checkpoint" && !manifest.capabilities.includes("CHECKPOINTS")) { reply("save_failed", { message: "这个内容没有启用检查点" }); return; }
        if (message.type === "complete" && !manifest.capabilities.includes("COMPLETION")) { reply("save_failed", { message: "这个内容没有启用完成事件" }); return; }
        const value = message.type === "checkpoint" ? payload.game_state : payload.game_result;
        if (!isObject(value) || JSON.stringify(value).length > 65536) { reply("save_failed", { message: "提交的数据无效或过大" }); return; }
        if (message.type === "checkpoint") {
          if (checkpointTimer.current !== null) window.clearTimeout(checkpointTimer.current);
          if (checkpointBatch.current) {
            checkpointBatch.current.gameState = value;
            checkpointBatch.current.messageIds.push(message.message_id);
          } else checkpointBatch.current = { gameState: value, messageIds: [message.message_id] };
          pending.current = { game_state: value };
          setSaveStatus("saving");
          checkpointTimer.current = window.setTimeout(() => {
            void flushCheckpoint().catch(() => undefined);
          }, 1000);
          return;
        }
        const batch = checkpointBatch.current;
        if (checkpointTimer.current !== null) window.clearTimeout(checkpointTimer.current);
        checkpointTimer.current = null;
        checkpointBatch.current = null;
        const patch = { complete: true, game_state: batch?.gameState ?? pending.current?.game_state ?? session.game_state, game_result: value, source: "SDK_REPORTED" as const };
        void persist(patch).then((saved) => {
          reply("saved", saved);
          for (const messageId of batch?.messageIds ?? []) post("saved", messageId, saved);
          if (message.type === "complete") {
            const prompt = manifest.prompts.find((item) => item.trigger === "ACTIVITY_COMPLETE");
            if (prompt) void playPrompt(prompt);
          }
        }).catch((caught) => {
          reply("save_failed", { message: caught instanceof Error ? caught.message : "保存失败" });
          for (const messageId of batch?.messageIds ?? []) post("save_failed", messageId, { message: "检查点未保存" });
        });
        return;
      }
      if (message.type === "error") { setError("互动内容运行出错，可以重新加载或返回目录。"); return; }
      reply("save_failed", { message: "不支持的互动消息" });
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [askTeacher, detail, flushCheckpoint, manifest, narrator, persist, playPrompt, post, sceneId, started]);

  const initFrame = () => {
    const session = sessionRef.current;
    if (!session) return;
    post("init", crypto.randomUUID(), {
      game_state: manifest?.capabilities.includes("CHECKPOINTS") ? session.game_state : {},
      current_scene_id: session.current_scene_id, preview: false,
    });
  };

  const enableVoice = async () => {
    if (!account?.preferences) return;
    try {
      const updated = await patchPreferences({ base_revision: account.preferences.profile_revision, voice_preference: "OUTPUT_ONLY" });
      setVoiceEnabled(updated.preferences?.voice_preference === "OUTPUT_ONLY" || updated.preferences?.voice_preference === "INPUT_AND_OUTPUT");
      setSaveError("");
    } catch (caught) { setSaveError(caught instanceof Error ? caught.message : "朗读偏好未保存"); }
  };

  const saveAndExit = async () => {
    try { await flushCheckpoint(); if (pending.current) await persist(pending.current); else await queue.current; window.location.assign(catalogRoute); }
    catch { setSaveStatus("unsaved"); }
  };

  if (loading) return <main className="interactive-player" role="status">正在读取互动内容与已保存活动…</main>;
  if (error && !detail) return <main className="interactive-player"><h1>内容暂时不可用</h1><p role="alert">{error}</p><button onClick={() => setRetryIndex((value) => value + 1)}>重试</button> <Link to={stage?.startsWith("PRIMARY") ? "/animations" : "/activities"}>返回目录</Link></main>;
  if (!detail || !manifest) return null;
  const session = detail.session;
  return <main className={`interactive-player${large ? " interactive-player--large" : ""}`} data-testid="interactive-player">
    <header className="interactive-player-header"><Link to={catalogRoute} onClick={narrator.stop}>← 返回目录</Link><div><span className="interactive-kicker">{detail.resource.subject} · {manifest.content_key}</span><h1>{detail.resource.title}</h1></div><span className="interactive-status">{session.status === "COMPLETED" ? "活动已完成" : saveStatus === "saving" ? "正在保存…" : saveStatus === "saved" ? "已保存" : saveStatus === "unsaved" ? "未保存" : "进行中"}</span></header>
    <div className="interactive-player-layout"><section className="interactive-stage" aria-label="互动内容"><div className="interactive-stage-toolbar"><span>{currentScene?.title ?? "互动场景"}</span><button type="button" onClick={() => setLarge((value) => !value)}>{large ? "退出大画布" : "大画布"}</button></div>
      {!started ? <div className="interactive-start"><h2>{session.status === "COMPLETED" ? "本次活动已完成" : session.base_revision > 0 && manifest.capabilities.includes("CHECKPOINTS") ? "继续上次活动" : "准备开始"}</h2><p>{session.status === "COMPLETED" ? "这次活动的记录已保存在账号中。再次体验会开始一轮新活动。" : manifest.summary || "你可以点击、拖动和输入，试着探索这个内容。"}</p>{session.status === "COMPLETED" ? <button type="button" onClick={() => { void startInteractive(resourceId, true).then(() => setRetryIndex((value) => value + 1)).catch((caught) => setSaveError(caught instanceof Error ? caught.message : "重新开始失败")); }}>再玩一次</button> : <button type="button" onClick={() => { setStarted(true); const prompt = manifest.prompts.find((item) => item.scene_id === (sceneId ?? manifest.scenes[0]?.id) && item.trigger === "SCENE_ENTER"); if (prompt) void playPrompt(prompt); }}>开始学习</button>}</div> : null}
      {started && session.status === "ACTIVE" && documentHtml ? <iframe ref={frame} key={instanceId.current} title={detail.resource.title} sandbox="allow-scripts" referrerPolicy="no-referrer" srcDoc={documentHtml} onLoad={initFrame} /> : <div className="interactive-stage-blank" />}
    </section><aside className="interactive-guide"><div className="interactive-guide-heading"><span className="interactive-kicker">当前场景</span><h2>{currentScene?.title ?? "互动说明"}</h2><p>{currentScene?.summary || manifest.summary}</p></div><details open><summary>预设问题与朗读</summary><ul>{prompts.map((prompt) => <li key={prompt.id}><p>{prompt.text}</p><button type="button" onClick={() => void playPrompt(prompt)} disabled={!started || !voiceEnabled}>朗读问题</button><button type="button" className="secondary" onClick={() => askTeacher(prompt.id)}>问老师</button></li>)}</ul>{prompts.length === 0 ? <p>当前场景没有预设问题。</p> : null}</details>
      {!voiceEnabled ? <button type="button" onClick={() => void enableVoice()}>开启朗读</button> : <div className="interactive-voice-controls"><button type="button" onClick={narrator.status === "paused" ? narrator.resume : narrator.pause} disabled={narrator.status !== "speaking" && narrator.status !== "paused"}>{narrator.status === "paused" ? "继续" : "暂停"}</button><button type="button" onClick={narrator.stop}>停止</button><button type="button" onClick={() => void narrator.replay()}>重播</button><label>语速<select value={narrator.rate} onChange={(event) => narrator.setRate(Number(event.target.value))}><option value="0.8">慢</option><option value="1">正常</option><option value="1.2">快</option></select></label><label><input type="checkbox" checked={narrator.muted} onChange={(event) => { narrator.setMuted(event.target.checked); if (event.target.checked) narrator.stop(); }} />静音</label></div>}
      {narrator.subtitle && <p className="interactive-subtitle" role="status">{narrator.subtitle}</p>}{narrator.status === "unavailable" && <p role="alert">当前设备没有可用的中文声音，请阅读字幕继续。</p>}{narrator.status === "error" && <p role="alert">音频播放失败，请阅读字幕或重试。</p>}
    </aside></div>
    {session.status === "ACTIVE" && latestRevisionId && latestRevisionId !== session.revision_id && <div className="interactive-version-notice">这次活动仍使用原版本，已保存进度不会迁移。<button type="button" onClick={() => { if (window.confirm("开始新版本会保留旧活动记录，但不导入旧检查点。确定继续吗？")) void startInteractive(resourceId, true).then(() => setRetryIndex((value) => value + 1)).catch((caught) => setSaveError(caught instanceof Error ? caught.message : "新版本启动失败")); }}>结束旧活动并使用新版本</button></div>}
    <footer className="interactive-player-actions"><button type="button" onClick={() => void saveAndExit()} disabled={saveStatus === "saving"}>保存并退出</button><button type="button" className="secondary" onClick={() => { if (window.confirm("重新开始会保留旧活动记录，确定继续吗？")) void startInteractive(resourceId, true).then(() => setRetryIndex((value) => value + 1)).catch((caught) => setSaveError(caught instanceof Error ? caught.message : "重新开始失败")); }}>重新开始</button>{!manifest.capabilities.includes("COMPLETION") && session.status === "ACTIVE" ? <button type="button" className="secondary" onClick={() => void persist({ complete: true, source: "USER_CONFIRMED", game_result: {} })}>标记本次完成</button> : null}<button type="button" className="secondary" onClick={() => askTeacher()}>继续问老师</button>{saveStatus === "unsaved" && <button type="button" onClick={() => pending.current && void persist(pending.current)}>重试保存</button>}{saveStatus === "unsaved" && /冲突|已更新|其他窗口/.test(saveError) && <button type="button" className="secondary" onClick={() => { if (window.confirm("读取远端记录会放弃本页未保存的操作；旧操作会留在这里直到你确认。确定读取吗？")) setRetryIndex((value) => value + 1); }}>读取远端记录</button>}</footer>
    {saveError ? <p role="alert">{saveError}</p> : null}{error ? <div role="alert">{error}<button onClick={() => setRetryIndex((value) => value + 1)}>重新加载</button></div> : null}
    {session.status === "COMPLETED" && <p className="interactive-complete">本次互动活动已完成{session.game_result && "score" in session.game_result ? ` · 游戏上报得分 ${String(session.game_result.score)}` : ""}。游戏结果不计入正式练习成绩。</p>}
  </main>;
}
