import type { ReactNode } from "react";
import type { QuizSessionDTO } from "../../features/quiz/types";

export function PracticeStatus({ completed, children }: { completed: boolean; children: ReactNode }) {
  return <span className={`practice-status${completed ? " is-complete" : ""}`}><span aria-hidden="true">{completed ? "✓" : "◷"}</span><span>{children}</span></span>;
}

export function QuizProgress({ quiz }: { quiz: QuizSessionDTO }) {
  return <div className="practice-card-progress"><p>已作答 <strong>{quiz.progress.answered}/{quiz.progress.total}</strong> 题{quiz.status === "COMPLETED" ? ` · 答对 ${quiz.progress.correct} 题` : ""}</p><progress value={quiz.progress.answered} max={Math.max(quiz.progress.total, 1)} aria-label={`已作答 ${quiz.progress.answered} 题，共 ${quiz.progress.total} 题`} /></div>;
}

export function PracticeContentCard({ className = "", cover, category, title, description, status, meta, progress, actions }: {
  className?: string; cover?: ReactNode; category: string; title: string; description?: string;
  status: ReactNode; meta: ReactNode; progress?: ReactNode; actions: ReactNode;
}) {
  return <article className={`practice-content-card ${className}`} data-testid="practice-content-card">
    {cover ? <div className="practice-card-cover">{cover}</div> : null}
    <div className="practice-card-body"><div className="practice-card-eyebrow"><span>{category}</span>{status}</div><h2>{title}</h2>{description ? <p className="practice-card-description" title={description}>{description}</p> : null}{meta ? <p className="practice-list-meta">{meta}</p> : null}{progress}<div className="practice-card-actions" data-pet-avoid>{actions}</div></div>
  </article>;
}
