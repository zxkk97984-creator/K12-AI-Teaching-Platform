import { useEffect } from "react";
import { ErrorState, LoadingState, StatePanel } from "../../shared/ui/state";
import { WorkbenchShell } from "../../features/workbench/WorkbenchShell";
import { useWorkbenchSession } from "../../features/workbench/useWorkbenchSession";
import { logout } from "../../features/identity/api";
import { navigate } from "../../features/identity/session";
import "../../features/workbench/workbench.css";

async function signOut() {
  await logout();
  navigate("/login");
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <main className="wb-page">
      <div className="wb-frame">{children}</div>
    </main>
  );
}

function AdminNotice({ username }: { username: string }) {
  return (
    <StatePanel
      tone="empty"
      title="管理员账号不进入学生工作台"
      description={`${username} 的角色由服务端会话校验。管理端能力请从资源管理、互动内容和 AI 教师设置进入。`}
      action={
        <>
          <a className="wb-link" href="/admin/resources">
            打开资源管理
          </a>
          <button type="button" className="secondary" onClick={signOut}>
            退出登录
          </button>
        </>
      }
      testId="admin-notice"
    />
  );
}

function NeedsStage() {
  return (
    <StatePanel
      tone="empty"
      title="先完成学段选择"
      description="学习内容按学段筛选，未选择学段时不展示任何课程、统计或推荐。"
      action={
        <a className="wb-link" href="/onboarding">
          去选择学段与偏好
        </a>
      }
      testId="needs-stage"
    />
  );
}

export function WorkbenchPage() {
  const { state, reload } = useWorkbenchSession();

  useEffect(() => {
    document.title = "教学工作台 · 霜铃 K12";
  }, []);

  if (state.kind === "loading") {
    return (
      <Frame>
        <LoadingState label="正在读取学习档案…" />
      </Frame>
    );
  }

  if (state.kind === "error") {
    if (state.status === 401) {
      return (
        <Frame>
          <ErrorState
            title="登录已失效"
            message="会话已过期或被撤销，正在跳转到登录页。"
          />
        </Frame>
      );
    }
    return (
      <Frame>
        <ErrorState
          title="暂时无法打开工作台"
          message={state.message}
          requestId={state.requestId}
          onRetry={reload}
        />
      </Frame>
    );
  }

  const { me } = state;
  if (me.user.role === "admin") {
    return (
      <Frame>
        <AdminNotice username={me.user.username} />
      </Frame>
    );
  }

  if (!me.profile?.stage) {
    return (
      <Frame>
        <NeedsStage />
      </Frame>
    );
  }

  return (
    <main className="wb-page">
      <WorkbenchShell me={me} />
    </main>
  );
}
