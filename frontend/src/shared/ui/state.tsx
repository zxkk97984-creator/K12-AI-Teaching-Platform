import { useId, type ReactNode } from "react";
import "./state.css";

export type StateTone = "loading" | "empty" | "error" | "disabled";

const GLYPHS: Record<StateTone, string> = {
  loading: "…",
  empty: "○",
  error: "!",
  disabled: "–",
};

const TONE_LABELS: Record<StateTone, string> = {
  loading: "载入中",
  empty: "暂无内容",
  error: "错误",
  disabled: "未启用",
};

type StatePanelProps = {
  tone: StateTone;
  title: string;
  description?: string;
  detail?: ReactNode;
  action?: ReactNode;
  density?: "spacious" | "compact";
  testId?: string;
};

/**
 * A single honest state surface. The tone is always visible as text (not only
 * as a colour) and screens carry a real ARIA role so assistive tech can tell
 * "still loading" from "failed" from "not implemented yet".
 */
export function StatePanel({
  tone,
  title,
  description,
  detail,
  action,
  density = "compact",
  testId,
}: StatePanelProps) {
  const titleId = useId();
  return (
    <section
      className="sl-state"
      data-state={tone}
      data-density={density}
      data-testid={testId}
      role={tone === "error" ? "alert" : tone === "loading" ? "status" : undefined}
      aria-live={tone === "loading" ? "polite" : undefined}
      aria-labelledby={titleId}
    >
      <div className="sl-state__head">
        <span className="sl-state__glyph" aria-hidden="true">
          {GLYPHS[tone]}
        </span>
        <p className="sl-state__title" id={titleId}>
          {title}
        </p>
        <span className="sl-state__detail">（{TONE_LABELS[tone]}）</span>
      </div>
      {description ? <p className="sl-state__body">{description}</p> : null}
      {detail ? <p className="sl-state__detail">{detail}</p> : null}
      {action ? <div className="sl-state__actions">{action}</div> : null}
    </section>
  );
}

export function LoadingState({ label }: { label: string }) {
  return <StatePanel tone="loading" title={label} />;
}

export function ErrorState({
  title,
  message,
  requestId,
  onRetry,
}: {
  title: string;
  message: string;
  requestId?: string | null;
  onRetry?: () => void;
}) {
  return (
    <StatePanel
      tone="error"
      title={title}
      description={message}
      detail={requestId ? `请求编号：${requestId}` : undefined}
      action={
        onRetry ? (
          <button type="button" onClick={onRetry}>
            重新加载
          </button>
        ) : undefined
      }
    />
  );
}

export function DisabledState({
  title,
  description,
  ownerTask,
  testId,
  density = "compact",
}: {
  title: string;
  description: string;
  ownerTask: string;
  testId?: string;
  density?: "spacious" | "compact";
}) {
  return (
    <StatePanel
      tone="disabled"
      title={title}
      description={description}
      detail={<span className="sl-state__owner">归属任务：{ownerTask}</span>}
      testId={testId}
      density={density}
    />
  );
}
