import { useEffect, useLayoutEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { registerNavigator } from "../../features/identity/session";

/** Keep existing feature links compatible while preserving the global companion. */
export function NavigationBridge() {
  const navigate = useNavigate();
  const location = useLocation();
  useLayoutEffect(
    () =>
      registerNavigator((path) => {
        void navigate(path);
      }),
    [navigate],
  );
  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      )
        return;
      const anchor = (event.target as Element).closest?.(
        "a[href]",
      ) as HTMLAnchorElement | null;
      if (
        !anchor ||
        anchor.hasAttribute("download") ||
        (anchor.target && anchor.target !== "_self")
      )
        return;
      const url = new URL(anchor.href, window.location.href);
      if (
        url.origin !== window.location.origin ||
        url.pathname.startsWith("/api/") ||
        url.hash
      )
        return;
      if (
        !/^\/(?:$|home$|workbench|study|login|onboarding|settings|courses|chapters|books|picturebooks|conversations|lessons|practice|growth|learn|resources|animations|code|admin)/.test(
          url.pathname,
        )
      )
        return;
      event.preventDefault();
      void navigate(url.pathname + url.search);
    };
    document.addEventListener("click", onClick);
    return () => document.removeEventListener("click", onClick);
  }, [navigate]);
  useEffect(() => {
    const titles: Record<string, string> = {
      workbench: "学习工作台",
      study: "学习中心",
      courses: "课程",
      chapters: "章节阅读",
      lessons: "课堂",
      conversations: "对话学习",
      practice: "练习",
      growth: "个人记忆",
      learn: "学习建议",
      code: "编程实践",
      resources: "学习资源",
      books: "教材阅读",
      picturebooks: "绘本阅读",
      animations: "动画探索",
      settings: "设置",
      onboarding: "学习档案",
      login: "登录",
      admin: "教学管理",
    };
    document.title = `${titles[location.pathname.split("/")[1]] ?? "学习平台"} · K12学习平台`;
    window.scrollTo(0, 0);
    document
      .querySelector<HTMLElement>("#page-content")
      ?.focus({ preventScroll: true });
  }, [location.pathname]);
  return null;
}
