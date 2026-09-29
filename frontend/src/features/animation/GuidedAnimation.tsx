import { useEffect, useState } from "react";
import type { Stage } from "../identity/types";
import { getStudentContent, type GuidedStudentAnimation } from "../study/api";
import { openCompanion } from "../companion/openCompanion";

function GuidedVisual({ kind, step }: { kind: "shape" | "fraction" | "chain" | "function"; step: number }) {
  if (kind === "shape") return <svg viewBox="0 0 320 180" role="img" aria-label={`三角形，当前展示第 ${step + 1} 步`}><path d="M160 24 47 150 273 150Z" fill="#fff6dc" stroke="#a7a39a" strokeWidth="3" /><path d={step === 0 ? "" : step === 1 ? "M160 24 47 150" : step === 2 ? "M160 24 47 150 273 150" : "M160 24 47 150 273 150 160 24"} fill="none" stroke="#9b6c12" strokeWidth="8" strokeLinecap="round" strokeLinejoin="round" /></svg>;
  if (kind === "fraction") return <div className="guided-fractions" role="img" aria-label={`四等份分数条，突出显示 ${step === 0 ? 0 : step} 份`}>{[0, 1, 2, 3].map((part) => <span key={part} className={part < step ? "is-active" : ""}>¼</span>)}</div>;
  if (kind === "chain") return <div className="guided-chain" role="img" aria-label={`食物链，到第 ${step + 1} 个环节`}>{["草", "蝗虫", "青蛙", "蛇"].map((item, index) => <span key={item} className={index <= step ? "is-active" : ""}>{index > 0 ? <b aria-hidden="true">→</b> : null}{item}</span>)}</div>;
  return <svg viewBox="0 0 320 180" role="img" aria-label={`一次函数 y 等于 2x 加 1，已显示 ${step} 个坐标点`}><path d="M28 145H295M55 158V18" stroke="#a7a39a" strokeWidth="2" /><path d="M55 130 255 30" stroke="#9b6c12" strokeWidth="4" />{[[55,130],[105,105],[155,80],[205,55]].slice(0,step+1).map(([x,y],index)=><circle key={index} cx={x} cy={y} r="6" fill="#9b6c12" />)}</svg>;
}

export function GuidedAnimation({ stage }: { stage: Stage }) {
  const [item, setItem] = useState<GuidedStudentAnimation | null>(null);
  const [error, setError] = useState("");
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  useEffect(() => {
    let active = true;
    setItem(null); setStep(0); setPlaying(false); setError("");
    void getStudentContent().then((body) => {
      if (active && body.stage === stage) setItem(body.guided_animation);
    }).catch((caught) => { if (active) setError(caught instanceof Error ? caught.message : "示例动画暂时无法读取"); });
    return () => { active = false; };
  }, [stage]);
  useEffect(() => {
    if (!playing || !item) return;
    const timer = window.setInterval(() => setStep((value) => {
      if (value >= item.steps.length - 1) { setPlaying(false); return value; }
      return value + 1;
    }), 1800);
    return () => window.clearInterval(timer);
  }, [playing, item]);
  if (error) return <p role="alert">{error}</p>;
  if (!item) return <p role="status">正在读取示例讲解…</p>;
  const ask = () => openCompanion({
    page_type: "animation", activity_type: "watching",
    content_kind: "GUIDED_ANIMATION", content_id: item.id, content_version: item.version,
    section_index: step, visible_section: `${item.title} · 第 ${step + 1} 步`,
    selected_text: item.steps[step], knowledge_points: [item.topic],
    suggestedQuestion: `请结合「${item.title}」第 ${step + 1} 步帮我理解：${item.steps[step]}`,
  });
  return <section className="guided-animation" aria-label="当前学段示例动画">
    <div className="guided-animation-heading"><div><span>{item.subject} · {item.topic} · 示例讲解</span><h2>{item.title}</h2></div><button type="button" className="secondary" onClick={ask}>问问老师</button></div>
    <div className="guided-animation-body"><div className="guided-animation-visual"><GuidedVisual kind={item.id as "shape" | "fraction" | "chain" | "function"} step={step} /></div><div className="guided-animation-copy"><span>第 {step + 1} / {item.steps.length} 步</span><p role="status">{item.steps[step]}</p><div className="guided-animation-controls"><button type="button" onClick={() => setPlaying((value) => !value)} disabled={step === item.steps.length - 1}>{playing ? "暂停" : "播放"}</button><button type="button" className="secondary" onClick={() => { setPlaying(false); setStep((value) => Math.max(0,value-1)); }} disabled={step === 0}>上一步</button><button type="button" className="secondary" onClick={() => { setPlaying(false); setStep((value) => Math.min(item.steps.length-1,value+1)); }} disabled={step === item.steps.length-1}>下一步</button><button type="button" className="secondary" onClick={() => { setPlaying(false); setStep(0); }}>重置</button></div></div></div>
    <details><summary>查看完整文字讲解</summary><ol>{item.steps.map((text,index)=><li key={index}>{text}</li>)}</ol></details>
    <p className="animation-notice">本段为版本化示例讲解，未请求 AI 生成；下方已发布动画由服务端提供定义并校验参数。</p>
  </section>;
}
