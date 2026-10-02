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
import { ConversationRoutePage } from "./features/conversation/ConversationPage";
import { LessonPage } from "./features/lesson/LessonPage";
import { StagePracticePage } from "./pages/practice/StagePracticePage";
import { GrowthPage } from "./features/growth/GrowthPage";
import { NextStepPage } from "./features/learning-next/NextStepPage";
import { ResourceDetailPage } from "./features/resources/ResourceDetailPage";
import { AnimationPage } from "./features/animation/AnimationPage";
import { AdminResourcesPage } from "./pages/admin/AdminResourcesPage";
const AdminAIPage = lazy(() => import("./pages/admin/AdminAIPage").then((module) => ({ default: module.AdminAIPage })));
import { AdminAuthoringPage } from "./pages/admin/AdminAuthoringPage";
import { StudyPage } from "./features/study/StudyPage";
import { PicturebookPage } from "./features/picturebooks/PicturebookPage";
import { ResourceLibraryPage } from "./features/resources/ResourceLibraryPage";
import { InteractiveCatalogPage } from "./features/interactive/InteractiveCatalogPage";
import { InteractivePlayerPage } from "./features/interactive/InteractivePlayerPage";
import { AdminInteractivePage } from "./pages/admin/AdminInteractivePage";
import { MorePage } from "./pages/more/MorePage";
import "./styles.css";
import { createBrowserRouter, Navigate, RouterProvider, useLocation } from "react-router-dom";
import { AppLayout } from "./app/layout/AppLayout";
import { NavigationBridge } from "./app/layout/NavigationBridge";
import "./app/layout/design-system.css";
import "./app/layout/k12-redesign.css";
import "./app/layout/student-pages.css";
import { navigate } from "./features/identity/session";

const CodeLabPage = lazy(() =>
  import("./pages/code/CodeLabPage").then((module) => ({
    default: module.CodeLabPage,
  })),
);
const BookReaderPage = lazy(() =>
  import("./features/books/BookReaderPage").then((module) => ({
    default: module.BookReaderPage,
  })),
);

function Page() {
  const { pathname: path, search } = useLocation();
  if (path.startsWith("/login")) return <LoginPage />;
  if (path.startsWith("/onboarding")) return <OnboardingPage />;
  if (path.startsWith("/settings")) return <SettingsPage />;
  if (path.startsWith("/workbench")) return <WorkbenchPage />;
  if (path.startsWith("/study/lesson")) return <LessonPage />;
  if (path === "/study") return <StudyPage />;
  if (path.startsWith("/lessons")) return <LessonPage />;
  if (path.startsWith("/practice")) return <StagePracticePage />;
  if (path.startsWith("/growth")) return <GrowthPage />;
  if (path === "/learn") return <Navigate to="/study" replace />;
  if (path.startsWith("/learn/")) return <NextStepPage />;
  if (path.startsWith("/admin/ai")) return <AdminAIPage />;
  if (path.startsWith("/admin/authoring")) return <AdminAuthoringPage />;
  if (path.startsWith("/admin/resources/interactive")) return <AdminInteractivePage />;
  if (path.startsWith("/admin/resources")) return <AdminResourcesPage />;
  if (path.startsWith("/code")) {
    return (
      <Suspense fallback={<main>正在加载 CodeLab…</main>}>
        <CodeLabPage />
      </Suspense>
    );
  }
  if (path.startsWith("/interactive/")) return <InteractivePlayerPage />;
  if (path.startsWith("/activities")) return <InteractiveCatalogPage />;
  if (path.startsWith("/animations/")) return <AnimationPage />;
  if (path === "/animations") return new URLSearchParams(search).has("legacy") ? <AnimationPage /> : <InteractiveCatalogPage purposeOverride="LESSON" />;
  if (path.startsWith("/more")) return <MorePage />;
  if (path === "/resources") {
    const type = new URLSearchParams(search).get("type");
    return type === "course" ? <StudyPage resourcesOnly catalogKind="COURSE" /> : <ResourceLibraryPage />;
  }
  if (path.startsWith("/resources/")) return <ResourceDetailPage />;
  if (path.startsWith("/conversations")) return <ConversationRoutePage />;
  if (path.startsWith("/chapters/")) return <ChapterReaderPage />;
  if (path.startsWith("/books/")) {
    return (
      <Suspense fallback={<main className="book-reader-loading" role="status">正在打开教材…</main>}>
        <BookReaderPage />
      </Suspense>
    );
  }
  if (path.startsWith("/picturebooks/") || path === "/picturebooks") return <PicturebookPage />;
  if (path === "/courses") return <CourseListPage />;
  if (path.startsWith("/courses/")) return <CourseDetailPage />;
  if (path.startsWith("/courses")) return <CourseListPage />;
  if (path === "/" || path === "/home")
    return <Navigate to="/workbench" replace />;
  if (path === "/admin") return <Navigate to="/admin/resources" replace />;
  if (path === "/status") return <Home />;
  return (
    <main className="not-found">
      <h1>页面不存在</h1>
      <a href="/workbench">返回学习首页</a>
    </main>
  );
}

window.addEventListener("identity:unauthorized", () => {
  if (!window.location.pathname.startsWith("/login")) navigate("/login");
});

function App() {
  const location = useLocation();
  // Keep page component identity stable when only a query parameter changes.
  // Conversation, reader and practice pages own their URL state and should
  // reconcile it without destroying their in-flight requests.
  const page = <Page />;
  return (
    <>
      <NavigationBridge />
      {location.pathname === "/login" || location.pathname === "/status" ? (
        page
      ) : (
        <AppLayout>{page}</AppLayout>
      )}
    </>
  );
}

// The data router is created once outside the React tree so query changes do
// not recreate the application shell or cancel in-flight business requests.
// Keep one stable shell while giving the data router explicit addressable
// entries.  Page remains the compatibility dispatcher for legacy paths and
// query-driven variants; unknown paths still reach its honest 404 state.
const ROUTE_PATHS = [
  "/", "/home", "/login", "/onboarding", "/conversations", "/study", "/study/lesson",
  "/resources", "/resources/:resourceId", "/courses", "/courses/:courseId", "/chapters/:chapterId",
  "/books/:bookSlug", "/picturebooks", "/picturebooks/:storyId",
  "/practice", "/practice/sessions/:quizId", "/code", "/growth", "/settings", "/workbench",
  "/learn", "/learn/:path", "/animations", "/animations/:animationId", "/activities", "/interactive/:resourceId", "/more", "/lessons",
  "/admin", "/admin/ai", "/admin/resources", "/admin/resources/interactive", "/admin/authoring", "/status",
];
const router = createBrowserRouter([
  ...ROUTE_PATHS.map((path) => ({ path, element: <App /> })),
  { path: "*", element: <App /> },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
