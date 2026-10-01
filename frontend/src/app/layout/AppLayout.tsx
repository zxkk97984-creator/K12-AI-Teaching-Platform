import { useEffect, useRef, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { ApiError, getMe } from "../../features/identity/api";
import { AccountAvatar } from "../../features/identity/AccountAvatar";
import { AccountProvider } from "../../features/identity/AccountContext";
import { navigate } from "../../features/identity/session";
import { gradeLabel, type MeResponse, type Stage } from "../../features/identity/types";
import { ConversationProvider, useConversation } from "../../features/conversation/ConversationProvider";
import { listSessions, updateSession } from "../../features/conversation/api";
import { Companion } from "../../features/companion/components/Companion";
import { LearningTeacherProvider } from "../../features/companion/LearningTeacherContext";
import { CompanionAvatarProvider } from "../../features/companion/CompanionAvatar";
import { EditingGuardProvider } from "../editing/EditingGuard";

type NavigationItem = { path: string; label: string; mobileLabel: string; icon: string; end?: boolean };

function studentNavigation(stage: Stage | null | undefined, mobile = false): NavigationItem[] {
  const lower = stage === "PRIMARY_LOWER";
  const upper = stage === "PRIMARY_UPPER";
  const junior = stage === "JUNIOR";
  const book = lower ? "绘本书库" : upper ? "学习书库" : junior ? "学科资料" : "专题资料";
  const practice = lower || upper ? "趣味练习" : junior ? "专项练习" : "巩固训练";
  const teacher = lower || upper ? "AI 老师" : "AI 教师";
  if (mobile) return [
    { path: "/workbench", label: "学习首页", mobileLabel: "首页", icon: "home", end: true },
    { path: "/resources", label: book, mobileLabel: "学习", icon: "book" },
    { path: "/practice", label: practice, mobileLabel: "练习", icon: "practice" },
    { path: "/conversations", label: teacher, mobileLabel: "老师", icon: "chat" },
    { path: "/more", label: "更多", mobileLabel: "更多", icon: "resource" },
  ];
  return [
    { path: "/workbench", label: "学习首页", mobileLabel: "首页", icon: "home", end: true },
    { path: "/resources", label: book, mobileLabel: "学习", icon: "book" },
    { path: lower || upper ? "/animations" : "/activities", label: lower || upper ? "动画讲解" : junior ? "互动探索" : "互动实验", mobileLabel: "互动", icon: "resource" },
    { path: "/practice", label: practice, mobileLabel: "练习", icon: "practice" },
    ...(!lower && !upper ? [{ path: "/code", label: junior ? "编程入门" : "编程实践", mobileLabel: "编程", icon: "code" }] : []),
    { path: "/conversations", label: teacher, mobileLabel: "老师", icon: "chat" },
    { path: "/growth", label: "个人记忆", mobileLabel: "记忆", icon: "memory" },
  ];
}

const STUDENT_SIDEBAR_EXTRA: Pick<NavigationItem, "path" | "label" | "icon">[] = [
  { path: "/settings", label: "学习设置", icon: "settings" },
];

const ADMIN_NAV: NavigationItem[] = [
  { path: "/admin/ai", label: "AI 教师与能力", mobileLabel: "教师", icon: "chat" },
  { path: "/admin/resources", label: "资源管理", mobileLabel: "资源", icon: "resource", end: true },
  { path: "/admin/resources/interactive", label: "互动内容", mobileLabel: "互动", icon: "interactive" },
  { path: "/admin/authoring", label: "课程编排", mobileLabel: "课程", icon: "practice" },
];

function studentSection(pathname: string, search = ""): string | null {
  if (pathname.startsWith("/workbench") || pathname === "/study" || pathname === "/learn") return "/workbench";
  if (pathname.startsWith("/animations")) return "/animations";
  if (pathname.startsWith("/activities")) return "/activities";
  if (pathname.startsWith("/interactive")) {
    const from = new URLSearchParams(search).get("from");
    return from === "practice" ? "/practice" : from === "animations" ? "/animations" : "/activities";
  }
  if (pathname.startsWith("/code")) return "/code";
  if (pathname.startsWith("/more")) return "/more";
  if (["/courses", "/chapters", "/books", "/picturebooks", "/resources", "/lessons", "/study/lesson", "/learn/"].some((path) => pathname.startsWith(path))) return "/resources";
  if (pathname.startsWith("/practice")) return "/practice";
  if (pathname.startsWith("/conversations")) return "/conversations";
  if (pathname.startsWith("/growth")) return "/growth";
  return null;
}

function Icon({ name }: { name: string }) {
  const common = {
    width: 20,
    height: 20,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    "aria-hidden": true,
  };
  if (name === "interactive") return <svg {...common}><rect x="3" y="4" width="18" height="13" rx="2" /><path d="m10 8 5 3-5 3zM8 21h8M12 17v4" /></svg>;
  if (name === "home") return <svg {...common}><path d="m3 10 9-7 9 7v10H3z" /><path d="M9 20v-7h6v7" /></svg>;
  if (name === "code") return <svg {...common}><path d="m8 7-5 5 5 5m8-10 5 5-5 5M14 5l-4 14" /></svg>;
  if (name === "book") return <svg {...common}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5z" /><path d="M4 5.5v16A2.5 2.5 0 0 1 6.5 19H20" /><path d="M8 7h8M8 11h7" /></svg>;
  if (name === "practice") return <svg {...common}><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /><path d="m16.5 15.5 1.5 1.5-3 3-1.5.2.2-1.5z" /></svg>;
  if (name === "resource") return <svg {...common}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z" /><path d="M4 5.5v15M8 7h8M8 11h8M8 15h5" /></svg>;
  if (name === "memory") return <svg {...common}><path d="M12 3.5 14 5l2.5-.1.9 2.3 2.1 1.3-.8 2.4.8 2.4-2.1 1.3-.9 2.3L14 17l-2 1.5L10 17l-2.5.1-.9-2.3-2.1-1.3.8-2.4-.8-2.4 2.1-1.3.9-2.3L10 5z" /><path d="m8.5 11.5 2.2 2.2 4.8-5" /></svg>;
  if (name === "settings") return <svg {...common}><path d="M10.25 4.97L10.75 3.09L13.25 3.09L13.75 4.97L15.73 5.79L17.42 4.81L19.19 6.58L18.21 8.27L19.03 10.25L20.91 10.75L20.91 13.25L19.03 13.75L18.21 15.73L19.19 17.42L17.42 19.19L15.73 18.21L13.75 19.03L13.25 20.91L10.75 20.91L10.25 19.03L8.27 18.21L6.58 19.19L4.81 17.42L5.79 15.73L4.97 13.75L3.09 13.25L3.09 10.75L4.97 10.25L5.79 8.27L4.81 6.58L6.58 4.81L8.27 5.79Z" /><circle cx="12" cy="12" r="3" /></svg>;
  return <svg {...common}><path d="M4 5h16v12H7l-3 3z" /><path d="M8 9h8M8 13h5" /></svg>;
}

function GlobalConversationHistory({ onSelect }: { onSelect?: () => void }) {
  const { controller, sessions, detail, selecting, loading } = useConversation();
  const navigateTo = useNavigate();
  const [query, setQuery] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  // R30: these actions are not idempotent, so guard against a double click.
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState("");
  const [archivedSessions, setArchivedSessions] = useState<typeof sessions>([]);
  const [archiveLoading, setArchiveLoading] = useState(false);
  useEffect(() => {
    if (!showArchived) return;
    setArchiveLoading(true);
    void listSessions(true).then((items) => setArchivedSessions(items.filter((item) => item.archived_at))).catch(() => setArchivedSessions([])).finally(() => setArchiveLoading(false));
  }, [showArchived, sessions]);
  const displayedSessions = showArchived ? archivedSessions : sessions;
  const filtered = displayedSessions.filter((session) => {
    const title = session.title ?? session.chapter_title ?? "新对话";
    return !query.trim() || title.toLowerCase().includes(query.trim().toLowerCase());
  });

  useEffect(() => { void controller.initialize(); }, [controller]);

  const runAction = async (key: string, action: () => Promise<void>) => {
    if (busyAction) return;
    setBusyAction(key);
    setActionError("");
    try { await action(); }
    catch (error) { setActionError(error instanceof Error ? error.message : "操作失败，请重试"); }
    finally { setBusyAction(null); }
  };

  return <section className="app-history" aria-labelledby="app-history-title">
    <div className="app-history-toolbar">
      <div className="app-history-heading"><h2 id="app-history-title">{showArchived ? "已归档对话" : "最近对话"}</h2><span>{displayedSessions.length}</span><button type="button" className="app-history-toggle" onClick={() => setShowArchived((value) => !value)}>{showArchived ? "返回最近" : "查看归档"}</button></div>
      <label className="app-history-search"><span>搜索对话</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索对话" aria-label="搜索历史对话" /></label>
    </div>
    <div className="app-history-list">
      {loading && sessions.length === 0 || archiveLoading ? <p role="status">正在读取…</p> : null}
      {!loading && !archiveLoading && filtered.length === 0 ? <p className="app-history-empty">{query.trim() ? "没有搜索结果。" : showArchived ? "暂无归档对话。" : "尚无对话，先问一个问题吧。"}</p> : <ul>{filtered.map((session) => {
        const title = session.title ?? session.chapter_title ?? "新对话";
        return <li key={session.id}>
          <button type="button" className={detail?.id === session.id ? "is-active" : ""} disabled={selecting} onClick={() => { void controller.select(session.id); navigateTo(`/conversations?session=${session.id}`); onSelect?.(); }} title={title}>
            <span className="app-history-icon" aria-hidden="true"><Icon name="chat" /></span><span className="app-history-copy"><span className="app-history-title">{title}</span><span className="app-history-meta">{session.message_count} 条消息</span></span>
          </button>
          <div className="app-history-actions"><button type="button" disabled={busyAction !== null} aria-label={`重命名 ${title}`} onClick={() => runAction(`rename:${session.id}`, async () => { const next = window.prompt("给这段对话取个名字", title); if (next?.trim()) await controller.rename(session.id, next.trim()); })}>改名</button>{showArchived ? <button type="button" disabled={busyAction !== null} aria-label={`取消归档 ${title}`} onClick={() => runAction(`unarchive:${session.id}`, async () => { await updateSession(session.id, { archived: false }); await controller.reconnect(); })}>取消归档</button> : <button type="button" disabled={busyAction !== null} aria-label={`归档 ${title}`} onClick={() => runAction(`archive:${session.id}`, () => controller.archive(session.id))}>归档</button>}<button type="button" className="k12-danger-text" disabled={busyAction !== null} aria-label={`删除 ${title}`} onClick={() => { if (window.confirm("确认删除这段对话？删除后无法恢复。")) void runAction(`delete:${session.id}`, () => controller.remove(session.id)); }}>删除</button></div>
        </li>;
      })}</ul>}
      {actionError ? <p className="app-history-error" role="alert">{actionError}</p> : null}
    </div>
  </section>;
}

export function AppLayout({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<MeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const { pathname } = useLocation();
  useEffect(() => {
    let active = true;
    getMe().then((user) => { if (active) { setMe(user); setError(null); } }).catch((reason) => {
      if (!active) return;
      if (reason instanceof ApiError && reason.status === 401) navigate("/login");
      else setError(reason instanceof ApiError ? `${reason.message}${reason.requestId ? ` · ${reason.requestId}` : ""}` : "无法读取账号，请重试");
    });
    return () => { active = false; };
  }, [attempt, pathname]);
  useEffect(() => {
    const reset = () => { setMe(null); navigate("/login"); };
    const onUpdate = (event: Event) => {
      const updated = (event as CustomEvent<MeResponse>).detail;
      if (updated?.user?.id) setMe(updated);
    };
    window.addEventListener("identity:signed-out", reset);
    window.addEventListener("identity:unauthorized", reset);
    window.addEventListener("identity:updated", onUpdate);
    return () => { window.removeEventListener("identity:signed-out", reset); window.removeEventListener("identity:unauthorized", reset); window.removeEventListener("identity:updated", onUpdate); };
  }, []);
  if (error && !me) return <main className="auth-shell"><section className="auth-card" role="alert"><h1>暂时无法打开学习平台</h1><p>{error}</p><button onClick={() => setAttempt((v) => v + 1)}>重新加载</button></section></main>;
  if (!me) return <main className="auth-shell" role="status">正在读取学习档案…</main>;
  return <AccountLayout key={me.user.id} me={me}>{error ? <p role="alert">{error} <button className="secondary" onClick={() => setAttempt((v) => v + 1)}>重新读取账号</button></p> : null}{children}</AccountLayout>;
}

function AccountLayout({ me, children }: { me: MeResponse; children: ReactNode }) {
  return <AccountProvider me={me}><CompanionAvatarProvider userId={me.user.id}><ConversationProvider key={me.user.id}><LearningTeacherProvider><EditingGuardProvider><AccountFrame me={me}>{children}</AccountFrame></EditingGuardProvider></LearningTeacherProvider></ConversationProvider></CompanionAvatarProvider></AccountProvider>;
}

function AccountFrame({ me, children }: { me: MeResponse; children: ReactNode }) {
  const { pathname, search } = useLocation();
  const navigateTo = useNavigate();
  const { controller, detail: activeConversation } = useConversation();
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const historyDialog = useRef<HTMLDialogElement>(null);
  useEffect(() => { historyDialog.current?.close(); setMobileNavOpen(false); }, [pathname]);
  const admin = me.user.role === "admin";
  const adminPage = pathname.startsWith("/admin");
  const stage = me.profile?.stage;
  const items = adminPage ? ADMIN_NAV : studentNavigation(stage);
  const currentSection = adminPage ? null : studentSection(pathname, search);
  const mobileSection = (
    (currentSection && ["/activities", "/animations", "/code", "/growth"].includes(currentSection))
    || pathname.startsWith("/settings")
  ) ? "/more" : currentSection;
  const navTitle = adminPage ? "教学管理"
    : pathname.startsWith("/conversations") ? items.find((item) => item.path === "/conversations")?.label ?? "AI 教师"
    : pathname.startsWith("/chapters/") ? "章节学习"
    : pathname.startsWith("/picturebooks") ? "绘本阅读"
    : pathname.startsWith("/resources/") ? "资源详情"
    : pathname.startsWith("/animations") ? "教学动画"
    : pathname.startsWith("/activities") || pathname.startsWith("/interactive") ? "互动内容"
    : pathname.startsWith("/code") ? "在线编程"
    : pathname.startsWith("/more") ? "更多入口"
    : pathname.startsWith("/growth") ? "个人记忆"
    : pathname.startsWith("/settings") ? "学习设置"
    : items.find((item) => item.path === currentSection)?.label ?? "学习平台";
  const conversationPage = pathname.startsWith("/conversations");
  const interactiveSurface = pathname.startsWith("/interactive/");
  const [interactiveFocused, setInteractiveFocused] = useState(false);
  useEffect(() => {
    const update = (event: Event) => setInteractiveFocused(Boolean((event as CustomEvent).detail?.focused));
    window.addEventListener("interactive:layout", update);
    return () => window.removeEventListener("interactive:layout", update);
  }, []);
  useEffect(() => { setInteractiveFocused(false); }, [pathname]);
  const codeParams = new URLSearchParams(search);
  const codeSurface = pathname === "/code"
    ? Boolean(codeParams.get("task")) && !(codeParams.get("tab") === "history" && codeParams.get("view") === "record" && Boolean(codeParams.get("run")))
      ? "workspace" : "catalog"
    : undefined;
  // One topbar, not two: when a conversation is open its title replaces the
  // generic nav label rather than sitting in a second header beneath it.
  const activeTitle = conversationPage && activeConversation
    ? activeConversation.title ?? activeConversation.chapter_title ?? "新对话"
    : navTitle;
  const activeChapter = conversationPage ? activeConversation?.chapter_title ?? null : null;
  const closeMobile = () => setMobileNavOpen(false);
  const startConversation = () => { void controller.start().then((id) => { if (id) navigateTo(`/conversations?session=${id}`); }); };

  const readingSurface = pathname === "/resources" || pathname.startsWith("/books/");
  return <div className="app-shell" data-stage={stage ?? ""} data-admin={adminPage} data-interactive-surface={interactiveSurface} data-interactive-focused={interactiveSurface && interactiveFocused} data-reading-surface={readingSurface} data-code-surface={codeSurface}>
    <a href="#page-content" className="skip-link">跳到主要内容</a>
    {adminPage ? <button type="button" className="app-mobile-toggle" aria-label={mobileNavOpen ? "关闭导航" : "打开导航"} aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen((value) => !value)}><Icon name="book" /></button> : <NavLink to="/settings" className="k12-mobile-settings" aria-label="打开学习设置"><Icon name="settings" /></NavLink>}
    {mobileNavOpen ? <button type="button" className="app-sidebar-backdrop" aria-label="关闭导航" onClick={closeMobile} /> : null}
    <aside className={`app-sidebar${mobileNavOpen ? " is-open" : ""}`} aria-label="平台导航">
      <a className="app-brand" href={admin ? "/admin/resources" : "/workbench"} onClick={closeMobile}><span className="app-brand-mark" aria-hidden="true"><img className="brand-symbol" src="/shuangling-brand.svg" width="40" height="40" alt="" /></span><span className="app-brand-copy"><strong>霜铃 K12</strong><small>让每个问题都有回应</small></span></a>
      <nav className="app-sidebar-nav" aria-label={adminPage ? "管理导航" : "学生导航"}>
        {items.map((item) => <NavLink key={item.path} to={item.path} end={item.end} className={({ isActive }) => isActive || currentSection === item.path ? "active" : ""} onClick={closeMobile}><Icon name={item.icon} /><span>{item.label}</span></NavLink>)}
      </nav>
      {!adminPage ? <nav className="app-sidebar-secondary" aria-label="学习设置与管理入口">
        {!adminPage ? STUDENT_SIDEBAR_EXTRA.map((item) => <NavLink key={item.path} to={item.path} className={({ isActive }) => isActive ? "active" : ""} onClick={closeMobile}><Icon name={item.icon} /><span>{item.label}</span></NavLink>) : null}
        {admin && !adminPage ? <NavLink to="/admin/resources" onClick={closeMobile}><Icon name="settings" /><span>管理入口</span></NavLink> : null}
      </nav> : null}
      <NavLink to="/settings" className="app-sidebar-user" aria-label="打开个人设置" onClick={closeMobile}>
        <AccountAvatar me={me} />
        <span className="app-user-copy"><strong title={me.profile?.nickname || me.user.username}>{me.profile?.nickname || me.user.username}</strong><small>{admin ? "管理员" : gradeLabel(me.profile?.grade)}</small></span>
      </NavLink>
    </aside>
    <div className={`app-main${conversationPage ? " app-main--conversation" : ""}`}>
      {codeSurface ? <span className="codelab-pet-slot" aria-hidden="true" /> : null}
      <header className={`app-topbar${conversationPage ? " app-topbar--conversation" : ""}`}><div className="app-topbar-title"><p className="app-breadcrumb">{adminPage ? "管理端" : "我的学习"}</p>{conversationPage ? <h1 className="app-topbar-page-title">{activeTitle}</h1> : <p className="app-topbar-page-title">{activeTitle}</p>}</div>{activeChapter && activeChapter !== activeTitle ? <span className="conv-context-chip">当前参考：{activeChapter}</span> : null}<div className="app-topbar-account">{conversationPage ? <><button type="button" className="secondary" onClick={() => historyDialog.current?.showModal()}>对话记录</button><button type="button" onClick={startConversation}>新对话</button></> : <>{!adminPage ? <NavLink to="/conversations" className="k12-mobile-chat" aria-label="打开完整聊天界面"><Icon name="chat" /><span>聊天</span></NavLink> : null}<span className="app-stage-label">{adminPage ? "管理员" : gradeLabel(me.profile?.grade)}</span></>}</div></header>
      <div id="page-content" className={`app-content${conversationPage ? " app-content--conversation" : ""}`} tabIndex={-1}>{adminPage && !admin ? <main><h1>仅管理员可访问</h1><a href="/conversations">返回学习平台</a></main> : children}</div>
    </div>
    {conversationPage ? <dialog ref={historyDialog} className="k12-history-dialog" onClick={(event) => { if (event.target === event.currentTarget) historyDialog.current?.close(); }}><div className="k12-dialog-heading"><h2>对话记录</h2><button type="button" className="secondary" aria-label="关闭对话记录" onClick={() => historyDialog.current?.close()}>关闭</button></div><GlobalConversationHistory onSelect={() => historyDialog.current?.close()} /></dialog> : null}
    {!adminPage ? <nav className="k12-mobile-nav" aria-label="主要导航">{studentNavigation(stage, true).map((item) => <NavLink key={item.path} to={item.path} end={item.end} className={({ isActive }) => isActive || mobileSection === item.path ? "active" : ""}><Icon name={item.icon} /><span>{item.mobileLabel}</span></NavLink>)}</nav> : null}
    {!admin && stage && pathname !== "/onboarding" && !adminPage ? <Companion userId={me.user.id} /> : null}
  </div>;
}
