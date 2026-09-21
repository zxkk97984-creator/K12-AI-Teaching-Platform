import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router-dom";
import { ApiError, getMe, logout } from "../../features/identity/api";
import { navigate } from "../../features/identity/session";
import { stageLabel, type MeResponse } from "../../features/identity/types";
import { ConversationProvider, useConversation } from "../../features/conversation/ConversationProvider";
import { listSessions, updateSession } from "../../features/conversation/api";
import { Companion } from "../../features/companion/components/Companion";
import { EditingGuardProvider } from "../editing/EditingGuard";

type NavigationItem = { path: string; label: string; icon: string; end?: boolean };

const STUDENT_NAV: NavigationItem[] = [
  { path: "/conversations", label: "AI 对话", icon: "chat", end: true },
  { path: "/study", label: "学习中心", icon: "book", end: true },
  { path: "/practice", label: "自主练习", icon: "practice" },
  { path: "/resources", label: "资源中心", icon: "resource" },
  { path: "/growth", label: "成长与记忆", icon: "memory" },
  { path: "/settings", label: "设置", icon: "settings" },
];

const ADMIN_NAV: NavigationItem[] = [
  { path: "/admin/resources", label: "资源管理", icon: "resource" },
  { path: "/admin/authoring", label: "课程编排", icon: "book" },
];

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
  if (name === "book") return <svg {...common}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5z" /><path d="M4 5.5v16A2.5 2.5 0 0 1 6.5 19H20" /><path d="M8 7h8M8 11h7" /></svg>;
  if (name === "practice") return <svg {...common}><rect x="4" y="3" width="16" height="18" rx="2" /><path d="M8 8h8M8 12h8M8 16h5" /><path d="m16.5 15.5 1.5 1.5-3 3-1.5.2.2-1.5z" /></svg>;
  if (name === "resource") return <svg {...common}><path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H20v15H6.5A2.5 2.5 0 0 0 4 20.5z" /><path d="M4 5.5v15M8 7h8M8 11h8M8 15h5" /></svg>;
  if (name === "memory") return <svg {...common}><path d="M12 3.5 14 5l2.5-.1.9 2.3 2.1 1.3-.8 2.4.8 2.4-2.1 1.3-.9 2.3L14 17l-2 1.5L10 17l-2.5.1-.9-2.3-2.1-1.3.8-2.4-.8-2.4 2.1-1.3.9-2.3L10 5z" /><path d="m8.5 11.5 2.2 2.2 4.8-5" /></svg>;
  if (name === "settings") return <svg {...common}><path d="M12 8.5A3.5 3.5 0 1 0 12 15.5 3.5 3.5 0 0 0 12 8.5Z" /><path d="m19 13 .1-2 1.7-1.4-1.8-3-2.1.6-1.6-1.2L15 3.9h-3.5l-.4 2.1-1.7 1.2-2.1-.6-1.8 3L7.2 11l.1 2-1.7 1.4 1.8 3 2.1-.6 1.6 1.2.4 2.1H15l.4-2.1 1.7-1.2 2.1.6 1.8-3z" /></svg>;
  return <svg {...common}><path d="M4 5h16v12H7l-3 3z" /><path d="M8 9h8M8 13h5" /></svg>;
}

