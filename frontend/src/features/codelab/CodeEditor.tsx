import { useEffect, useRef } from "react";
import { python } from "@codemirror/lang-python";
import { defaultHighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { defaultKeymap, history, historyKeymap, indentWithTab } from "@codemirror/commands";
import { EditorState } from "@codemirror/state";
import { EditorView, keymap, lineNumbers } from "@codemirror/view";

type Props = {
  value: string;
  onChange: (value: string) => void;
  ariaLabel?: string;
  readOnly?: boolean;
};

export function CodeEditor({
  value,
  onChange,
  ariaLabel = "Python 代码编辑器",
  readOnly = false,
}: Props) {
  const host = useRef<HTMLDivElement | null>(null);
  const viewRef = useRef<EditorView | null>(null);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange;

  useEffect(() => {
    if (!host.current) return undefined;
    const state = EditorState.create({
      doc: value,
      extensions: [
        lineNumbers(),
        python(),
        syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
        history(),
        keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
        EditorState.readOnly.of(readOnly),
        EditorView.editable.of(!readOnly),
        EditorView.contentAttributes.of({ "aria-label": ariaLabel, "aria-readonly": String(readOnly) }),
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
    viewRef.current = view;
    return () => {
      view.destroy();
      viewRef.current = null;
    };
  }, [ariaLabel, readOnly]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view || view.state.doc.toString() === value) return;
    view.dispatch({
      changes: { from: 0, to: view.state.doc.length, insert: value },
    });
  }, [value]);

  return <div className="codelab-editor" data-testid="codelab-editor" ref={host} />;
}
