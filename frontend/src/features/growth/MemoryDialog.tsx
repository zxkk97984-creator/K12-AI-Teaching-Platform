import { createPortal } from "react-dom";
import { useEffect, useRef, type KeyboardEvent, type ReactNode } from "react";

type MemoryDialogProps = {
  title: string;
  onClose: () => void;
  children: ReactNode;
};

export function MemoryDialog({ title, onClose, children }: MemoryDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (!triggerRef.current) triggerRef.current = document.activeElement as HTMLElement | null;
    ref.current?.showModal();
    // Removing the dialog closes it. Calling close in StrictMode's effect
    // cleanup would fire onClose and dismiss the newly opened panel.
    return () => triggerRef.current?.focus();
  }, []);

  const trapFocus = (event: KeyboardEvent<HTMLDialogElement>) => {
    if (event.key !== "Tab") return;
    const selector = 'button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), a[href], [tabindex="0"]';
    const controls = Array.from(ref.current?.querySelectorAll<HTMLElement>(selector) ?? [])
      .filter((element) => element.getClientRects().length > 0);
    const first = controls[0];
    const last = controls[controls.length - 1];
    if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first?.focus();
    }
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last?.focus();
    }
  };

  return createPortal(
    <dialog ref={ref} className="memory-panel" aria-label={title}
      onKeyDown={trapFocus} onCancel={onClose} onClose={onClose}>
      <header>
        <h2>{title}</h2>
        <button type="button" className="secondary" aria-label="关闭" onClick={onClose}>关闭</button>
      </header>
      {children}
    </dialog>,
    document.body,
  );
}