function GlobalConversationHistory() {
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
    <div className="app-history-heading"><h2 id="app-history-title">{showArchived ? "已归档对话" : "最近对话"}</h2><button type="button" className="app-history-toggle" onClick={() => setShowArchived((value) => !value)}>{showArchived ? "返回最近" : "查看归档"}</button><span>{displayedSessions.length > 0 ? displayedSessions.length : ""}</span></div>
    <label className="app-history-search"><span className="sr-only">搜索对话</span><input type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索历史" aria-label="搜索历史对话" /></label>
    <div className="app-history-list">
      {loading && sessions.length === 0 || archiveLoading ? <p role="status">正在读取…</p> : null}
      {!loading && !archiveLoading && filtered.length === 0 ? <p className="app-history-empty">{query.trim() ? "没有搜索结果。" : showArchived ? "暂无归档对话。" : "尚无对话，先问一个问题吧。"}</p> : <ul>{filtered.map((session) => {
        const title = session.title ?? session.chapter_title ?? "新对话";
        return <li key={session.id}>
          <button type="button" className={detail?.id === session.id ? "is-active" : ""} disabled={selecting} onClick={() => { void controller.select(session.id); navigateTo(`/conversations?session=${session.id}`); }} title={title}>
            <span className="app-history-icon" aria-hidden="true"><Icon name="chat" /></span><span className="app-history-copy"><span className="app-history-title">{title}</span><span className="app-history-meta">{session.message_count} 条消息</span></span>
          </button>
          <div className="app-history-actions"><button type="button" disabled={busyAction !== null} aria-label={`重命名 ${title}`} onClick={() => runAction(`rename:${session.id}`, async () => { const next = window.prompt("给这段对话取个名字", title); if (next?.trim()) await controller.rename(session.id, next.trim()); })}>改名</button>{showArchived ? <button type="button" disabled={busyAction !== null} aria-label={`取消归档 ${title}`} onClick={() => runAction(`unarchive:${session.id}`, async () => { await updateSession(session.id, { archived: false }); await controller.reconnect(); })}>取消归档</button> : <button type="button" disabled={busyAction !== null} aria-label={`归档 ${title}`} onClick={() => runAction(`archive:${session.id}`, () => controller.archive(session.id))}>归档</button>}</div>
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
    window.addEventListener("identity:signed-out", reset);
    window.addEventListener("identity:unauthorized", reset);
    return () => { window.removeEventListener("identity:signed-out", reset); window.removeEventListener("identity:unauthorized", reset); };
  }, []);
  if (error && !me) return <main className="auth-shell"><section className="auth-card" role="alert"><h1>暂时无法打开学习平台</h1><p>{error}</p><button onClick={() => setAttempt((v) => v + 1)}>重新加载</button></section></main>;
  if (!me) return <main className="auth-shell" role="status">正在读取学习档案…</main>;
  return <AccountLayout key={me.user.id} me={me}>{error ? <p role="alert">{error} <button className="secondary" onClick={() => setAttempt((v) => v + 1)}>重新读取账号</button></p> : null}{children}</AccountLayout>;
}

function AccountLayout({ me, children }: { me: MeResponse; children: ReactNode }) {
  return <ConversationProvider key={me.user.id}><EditingGuardProvider><AccountFrame me={me}>{children}</AccountFrame></EditingGuardProvider></ConversationProvider>;
}

function AccountFrame({ me, children }: { me: MeResponse; children: ReactNode }) {
  const { pathname } = useLocation();
  const navigateTo = useNavigate();
  const { controller } = useConversation();
  const [logoutError, setLogoutError] = useState("");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const admin = me.user.role === "admin";
  const adminPage = pathname.startsWith("/admin");
  const stage = me.profile?.stage;
  const items = adminPage ? ADMIN_NAV : STUDENT_NAV;
  const activeTitle = adminPage ? "教学管理" : items.find((item) => pathname === item.path || pathname.startsWith(`${item.path}/`))?.label ?? (pathname.startsWith("/workbench") ? "学习工作台" : "学习平台");
  const conversationPage = pathname.startsWith("/conversations");
  const signOut = () => { void logout().then(() => navigate("/login")).catch(() => setLogoutError("退出失败，请重试")); };
  const closeMobile = () => setMobileNavOpen(false);
  const startConversation = () => { void controller.start().then((id) => { if (id) navigateTo(`/conversations?session=${id}`); }); };

  return <div className="app-shell" data-stage={stage ?? ""} data-admin={adminPage}>
    <a href="#page-content" className="skip-link">跳到主要内容</a>
    <button type="button" className="app-mobile-toggle" aria-label={mobileNavOpen ? "关闭导航" : "打开导航"} aria-expanded={mobileNavOpen} onClick={() => setMobileNavOpen((value) => !value)}><span aria-hidden="true">☰</span></button>
    {mobileNavOpen ? <button type="button" className="app-sidebar-backdrop" aria-label="关闭导航" onClick={closeMobile} /> : null}
    <aside className={`app-sidebar${mobileNavOpen ? " is-open" : ""}`} aria-label="平台导航">
      <a className="app-brand" href={admin ? "/admin/resources" : "/conversations"} onClick={closeMobile}><span className="app-brand-mark" aria-hidden="true">书</span><span className="app-brand-copy"><strong>K12学习平台</strong><small>AI陪伴 · 快乐学习</small></span></a>
      {!adminPage ? <button type="button" className="app-new-conversation" onClick={() => { closeMobile(); startConversation(); }}><span aria-hidden="true">＋</span> 新对话</button> : null}
      <nav className="app-sidebar-nav" aria-label={adminPage ? "管理导航" : "学生导航"}>
        {items.map((item) => <NavLink key={item.path} to={item.path} end={item.end} onClick={closeMobile}><Icon name={item.icon} /><span>{item.label}</span></NavLink>)}
        {admin && !adminPage ? <NavLink to="/admin/resources" onClick={closeMobile}><Icon name="settings" /><span>管理入口</span></NavLink> : null}
      </nav>
      {!adminPage ? <GlobalConversationHistory /> : null}
      <div className="app-sidebar-user"><span className="app-avatar" aria-hidden="true">{me.user.username.slice(0, 1).toUpperCase()}</span><span className="app-user-copy"><strong title={me.user.username}>{me.user.username}</strong><small>{admin ? "管理员" : stageLabel(stage)}</small></span><button type="button" className="app-logout" onClick={signOut}>退出</button></div>
      {logoutError ? <p className="app-logout-error" role="alert">{logoutError}</p> : null}
    </aside>
    <div className={`app-main${conversationPage ? " app-main--conversation" : ""}`}>
      <header className={`app-topbar${conversationPage ? " app-topbar--conversation" : ""}`}><div><p className="app-breadcrumb">{adminPage ? "管理端" : "我的学习"}</p><h1>{activeTitle}</h1></div><div className="app-topbar-account"><span className="app-topbar-dot" aria-hidden="true" />{me.user.username}</div></header>
      <div id="page-content" className={`app-content${conversationPage ? " app-content--conversation" : ""}`} tabIndex={-1}>{adminPage && !admin ? <main><h1>仅管理员可访问</h1><a href="/conversations">返回学习平台</a></main> : children}</div>
    </div>
    {!admin && stage && pathname !== "/onboarding" && !adminPage ? <Companion userId={me.user.id} /> : null}
  </div>;
}
