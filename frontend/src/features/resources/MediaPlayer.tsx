/** Video player for a registered teaching resource (T20 R3/R8).
 *
 * The element gets the server's own content URL only; it never takes a URL
 * from model text. `loadeddata`, `error` and `ended` are all handled so a
 * broken file shows a readable message instead of an empty box.
 */

import { useCallback, useState } from "react";
import { contentUrl } from "./api";

type PlayerState = "idle" | "loading" | "ready" | "failed" | "ended";

export function MediaPlayer({
  resourceId,
  variant = "SOURCE",
  title,
}: {
  resourceId: string;
  variant?: "SOURCE" | "PREVIEW";
  title: string;
}) {
  const [state, setState] = useState<PlayerState>("idle");
  const [message, setMessage] = useState<string | null>(null);

  const onLoaded = useCallback(() => {
    setState("ready");
    setMessage(null);
  }, []);
  const onError = useCallback(() => {
    setState("failed");
    setMessage("视频无法播放：文件缺失或格式不受支持，请联系老师。");
  }, []);
  const onEnded = useCallback(() => setState("ended"), []);

  return (
    <figure className="resource-player" data-testid="resource-player">
      <video
        data-testid={`resource-video-${resourceId}`}
        controls
        preload="metadata"
        src={contentUrl(resourceId, variant, "inline")}
        onLoadStart={() => setState((current) => (current === "failed" ? current : "loading"))}
        onLoadedData={onLoaded}
        onError={onError}
        onEnded={onEnded}
      />
      <figcaption data-testid="resource-player-state">
        {state === "idle" && `正在准备「${title}」…`}
        {state === "loading" && "视频加载中…"}
        {state === "ready" && `正在播放：「${title}」`}
        {state === "ended" && `已播放完：「${title}」`}
        {state === "failed" && message}
      </figcaption>
    </figure>
  );
}
