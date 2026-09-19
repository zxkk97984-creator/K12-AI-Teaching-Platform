/** Animation types (T21).
 *
 * Hand-written against `backend/app/modules/resources/animation_service.py`.
 * The server sends data only (template id, bounded parameter schema, narration,
 * text alternative); the step list is produced by the pure functions in
 * `templates.ts`. There is no HTML/JS payload anywhere in this feature.
 */

export type AnimationTemplate = "SORT_STEPS" | "BINARY_SEARCH";

export type IntArraySpec = {
  type: "int_array";
  min_items: number;
  max_items: number;
  min_value: number;
  max_value: number;
};

export type IntSpec = {
  type: "int";
  min_value: number;
  max_value: number;
};

export type ParamSchema = {
  type: "object";
  additional_properties: false;
  required: string[];
  properties: Record<string, IntArraySpec | IntSpec>;
};

export type AnimationDefinition = {
  id: string;
  template: AnimationTemplate;
  title: string;
  summary: string;
  stage: string;
  grade_min: number | null;
  grade_max: number | null;
  course_slug: string | null;
  chapter_slug: string | null;
  chapter_revision: number | null;
  knowledge_points: string[];
  objectives: string[];
  preconditions: string[];
  text_alternative: string;
  param_schema: ParamSchema;
  defaults: Record<string, unknown>;
  limits: { max_items: number; max_steps: number; min_value: number; max_value: number };
  review_status: string | null;
  publication_status: string | null;
  license_code: string | null;
  is_test_fixture: boolean;
  content_notice: string | null;
};

export type AnimationList = { items: AnimationDefinition[]; profile: string };

export type AnimationSpec = {
  definition: AnimationDefinition;
  params: Record<string, unknown>;
  step_source: "CLIENT_PURE_FUNCTION";
};

export type SortStepKind = "INITIAL" | "COMPARE" | "SWAP" | "NO_SWAP" | "PASS_DONE" | "DONE";

export type SortStep = {
  kind: SortStepKind;
  array: number[];
  compare: [number, number] | null;
  highlight: number[];
  sortedFrom: number;
  narration: string;
  invariant: string;
};

export type SearchStepKind =
  | "INITIAL"
  | "PROBE"
  | "NARROW_LEFT"
  | "NARROW_RIGHT"
  | "FOUND"
  | "NOT_FOUND";

export type SearchStep = {
  kind: SearchStepKind;
  array: number[];
  low: number;
  high: number;
  mid: number | null;
  highlight: number[];
  excluded: number[];
  narration: string;
};

export type AnimationStep = SortStep | SearchStep;
