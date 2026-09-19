import { useEffect, useState } from "react";
import { fetchHealth, type HealthPayload } from "../app/api";

type State = { kind: "loading" } | { kind: "ready"; live: HealthPayload; ready: HealthPayload } | { kind: "error"; message: string };

export function Home() {
  const [state, setState] = useState<State>({ kind: "loading" });

  useEffect(() => {
    let active = true;
    Promise.all([fetchHealth("/health/live"), fetchHealth("/health/ready")])
      .then(([live, ready]) => {
        if (active) setState({ kind: "ready", live, ready });
      })
      .catch((error: unknown) => {
        if (active) {
          setState({ kind: "error", message: error instanceof Error ? error.message : "未知错误" });
        }
      });
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="shell">
      <p className="eyebrow">SYNTHETIC-FIRST FOUNDATION</p>
      <h1>霜铃 K12 · 本地业务骨架</h1>
      <p className="lede">
        这里只验证独立运行环境、请求 ID 和数据库 readiness。教学页面将在后续任务按真实业务契约逐步建立。
      </p>
      <section className="status-card" aria-live="polite">
        {state.kind === "loading" && <p>正在检查本地服务…</p>}
        {state.kind === "error" && (
          <>
            <span className="pill pill-error">不可用</span>
            <p>{state.message}</p>
          </>
        )}
        {state.kind === "ready" && (
          <>
            <span className="pill pill-ready">就绪</span>
            <dl>
              <div><dt>后端进程</dt><dd>{state.live.status}</dd></div>
              <div><dt>PostgreSQL</dt><dd>{state.ready.database}</dd></div>
              <div><dt>请求 ID</dt><dd>{state.ready.request_id}</dd></div>
            </dl>
          </>
        )}
      </section>
      <p className="boundary-note">
        无非真实 Knodo 调用，无真实学生数据。Fixture、内置测试和部署状态在界面中保持可区分。
      </p>
    </main>
  );
}
