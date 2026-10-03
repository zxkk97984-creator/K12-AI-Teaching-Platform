import { PageHeading } from "../../app/layout/pageChrome";
import { Link } from "react-router-dom";
import { useAccount } from "../../features/identity/AccountContext";
import "./more.css";

export function MorePage() {
  const stage = useAccount()?.profile?.stage;
  const primary = stage?.startsWith("PRIMARY");
  return <main className="more-page"><PageHeading title="更多入口" /><div className="more-links"><Link to="/history"><strong>历史记录</strong><span>继续题目练习，查看作答结果</span></Link><Link to={primary ? "/animations" : "/activities"}><strong>{primary ? "动画讲解" : "动画与实验"}</strong><span>{primary ? "观看动画讲解" : "查看动画讲解和互动实验"}</span></Link>{!primary && <Link to="/code"><strong>{stage === "JUNIOR" ? "编程入门" : "编程实践"}</strong><span>打开真实 CodeLab 任务</span></Link>}<Link to="/growth"><strong>个人记忆</strong><span>查看和编辑自己的 Markdown 文档</span></Link><Link to="/settings"><strong>学习设置</strong><span>调整学段、教师风格和桌宠</span></Link></div></main>;
}
