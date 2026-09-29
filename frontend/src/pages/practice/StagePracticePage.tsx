import { useLocation } from "react-router-dom";
import { useAccount } from "../../features/identity/AccountContext";
import { InteractiveCatalogPage } from "../../features/interactive/InteractiveCatalogPage";
import { PracticeRoutePage } from "./PracticePage";
import { WrongQuestionsPage } from "./WrongQuestionsPage";
import "./stage-practice.css";

export function StagePracticePage() {
  const stage = useAccount()?.profile?.stage;
  const { pathname, search } = useLocation();
  const tab = new URLSearchParams(search).get("tab");
  if (pathname.startsWith("/practice/sessions/")) return <PracticeRoutePage />;
  if (stage?.startsWith("PRIMARY")) {
    return <main className="stage-practice"><nav className="interactive-tabs" aria-label="练习类型"><a href="/practice" aria-current={tab !== "teacher" ? "page" : undefined}>互动小游戏</a><a href="/practice?tab=teacher" aria-current={tab === "teacher" ? "page" : undefined}>老师给我的练习</a></nav>{tab === "teacher" ? <PracticeRoutePage /> : <InteractiveCatalogPage purposeOverride="GAME" />}</main>;
  }
  return <main className="stage-practice"><nav className="interactive-tabs" aria-label="练习类型"><a href="/practice" aria-current={tab !== "wrong" ? "page" : undefined}>{stage === "SENIOR" ? "巩固训练" : "专项练习"}</a><a href="/practice?tab=wrong" aria-current={tab === "wrong" ? "page" : undefined}>错题回顾</a></nav>{tab === "wrong" ? <WrongQuestionsPage /> : <PracticeRoutePage />}</main>;
}
