import { useEffect, useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Native modal supplies focus trapping, Escape and an inert background. */
export function AdminDrawer({
  title,
  description,
  children,
  footer,
  onClose,
  busy = false,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
  onClose: () => void;
  busy?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const descriptionId = useId();
  useEffect(() => {
    const trigger =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    const dialog = ref.current;
    if (!dialog) return;
    if (dialog.showModal) dialog.showModal();
    else dialog.setAttribute("open", "");
    dialog
      .querySelector<HTMLElement>(
        "[data-autofocus], input:not([readonly]):not([disabled]), select:not([disabled]), textarea:not([readonly]):not([disabled])",
      )
      ?.focus();
    return () => {
      dialog.close?.();
      if (trigger?.isConnected) trigger.focus();
    };
  }, []);
  return createPortal(
    <dialog
      ref={ref}
      className="admin-drawer"
      aria-labelledby={titleId}
      aria-describedby={description ? descriptionId : undefined}
      onCancel={(event) => {
        event.preventDefault();
        if (!busy) onClose();
      }}
    >
      <header className="admin-drawer-head">
        <div>
          <h2 id={titleId}>{title}</h2>
          {description && <p id={descriptionId}>{description}</p>}
          {busy && <p role="status">正在处理请求，请稍候。</p>}
        </div>
        <button
          type="button"
          className="admin-button-quiet"
          disabled={busy}
          aria-label="关闭编辑面板"
          onClick={onClose}
        >
          关闭
        </button>
      </header>
      <div className="admin-drawer-body">{children}</div>
      {footer && <footer className="admin-drawer-foot">{footer}</footer>}
    </dialog>,
    document.body,
  );
}
