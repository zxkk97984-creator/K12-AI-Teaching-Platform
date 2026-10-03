/** Explicit student commands only; model suggestions and page prose never run jobs. */
export function practiceIntent(message: string): { count: number | null; topic?: string } | null {
  const text = message.trim();
  if (/(?:别|不要|不用|不想|不需要|不必|无需)[^，。；\n]{0,12}(?:出|生成|练习)|(?:怎么|如何|为什么)[^，。；\n]{0,12}(?:出|生成)|(?:解释|介绍|讨论|分析|讲解)[^，。；\n]{0,12}(?:出题|生成[^，。；\n]{0,8}题)|是什么意思|[“「"].*(?:出|生成).*?[”」"]/.test(text)) return null;
  if (!/^(?:(?:请|麻烦|帮|给|为|能不能|可以|我想|我需要|我要|再|继续|根据|按照|针对|围绕|关于)[\s\S]*?)?(?:生成|出|来|做)[\s\S]*(?:题|练习)[。.!！?？]?$/.test(text)) return null;
  const amount = text.match(/([+-]?[\d./]+(?:[eE][+-]?\d+)?|[零一二三四五六七八九十百千两]+)\s*(?:道|个)?\s*(?:题|练习)/)?.[1];
  const digits: Record<string, number> = { 零:0, 一:1, 二:2, 两:2, 三:3, 四:4, 五:5, 六:6, 七:7, 八:8, 九:9 };
  let count: number | null = null;
  if (amount) {
    if (/^[+-]?[\d./]+(?:[eE][+-]?\d+)?$/.test(amount)) count = Number(amount);
    else if (/[百千]/.test(amount)) count = Number.NaN;
    else if (amount.includes("十")) {
      const [tens, units] = amount.split("十");
      count = (tens ? digits[tens] : 1) * 10 + (units ? digits[units] : 0);
    } else count = digits[amount];
  }
  const candidate = text.match(/(?:围绕|关于|针对)(.+?)(?:生成|出|来|做)/)?.[1]?.trim();
  return { count, topic: candidate && !/^(?:本章|这章|本节|当前内容|这个知识点)$/.test(candidate) ? candidate.slice(0,160) : undefined };
}
