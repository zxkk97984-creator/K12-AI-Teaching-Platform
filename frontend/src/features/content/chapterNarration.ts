export type ReadingSegment = { text: string; blockId: string | null; range?: Range };
type Sentence = { text: string; start: number; end: number };
type TextPart = { text: string; node: Text | Element; offset?: number };

/** Sentence offsets use DOM's UTF-16 indexing; very long sentences stay bounded. */
function sentences(text: string): Sentence[] {
  const result: Sentence[] = [];
  let start = 0;
  const append = (end: number) => {
    const value = text.slice(start, end);
    const leading = value.length - value.trimStart().length;
    const trailing = value.length - value.trimEnd().length;
    if (value.trim()) result.push({ text: value.trim(), start: start + leading, end: end - trailing });
    start = end;
  };
  for (let index = 0; index < text.length; index += 1) {
    const character = text[index];
    const ending = /[。！？!?；;\n]/u.test(character) || (character === "." && (!text[index + 1] || /\s/u.test(text[index + 1])));
    if (ending) {
      while (/[。！？!?；;”’"'）)\]】]/u.test(text[index + 1] ?? "")) index += 1;
      append(index + 1);
    } else if (index - start >= 219) {
      if (/[\uD800-\uDBFF]/u.test(character)) index += 1;
      append(index + 1);
    }
  }
  append(text.length);
  return result;
}

export function splitNarrationText(text: string): string[] {
  return sentences(text).map((sentence) => sentence.text);
}

function textRange(parts: TextPart[], start: number, end: number): Range | undefined {
  const range = document.createRange();
  let offset = 0;
  let started = false;
  for (const part of parts) {
    const next = offset + part.text.length;
    if (!started && start < next) {
      range.setStart(part.node, part.node instanceof Text ? (part.offset ?? 0) + start - offset : 0);
      started = true;
    }
    if (started && end <= next) {
      range.setEnd(part.node, part.node instanceof Text ? (part.offset ?? 0) + end - offset : part.node.childNodes.length);
      return range;
    }
    offset = next;
  }
  return undefined;
}

/** Read the displayed chapter with sentence ranges that retain inline formatting. */
export function chapterNarrationSegments(root: HTMLElement): ReadingSegment[] {
  const result: ReadingSegment[] = [];
  for (const block of root.querySelectorAll(".content-reader__title, .content-reader__blocks > [data-block-id]")) {
    const blockId = block.getAttribute("data-block-id");
    let parts: TextPart[] = [];
    const flush = () => {
      for (const sentence of sentences(parts.map((part) => part.text).join(""))) {
        result.push({ text: sentence.text, blockId, range: textRange(parts, sentence.start, sentence.end) });
      }
      parts = [];
    };
    const visit = (node: Node) => {
      if (node instanceof Text) { parts.push({ text: node.data, node }); return; }
      if (!(node instanceof Element)) return;
      if (node.matches(".content-block__unsupported, .content-figure__pending")) return;
      if (node.matches("pre")) {
        flush();
        result.push({ text: "代码示例，请对照正文查看。", blockId });
        return;
      }
      if (node.matches(".katex")) {
        const formula = node.querySelector('annotation[encoding="application/x-tex"]')?.textContent;
        parts.push({ text: formula ? ` 公式 ${formula} ` : node.textContent ?? "", node });
        return;
      }
      if (node.matches("br")) { flush(); return; }
      const separate = node.matches("h1,h2,h3,h4,h5,h6,p,li,tr,figcaption");
      if (separate) flush();
      node.childNodes.forEach(visit);
      if (separate) flush();
    };
    visit(block);
    flush();
  }
  return result;
}

/** Locate a validated selection without changing the user's own text selection. */
export function selectionNarrationSegments(root: HTMLElement, text: string, blockId: string | null): ReadingSegment[] {
  const candidates = chapterNarrationSegments(root).filter((segment) => !blockId || segment.blockId === blockId);
  let cursor = 0;
  return splitNarrationText(text).map((sentence) => {
    const index = candidates.findIndex((candidate, position) => position >= cursor && candidate.text.includes(sentence));
    const candidate = candidates[index];
    if (!candidate?.range) return { text: sentence, blockId };
    cursor = index + 1;
    const source = candidate.range;
    const parts: TextPart[] = [];
    const walker = document.createTreeWalker(source.commonAncestorContainer, NodeFilter.SHOW_TEXT);
    const nodes: Text[] = source.commonAncestorContainer instanceof Text ? [source.commonAncestorContainer] : [];
    while (walker.nextNode()) nodes.push(walker.currentNode as Text);
    for (const node of nodes) {
      if (!source.intersectsNode(node)) continue;
      const start = source.startContainer === node ? source.startOffset : 0;
      const end = source.endContainer === node ? source.endOffset : node.length;
      parts.push({ text: node.data.slice(start, end), node, offset: start });
    }
    const offset = parts.map((part) => part.text).join("").indexOf(sentence);
    return { text: sentence, blockId, range: offset >= 0 ? textRange(parts, offset, offset + sentence.length) : source };
  });
}
