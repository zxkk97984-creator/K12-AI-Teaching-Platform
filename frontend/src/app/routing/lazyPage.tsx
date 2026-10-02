import { Component, createElement, lazy, Suspense, useState, type ComponentProps, type ComponentType, type ReactNode } from "react";

class PageBoundary extends Component<{ children: ReactNode; label: string; retry: (error: unknown) => void }, { failed: boolean; error: unknown }> {
  state = { failed: false, error: null as unknown };
  static getDerivedStateFromError(error: unknown) { return { failed: true, error }; }
  render() {
    return this.state.failed ? <main className="route-load-state" role="alert">
      <p>{this.props.label}暂时无法打开，请检查网络后重试。</p>
      <button type="button" onClick={() => this.props.retry(this.state.error)}>重新加载页面</button>
    </main> : this.props.children;
  }
}

// Match React.lazy's component bound, preserving each page's concrete props.
export function createLazyPage<PageComponent extends ComponentType<any>>(
  loader: () => Promise<{ default: PageComponent }>,
  label: string,
  AfterRender?: ComponentType,
) {
  let pending: ReturnType<typeof loader> | undefined;
  let reloadRequired = false;
  function load() {
    // Idle preloads and navigation share one attempt. A failed preload must not
    // poison later navigation or an explicit retry.
    pending ??= loader().catch((error: unknown) => {
      pending = undefined;
      // Browsers cache failed module graphs. Retrying the same import URL in
      // this document still rejects, even when the network has recovered.
      reloadRequired = error instanceof Error && /dynamically imported module|module script|preload CSS/i.test(error.message);
      throw error;
    });
    return pending;
  }
  function LazyPage(props: ComponentProps<PageComponent>) {
    const [Content, setContent] = useState(() => lazy(load));
    const [attempt, setAttempt] = useState(0);
    return <PageBoundary key={attempt} label={label} retry={(error) => {
      if (reloadRequired || (error instanceof Error && /dynamically imported module|module script|preload CSS/i.test(error.message))) { window.location.reload(); return; }
      setContent(() => lazy(load));
      setAttempt((value) => value + 1);
    }}>
      <Suspense fallback={<main className="route-load-state" role="status">正在加载{label}…</main>}>
        {createElement(Content, props)}
        {AfterRender ? <AfterRender /> : null}
      </Suspense>
    </PageBoundary>;
  }
  return { Page: LazyPage, preload: load };
}

export function scheduleIdlePreloads(loaders: Array<() => Promise<unknown>>) {
  let cancelled = false;
  let idle: number | undefined;
  let timer: number | undefined;
  let index = 0;
  const queue = () => {
    if (cancelled || index >= loaders.length) return;
    if (window.requestIdleCallback) idle = window.requestIdleCallback(() => { void step(); }, { timeout: 2000 });
    else timer = window.setTimeout(() => { void step(); }, 200);
  };
  const step = async () => {
    if (cancelled) return;
    const loader = loaders[index++];
    try { await loader(); } catch { /* Navigation owns visible failure and retry. */ }
    queue();
  };
  // Give the rendered page and its own requests priority, then import one page
  // at a time. Imports do not mount pages or start their business requests.
  timer = window.setTimeout(queue, 1500);
  return () => {
    cancelled = true;
    window.clearTimeout(timer);
    if (idle !== undefined) window.cancelIdleCallback(idle);
  };
}
