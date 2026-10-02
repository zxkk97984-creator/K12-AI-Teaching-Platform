import { memo } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

const remarkPlugins = [remarkGfm, remarkMath];

export const ChapterMarkdown = memo(function ChapterMarkdown({ text }: { text: string }) {
  return <div className="chapter-markdown"><ReactMarkdown
    remarkPlugins={remarkPlugins}
    rehypePlugins={[[rehypeKatex, { trust: false, strict: "ignore", throwOnError: false }]]}
    components={{
      p: ({ children, node }) => {
        const hasOptions = node?.children.some((child) => child.type === "text" && /(?:^|\n)[A-D][.．、)]\s/.test(child.value));
        return <p className={hasOptions ? "chapter-choice-options" : undefined}>{children}</p>;
      },
      h1: ({ children }) => <h3>{children}</h3>,
      h2: ({ children }) => <h3>{children}</h3>,
      a: ({ href, children }) => <a href={href} target={/^https?:/.test(href ?? "") ? "_blank" : undefined} rel="noreferrer">{children}</a>,
      table: ({ children }) => <div className="chapter-table-scroll"><table>{children}</table></div>,
    }}
  >{text}</ReactMarkdown></div>;
});
