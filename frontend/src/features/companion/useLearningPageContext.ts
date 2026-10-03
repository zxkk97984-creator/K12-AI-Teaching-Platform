import { useContext, useLayoutEffect, useRef } from "react";
import { ConversationContext } from "../conversation/ConversationProvider";
import type { SceneSnapshot } from "../conversation/types";

/** Read current content at send time; registration expires with the page. */
export function useLearningPageContext(scene: Partial<SceneSnapshot> | null, extra?: () => Partial<SceneSnapshot>) {
  const controller = useContext(ConversationContext);
  const pathname = window.location.pathname;
  const search = window.location.search;
  const latest = useRef({ scene, extra });
  useLayoutEffect(() => { latest.current = { scene, extra }; });
  const identity = scene?.chapter_title ?? scene?.visible_section ?? "";
  useLayoutEffect(() => {
    if (!scene || !controller) return;
    return controller.registerPageContext(() => ({ ...latest.current.scene, ...latest.current.extra?.() }));
  }, [controller, pathname, search, identity, Boolean(scene)]);
}
