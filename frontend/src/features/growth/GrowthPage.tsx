import { useState, type KeyboardEvent } from "react";
import { AutomaticMemory } from "./AutomaticMemory";
import { MemoryDocuments } from "./MemoryDocuments";
import "./growth.css";

export function GrowthPage() {
  const [tab, setTab] = useState<"automatic" | "documents">("automatic");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [documentVisited, setDocumentVisited] = useState(false);
  const select = (next: typeof tab) => {
    setTab(next);
    if (next === "documents") setDocumentVisited(true);
  };
  const onTabKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const next = event.key === "Home" ? "automatic" : event.key === "End" ? "documents" : tab === "automatic" ? "documents" : "automatic";
    select(next);
    document.getElementById("memory-tab-" + next)?.focus();
  };
  return <main className="growth-page growth-page--document" data-testid="growth-page">
    <header className="memory-page-heading">
      <div><h1>个人记忆</h1><p className="growth-muted">管理 AI 整理的记忆，也可以写下你希望它了解的内容。</p></div>
      <button type="button" className="secondary" onClick={() => setSettingsOpen(true)}>记忆设置</button>
    </header>
    <div className="memory-tabs" role="tablist" aria-label="记忆内容">
      {([ ["automatic", "自动记忆"], ["documents", "我写的内容"] ] as const).map(([value, label]) => <button key={value} id={"memory-tab-" + value} role="tab" aria-selected={tab === value} aria-controls={"memory-content-" + value} tabIndex={tab === value ? 0 : -1} onKeyDown={onTabKey} onClick={() => select(value)}>{label}</button>)}
    </div>
    <section id="memory-content-automatic" role="tabpanel" aria-labelledby="memory-tab-automatic" hidden={tab !== "automatic"}>
      <AutomaticMemory settingsOpen={settingsOpen} onSettingsClose={() => setSettingsOpen(false)} />
    </section>
    <section id="memory-content-documents" role="tabpanel" aria-labelledby="memory-tab-documents" hidden={tab !== "documents"}>
      <p className="growth-muted memory-document-intro">你写下的内容单独保存，自动整理不会覆盖这里的文字。</p>
      {documentVisited && <MemoryDocuments />}
    </section>
    <details className="memory-privacy"><summary>使用与隐私说明</summary>
      <p>自动记忆由聊天中的明确信息整理而来，仅用于个性化辅导，不是测验成绩。你可以随时更正或遗忘。</p>
      <p>遗忘后，这条内容不再作为个人记忆使用；这不会删除原始聊天或外部 AI 服务中的历史会话。</p>
      <p>“用于 AI 辅导”控制 AI 教师是否参考你的个人记忆，包括已保存的个人文档；关闭后仍可管理内容。这里只指 AI 教师，不表示向真人教师共享。</p>
    </details>
  </main>;
}
