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
        !/^\/(?:$|home$|workbench|study|login|onboarding|settings|courses|chapters|books|picturebooks|conversations|lessons|practice|history|growth|learn|resources|animations|activities|interactive|more|code|admin)/.test(
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
    window.scrollTo(0, 0);
    document
      .querySelector<HTMLElement>("#page-content")
      ?.focus({ preventScroll: true });
  }, [location.pathname]);
  return null;
}
