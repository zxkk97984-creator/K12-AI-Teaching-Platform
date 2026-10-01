import { useEffect, useState } from "react";
import { listInteractive, type InteractiveItem } from "./api";

export function InteractiveLearningLinks({ revisionIds }: { revisionIds: string[] }) {
  const key = revisionIds.join(",");
  const [items, setItems] = useState<InteractiveItem[]>([]);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setItems([]); setFailed(false);
    const wanted = new Set(key.split(","));
    void listInteractive(undefined, undefined, controller.signal).then((catalog) => {
      if (!controller.signal.aborted) setItems(catalog.items.filter((item) => item.chapter_revision_ids?.some((id) => wanted.has(id))));
    }).catch(() => { if (!controller.signal.aborted) setFailed(true); });
    return () => controller.abort();
  }, [key, attempt]);
  if (failed) return <p className="content-note">配套互动讲解暂时无法读取。<button type="button" onClick={() => setAttempt((value) => value + 1)}>重试</button></p>;
  if (!items.length) return null;
  return <section className="chapter-interactive-links" aria-label="配套互动讲解"><h2>看一看，动一动</h2>{items.map((item) => <a className="content-link" key={item.id} href={`/interactive/${item.id}`}>{item.title} · {item.can_resume ? "继续互动讲解" : "打开互动讲解"} →</a>)}<p className="content-note">动态图形、动手操作与霜铃预设台词朗读。</p></section>;
}
