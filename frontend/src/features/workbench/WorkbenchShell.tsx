import { useState, type KeyboardEvent } from "react";
import { DisabledState } from "../../shared/ui/state";
import { logout } from "../identity/api";
import { navigate } from "../identity/session";
import { STYLES, stageLabel, type MeResponse, type Stage } from "../identity/types";
import { capability } from "./capabilities";
import { densityForStage } from "./density";
import { MAIN_NAV } from "./nav";
import "./workbench.css";

type TabId = "canvas" | "teacher" | "activity";

const TABS: Array<{ id: TabId; label: string }> = [
  { id: "canvas", label: "学习内容" },
  { id: "teacher", label: "教师" },
  { id: "activity", label: "当前活动" },
];

function stageSummary(stage: Stage | null, grade: number | null | undefined): string {
  const label = stageLabel(stage);
  return grade ? `${label} · ${grade} 年级` : `${label} · 未填年级`;
}

function MainNav() {
  return (
    <nav className="wb-mainnav" aria-label="主导航">
      <ul>
        {MAIN_NAV.map((item) =>
          item.enabled ? (
            <li key={item.id}>
              <a
                className="wb-mainnav__item"
                data-enabled="true"
                href={item.href}
                aria-current={item.id === "learn" ? "page" : undefined}
              >
                {item.label}
              </a>
            </li>
          ) : (
            <li key={item.id}>
              <span
                className="wb-mainnav__item"
                data-enabled="false"
                aria-disabled="true"
                title={`${item.label}将在 ${item.ownerTask} 接通`}
              >
                {item.label}
                <span className="wb-mainnav__tag">{item.ownerTask}</span>
              </span>
            </li>
          ),
        )}
      </ul>
    </nav>
  );
}

function ChapterNavigation({
  stage,
  grade,
  density,
}: {
  stage: Stage | null;
  grade: number | null | undefined;
  density: "spacious" | "compact";
}) {
  const catalog = capability("content-catalog");
  return (
    <div className="wb-rail__content">
      <p className="eyebrow">章节导航</p>
      <p className="wb-note">按你的学段筛选：{stageSummary(stage, grade)}</p>
      <DisabledState
        title="章节导航尚未接通"
        description={catalog.reason}
        ownerTask={catalog.ownerTask}
        density={density}
        testId="chapter-navigation"
      />
    </div>
  );
}

function TeacherPanel({
  preferences,
  density,
}: {
  preferences: MeResponse["preferences"];
  density: "spacious" | "compact";
}) {
  const teacher = capability("teacher");
  const preferredStyle = preferences
    ? (STYLES.find((item) => item.value === preferences.preferred_style)?.label ??
      preferences.preferred_style)
    : null;
  return (
    <>
      <p className="eyebrow">教师</p>
      <DisabledState
        title="教师未启用"
        description={teacher.reason}
        ownerTask={teacher.ownerTask}
        density={density}
        testId="teacher-capability"
      />
      <p className="wb-note">
        {preferredStyle
          ? `已记录偏好：${preferredStyle}。教师接通后会按此请求讲解，当前不产生任何输出。`
          : "尚未保存讲解偏好，可在设置中调整。"}
      </p>
    </>
  );
}

export function WorkbenchShell({ me }: { me: MeResponse }) {
  const stage = me.profile?.stage ?? null;
  const grade = me.profile?.grade ?? null;
  const density = densityForStage(stage);
  const [tab, setTab] = useState<TabId>("canvas");
  const [railOpen, setRailOpen] = useState(false);

  async function signOut() {
    await logout();
    navigate("/login");
  }

  function onTabKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const keyTargets: Record<string, number> = {
      ArrowRight: (index + 1) % TABS.length,
      ArrowLeft: (index - 1 + TABS.length) % TABS.length,
      Home: 0,
      End: TABS.length - 1,
    };
    const next = keyTargets[event.key];
    if (next === undefined) return;
    event.preventDefault();
    setTab(TABS[next].id);
    event.currentTarget.parentElement
      ?.querySelectorAll<HTMLButtonElement>("[role=tab]")
      ?.[next]?.focus();
  }

  return (
    <div
      className="workbench"
      data-density={density}
      data-rail={railOpen ? "open" : "closed"}
      data-testid="workbench-shell"
    >
      <header className="wb-header">
        <div className="wb-brand">
          <p className="eyebrow">霜铃 · 教学工作台</p>
          <h1 className="wb-brand__title">{me.user.username}</h1>
          <p className="wb-stage" data-testid="stage-summary">
            {stageSummary(stage, grade)}
          </p>
        </div>
        <div className="wb-header__actions">
          <MainNav />
          <div className="wb-account">
            <button type="button" className="secondary" onClick={signOut}>
              退出登录
            </button>
          </div>
        </div>
      </header>

      <div className="wb-toolbar">
        <button
          type="button"
          className="wb-rail__toggle"
          aria-expanded={railOpen}
          aria-controls="wb-rail"
          onClick={() => setRailOpen((value) => !value)}
        >
          {railOpen ? "收起章节" : "章节"}
        </button>
        <div className="wb-tabs" role="tablist" aria-label="工作台区域切换">
        {TABS.map((item, index) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            id={`wb-tab-${item.id}`}
            aria-selected={tab === item.id}
            aria-controls={`wb-panel-${item.id}`}
            tabIndex={tab === item.id ? 0 : -1}
            className="wb-tabs__tab"
            onClick={() => setTab(item.id)}
            onKeyDown={(event) => onTabKeyDown(event, index)}
          >
            {item.label}
          </button>
        ))}
        </div>
      </div>

      <div className="wb-body" data-active-tab={tab}>
        <nav
          className="wb-rail"
          id="wb-rail"
          aria-label="章节导航"
          data-open={railOpen ? "true" : "false"}
        >
          <ChapterNavigation stage={stage} grade={grade} density={density} />
        </nav>

        <div className="wb-center">
          <section
            className="wb-activity"
            id="wb-panel-activity"
            role="tabpanel"
            aria-labelledby="wb-tab-activity"
            aria-label="当前活动"
          >
            <p className="eyebrow">当前活动</p>
            <DisabledState
              title="当前活动尚未接通"
              description={capability("activity").reason}
              ownerTask={capability("activity").ownerTask}
              density={density}
              testId="activity-slot"
            />
          </section>

          <section
            className="wb-canvas"
            id="wb-panel-canvas"
            role="tabpanel"
            aria-labelledby="wb-tab-canvas"
            aria-label="学习内容"
          >
            <p className="eyebrow">本课目标</p>
            <DisabledState
              title="课程内容尚未接通"
              description={capability("content-catalog").reason}
              ownerTask={capability("content-catalog").ownerTask}
              density={density}
              testId="lesson-canvas"
            />
            {density === "spacious" ? (
              <p className="wb-note wb-note--large">
                一次只做一件事：课程接通后，这里会先给出一个很小的第一步。
              </p>
            ) : (
              <div className="wb-canvas__columns" data-testid="compact-panels">
                <div>
                  <p className="eyebrow">先备知识</p>
                  <p className="wb-note">由课程章节提供（T08）。</p>
                </div>
                <div>
                  <p className="eyebrow">学习资料</p>
                  <p className="wb-note">资料、动画与代码任务由 T20/T21/T23 接入。</p>
                </div>
              </div>
            )}
          </section>
        </div>

        <aside
          className="wb-teacher"
          id="wb-panel-teacher"
          role="tabpanel"
          aria-labelledby="wb-tab-teacher"
          aria-label="教师区"
        >
          <TeacherPanel preferences={me.preferences} density={density} />
        </aside>
      </div>
    </div>
  );
}
