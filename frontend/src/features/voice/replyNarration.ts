/** Speak explanation prose only, excluding fenced payloads, destinations and raw markup. */
export function replyNarrationText(markdown: string) {
  return markdown
    .replace(/```[^]*?```|~~~[^]*?~~~/g, " ")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/https?:\/\/[^\s<>]+/g, " ")
    .replace(/<[^>]*>/g, " ")
    .replace(/\{[^]*?\}/g, " ")
    .replace(/\b[0-9a-f]{8}-[0-9a-f-]{27,}\b/gi, " ")
    .replace(/^\s{0,3}(?:#{1,6}\s+|>\s*|[-*+]\s+|\d+[.)]\s+)/gm, "")
    .replace(/[*_~`|]/g, "")
    .replace(/\s+/g, " ").trim();
}
