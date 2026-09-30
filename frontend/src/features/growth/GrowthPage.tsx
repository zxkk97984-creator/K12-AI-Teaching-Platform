import { AutomaticMemory } from "./AutomaticMemory";
import { MemoryDocuments } from "./MemoryDocuments";
import "./growth.css";

export function GrowthPage() {
  return <main className="growth-page growth-page--document" data-testid="growth-page">
    <header className="growth-header"><p className="growth-eyebrow">我的学习档案</p><h1>个人记忆</h1><p className="growth-muted">对话中的重要信息会自动整理。你写下的内容单独保存，随时可以修改或遗忘。</p></header>
    <AutomaticMemory />
    <section aria-label="手写个人记忆"><h2>我亲自写下的内容</h2><p className="growth-muted">自动整理不会覆盖这里的文字。</p><MemoryDocuments /></section>
  </main>;
}
