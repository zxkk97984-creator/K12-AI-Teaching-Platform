import { ReplyNarrationControl } from "../voice/ReplyNarrationControl";
import { memo, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";
import type { CardDTO, MessageDTO } from "./types";
import { LookupCards } from "./LookupCards";
import { CompanionHeadAvatar, useCompanionName } from "../companion/CompanionAvatar";
function FixtureBadge() {
  return (
    <span className="conv-fixture" data-testid="fixture-badge">
      合成夹具（非真实 Knodo）
    </span>
  );
}

function CardView({ card, onRetryLookup }: { card: CardDTO; onRetryLookup?: () => void }) {
  const [copied, setCopied] = useState(false);
  const visibleSources = card.source_refs.filter((ref) => !ref.source_id.startsWith("lookup:"));
  const copy = async () => {
    try {
      await navigator.clipboard?.writeText(card.message_markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  return (
    <article className="conv-card" data-testid="assistant-card">
      <SafeMarkdown text={card.message_markdown} />
      <LookupCards cards={card.lookup_cards} onRetry={onRetryLookup} />
      <div className="conv-card-actions">
        <button type="button" className="secondary" onClick={() => void copy()} aria-label="复制回复">
          {copied ? "已复制" : "复制"}
        </button>
      </div>
      {card.followup_question ? (
        <p className="conv-followup">下一步：{card.followup_question}</p>
      ) : null}
      {visibleSources.length > 0 ? (
        <ul className="conv-sources" aria-label="来源">
          {visibleSources.map((ref) => (
            <li key={`${ref.source_id}:${ref.locator}`}>
              {ref.source_id} · {ref.locator}
            </li>
          ))}
        </ul>
      ) : !card.lookup_cards?.length ? (
        <p className="conv-muted">本条没有可用来源（依据不足时不编造）。</p>
      ) : null}
      {card.warnings.length > 0 ? (
        <p className="conv-warnings">提示：{card.warnings.join("、")}</p>
      ) : null}
      {card.fixture ? <FixtureBadge /> : null}
      {card.fixture && card.action ? (
        <p className="conv-muted">合成夹具动作不可点击（避免假资源）。</p>
      ) : null}
    </article>
  );
}

const markdownPlugins = [remarkGfm,remarkMath];

const SafeMarkdown = memo(function SafeMarkdown({ text }: { text: string }) {
  return (
    <div className="conv-card-text">
      <ReactMarkdown remarkPlugins={markdownPlugins} rehypePlugins={[[rehypeKatex,{trust:false,strict:"ignore",throwOnError:false}]]} skipHtml components={{
        h1: ({ children }) => <h3>{children}</h3>,
        h2: ({ children }) => <h3>{children}</h3>,
        pre: ({ children }) => <pre className="conv-code-block">{children}</pre>,
        table: ({ children }) => <div className="conv-table-scroll"><table>{children}</table></div>,
        a: ({ href, children }) => href ? <a href={href} target={/^https?:/.test(href) ? "_blank" : undefined} rel="noopener noreferrer">{children}</a> : <span>{children}</span>,
        // AI replies must not load arbitrary remote images or execute raw HTML.
        img: ({ alt }) => <span>{alt}</span>,
      }}>{text}</ReactMarkdown>
    </div>
  );
});

export function MessageView({ message, extra, onRetryLookup }: { message: MessageDTO; extra?: ReactNode; onRetryLookup?: () => void }) {
  const companionName = useCompanionName();
  const [copied, setCopied] = useState(false);
  const copyReply = async () => {
    try {
      await navigator.clipboard.writeText(message.content_markdown);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  };
  if (message.role === "USER") {
    return (
      <>
      <li className="conv-message conv-message-user" data-testid="user-message">
        <strong className="sr-only">你</strong>
        <p>{message.content_markdown}</p>
      </li>
      {extra ? <li className="conv-message conv-message-assistant">
        <div className="conv-assistant-author"><CompanionHeadAvatar /><strong>{companionName}</strong></div>
        {extra}
      </li> : null}
      </>
    );
  }
  return (
    <li className="conv-message conv-message-assistant">
      <div className="conv-assistant-author"><CompanionHeadAvatar /><strong>{companionName}</strong></div>
      {message.source_label && <p className="conv-current-reference">本条参考：{message.source_label}</p>}
      {message.card ? (
        <CardView card={message.card} onRetryLookup={onRetryLookup} />
      ) : (
        <SafeMarkdown text={message.content_markdown} />
      )}
      {!message.card && message.content_markdown ? <div className="conv-message-actions"><button type="button" className="secondary" onClick={() => void copyReply()} aria-label="复制回复">{copied ? "已复制" : "复制"}</button></div> : null}
      {message.content_markdown ? <ReplyNarrationControl messageId={message.id} text={message.card?.message_markdown ?? message.content_markdown} /> : null}
      {extra}
    </li>
  );
}

/** A provisional answer is never offered as a finished, copyable card. */
export function StreamingMessageView({ text }: { text: string | null }) {
  const companionName = useCompanionName();
  return (
    <li className="conv-message conv-message-assistant conv-message-streaming" data-testid="streaming-message" aria-live="off">
      <div className="conv-assistant-author"><CompanionHeadAvatar /><strong>{companionName}</strong><span className="conv-streaming-label">正在回复</span></div>
      {text ? <SafeMarkdown text={text} /> : <p className="conv-streaming-wait">正在思考你的问题…</p>}
    </li>
  );
}
