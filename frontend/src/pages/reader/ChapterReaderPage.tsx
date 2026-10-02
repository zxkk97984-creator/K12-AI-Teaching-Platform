import { useEffect, useRef, useState } from "react";
import { ChapterReader } from "../../features/content/ChapterReader";
import { ContentLayout } from "../../features/content/ContentLayout";
import { useReader } from "../../features/content/useReader";
import { getCourse } from "../../features/content/api";
import type { CourseSummaryDTO } from "../../features/content/types";
import { ErrorState, LoadingState } from "../../shared/ui/state";
import { openCompanion } from "../../features/companion/openCompanion";
import { InteractiveLearningLinks } from "../../features/interactive/InteractiveLearningLinks";
import { useAccount } from "../../features/identity/AccountContext";
import { useChapterNarration } from "../../features/content/useChapterNarration";
import { chapterNarrationSegments, selectionNarrationSegments } from "../../features/content/chapterNarration";
import { ReaderNarrationPanel } from "../../features/content/ReaderNarrationPanel";
import "../../features/content/reading.css";

function chapterIdFromPath(): string {
  return window.location.pathname.split("/").filter(Boolean)[1] ?? "";
}
function revisionFromUrl(): number | undefined {
  const value = Number(new URLSearchParams(window.location.search).get("revision"));
  return Number.isInteger(value) && value >= 1 ? value : undefined;
}

