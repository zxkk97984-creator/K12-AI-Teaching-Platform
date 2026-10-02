import type { ReactNode } from "react";
import "./content.css";

export function ContentLayout({
  title,
  subtitle,
  toolbar,
  rail,
  aside,
  children,
  variant = "default",
  className = "",
  eyebrow = "霜铃 · 课程",
}: {
  title: string;
  subtitle?: string;
  toolbar?: ReactNode;
  rail?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  variant?: "default" | "reading";
  className?: string;
  eyebrow?: string;
}) {
  return (
    <main className={`content-page content-page--${variant} ${className}`}>
      <header className="content-page__header">
        <div className="content-page__heading">
          {variant === "reading" ? <a className="reader-library-back" href="/resources">← 返回资料库</a> : <p className="eyebrow">{eyebrow}</p>}
          {variant === "reading" ? <p className="reader-course-name">{title}</p> : <h1 className="content-page__title">{title}</h1>}
          {subtitle ? <p className="content-page__subtitle">{subtitle}</p> : null}
        </div>
        <div className="content-page__actions">
          {toolbar}
          {variant !== "reading" ? <a className="content-link" href="/workbench">
            返回工作台
          </a> : null}
        </div>
      </header>
      <div
        className="content-page__body"
        data-has-rail={rail ? "true" : "false"}
        data-has-aside={aside ? "true" : "false"}
      >
        {rail ? (
          <nav className="content-page__rail" aria-label="章节导航">
            {rail}
          </nav>
        ) : null}
        <section className="content-page__main">{children}</section>
        {aside ? (
          <aside className="content-page__aside" aria-label="页面信息">
            {aside}
          </aside>
        ) : null}
      </div>
    </main>
  );
}
