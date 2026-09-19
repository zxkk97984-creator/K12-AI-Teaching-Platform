import { useEffect, useRef } from "react";
import { python } from "@codemirror/lang-python";
import { EditorState } from "@codemirror/state";
import { EditorView, lineNumbers } from "@codemirror/view";

export function CodeEditor({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  const host = useRef<HTMLDivElement | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!host.current) return undefined;
    const state = EditorState.create({
      doc: value,
      extensions: [
        lineNumbers(),
        python(),
        EditorView.theme({
          "&": { minHeight: "360px", fontSize: "14px" },
          ".cm-scroller": { overflow: "auto", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" },
          ".cm-content": { padding: "16px" },
        }),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) onChangeRef.current(update.state.doc.toString());
        }),
      ],
    });
    const view = new EditorView({ state, parent: host.current });
    return () => view.destroy();
  }, []);

  return <div className="codelab-editor" data-testid="codelab-editor" ref={host} />;
}
