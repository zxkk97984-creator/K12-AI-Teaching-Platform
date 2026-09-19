import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { Home } from "./pages/Home";
import { LoginPage } from "./pages/login/LoginPage";
import { OnboardingPage } from "./pages/onboarding/OnboardingPage";
import { SettingsPage } from "./pages/settings/SettingsPage";
import { WorkbenchPage } from "./pages/workbench/WorkbenchPage";
import { CourseListPage } from "./pages/courses/CourseListPage";
import { CourseDetailPage } from "./pages/courses/CourseDetailPage";
import { ChapterReaderPage } from "./pages/reader/ChapterReaderPage";
import { ConversationPage } from "./features/conversation/ConversationPage";
import { LessonPage } from "./features/lesson/LessonPage";
import { PracticePage } from "./pages/practice/PracticePage";
import { GrowthPage } from "./features/growth/GrowthPage";
import { NextStepPage } from "./features/learning-next/NextStepPage";
import { ResourceLibraryPage } from "./features/resources/ResourceLibraryPage";
import { AnimationPage } from "./features/animation/AnimationPage";
import { AdminResourcesPage } from "./pages/admin/AdminResourcesPage";
import { AdminAuthoringPage } from "./pages/admin/AdminAuthoringPage";
import "./styles.css";
import { navigate } from "./features/identity/session";

const CodeLabPage = lazy(() =>
  import("./pages/code/CodeLabPage").then((module) => ({ default: module.CodeLabPage })),
);

function route() {
  const path = window.location.pathname;
  if (path.startsWith("/login")) return <LoginPage />;
  if (path.startsWith("/onboarding")) return <OnboardingPage />;
  if (path.startsWith("/settings")) return <SettingsPage />;
  if (path.startsWith("/workbench")) return <WorkbenchPage />;
  if (path.startsWith("/lessons")) return <LessonPage />;
  if (path.startsWith("/practice")) return <PracticePage />;
  if (path.startsWith("/growth")) return <GrowthPage />;
  if (path.startsWith("/learn")) return <NextStepPage />;
  if (path.startsWith("/admin/authoring")) return <AdminAuthoringPage />;
  if (path.startsWith("/admin/resources")) return <AdminResourcesPage />;
  if (path.startsWith("/code")) {
    return (
      <Suspense fallback={<main>正在加载 CodeLab…</main>}>
        <CodeLabPage />
      </Suspense>
    );
  }
  if (path.startsWith("/animations")) return <AnimationPage />;
  if (path.startsWith("/resources")) return <ResourceLibraryPage />;
  if (path.startsWith("/conversations")) return <ConversationPage />;
  if (path.startsWith("/chapters/")) return <ChapterReaderPage />;
  if (path.startsWith("/courses/")) return <CourseDetailPage />;
  if (path.startsWith("/courses")) return <CourseListPage />;
  return <Home />;
}

window.addEventListener("identity:unauthorized", () => {
  if (!window.location.pathname.startsWith("/login")) navigate("/login");
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>{route()}</StrictMode>,
);
