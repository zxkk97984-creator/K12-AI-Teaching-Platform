import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { useEditingRegistration } from "../../app/editing/EditingGuard";
import { useAccount } from "../identity/AccountContext";
import { patchPreferences } from "../identity/api";
import { useLearningPageContext } from "../companion/useLearningPageContext";
import { useConversation } from "../conversation/ConversationProvider";
import { useLearningTeacher } from "../companion/LearningTeacherContext";
import { getInteractive, getInteractiveDocument, getInteractiveSession, listInteractive, startInteractive, type InteractiveDetail, type InteractivePrompt, type InteractiveSession } from "./api";
import { useNarration } from "./useNarration";
import { CHANNEL, isObject, validatedMessage, type PlaybackStep, type WorkspaceCommand } from "./bridge";
import { useLessonPlayback } from "./useLessonPlayback";
import { ActivitySaveQueue, type ActivityPatch } from "./ActivitySaveQueue";
import { NarrationControls } from "./LearningControls";
import { practiceReturn, practiceDate } from "../../pages/practice/navigation";
import { interactiveStatus } from "./presentation";
import "./interactive.css";

type CommandRequest = { resolve: () => void; reject: (error: Error) => void; timer: number; sceneId?: unknown; narrate: boolean };
export function InteractivePlayerPage() {
  const location = useLocation();
  const query = new URLSearchParams(location.search);
  const requestedSessionId = query.get("session");
  const recordView = query.get("view") === "record";
  const returnTo = practiceReturn(query.get("returnTo"));
  const { resourceId = "" } = useParams();
  const navigate = useNavigate();
  const account = useAccount();
  const stage = account?.profile?.stage;
  const { controller } = useConversation();
  const learningTeacher = useLearningTeacher();
  const [detail, setDetail] = useState<InteractiveDetail | null>(null);
  const [documentHtml, setDocumentHtml] = useState("");
  const [latestRevisionId, setLatestRevisionId] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saveStatus, setSaveStatus] = useState<"ready" | "saving" | "saved" | "unsaved">("ready");
  const [saveError, setSaveError] = useState("");
  const [started, setStarted] = useState(false);
  const [frameMounted, setFrameMounted] = useState(false);
  const [exitRequested, setExitRequested] = useState<string | null>(null);
  const [focused, setFocused] = useState(false);
  const [panelOpen, setPanelOpen] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [commands, setCommands] = useState<WorkspaceCommand[]>([]);
  const [playbackSteps, setPlaybackSteps] = useState<PlaybackStep[]>([]);
  const playbackController = useRef<ReturnType<typeof useLessonPlayback> | null>(null);
  const autoStartRequested = useRef(false);
  const resumeFrom = useRef(0);
  const viewedRequested = useRef(false);
  const [commandBusy, setCommandBusy] = useState(false);
  const [checkpointDirty, setCheckpointDirty] = useState(false);
  const [hint, setHint] = useState("");
  const [voiceEnabled, setVoiceEnabled] = useState(() => ['OUTPUT_ONLY', 'INPUT_AND_OUTPUT'].includes(account?.preferences?.voice_preference ?? ''));
  const [sceneId, setSceneId] = useState<string | null>(null);
  const [promptId, setPromptId] = useState("");
  const [retryIndex, setRetryIndex] = useState(0);
  const frame = useRef<HTMLIFrameElement>(null);
  const root = useRef<HTMLElement>(null);
  const panel = useRef<HTMLElement>(null);
  const focusButton = useRef<HTMLButtonElement>(null);
  const panelButton = useRef<HTMLButtonElement>(null);
  const beforeFocus = useRef(true);
  const alivePage = useRef(true);
  const startedRef = useRef(false);
  const instanceId = useRef(crypto.randomUUID());
  const sessionRef = useRef<InteractiveSession | null>(null);
  const checkpointBatch = useRef<{ gameState: Record<string, unknown>; messageIds: string[] } | null>(null);
  const checkpointTimer = useRef<number | null>(null);
  const commandRequests = useRef(new Map<string, CommandRequest>());
  const narrator = useNarration(prompt => `/api/v1/interactive/sessions/${sessionRef.current?.id}/audio/${encodeURIComponent(prompt.id)}`, `k12:interactive:voice:${account?.user.id}:v1`);
  const manifest = detail?.manifest;
  const catalogRoute = returnTo ?? (detail?.resource.purpose === "GAME" ? "/practice" : detail?.resource.purpose === "LESSON" ? "/animations" : "/activities");
  const currentScene = manifest?.scenes.find(item => item.id === sceneId) ?? manifest?.scenes[0];
  const prompts = manifest?.prompts.filter(item => item.scene_id === currentScene?.id) ?? [];
  const currentPrompt = prompts.find(item => item.id === promptId) ?? prompts.find(item => item.trigger === 'SCENE_ENTER') ?? prompts[0];
  useLearningPageContext(manifest && sessionRef.current ? {
    page_type:"INTERACTIVE", activity_type:detail?.resource.purpose, content_kind:"INTERACTIVE",
    content_id:sessionRef.current.resource_id, content_version:sessionRef.current.revision_id,
    interactive_session_id:sessionRef.current.id, interactive_scene_id:currentScene?.id,
    interactive_prompt_id:currentPrompt?.id, visible_section:`${manifest.title} · ${currentScene?.title ?? ""}`,
    knowledge_points:manifest.knowledge_points,
  } : null);
  const post = useCallback((type: string, messageId: string, payload: unknown = null) => {
    const session = sessionRef.current;
    if (!session || !frame.current?.contentWindow) return;
    // allow-scripts srcdoc has an opaque origin; target this window only.
    frame.current.contentWindow.postMessage({ channel: CHANNEL, instance_id: instanceId.current, session_id: session.id, revision_id: session.revision_id, message_id: messageId, type, payload }, "*");
  }, []);
  const saver = useRef<ActivitySaveQueue | null>(null);
  if (!saver.current) saver.current = new ActivitySaveQueue({
    session: () => sessionRef.current,
    saved: saved => {
      sessionRef.current = saved;
      setDetail(previous => previous ? {...previous, session: saved} : previous);
      setSceneId(saved.current_scene_id);
      post('workspace_state', crypto.randomUUID(), {scene_id: saved.current_scene_id, base_revision: saved.base_revision, game_state: saved.game_state});
      if (saved.status === 'COMPLETED') { startedRef.current = false; playbackController.current?.stop(); narrator.stop(); setStarted(false); }
    },
    status: (status, message) => { setSaveStatus(status); setSaveError(message ?? ''); },
  });
  const persist = useCallback((patch: ActivityPatch) => saver.current!.enqueue(patch), []);
  useEditingRegistration(`interactive:${resourceId}`, checkpointDirty || saveStatus === 'saving' || saveStatus === 'unsaved');

  useEffect(() => {
    let alive = true; alivePage.current = true;
    const abort = new AbortController();
    playbackController.current?.stop(); autoStartRequested.current = false;
    setLoading(true); setError(''); setDetail(null); setDocumentHtml(''); setCommands([]); setPlaybackSteps([]); setHint('');
    startedRef.current = false; setStarted(false); setFrameMounted(false); setExitRequested(null); setCommandBusy(false); setSaveStatus('ready'); setSaveError(''); setCheckpointDirty(false);
    saver.current!.reset(); resumeFrom.current = 0; viewedRequested.current = false; sessionRef.current = null; instanceId.current = crypto.randomUUID();
    setFocused(false);
    if (checkpointTimer.current !== null) window.clearTimeout(checkpointTimer.current);
    checkpointBatch.current = null; checkpointTimer.current = null;
    void (async () => {
      const [content, catalog] = await Promise.all([getInteractive(resourceId, abort.signal), listInteractive(undefined, undefined, abort.signal)]);
      if (!alive) return;
      setLatestRevisionId(content.revision_id);
      const recent = catalog.items.find(item => item.id === content.id);
      const session = requestedSessionId ? (await getInteractiveSession(requestedSessionId, abort.signal)).session : recent?.session_id && ['ACTIVE', 'COMPLETED'].includes(recent.activity_status)
        ? (await getInteractiveSession(recent.session_id, abort.signal)).session
        : await startInteractive(content.id);
      if (!alive) return;
      const activity = await getInteractiveSession(session.id, abort.signal);
      if (activity.session.resource_id !== content.id) throw new Error('这条记录不属于当前活动。');
      const document = session.status === 'ACTIVE' && !recordView ? await getInteractiveDocument(session.id, abort.signal) : null;
      if (!alive) return;
      if (activity.session.stage !== stage || (document && document.revision_id !== session.revision_id)) throw new Error('课件版本或学段已变化，请重新读取。');
      const position = activity.session.host_state?.playback_step;
      resumeFrom.current = typeof position === "number" && Number.isInteger(position) && position >= 0 && position < activity.manifest.scenes.length ? position : 0;
      viewedRequested.current = Boolean(activity.session.viewed_at);
      sessionRef.current = activity.session; setDetail(activity); setDocumentHtml(document?.document_html ?? ''); setFrameMounted(Boolean(document));
      setSceneId(activity.session.current_scene_id ?? activity.manifest.scenes[0]?.id ?? null);
    })().catch(caught => { if (alive) setError(caught instanceof Error ? caught.message : '内容暂时无法打开'); })
      .finally(() => { if (alive) setLoading(false); });
    return () => {
      alive = false; alivePage.current = false; startedRef.current = false; instanceId.current = crypto.randomUUID(); abort.abort(); playbackController.current?.stop(); narrator.stop(); saver.current!.reset();
      if (checkpointTimer.current !== null) window.clearTimeout(checkpointTimer.current);
      checkpointTimer.current = null; checkpointBatch.current = null;
      for (const request of commandRequests.current.values()) { clearTimeout(request.timer); request.reject(new Error('活动已切换')); }
      commandRequests.current.clear();
    };
  }, [resourceId, requestedSessionId, recordView, account?.user.id, stage, retryIndex, narrator.stop]);

  useLayoutEffect(() => {
    if (!root.current) return;
    const style = getComputedStyle(root.current);
    const compact = root.current.clientWidth - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight) < 1040;
    setDrawer(compact);
    setPanelOpen(!compact && detail?.resource.purpose !== "GAME");
    const observer = new ResizeObserver(([entry]) => {
      const nextDrawer = entry.contentRect.width < 1040;
      setDrawer(nextDrawer);
      if (nextDrawer) setPanelOpen(false);
    });
    observer.observe(root.current);
    return () => observer.disconnect();
  }, [loading, detail?.resource.purpose]);
  useEffect(() => {
    window.dispatchEvent(new CustomEvent('interactive:layout', {detail: {focused}}));
    return () => { window.dispatchEvent(new CustomEvent('interactive:layout', {detail: {focused: false}})); };
  }, [focused]);
  const toggleFocus = useCallback(() => {
    if (!focused) { beforeFocus.current = panelOpen; setPanelOpen(false); }
    else { setPanelOpen(beforeFocus.current); focusButton.current?.focus(); }
    setFocused(value => !value);
  }, [focused, panelOpen]);
  useEffect(() => {
    const close = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      if (learningTeacher.isVisible()) return;
      if (drawer && panelOpen) { setPanelOpen(false); panelButton.current?.focus(); }
      else if (focused) toggleFocus();
    };
    window.addEventListener('keydown', close);
    return () => window.removeEventListener('keydown', close);
  }, [drawer, focused, learningTeacher, panelOpen, toggleFocus]);
  useEffect(() => {
    if (drawer && panelOpen) panel.current?.querySelector<HTMLButtonElement>('button')?.focus();
  }, [drawer, panelOpen]);

  const command = useCallback((value: WorkspaceCommand, payload: Record<string, unknown> = {}, options = {narrate: true}) => {
    if (!commands.includes(value)) return Promise.reject(new Error('此课件未接管这项操作，请使用课件内的控件。'));
    const id = crypto.randomUUID();
    return new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => { commandRequests.current.delete(id); reject(new Error('课件未确认操作，请重试。')); }, 20000);
      commandRequests.current.set(id, {resolve, reject, timer, sceneId: value === 'scene' ? payload.scene_id : undefined, narrate: options.narrate});
      post('workspace_command', id, {command: value, ...payload});
    });
  }, [commands, post]);
  const flushCheckpoint = useCallback(async () => {
    if (checkpointTimer.current !== null) window.clearTimeout(checkpointTimer.current);
    checkpointTimer.current = null;
    const batch = checkpointBatch.current; checkpointBatch.current = null;
    try {
      const saved = batch ? await persist({game_state: batch.gameState}) : await saver.current!.flush();
      for (const id of batch?.messageIds ?? []) post('saved', id, saved);
      if (!checkpointBatch.current) setCheckpointDirty(false);
      return saved;
    } catch (caught) {
      for (const id of batch?.messageIds ?? []) post('save_failed', id, {message: caught instanceof Error ? caught.message : '操作未保存'});
      throw caught;
    }
  }, [persist, post]);
  const presentStep = useCallback(async (step: PlaybackStep, isCurrent: () => boolean) => {
    await flushCheckpoint();
    if (!isCurrent() || !alivePage.current) return;
    if (sessionRef.current?.current_scene_id !== step.scene_id) await command('scene', {scene_id: step.scene_id}, {narrate: false});
    if (!isCurrent() || !alivePage.current) return;
    await command('demonstrate', {prompt_id: step.prompt_id});
    if (isCurrent()) {
      await persist({playback_step: playbackSteps.findIndex(item => item.prompt_id === step.prompt_id)});
      if (isCurrent()) setPromptId(step.prompt_id);
    }
  }, [command, flushCheckpoint, persist, playbackSteps]);
  const reportViewed = useCallback(() => {
    if (viewedRequested.current || !alivePage.current) return;
    viewedRequested.current = true;
    void persist({viewed: true}).catch(() => { /* Exact event stays queued for retry. */ });
  }, [persist]);
  const playback = useLessonPlayback({resumeFrom: resumeFrom.current, onEnded: reportViewed, steps: playbackSteps, prompts: manifest?.prompts ?? [], narrator, present: presentStep});
  playbackController.current = playback;
  useEffect(() => {
    if (started && playbackSteps.length && autoStartRequested.current) {
      autoStartRequested.current = false;
      playback.start(resumeFrom.current);
    }
  }, [started, playbackSteps, playback.start]);
  const tryManually = useCallback(() => {
    autoStartRequested.current = false; playback.stop();
    if (commands.includes('demonstrate')) void command('demonstrate', {prompt_id: null}).catch(caught => setError(caught.message));
  }, [command, commands, playback.stop]);
  const setTeacherContext = useCallback((selectedPrompt?: string) => {
    const session = sessionRef.current;
    if (!session || !manifest) return;
    controller.setPageContext({page_type: 'INTERACTIVE', activity_type: detail?.resource.purpose, content_kind: 'INTERACTIVE', content_id: session.resource_id, content_version: session.revision_id, interactive_session_id: session.id, interactive_scene_id: session.current_scene_id ?? manifest.scenes[0]?.id, interactive_prompt_id: selectedPrompt, visible_section: currentScene?.title ?? manifest.title, knowledge_points: manifest.knowledge_points});
  }, [controller, currentScene?.title, detail?.resource.purpose, manifest]);
  const prepareTeacher = useCallback((selectedPrompt?: string) => {
    playbackController.current?.pause();
    if (narrator.status === 'speaking') narrator.pause();
    else if (narrator.status === 'loading') narrator.stop();
    if (commands.includes('pause')) void command('pause').catch(() => {});
    setTeacherContext(selectedPrompt ?? currentPrompt?.id); if (drawer) setPanelOpen(false);
    if (!controller.getSnapshot().draft.trim() && manifest) controller.setDraft(`请结合「${manifest.title}」的${currentScene?.title ?? '当前环节'}和当前操作，给我一点讲解。`);
    return `${manifest?.title ?? ''} · ${currentScene?.title ?? '当前环节'}`;
  }, [command, commands, controller, currentPrompt?.id, currentScene?.title, drawer, manifest, narrator.pause, narrator.status, narrator.stop, setTeacherContext]);
  const askTeacher = useCallback((selectedPrompt?: string) => {
    window.dispatchEvent(new CustomEvent('companion:open', {detail: {interactive_prompt_id: selectedPrompt}}));
  }, []);
  useEffect(() => {
    const show = () => askTeacher(currentPrompt?.id);
    window.addEventListener('interactive:ask', show);
    return () => window.removeEventListener('interactive:ask', show);
  }, [askTeacher, currentPrompt?.id]);
  const beforeSend = useCallback(async () => { const generation = instanceId.current; await flushCheckpoint(); if (!alivePage.current || generation !== instanceId.current) throw new Error('学习页面已切换，问题未发送。'); setTeacherContext(currentPrompt?.id); }, [currentPrompt?.id, flushCheckpoint, setTeacherContext]);
  useLayoutEffect(() => learningTeacher.register({beforeOpen: prepareTeacher, beforeSend}), [learningTeacher, prepareTeacher, beforeSend]);
  const playPrompt = useCallback(async (prompt: InteractivePrompt) => {
    if (!voiceEnabled) return false;
    return narrator.play(prompt);
  }, [narrator.play, voiceEnabled]);
  useEffect(() => {
    if (started) post('narration_state', crypto.randomUUID(), {status: narrator.status, prompt_id: narrator.prompt_id, subtitle: narrator.subtitle});
  }, [narrator.prompt_id, narrator.status, narrator.subtitle, post, started]);

  useEffect(() => {
    if (!manifest) return;
    const onMessage = (event: MessageEvent) => {
      const session = sessionRef.current;
      if (!session) return;
      const message = validatedMessage(event, frame.current?.contentWindow, {instanceId: instanceId.current, sessionId: session.id, revisionId: session.revision_id});
      if (!message) return;
      const generation = instanceId.current;
      const persistCurrent = (patch: ActivityPatch) => { if (!alivePage.current || generation !== instanceId.current) throw new Error('活动已切换'); return persist(patch); };
      const payload = isObject(message.payload) ? message.payload : {};
      const reply = (type: 'saved' | 'save_failed', value: unknown) => post(type, message.message_id, value);
      const failed = (caught: unknown) => reply('save_failed', {message: caught instanceof Error ? caught.message : '操作未保存'});
      if (message.type === 'command_result') {
        const request = commandRequests.current.get(message.message_id);
        if (request) { clearTimeout(request.timer); commandRequests.current.delete(message.message_id); if (payload.ok) request.resolve(); else request.reject(new Error(String(payload.error ?? '课件操作失败'))); }
        return;
      }
      if (message.type === 'ready') { post('narration_state', crypto.randomUUID(), {status: narrator.status, prompt_id: narrator.prompt_id, subtitle: narrator.subtitle}); return; }
      if (message.type === 'workspace_ready') {
        if (session.status !== 'ACTIVE') return;
        setCommands(payload.commands as WorkspaceCommand[]);
        const steps = payload.playback_steps as PlaybackStep[] | undefined;
        setPlaybackSteps(steps && detail?.resource.purpose === 'LESSON' && steps.every(step => manifest.scenes.some(scene => scene.id === step.scene_id) && manifest.prompts.some(prompt => prompt.id === step.prompt_id && prompt.scene_id === step.scene_id)) ? steps : []);
        const style = getComputedStyle(root.current!);
        reply('saved', {embedded: true, theme: {'font-family': style.fontFamily, text: style.getPropertyValue('--sl-text').trim(), muted: style.getPropertyValue('--sl-text-muted').trim(), surface: '#fff', soft: '#fffcf4', line: style.getPropertyValue('--sl-border-color').trim() || '#e2e2df', accent: style.getPropertyValue('--sl-primary').trim(), radius: '12px'}});
        return;
      }
      if (!startedRef.current || session.status !== 'ACTIVE') { reply('save_failed', {message: '请先开始学习'}); return; }
      if (message.type === 'activity_state') {
        if (payload.scene_id !== (session.current_scene_id ?? manifest.scenes[0]?.id)) { reply('save_failed', {message: '环节已变化'}); return; }
        setHint(payload.hint as string); reply('saved', {received: true}); return;
      }
      if (message.type === 'ask_teacher') { askTeacher(currentPrompt?.id); reply('saved', {opened: true}); return; }
      if (message.type === 'request_narration') {
        const prompt = manifest.prompts.find(item => item.id === payload.prompt_id && item.scene_id === (session.current_scene_id ?? manifest.scenes[0]?.id));
        if (!prompt) { reply('save_failed', {message: '当前环节没有这个讲解'}); return; }
        playbackController.current?.stop(); setPromptId(prompt.id);
        void playPrompt(prompt).then(accepted => reply(accepted ? 'saved' : 'save_failed', {message: accepted ? '朗读已开始' : '朗读不可用，请阅读讲解'})); return;
      }
      if (message.type === 'scene_changed') {
        if (!manifest.scenes.some(item => item.id === payload.scene_id)) { reply('save_failed', {message: '环节不存在'}); return; }
        const automaticScene = [...commandRequests.current.values()].some(request => request.sceneId === payload.scene_id && !request.narrate);
        narrator.stop();
        void flushCheckpoint().then(() => persistCurrent({scene_id: payload.scene_id as string})).then(saved => {
          reply('saved', saved); setHint('');
          const prompt = manifest.prompts.find(item => item.scene_id === payload.scene_id && item.trigger === 'SCENE_ENTER');
          if (prompt && !automaticScene && sessionRef.current?.id === session.id && !learningTeacher.isVisible() && !playbackController.current?.isRunning()) void playPrompt(prompt);
        }).catch(failed); return;
      }
      if (message.type === 'checkpoint') {
        if (!manifest.capabilities.includes('CHECKPOINTS')) { reply('save_failed', {message: '课件不支持保存实验操作'}); return; }
        if (checkpointTimer.current !== null) clearTimeout(checkpointTimer.current);
        const batch = checkpointBatch.current;
        checkpointBatch.current = {gameState: payload.game_state as Record<string, unknown>, messageIds: [...(batch?.messageIds ?? []), message.message_id]};
        setCheckpointDirty(true);
        checkpointTimer.current = window.setTimeout(() => { void flushCheckpoint().catch(() => {}); }, 350);
        return;
      }
      if (message.type === 'complete') {
        if (!manifest.capabilities.includes('COMPLETION')) { reply('save_failed', {message: '课件不支持完成事件'}); return; }
        narrator.stop();
        void flushCheckpoint().then(() => persistCurrent({complete: true, source: 'SDK_REPORTED', game_result: payload.game_result as Record<string, unknown>})).then(saved => reply('saved', saved)).catch(failed); return;
      }
      if (message.type === 'error') setError('互动内容运行出错，可以重新加载或返回目录。');
    };
    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [askTeacher, currentPrompt?.id, detail?.resource.purpose, flushCheckpoint, manifest, narrator.pause, narrator.prompt_id, narrator.status, narrator.stop, narrator.subtitle, learningTeacher, persist, playPrompt, post, started]);

  const initFrame = () => {
    const session = sessionRef.current;
    if (session) post('init', crypto.randomUUID(), {game_state: manifest?.capabilities.includes('CHECKPOINTS') ? session.game_state : {}, current_scene_id: session.current_scene_id, preview: false, prompts: manifest?.prompts ?? []});
  };
  const enableVoice = async () => {
    if (!account?.preferences) return;
    try {
      const updated = await patchPreferences({base_revision: account.preferences.profile_revision, voice_preference: account.preferences.voice_preference === 'INPUT_ONLY' ? 'INPUT_AND_OUTPUT' : 'OUTPUT_ONLY'});
      setVoiceEnabled(['OUTPUT_ONLY', 'INPUT_AND_OUTPUT'].includes(updated.preferences?.voice_preference ?? '')); setError('');
    } catch (caught) { setError(caught instanceof Error ? caught.message : '朗读偏好未保存'); }
  };
  const runCommand = async (value: WorkspaceCommand, payload?: Record<string, unknown>) => {
    if (commandBusy) return;
    if (playback.active) tryManually();
    const generation = instanceId.current;
    setCommandBusy(true); setError(''); narrator.stop();
    try { await flushCheckpoint(); if (!alivePage.current || generation !== instanceId.current) return; await command(value, payload); }
    catch (caught) { setError(caught instanceof Error ? caught.message : '操作未完成'); }
    finally { if (alivePage.current && generation === instanceId.current) setCommandBusy(false); }
  };
  const restart = async () => {
    if (commandBusy) return;
    const generation = instanceId.current;
    playback.stop(); narrator.stop(); setCommandBusy(true);
    try { await flushCheckpoint(); if (!alivePage.current || generation !== instanceId.current) return; const fresh = await startInteractive(resourceId, true); if (alivePage.current && generation === instanceId.current) navigate(`/interactive/${resourceId}?session=${fresh.id}${returnTo ? `&returnTo=${encodeURIComponent(returnTo)}` : ""}`); }
    catch (caught) { if (alivePage.current && generation === instanceId.current) setError(caught instanceof Error ? caught.message : '重新开始失败'); }
    finally { if (alivePage.current && generation === instanceId.current) setCommandBusy(false); }
  };
  const finishManual = async () => {
    const generation = instanceId.current; playback.stop(); narrator.stop();
    try { await flushCheckpoint(); if (alivePage.current && generation === instanceId.current) await persist({complete: true, source: 'USER_CONFIRMED', game_result: {}}); } catch { /* Saving exposes its recoverable error. */ }
  };
  const saveAndExit = async () => { const generation = instanceId.current; playback.stop(); narrator.stop(); try { await flushCheckpoint(); if (alivePage.current && generation === instanceId.current) setExitRequested(catalogRoute); } catch { /* Keep current work and expose retry. */ } };
  useEffect(() => {
    if (exitRequested && !checkpointDirty && saveStatus !== 'saving' && saveStatus !== 'unsaved') {
      const destination = exitRequested;
      setExitRequested(null);
      navigate(destination);
    }
  }, [exitRequested, checkpointDirty, saveStatus, navigate]);
  const restored = Boolean(detail && detail.session.base_revision > 0);
  const active = detail?.session.status === 'ACTIVE';
  const sceneIndex = manifest?.scenes.findIndex(item => item.id === currentScene?.id) ?? 0;
  const openPanel = () => setPanelOpen(value => !value);
  const panelModal = drawer && panelOpen;

  if (loading) return <main className="interactive-player" role="status">正在读取课件与账号中已保存的活动…</main>;
  if (!detail || !manifest) return <main className="interactive-player"><h1>内容暂时不可用</h1><p role="alert">{error || '无法读取上次进度，请重试。'}</p><button onClick={() => setRetryIndex(value => value + 1)}>重试</button><Link to={catalogRoute}>返回目录</Link></main>;
  if (recordView || (!active && detail.resource.purpose === "GAME")) return <main className="interactive-player interactive-record" data-testid="interactive-record">
    <header><Link to={catalogRoute}>← {returnTo?.startsWith("/history") ? "返回历史记录" : detail.resource.purpose === "GAME" ? "返回找练习" : "返回目录"}</Link><h1>{detail.resource.title}</h1></header>
    <h2>{detail.session.status === "COMPLETED" ? "本次活动已完成" : detail.session.status === "ABANDONED" ? "本次活动已停止" : "活动记录"}</h2>
    <p>{interactiveStatus(detail.session)} · {practiceDate(detail.session.updated_at ?? detail.session.created_at)}</p>
    <p>本次停留在：{currentScene?.title ?? "开始环节"}</p>
    {typeof detail.session.game_result?.score === "number" ? <p>小游戏记录得分：{detail.session.game_result.score}</p> : null}
    <p>{manifest.summary}</p>
    <div className="practice-actions">{active ? <Link className="practice-primary-link" to={`/interactive/${resourceId}?session=${detail.session.id}&view=activity${returnTo ? `&returnTo=${encodeURIComponent(returnTo)}` : ""}`}>继续活动 →</Link> : <button type="button" disabled={commandBusy} onClick={() => void restart()}>重新体验</button>}<Link to={catalogRoute}>返回列表</Link></div>
    {error ? <p role="alert">{error}</p> : null}
  </main>;
  return <main ref={root} className={`interactive-player${focused ? ' is-focused' : ''}${drawer ? ' has-drawer' : ''}`} data-testid="interactive-player" data-panel-open={panelOpen} data-playback={playback.status} data-playback-step={playback.index}>
    <header className="interactive-player-header" data-pet-avoid><Link to={catalogRoute} onClick={event => { event.preventDefault(); void saveAndExit(); }}>← 返回</Link><div className="interactive-course-title"><h1>{detail.resource.title}</h1><div className="interactive-course-meta"><span>{currentScene?.title} · 环节 {sceneIndex + 1}/{manifest.scenes.length}</span>{detail.session.viewed_at ? <span className="interactive-status" data-testid="lesson-viewed">已看完 · 可继续实验</span> : null}<span className="interactive-status" role="status">{saveStatus === 'unsaved' ? '未保存 · 请重试' : checkpointDirty || saveStatus === 'saving' ? '正在保存…' : restored || saveStatus === 'saved' ? '已保存到账号' : '尚未记录操作'}</span></div></div><button ref={focusButton} type="button" className="secondary" aria-pressed={focused} onClick={toggleFocus}>{focused ? '退出专注' : '专注模式'}</button></header>
    <nav className="interactive-scene-nav" aria-label="课程环节" data-pet-avoid>
      {started && commands.includes('scene') ? <><button type="button" className="secondary" disabled={sceneIndex === 0 || commandBusy} onClick={() => void runCommand('scene', {scene_id: manifest.scenes[sceneIndex - 1].id})}>上一环节</button><select aria-label="当前课程环节" value={currentScene?.id} disabled={commandBusy} onChange={event => void runCommand('scene', {scene_id: event.target.value})}>{manifest.scenes.map((scene, index) => <option key={scene.id} value={scene.id}>{index + 1}. {scene.title}</option>)}</select><button type="button" className="secondary" disabled={sceneIndex === manifest.scenes.length - 1 || commandBusy} onClick={() => void runCommand('scene', {scene_id: manifest.scenes[sceneIndex + 1].id})}>下一环节</button></> : <span>{started ? '原版课件 · 请使用画布内的环节与实验控件' : detail.resource.subject}</span>}
      <button ref={panelButton} type="button" className="secondary interactive-panel-toggle" aria-expanded={panelOpen} aria-controls="interactive-guide" onClick={openPanel}>{panelOpen ? '收起讲解' : '本步讲解'}</button><button type="button" className="secondary" onClick={() => askTeacher(currentPrompt?.id)}>问老师</button>
    </nav>
    <div className="interactive-player-layout">
      <section className="interactive-stage" aria-label="互动画布" inert={panelModal}>
        {!started ? <div className="interactive-start"><div>{manifest.cover && latestRevisionId === detail.session.revision_id ? <img className="interactive-preview" src={`/api/v1/interactive/resources/${resourceId}/cover`} alt={`${detail.resource.title}课件预览`} /> : <div className="interactive-preview-text">{manifest.scenes.map((scene, index) => <span key={scene.id}>{index + 1}. {scene.title}</span>)}</div>}</div><div><span className="interactive-kicker">{active ? restored ? '继续上次学习' : '准备开始' : '学习记录'}</span><h2>{active && restored ? `上次学到：${currentScene?.title}` : active ? playbackSteps.length ? '点一下，听讲解、看演示' : '观察、操作，再说出你的发现' : '本次活动已完成'}</h2><p>{manifest.summary}</p>{!active && detail.session.game_result && "score" in detail.session.game_result ? <p>游戏上报得分 {String(detail.session.game_result.score)}。游戏结果不计入正式练习成绩。</p> : null}{manifest.knowledge_points.length ? <p>学习目标：{manifest.knowledge_points.join('、')}</p> : null}<button type="button" onClick={() => {
          if (!active) { void restart(); return; }
          if (startedRef.current) return;
          startedRef.current = true; setFrameMounted(true); setStarted(true);
          setVoiceEnabled(true);
          autoStartRequested.current = stage === 'PRIMARY_LOWER' && detail.resource.purpose === 'LESSON';
          if (!autoStartRequested.current || !playbackSteps.length) { const prompt = prompts.find(item => item.trigger === 'SCENE_ENTER'); if (prompt) void narrator.play(prompt); }
        }}>{active ? restored ? '继续学习' : '开始学习' : '重新体验'}</button></div></div> : null}
        {frameMounted && documentHtml ? <iframe hidden={!started} ref={frame} key={instanceId.current} title={detail.resource.title} sandbox="allow-scripts" referrerPolicy="no-referrer" srcDoc={documentHtml} onLoad={initFrame} /> : null}
      </section>
      {panelModal ? <button className="interactive-panel-backdrop" aria-label="关闭学习面板" onClick={() => { setPanelOpen(false); panelButton.current?.focus(); }} /> : null}
      <aside ref={panel} id="interactive-guide" className="interactive-guide" hidden={!panelOpen} role={panelModal ? 'dialog' : undefined} aria-modal={panelModal || undefined} aria-label="本步讲解面板" onKeyDown={event => {
        if (!panelModal || event.key !== 'Tab') return;
        const elements = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], textarea, select, input, summary, [tabindex="0"]')].filter(item => item.getClientRects().length);
        const target = event.shiftKey ? elements.at(-1) : elements[0];
        if (document.activeElement === (event.shiftKey ? elements[0] : elements.at(-1))) { event.preventDefault(); target?.focus(); }
      }}>
        <div className="interactive-guide-tabs" data-pet-avoid><strong>本步讲解</strong>{drawer ? <button type="button" className="secondary interactive-guide-close" aria-label="关闭学习面板" onClick={() => { setPanelOpen(false); panelButton.current?.focus(); }}>×</button> : null}</div>
        <div className="interactive-explanation"><p className="interactive-kicker">{playback.active ? `自动演示 · 第 ${playback.index + 1}/${playbackSteps.length} 段` : '预设讲解 · 可反复朗读'}</p>{prompts.length > 1 ? <label>讲解段落<select value={currentPrompt?.id} onChange={event => { tryManually(); narrator.stop(); setPromptId(event.target.value); }}>{prompts.map((prompt, index) => <option key={prompt.id} value={prompt.id}>第 {index + 1} 段</option>)}</select></label> : null}<p className={`interactive-explanation-text${narrator.status === 'speaking' && narrator.prompt_id === currentPrompt?.id ? ' is-speaking' : ''}`}>{currentPrompt?.text ?? currentScene?.summary ?? '本环节没有预设讲解，请观察课件中的操作提示。'}</p><p className="interactive-guide-note">{playbackSteps.length ? '画面会自动演示，讲完一段再往下走。可以暂停、问老师，或选择“自己试一试”。' : '看画布中的变化，有疑问时点击“问老师”，也可以拖动桌宠打开随身对话。'}</p></div>
      </aside>
    </div>
    <NarrationControls narrator={narrator} prompt={currentPrompt} enabled={voiceEnabled} started={started} enable={() => void enableVoice()} play={prompt => void playPrompt(prompt)} automatic={playbackSteps.length ? { ...playback, total: playbackSteps.length, begin: () => { setVoiceEnabled(true); playback.start(playback.status === 'ended' || detail.session.viewed_at ? 0 : resumeFrom.current); }, manual: tryManually } : undefined}>
      <details className="interactive-more"><summary aria-label="学习操作" title="更多学习操作"><svg aria-hidden="true" width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><circle cx="5" cy="12" r="2"/><circle cx="12" cy="12" r="2"/><circle cx="19" cy="12" r="2"/></svg><span className="interactive-control-label">学习操作</span></summary><div className="interactive-more-menu">
        <button type="button" className="secondary" onClick={() => { if (playback.active) tryManually(); else narrator.stop(); }} disabled={!playback.active && (narrator.status === 'idle' || narrator.status === 'ended')}>停止讲解</button>
        {commands.includes('reset') && started ? <button type="button" className="secondary" disabled={commandBusy} onClick={() => { if (window.confirm('重置当前实验会清除实验操作进度，保留当前课程环节。确定继续吗？')) void runCommand('reset'); }}>重置当前实验</button> : null}
        {commands.includes('complete') && started ? <button type="button" disabled={commandBusy} onClick={() => void runCommand('complete')}>完成本次学习</button> : null}
        {!playbackSteps.length && !manifest.capabilities.includes('COMPLETION') && active && started ? <button type="button" onClick={() => void finishManual()}>标记本次完成</button> : null}
        <button type="button" className="secondary" disabled={commandBusy} onClick={() => void restart()}>重新开始学习</button><button type="button" className="secondary" onClick={() => void saveAndExit()}>保存并退出</button>
        {active && latestRevisionId !== detail.session.revision_id ? <p>当前活动使用原版本，重新开始才使用新版；旧记录会保留。</p> : null}
      </div></details>
    </NarrationControls>
    {(saveError || error) ? <div className="interactive-feedback" role={saveError || error ? 'alert' : 'status'} data-pet-avoid><span>{saveError || error}</span>{saveStatus === 'unsaved' ? <><button type="button" className="secondary" onClick={() => void flushCheckpoint().catch(() => {})}>重试保存</button>{/冲突|已更新|其他窗口/.test(saveError) ? <button type="button" className="secondary" onClick={() => { if (window.confirm('读取远端记录会放弃本页未保存的操作。确定继续吗？')) { setCheckpointDirty(false); setSaveStatus('ready'); setRetryIndex(value => value + 1); } }}>读取远端记录</button> : null}</> : null}</div> : null}
  </main>;
}
