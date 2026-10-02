import { useEffect } from "react";
import { useLocation } from "react-router-dom";
import { useAccount } from "../../features/identity/AccountContext";
import type { Stage } from "../../features/identity/types";
import { createLazyPage, scheduleIdlePreloads } from "./lazyPage";

const preparedStages = new Set<Stage>();
function IdleStagePreload() {
  const account = useAccount();
  const { pathname } = useLocation();
  const stage = account?.profile?.stage;
  const student = account?.user.role === "student";
  useEffect(() => {
    if (!student || !stage || preparedStages.has(stage)) return;
    const connection = (navigator as Navigator & { connection?: { saveData?: boolean; effectiveType?: string } }).connection;
    if (connection?.saveData || ["slow-2g", "2g"].includes(connection?.effectiveType ?? "")) return;
    const common = stage === "PRIMARY_LOWER" ? [resourceLibrary, interactiveCatalog]
      : stage === "PRIMARY_UPPER" ? [resourceLibrary, interactiveCatalog, practice]
      : [resourceLibrary, practice];
    const cancel = scheduleIdlePreloads([
      ...common.map((page) => page.preload),
      async () => { preparedStages.add(stage); },
    ]);
    return cancel;
  }, [student, stage, pathname]);
  return null;
}

const home = createLazyPage(() => import("../../pages/Home").then(m => ({ default: m.Home })), "服务状态");
const login = createLazyPage(() => import("../../pages/login/LoginPage").then(m => ({ default: m.LoginPage })), "登录");
const onboarding = createLazyPage(() => import("../../pages/onboarding/OnboardingPage").then(m => ({ default: m.OnboardingPage })), "学习档案");
const settings = createLazyPage(() => import("../../pages/settings/SettingsPage").then(m => ({ default: m.SettingsPage })), "学习设置", IdleStagePreload);
const workbench = createLazyPage(() => import("../../pages/workbench/WorkbenchPage").then(m => ({ default: m.WorkbenchPage })), "学习首页", IdleStagePreload);
const courses = createLazyPage(() => import("../../pages/courses/CourseListPage").then(m => ({ default: m.CourseListPage })), "课程目录", IdleStagePreload);
const courseDetail = createLazyPage(() => import("../../pages/courses/CourseDetailPage").then(m => ({ default: m.CourseDetailPage })), "课程", IdleStagePreload);
const chapter = createLazyPage(() => import("../../pages/reader/ChapterReaderPage").then(m => ({ default: m.ChapterReaderPage })), "章节", IdleStagePreload);
const conversation = createLazyPage(() => import("../../features/conversation/ConversationPage").then(m => ({ default: m.ConversationRoutePage })), "AI 教师", IdleStagePreload);
const lesson = createLazyPage(() => import("../../features/lesson/LessonPage").then(m => ({ default: m.LessonPage })), "章节课堂", IdleStagePreload);
const practice = createLazyPage(() => import("../../pages/practice/StagePracticePage").then(m => ({ default: m.StagePracticePage })), "练习", IdleStagePreload);
const growth = createLazyPage(() => import("../../features/growth/GrowthPage").then(m => ({ default: m.GrowthPage })), "个人记忆", IdleStagePreload);
const next = createLazyPage(() => import("../../features/learning-next/NextStepPage").then(m => ({ default: m.NextStepPage })), "下一步", IdleStagePreload);
const resourceDetail = createLazyPage(() => import("../../features/resources/ResourceDetailPage").then(m => ({ default: m.ResourceDetailPage })), "学习资料", IdleStagePreload);
const animation = createLazyPage(() => import("../../features/animation/AnimationPage").then(m => ({ default: m.AnimationPage })), "动画", IdleStagePreload);
const adminResources = createLazyPage(() => import("../../pages/admin/AdminResourcesPage").then(m => ({ default: m.AdminResourcesPage })), "资源管理");
const adminAI = createLazyPage(() => import("../../pages/admin/AdminAIPage").then(m => ({ default: m.AdminAIPage })), "AI 教师设置");
const adminAuthoring = createLazyPage(() => import("../../pages/admin/AdminAuthoringPage").then(m => ({ default: m.AdminAuthoringPage })), "教学包历史");
const study = createLazyPage(() => import("../../features/study/StudyPage").then(m => ({ default: m.StudyPage })), "书架", IdleStagePreload);
const picturebook = createLazyPage(() => import("../../features/picturebooks/PicturebookPage").then(m => ({ default: m.PicturebookPage })), "绘本", IdleStagePreload);
const resourceLibrary = createLazyPage(() => import("../../features/resources/ResourceLibraryPage").then(m => ({ default: m.ResourceLibraryPage })), "资料库", IdleStagePreload);
const interactiveCatalog = createLazyPage(() => import("../../features/interactive/InteractiveCatalogPage").then(m => ({ default: m.InteractiveCatalogPage })), "互动目录", IdleStagePreload);
const interactivePlayer = createLazyPage(() => import("../../features/interactive/InteractivePlayerPage").then(m => ({ default: m.InteractivePlayerPage })), "互动内容", IdleStagePreload);
const adminInteractive = createLazyPage(() => import("../../pages/admin/AdminInteractivePage").then(m => ({ default: m.AdminInteractivePage })), "互动管理");
const more = createLazyPage(() => import("../../pages/more/MorePage").then(m => ({ default: m.MorePage })), "更多入口", IdleStagePreload);
const code = createLazyPage(() => import("../../pages/code/CodeLabPage").then(m => ({ default: m.CodeLabPage })), "CodeLab", IdleStagePreload);
const book = createLazyPage(() => import("../../features/books/BookReaderPage").then(m => ({ default: m.BookReaderPage })), "教材", IdleStagePreload);

export const pages = {
  Home: home.Page, LoginPage: login.Page, OnboardingPage: onboarding.Page, SettingsPage: settings.Page,
  WorkbenchPage: workbench.Page, CourseListPage: courses.Page, CourseDetailPage: courseDetail.Page,
  ChapterReaderPage: chapter.Page, ConversationRoutePage: conversation.Page, LessonPage: lesson.Page,
  StagePracticePage: practice.Page, GrowthPage: growth.Page, NextStepPage: next.Page,
  ResourceDetailPage: resourceDetail.Page, AnimationPage: animation.Page,
  AdminResourcesPage: adminResources.Page, AdminAIPage: adminAI.Page, AdminAuthoringPage: adminAuthoring.Page,
  StudyPage: study.Page, PicturebookPage: picturebook.Page, ResourceLibraryPage: resourceLibrary.Page,
  InteractiveCatalogPage: interactiveCatalog.Page, InteractivePlayerPage: interactivePlayer.Page,
  AdminInteractivePage: adminInteractive.Page, MorePage: more.Page, CodeLabPage: code.Page, BookReaderPage: book.Page,
};
