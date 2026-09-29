import type { SceneSnapshot } from "../conversation/types";

export type CompanionPageContext = Pick<SceneSnapshot,
  "page_type" | "visible_section" | "selected_text" | "knowledge_points" |
  "activity_type" | "quiz_session_id" | "question_id" |
  "content_kind" | "content_id" | "content_version" | "section_index" |
  "interactive_session_id" | "interactive_scene_id" | "interactive_prompt_id"
> & { chapterId?: string; conversationId?: string; suggestedQuestion?: string };

/** Ask on the current page without navigating away from reading or practice. */
export function openCompanion(context: CompanionPageContext) {
  window.dispatchEvent(new CustomEvent<CompanionPageContext>("companion:open", { detail: context }));
}
