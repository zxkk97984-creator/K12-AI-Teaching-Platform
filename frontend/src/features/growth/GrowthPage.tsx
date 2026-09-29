import { MemoryDocuments } from "./MemoryDocuments";
import "./growth.css";

export function GrowthPage() {
  return <main className="growth-page growth-page--document" data-testid="growth-page">
    <header className="growth-header"><p className="growth-eyebrow">我的学习档案</p><h1>个人记忆</h1><p className="growth-muted">保存的当前版本会供 AI 教师参考；较长内容会按对话上下文长度截取。学段和教师风格在学习设置中调整。</p></header>
    <MemoryDocuments />
  </main>;
}