export function ChapterReaderPage() {
  const chapterId = chapterIdFromPath();
  const revision = revisionFromUrl();
  const [focused, setFocused] = useState(false);
  const [fontSize, setFontSize] = useState(18);
  const [directoryOpen, setDirectoryOpen] = useState(false);
  const { state, resume, context, contextError, selectText, recordPosition } = useReader(chapterId, revision);
  const account = useAccount();
  const documentRef = useRef<HTMLDivElement>(null);
  const [narrationOpen, setNarrationOpen] = useState(false);
  const narrator = useChapterNarration(`${chapterId}:${state.kind === "ready" ? state.chapter.revision_id : ""}`, account?.user.id);
  useEffect(() => {
    if (!window.CSS?.highlights || typeof Highlight === "undefined") return;
    if (narrator.activeRange) CSS.highlights.set("reader-narration", new Highlight(narrator.activeRange));
    else CSS.highlights.delete("reader-narration");
    return () => { CSS.highlights.delete("reader-narration"); };
  }, [narrator.activeRange]);
  const [directory, setDirectory] = useState<CourseSummaryDTO | null>(null);
  const [directoryFailed, setDirectoryFailed] = useState(false);
  const [directoryAttempt, setDirectoryAttempt] = useState(0);
  const courseId = state.kind === "ready" ? state.chapter.course_id : null;
  useEffect(() => {
    if (!courseId) return;
    let active = true;
    setDirectoryFailed(false);
    void getCourse(courseId).then((course) => {
      if (active) setDirectory(course);
    }).catch(() => { if (active) setDirectoryFailed(true); });
    return () => { active = false; };
  }, [courseId, directoryAttempt]);

  if (state.kind === "loading") return <ContentLayout title="章节"><LoadingState label="正在读取章节…" /></ContentLayout>;
  if (state.kind === "error") return <ContentLayout title="章节" toolbar={<a className="content-link" href="/resources">返回资料库</a>}>
    <ErrorState title={state.status === 404 ? "章节不可用" : "暂时无法打开章节"} message={state.status === 404 ? "这个章节未发布、已撤回，或不属于你的学段。" : state.message} requestId={state.requestId} />
  </ContentLayout>;

  const chapter = state.chapter;
  const { prev, next } = chapter.navigation;
  const directoryReady = directory?.course_id === chapter.course_id;
  const chapters = directoryReady ? directory.chapters : [{ chapter_id: chapterId, title: chapter.title }];
  const currentIndex = chapters.findIndex((item) => item.chapter_id === chapterId);
  const askTeacher = () => openCompanion({
    page_type: "chapter_reader", activity_type: "reading", chapterId,
    visible_section: chapter.title,
    selected_text: context?.selectedText || window.getSelection()?.toString().trim().slice(0, 4000) || undefined,
    suggestedQuestion: `我正在阅读「${chapter.title}」，请帮我讲讲这里的内容。`,
  });
  const readChapter = () => {
    setNarrationOpen(true);
    if (documentRef.current?.querySelector('[role="status"]')) {
      narrator.start([]);
      return;
    }
    narrator.start(documentRef.current ? chapterNarrationSegments(documentRef.current) : []);
  };
  const readSelection = () => {
    if (!context?.selectedText || !documentRef.current) return;
    setNarrationOpen(true);
    narrator.start(selectionNarrationSegments(documentRef.current, context.selectedText, context.blockId), "selection");
  };

  return <ContentLayout title={chapter.course_title} variant="reading" className={focused ? "reader-focus" : ""}
    toolbar={<>
      <div className="reader-font-controls" role="group" aria-label="正文字号">
        <button type="button" aria-label="减小正文字号" disabled={fontSize <= 16} onClick={() => setFontSize((n) => n - 1)}>A−</button>
        <span>{fontSize}</span>
        <button type="button" aria-label="增大正文字号" disabled={fontSize >= 22} onClick={() => setFontSize((n) => n + 1)}>A+</button>
      </div>
      <button type="button" className="reader-focus-button" aria-pressed={focused} onClick={() => setFocused((value) => !value)}>{focused ? "退出专注" : "专注阅读"}</button>
      <button type="button" className="reader-narration-button" aria-expanded={narrationOpen} aria-controls="reader-narration" onClick={() => {
        if (narrationOpen) { narrator.stop(); setNarrationOpen(false); }
        else readChapter();
      }}><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4V5Zm4 3a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14" /></svg>{narrationOpen ? "收起朗读" : "朗读本章"}</button>
      <button type="button" className="reader-teacher-button" onClick={askTeacher}>问问老师</button>
    </>}
    rail={<div className="reader-navigation" data-expanded={directoryOpen}>
      <button className="reader-navigation-toggle" type="button" aria-expanded={directoryOpen} aria-controls="reader-navigation-list" onClick={() => setDirectoryOpen((value) => !value)}>章节目录 <span>{directoryReady ? `${chapters.length} 章` : "仅当前章"}</span></button>
      <div className="reader-navigation-content" id="reader-navigation-list">
        <div className="reader-navigation-heading"><h2>章节目录</h2><span>{directoryReady ? `${chapters.length} 章` : "仅当前章"}</span></div>
        {directoryFailed ? <p className="content-note">目录暂时无法读取。<button type="button" onClick={() => setDirectoryAttempt((value) => value + 1)}>重试</button></p> : null}
        <ol>{chapters.map((item, index) => <li key={item.chapter_id}><a href={`/chapters/${item.chapter_id}`} aria-current={item.chapter_id === chapterId ? "page" : undefined}><span>{String(index + 1).padStart(2, "0")}</span><span>{item.title}</span></a></li>)}</ol>
        <a className="reader-full-directory" href={`/courses/${chapter.course_id}`}>查看课程说明 →</a>
      </div>
    </div>}
  >
    <div className="reader-position-bar"><span>{directoryReady && currentIndex >= 0 ? `第 ${currentIndex + 1} / ${chapters.length} 章` : "章节阅读"}</span><span>{resume?.is_current_revision ? "已恢复上次阅读位置" : "阅读进度自动保存"}</span></div>
    {resume && !resume.is_current_revision ? <p className="content-note" data-testid="resume-note">章节已更新为 r{chapter.revision}，从当前版本开始阅读。</p> : null}
    {narrationOpen ? <ReaderNarrationPanel narrator={narrator} onReadChapter={readChapter} /> : null}
    <div ref={documentRef} className="reader-document" style={{ fontSize }}>
      <ChapterReader chapter={chapter} resume={resume} locationHash={window.location.hash} onReadPosition={recordPosition} onSelect={selectText} />
    </div>
    {context ? <div className="reader-selection-bar" data-testid="reader-aside" aria-live="polite"><span>已选中 {context.selectedChars} 字，可以朗读或向老师提问。</span><div className="reader-selection-actions"><button type="button" onClick={readSelection}>朗读这段</button><button type="button" onClick={askTeacher}>解释这段内容</button></div></div> : null}
    {contextError ? <p className="form-error" role="alert">{contextError}</p> : null}
    <div className="reader-learning-links"><InteractiveLearningLinks revisionIds={[chapter.revision_id]} /></div>
    <div className="reader-study-actions" data-testid="practice-slot"><div><h2>学完这一章</h2><p>进入课堂，继续讲解、检查理解和练习。</p></div><a href={`/study/lesson?chapter=${chapterId}`}>进入本章课堂 →</a></div>
    <nav className="reader-page-turn" aria-label="章节翻页">
      {prev ? <a href={`/chapters/${prev.chapter_id}`} data-testid="prev-chapter"><span>← 上一章</span><strong>{prev.title}</strong></a> : <a href={`/courses/${chapter.course_id}`}><span>课程目录</span><strong>查看全部可读章节</strong></a>}
      {next ? <a href={`/chapters/${next.chapter_id}`} data-testid="next-chapter"><span>下一章 →</span><strong>{next.title}</strong></a> : <a href="/resources"><span>已到本课程末章</span><strong>返回资料库 →</strong></a>}
    </nav>
  </ContentLayout>;
}
