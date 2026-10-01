import { useEffect, useMemo, useRef, useState } from "react";
import { adminCreateResource, adminListResources, adminPatchResource } from "../../features/resources/api";
import type { ResourceSummary } from "../../features/resources/types";
import {
  adminActivateInteractive, adminListInteractiveVersions, adminPreviewInteractive,
  adminCloneInteractive,
  adminListInteractiveOverview,
  adminSaveInteractiveManifest, adminUploadInteractive, adminUploadPromptAudio,
  type InteractiveManifest, type InteractivePurpose,
} from "../../features/interactive/api";
import { useNarration } from "../../features/interactive/useNarration";
import "./admin-interactive.css";

type ImportItem = { file: File; title: string; stage: string; purpose: InteractivePurpose; subject: string; status: string; resourceId?: string };
type Version = { id: string; revision: number; manifest: InteractiveManifest; locked: boolean; package_sha256: string; capabilities: string[] };
const STAGES = [
  ["PRIMARY_LOWER", "小学 1–3 年级"], ["PRIMARY_UPPER", "小学 4–6 年级"],
  ["JUNIOR", "初中"], ["SENIOR", "高中"],
] as const;
const PURPOSES: Array<[InteractivePurpose, string]> = [["LESSON", "互动讲解"], ["GAME", "互动小游戏"], ["EXPERIMENT", "互动实验"]];
function message(error: unknown) { return error instanceof Error ? error.message : "操作失败，请重试"; }
function slugFor(file: File) {
  const stem = file.name.replace(/\.(html|zip)$/i, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return `${stem || "interactive"}-${crypto.randomUUID().slice(0, 8)}`;
}

export function AdminInteractivePage() {
  const [resources, setResources] = useState<ResourceSummary[]>([]);
  const [overview, setOverview] = useState<Awaited<ReturnType<typeof adminListInteractiveOverview>>["items"]>([]);
  const [selectedId, setSelectedId] = useState(() => new URLSearchParams(window.location.search).get("resource") ?? "");
  const [versions, setVersions] = useState<Version[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selectedVersion, setSelectedVersion] = useState("");
  const [manifestText, setManifestText] = useState("");
  const [imports, setImports] = useState<ImportItem[]>([]);
  const [defaultStage, setDefaultStage] = useState("PRIMARY_LOWER");
  const [defaultPurpose, setDefaultPurpose] = useState<InteractivePurpose>("LESSON");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [metaTitle, setMetaTitle] = useState("");
  const [metaDescription, setMetaDescription] = useState("");
  const [preview, setPreview] = useState<{ html: string; manifest: InteractiveManifest; revisionId: string } | null>(null);
  const [previewSize, setPreviewSize] = useState<"desktop" | "mobile">("desktop");
  const [previewEvents, setPreviewEvents] = useState<string[]>([]);
  const previewNarration = useNarration((prompt) => `/api/v1/admin/resources/${selectedId}/interactive-revisions/${preview?.revisionId}/audio/${encodeURIComponent(prompt.id)}`);
  useEffect(() => { if (!preview) previewNarration.stop(); }, [preview, previewNarration.stop]);
  const frame = useRef<HTMLIFrameElement>(null);
  const instanceId = useRef(crypto.randomUUID());
  useEffect(() => {
    if (!preview) return;
    frame.current?.contentWindow?.postMessage({
      channel: "k12-interactive-v1", instance_id: instanceId.current, session_id: "preview",
      revision_id: preview.revisionId, message_id: crypto.randomUUID(), type: "narration_state",
      payload: { status: previewNarration.status, prompt_id: previewNarration.prompt_id, subtitle: previewNarration.subtitle },
    }, "*");
  }, [preview, previewNarration.status, previewNarration.prompt_id, previewNarration.subtitle]);
  const resource = useMemo(() => resources.find((item) => item.id === selectedId), [resources, selectedId]);
  const version = versions.find((item) => item.id === selectedVersion);

  const reload = async () => {
    const [result, summary] = await Promise.all([adminListResources({ kind: "INTERACTIVE", limit: 100 }), adminListInteractiveOverview()]);
    setResources(result.items);
    setOverview(summary.items);
  };
  useEffect(() => { void reload().catch((caught) => setError(message(caught))); }, []);
  useEffect(() => {
    if (!selectedId) { setVersions([]); return; }
    let active = true;
    void adminListInteractiveVersions(selectedId).then((result) => {
      if (!active) return;
      setVersions(result.items as Version[]);
      setActiveId(result.active_revision_id);
      setSelectedVersion((current) => result.items.some((item) => item.id === current) ? current : result.items[0]?.id ?? "");
    }).catch((caught) => { if (active) setError(message(caught)); });
    return () => { active = false; };
  }, [selectedId, notice]);
  useEffect(() => { setManifestText(version ? JSON.stringify(version.manifest, null, 2) : ""); }, [version?.id, version?.manifest]);
  useEffect(() => { setMetaTitle(resource?.title ?? ""); setMetaDescription(resource?.description ?? ""); }, [resource?.id, resource?.title, resource?.description]);

  const act = async (action: () => Promise<unknown>, success: string) => {
    setBusy(true); setError(""); setNotice("");
    try { await action(); setNotice(success); await reload(); }
    catch (caught) { setError(message(caught)); }
    finally { setBusy(false); }
  };
  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const next = Array.from(files).map((file) => ({ file, title: file.name.replace(/\.(html|zip)$/i, ""), stage: defaultStage, purpose: defaultPurpose, subject: "数学", status: "待导入" }));
    setImports((old) => [...old, ...next]);
  };
  const updateImport = (index: number, patch: Partial<ImportItem>) => setImports((old) => old.map((row, at) => at === index ? { ...row, ...patch } : row));
  const runImport = async () => {
    setBusy(true); setError("");
    for (let index = 0; index < imports.length; index += 1) {
      const item = imports[index];
      if (item.status === "已导入") continue;
      if (!/\.(html|zip)$/i.test(item.file.name)) { updateImport(index, { status: "失败：只支持 HTML 或 ZIP" }); continue; }
      try {
        const resourceId = item.resourceId ?? (await adminCreateResource({
          slug: slugFor(item.file), title: item.title.trim(), description: `${item.title} · 互动内容`,
          kind: "INTERACTIVE", interactive_purpose: item.purpose, interactive_subject: item.subject.trim(),
          stage: item.stage, source_kind: "NEW_SOURCE", source_note: item.file.name,
          license_code: "PROJECT-ORIGINAL", license_note: "管理员导入",
        })).id;
        updateImport(index, { resourceId, status: "正在上传" });
        await adminUploadInteractive(resourceId, item.file);
        updateImport(index, { resourceId, status: "已导入" });
        setSelectedId(resourceId);
      } catch (caught) {
        const reason = message(caught);
        const needsDetails = /INTERACTIVE_(MANIFEST|STAGE_CONFLICT|METADATA|FILE_MISSING|AUDIO_MISSING)/.test(reason);
        updateImport(index, { status: `${needsDetails ? "待补充信息" : "失败"}：${reason}` });
      }
    }
    await reload().catch((caught) => setError(message(caught)));
    setBusy(false);
  };

  const saveManifest = async () => {
    if (!selectedId || !version) return;
    await act(async () => {
      const parsed = JSON.parse(manifestText) as InteractiveManifest;
      await adminSaveInteractiveManifest(selectedId, version.id, parsed);
    }, "场景与问题已保存，发布前可预览。当前版本发布后将锁定。 ");
  };
  const openPreview = async () => {
    if (!selectedId || !version) return;
    try {
      const result = await adminPreviewInteractive(selectedId, version.id);
      instanceId.current = crypto.randomUUID();
      setPreview({ html: result.document_html, manifest: result.manifest, revisionId: result.revision_id });
      setPreviewEvents([]);
    } catch (caught) { setError(message(caught)); }
  };
  useEffect(() => {
    if (!preview) return;
    const onMessage = (event: MessageEvent) => {
      const data = event.data;
      if (event.source !== frame.current?.contentWindow || event.origin !== "null" || data?.channel !== "k12-interactive-v1" || data.instance_id !== instanceId.current || data.session_id !== "preview" || data.revision_id !== preview.revisionId || typeof data.message_id !== "string") return;
      if (!["ready", "scene_changed", "request_narration", "checkpoint", "complete", "ask_teacher", "error"].includes(data.type)) return;
      setPreviewEvents((old) => [...old.slice(-19), `${new Date().toLocaleTimeString()} ${data.type} ${JSON.stringify(data.payload ?? {}).slice(0, 200)}`]);
      if (data.type === "ready") return;
      const reply = (type: string, payload: unknown) => frame.current?.contentWindow?.postMessage({ channel: "k12-interactive-v1", instance_id: instanceId.current, session_id: "preview", revision_id: preview.revisionId, message_id: data.message_id, type, payload }, "*");
      if (data.type === "request_narration") {
        const prompt = preview.manifest.prompts.find((item) => item.id === data.payload?.prompt_id);
        if (!prompt) { reply("save_failed", { message: "预设问题不存在" }); return; }
        void previewNarration.play(prompt).then((accepted) => reply(
          accepted ? "saved" : "save_failed",
          accepted ? { preview: true } : { message: "没有可用的朗读声音；可继续看字幕" },
        ));
        return;
      }
      reply("saved", { preview: true, persisted: false });
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [preview, selectedId, previewNarration.play]);

  return <main className="admin-interactive"><header><span className="interactive-kicker">资源管理 / 互动内容</span><h1>互动内容</h1><p>导入离线 HTML 或 ZIP，配置场景与问题，使用学生端相同的受限播放器预览后发布。</p></header>
    {error ? <p role="alert" className="admin-interactive-error">{error}</p> : null}{notice ? <p role="status">{notice}</p> : null}
    <section className="admin-interactive-panel"><h2>批量导入</h2><div className="admin-interactive-defaults"><label>默认学段<select value={defaultStage} onChange={(event) => setDefaultStage(event.target.value)}>{STAGES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>默认用途<select value={defaultPurpose} onChange={(event) => setDefaultPurpose(event.target.value as InteractivePurpose)}>{PURPOSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label><label>选择文件<input type="file" multiple accept=".html,.zip" onChange={(event) => addFiles(event.target.files)} /></label></div>
      {imports.length > 0 && <div className="admin-interactive-imports">{imports.map((item, index) => <div key={`${item.file.name}-${index}`}><strong>{item.file.name}</strong><input aria-label={`标题 ${item.file.name}`} value={item.title} disabled={item.status === "已导入"} onChange={(event) => updateImport(index, { title: event.target.value })} /><select aria-label={`学段 ${item.file.name}`} value={item.stage} disabled={item.status === "已导入"} onChange={(event) => updateImport(index, { stage: event.target.value })}>{STAGES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><select aria-label={`用途 ${item.file.name}`} value={item.purpose} disabled={item.status === "已导入"} onChange={(event) => updateImport(index, { purpose: event.target.value as InteractivePurpose })}>{PURPOSES.map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><input aria-label={`学科 ${item.file.name}`} value={item.subject} disabled={item.status === "已导入"} onChange={(event) => updateImport(index, { subject: event.target.value })} /><span>{item.status}</span></div>)}</div>}
      <button type="button" disabled={busy || !imports.length} onClick={() => void runImport()}>导入待处理文件</button><p className="admin-interactive-help">每个文件独立处理。ZIP 应包含 manifest.json 与 index.html；清单学段和用途必须与此处选择一致。失败项可修改后单独重试。</p></section>
    <section className="admin-interactive-panel"><h2>已登记内容</h2><div className="admin-interactive-list">{resources.map((item) => { const summary = overview.find((row) => row.id === item.id); return <button type="button" key={item.id} className={selectedId === item.id ? "selected" : ""} onClick={() => { setSelectedId(item.id); setPreview(null); }}>{item.title}<small>{item.stage} · {item.interactive_subject} · {item.interactive_purpose}</small><small>{summary?.active_revision ? `第 ${summary.active_revision} 版` : "待上传"} · {summary?.validation_report?.status === "PASS" ? "结构校验通过" : "待校验"} · {item.publication_status}</small><small>场景通信：{summary?.scene_capability_declared ? "已声明" : "未声明"} · 检查点：{summary?.checkpoint_capability_declared ? "已声明" : "未声明"}</small></button>; })}</div>{resources.length === 0 ? <p>还没有互动内容。</p> : null}</section>
    {resource && <section className="admin-interactive-panel"><h2>{resource.title}</h2><p>{resource.stage} · {resource.interactive_subject} · {resource.publication_status} · 审校 {resource.review_status}</p><form className="admin-interactive-defaults" onSubmit={(event) => { event.preventDefault(); void act(() => adminPatchResource(resource.id, { title: metaTitle.trim(), description: metaDescription.trim() }), "内容信息已更新。"); }}><label>标题<input value={metaTitle} onChange={(event) => setMetaTitle(event.target.value)} required /></label><label>简短介绍<input value={metaDescription} onChange={(event) => setMetaDescription(event.target.value)} /></label><button type="submit" disabled={busy}>保存信息</button></form><div className="admin-interactive-actions"><button type="button" disabled={busy || resource.review_status === "HUMAN_APPROVED"} onClick={() => void act(() => adminPatchResource(resource.id, { review_status: "HUMAN_APPROVED" }), "已记录管理员人工审校。")}>人工审校通过</button><button type="button" disabled={busy || !activeId || resource.review_status !== "HUMAN_APPROVED" || resource.is_test_fixture} onClick={() => void act(() => adminPatchResource(resource.id, { publication_status: "PUBLISHED" }), "内容已发布到指定学段。")}>发布</button><button type="button" disabled={busy || resource.publication_status === "WITHDRAWN"} onClick={() => void act(() => adminPatchResource(resource.id, { publication_status: "WITHDRAWN" }), "内容已下架。")}>下架</button></div>
      <label className="admin-interactive-help"><input type="checkbox" checked={Boolean(resource.local_demo_visible)} disabled={busy} onChange={(event) => { const enabled = event.target.checked; void act(() => adminPatchResource(resource.id, { local_demo_visible: enabled }), enabled ? "已开启本地演示可见。" : "已关闭本地演示可见。"); }} /> 本地比赛演示可见</label><label className="admin-interactive-help">上传新 HTML／ZIP 版本<input type="file" accept=".html,.zip" disabled={busy} onChange={(event) => { const file = event.target.files?.[0]; if (file) void act(async () => { const uploaded = await adminUploadInteractive(resource.id, file); setSelectedVersion(uploaded.id); }, "新版本已导入，可先编辑台词与预览。"); }} /></label><h3>版本</h3><div className="admin-interactive-versions">{versions.map((item) => <button type="button" key={item.id} className={selectedVersion === item.id ? "selected" : ""} onClick={() => setSelectedVersion(item.id)}>第 {item.revision} 版{item.id === activeId ? " · 当前发布版本" : ""}{item.locked ? " · 已锁定" : " · 可编辑"}</button>)}</div>
      {version && <div className="admin-interactive-version"><label>场景、台词与内容摘要（k12-interactive-v1 清单）<textarea value={manifestText} spellCheck={false} rows={20} disabled={version.locked} onChange={(event) => setManifestText(event.target.value)} /></label><p className="admin-interactive-help">场景和问题 ID 必须唯一。进入场景自动朗读的问题每场景最多一个。已发布版本只读；修改台词可复制为可编辑版本；修改 HTML 可上传新版本。</p><div className="admin-interactive-actions"><button type="button" disabled={busy} onClick={() => void act(async () => { const copied = await adminCloneInteractive(resource.id, version.id); setSelectedVersion(copied.id); }, "已创建可编辑版本，可修改台词后预览并设为当前版本。")}>复制为可编辑版本</button><button type="button" disabled={busy || version.locked} onClick={() => void saveManifest()}>保存配置</button><button type="button" disabled={busy} onClick={() => void openPreview()}>预览</button><a href={`/api/v1/admin/resources/${resource.id}/interactive-revisions/${version.id}/original`}>下载原始内容包</a><button type="button" disabled={busy || (!resource.local_demo_visible && resource.review_status !== "HUMAN_APPROVED")} onClick={() => void act(() => adminActivateInteractive(resource.id, version.id), "已将该版本设为当前版本。旧活动仍使用原版本。")}>设为当前版本</button></div><h4>问题音频</h4>{version.manifest.prompts.map((prompt) => <label className="admin-interactive-audio" key={prompt.id}>{prompt.id} · {prompt.text}<input type="file" accept=".mp3,.ogg,.wav,audio/*" disabled={busy || version.locked || Boolean(prompt.audio)} onChange={(event) => { const file = event.target.files?.[0]; if (file) void act(() => adminUploadPromptAudio(resource.id, version.id, prompt.id, file), `问题 ${prompt.id} 的音频已保存。`); }} />{prompt.audio && <audio controls src={`/api/v1/admin/resources/${resource.id}/interactive-revisions/${version.id}/audio/${prompt.id}`} />}</label>)}</div>}
    </section>}
    {preview && <section className="admin-interactive-panel"><div className="admin-interactive-preview-head"><h2>受限播放预览</h2><button type="button" onClick={() => { previewNarration.stop(); setPreview(null); }}>关闭预览</button><button type="button" onClick={() => setPreviewSize(previewSize === "desktop" ? "mobile" : "desktop")}>{previewSize === "desktop" ? "切换移动端" : "切换桌面"}</button></div><p>预览事件不会写入学生学习记录。</p><iframe key={instanceId.current} ref={frame} className={previewSize} title="互动内容管理预览" sandbox="allow-scripts" referrerPolicy="no-referrer" srcDoc={preview.html} onLoad={() => frame.current?.contentWindow?.postMessage({ channel: "k12-interactive-v1", instance_id: instanceId.current, session_id: "preview", revision_id: preview.revisionId, message_id: crypto.randomUUID(), type: "init", payload: { game_state: {}, current_scene_id: preview.manifest.scenes[0]?.id ?? null, prompts: preview.manifest.prompts, preview: true } }, "*")} /><h3>预设讲解与朗读</h3><ul className="admin-interactive-preview-prompts">{preview.manifest.prompts.map((prompt) => <li key={prompt.id}>{prompt.text} <button type="button" onClick={() => void previewNarration.play(prompt)}>试听{prompt.audio ? "上传音频" : "系统声音"}</button></li>)}</ul><div className="admin-interactive-actions"><button type="button" onClick={previewNarration.status === "paused" ? previewNarration.resume : previewNarration.pause} disabled={previewNarration.status !== "speaking" && previewNarration.status !== "paused"}>{previewNarration.status === "paused" ? "继续" : "暂停"}</button><button type="button" onClick={previewNarration.stop}>停止</button></div><p role="status">{previewNarration.status === "speaking" ? "正在朗读" : previewNarration.status === "unavailable" ? "没有可用的中文声音，请看字幕" : previewNarration.status === "error" ? "朗读失败，请检查音频" : ""} {previewNarration.subtitle}</p><h3>SDK 事件</h3><pre>{previewEvents.length ? previewEvents.join("\n") : "尚无事件"}</pre></section>}
  </main>;
}
