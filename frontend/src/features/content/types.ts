import type { components } from "../../shared/types/generated/content";

export type CourseListDTO = components["schemas"]["CourseListDTO"];
export type CourseSummaryDTO = components["schemas"]["CourseSummaryDTO"];
export type ChapterSummaryDTO = components["schemas"]["ChapterSummaryDTO"];
export type ChapterDetailDTO = components["schemas"]["ChapterDetailDTO"];
export type SelfTestQuestionDTO = components["schemas"]["SelfTestQuestionDTO"];
export type SelfTestAnswerDTO = components["schemas"]["SelfTestAnswerDTO"];
export type ChapterNavigationDTO = components["schemas"]["ChapterNavigationDTO"];
export type NeighborRefDTO = components["schemas"]["NeighborRefDTO"];
export type RenderedBlock = components["schemas"]["RenderedBlock"];
export type UnknownBlockDTO = components["schemas"]["UnknownBlockDTO"];
export type ReadingStateDTO = components["schemas"]["ReadingStateDTO"];
export type ReadingEventRequest = components["schemas"]["ReadingEventRequest"];
export type ReadingEventReceipt = components["schemas"]["ReadingEventReceipt"];
export type PageContextRequest = components["schemas"]["PageContextRequest"];
export type PageContextDTO = components["schemas"]["PageContextDTO"];
export type BlockKind = RenderedBlock | UnknownBlockDTO;

export function isUnsupportedBlock(block: BlockKind): block is UnknownBlockDTO {
  return block.type === "UNSUPPORTED";
}
