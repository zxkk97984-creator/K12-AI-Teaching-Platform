/* K12 interactive bridge v1. Injected by the host before authored scripts. */
(() => {
  "use strict";
  const channel = "k12-interactive-v1";
  let context = null;
  let parentOrigin = null;
  let resolveReady;
  const ready = new Promise((resolve) => { resolveReady = resolve; });
  const pending = new Map();
  const listeners = new Set();
  const sessionListeners = new Set();
  let commandHandler = null;
  let commands = [];
  const object = value => value && typeof value === "object" && !Array.isArray(value);
  const identifier = value => typeof value === "string" && /^[A-Za-z0-9_-]{1,100}$/.test(value);
  const send = (type, payload) => {
    if (!context) return Promise.reject(new Error("互动宿主尚未就绪"));
    const messageId = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        pending.delete(messageId);
        reject(new Error("宿主没有确认请求，请重试"));
      }, 15000);
      pending.set(messageId, { resolve, reject, timer });
      parent.postMessage({
        channel, instance_id: context.instance_id, session_id: context.session_id,
        revision_id: context.revision_id, message_id: messageId, type, payload,
      }, parentOrigin);
    });
  };
  window.addEventListener("message", (event) => {
    if (event.source !== parent || !object(event.data) || event.data.channel !== channel) return;
    const message = event.data;
    if (message.type === "init" && !context) {
      if (!/^https?:\/\//.test(event.origin) || ![message.instance_id, message.session_id, message.revision_id, message.message_id].every(identifier) || !object(message.payload)) return;
      parentOrigin = event.origin;
      context = {
        instance_id: message.instance_id, session_id: message.session_id,
        revision_id: message.revision_id, gameState: message.payload?.game_state ?? {},
        currentScene: message.payload?.current_scene_id ?? null,
        prompts: message.payload?.prompts ?? [],
        preview: Boolean(message.payload?.preview),
      };
      resolveReady(Object.freeze({ ...context }));
      parent.postMessage({
        channel, instance_id: context.instance_id, session_id: context.session_id,
        revision_id: context.revision_id, message_id: crypto.randomUUID(),
        type: "ready", payload: null,
      }, parentOrigin);
      return;
    }
    if (!context || event.origin !== parentOrigin ||
        message.instance_id !== context.instance_id ||
        message.session_id !== context.session_id ||
        message.revision_id !== context.revision_id) return;
    if (message.type === "saved" || message.type === "save_failed") {
      const request = pending.get(message.message_id);
      if (!request) return;
      clearTimeout(request.timer);
      pending.delete(message.message_id);
      if (message.type === "saved") request.resolve(message.payload);
      else request.reject(new Error(message.payload?.message ?? "操作未保存"));
    } else if (message.type === "narration_state") {
      if (object(message.payload) && ["idle", "loading", "speaking", "paused", "ended", "unavailable", "error"].includes(message.payload.status)) listeners.forEach((listener) => listener(message.payload));
    } else if (message.type === "workspace_state") {
      if (object(message.payload) && identifier(message.payload.scene_id)) sessionListeners.forEach(listener => listener(message.payload));
    } else if (message.type === "workspace_command") {
      if (!identifier(message.message_id) || !object(message.payload) || !commands.includes(message.payload.command) || !commandHandler) return;
      Promise.resolve().then(() => commandHandler(message.payload)).then(() => reply(true), error => reply(false, String(error?.message || "操作未完成").slice(0, 500)));
      function reply(ok, error) {
        parent.postMessage({ channel, ...{instance_id: context.instance_id, session_id: context.session_id, revision_id: context.revision_id}, message_id: message.message_id, type: "command_result", payload: {ok, ...(error ? {error} : {})} }, parentOrigin);
      }
    }
  });
  window.K12 = Object.freeze({
    ready: () => ready,
    scene: Object.freeze({ enter: (sceneId) => send("scene_changed", { scene_id: sceneId }) }),
    narration: Object.freeze({
      play: (promptId) => send("request_narration", { prompt_id: promptId }),
      onState: (listener) => { listeners.add(listener); return () => listeners.delete(listener); },
    }),
    checkpoint: Object.freeze({ save: (gameState) => send("checkpoint", { game_state: gameState }) }),
    complete: (result = {}) => send("complete", { game_result: result }),
    askTeacher: () => send("ask_teacher", {}),
    workspace: Object.freeze({
      register: (supported, handler, options = {}) => {
        if (!Array.isArray(supported) || supported.some(value => !["scene", "pause", "reset", "complete", "demonstrate"].includes(value)) || typeof handler !== "function") return Promise.reject(new Error("工作区控制无效"));
        commands = [...new Set(supported)]; commandHandler = handler;
        return send("workspace_ready", {version: 1, commands, ...(options.playback_steps ? {playback_steps: options.playback_steps} : {})});
      },
      report: (value) => send("activity_state", value),
      onSession: (listener) => { sessionListeners.add(listener); return () => sessionListeners.delete(listener); },
    }),
    assets: Object.freeze({
      url: (name) => {
        const value = window.__K12_ASSETS__?.[name];
        if (!value) throw new Error(`包内素材不存在：${name}`);
        return value;
      },
    }),
  });
})();
