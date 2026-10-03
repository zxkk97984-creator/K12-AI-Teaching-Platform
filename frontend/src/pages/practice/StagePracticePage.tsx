import { Navigate, useLocation } from "react-router-dom";
import { PracticeRoutePage } from "./PracticePage";
import { LegacyLearningEntry } from "../../features/lesson/LegacyLearningEntry";
import { PracticeHub } from "./PracticeHub";
import { historyLocation } from "./navigation";
import "./stage-practice.css";

export function StagePracticePage() {
  const { pathname, search } = useLocation();
  const query = new URLSearchParams(search);
  if (!pathname.startsWith("/practice/sessions/") && (query.get("view") === "history" || query.get("tab") === "history")) return <Navigate to={historyLocation(query)} replace />;
  if (pathname.startsWith("/practice/sessions/") || query.has("job")) return <PracticeRoutePage />;
  if (query.has("chapter")) return <LegacyLearningEntry />;
  if (query.get("tab") === "wrong") return <Navigate to={historyLocation(query)} replace />;
  if (query.get("type") === "questions" || ["teacher", "active"].includes(query.get("tab") ?? "")) {
    query.set("type", "questions");
    if (query.get("tab") === "active") query.set("status", "active");
    return <Navigate to={historyLocation(query)} replace />;
  }
  return <PracticeHub />;
}
