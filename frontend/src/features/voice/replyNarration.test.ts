import { expect, it } from "vitest";
import { replyNarrationText } from "./replyNarration";
it("keeps explanation and link labels without reading markdown, JSON, URLs or identifiers", () => {
  expect(replyNarrationText('# **老师讲解**\n- 看[课程](https://test.local/x)。\n```json\n{"internal_id":"secret"}\n```\n`条件判断` https://test.local/private 12345678-1234-1234-1234-123456789abc')).toBe("老师讲解 看课程。 条件判断");
});
