import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { pages } from "./app/routing/pages";
const {
  Home, LoginPage, OnboardingPage, SettingsPage, WorkbenchPage, CourseListPage, CourseDetailPage,
  ChapterReaderPage, ConversationRoutePage, LessonPage, StagePracticePage, HistoryPage, GrowthPage, NextStepPage,
  ResourceDetailPage, AnimationPage, AdminResourcesPage, AdminAIPage, AdminAuthoringPage, StudyPage,
  PicturebookPage, ResourceLibraryPage, InteractiveCatalogPage, InteractivePlayerPage, AdminInteractivePage,
  MorePage, CodeLabPage, BookReaderPage,
} = pages;
import "./styles.css";
import { createBrowserRouter, Navigate, RouterProvider, useLocation } from "react-router-dom";
import { AppLayout } from "./app/layout/AppLayout";
import { NavigationBridge } from "./app/layout/NavigationBridge";
import "./app/layout/design-system.css";
import "./app/layout/k12-redesign.css";
import "./app/layout/student-pages.css";
import { navigate } from "./features/identity/session";

function Page() {
  const { pathname: path, search } = useLocation();
  if (path.startsWith("/login")) return <LoginPage />;
  if (path.startsWith("/onboarding")) return <OnboardingPage />;
  if (path.startsWith("/settings")) return <SettingsPage />;
  if (path.startsWith("/workbench")) return <WorkbenchPage />;
  if (path.startsWith("/study/lesson")) return <LessonPage />;
  if (path === "/study") return <StudyPage />;
  if (path.startsWith("/lessons")) return <LessonPage />;
  if (path === "/history") return <HistoryPage />;
  if (path.startsWith("/practice")) return <StagePracticePage />;
  if (path.startsWith("/growth")) return <GrowthPage />;
  if (path === "/learn") return <Navigate to="/study" replace />;
  if (path.startsWith("/learn/")) return <NextStepPage />;
  if (path.startsWith("/admin/ai")) return <AdminAIPage />;
  if (path.startsWith("/admin/authoring")) return <AdminAuthoringPage />;
  if (path.startsWith("/admin/resources/interactive")) return <AdminInteractivePage />;
  if (path.startsWith("/admin/resources")) return <AdminResourcesPage />;
  if (path.startsWith("/code")) return <CodeLabPage />;
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
  if (path.startsWith("/books/")) return <BookReaderPage />;
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
  "/practice", "/practice/sessions/:quizId", "/history", "/code", "/growth", "/settings", "/workbench",
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
