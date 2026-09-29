import { Link } from "react-router-dom";
import { useAccount } from "../../features/identity/AccountContext";
import "./more.css";

export function MorePage() {
  const stage = useAccount()?.profile?.stage;
  const primary = stage?.startsWith("PRIMARY");
  return <main className="more-page"><span className="interactive-kicker">更多学习入口</span><h1>接下来想做什么？</h1><div className="more-links"><Link to={primary ? "/animations" : "/activities"}><strong>{primary ? "动画讲解" : stage === "JUNIOR" ? "互动探索" : "互动实验"}</strong><span>打开当前学段的互动内容</span></Link>{!primary && <Link to="/code"><strong>{stage === "JUNIOR" ? "编程入门" : "编程实践"}</strong><span>打开真实 CodeLab 任务</span></Link>}<Link to="/growth"><strong>个人记忆</strong><span>查看和编辑自己的 Markdown 文档</span></Link><Link to="/settings"><strong>学习设置</strong><span>调整学段、教师风格和桌宠</span></Link></div></main>;
}
