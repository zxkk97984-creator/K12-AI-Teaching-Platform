import { useEffect, useRef } from "react";
import { useMotionSafe } from "../../shared/motion/motion-safe";
import {
  advance,
  createParticles,
  linkColor,
  linkSegments,
  particleColor,
  particleCountFor,
  type Particle,
  type Pointer,
  type Viewport,
} from "./lib/particles";
import "./calm-background.css";

/**
 * B02 · calm 轻量背景。
 *
 * 只在欢迎/登录这类没有正文可读性的表面使用；章节阅读器、代码页和长聊天
 * 正文保持静态或更低透明度，这是第 07 章 §7.9 的边界要求。
 *
 * 这里不用 GSAP：光斑交给 CSS 关键帧，粒子交给 Canvas 2D，两者都不需要
 * 额外的补间引擎。五块光斑的时长已按手册使用 calm 档（full 时长 × 1.6）。
 *
 * 降级三档（第 07 章 §7.8，属于迁移建议，不是参考组件的原有接口）：
 *   static — 仅静态渐变，不建 Canvas、不挂监听、不起帧循环
 *   calm   — 默认，慢速光斑 + 少量粒子
 *   full   — 不在本次范围内（B01 未选中）
 */
export type CalmBackgroundTier = "static" | "calm";

const BLOBS = [
  { className: "sl-fblob--1", size: 600, style: { left: "-130px", top: "-150px" } },
  { className: "sl-fblob--2", size: 520, style: { right: "-80px", top: "14%" } },
  { className: "sl-fblob--3", size: 480, style: { right: "-60px", bottom: "-100px" } },
  { className: "sl-fblob--4", size: 400, style: { left: "14%", bottom: "4%" } },
  { className: "sl-fblob--5", size: 340, style: { left: "52%", top: "-8%" } },
] as const;

export function CalmBackground({ tier = "calm" }: { tier?: CalmBackgroundTier }) {
  const motionSafe = useMotionSafe();
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const active = tier === "calm" && motionSafe;

  useEffect(() => {
    if (!active) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext("2d");
    if (!context) return;

    let viewport: Viewport = { width: window.innerWidth, height: window.innerHeight };
    let particles: Particle[] = createParticles(viewport);
    const pointer: Pointer = { x: 0, y: 0, active: false };
    let frame = 0;
    let last = 0;
    let running = false;

    // 设备像素比上限为 2：CSS 尺寸与绘图缓冲分开设置，避免高 DPR 无限加价。
    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      viewport = { width: window.innerWidth, height: window.innerHeight };
      canvas.width = Math.floor(viewport.width * ratio);
      canvas.height = Math.floor(viewport.height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      // 粒子数只在初始化时决定一次，跨过断点不会重建一套配置。
      particles = createParticles(viewport);
    };

    const draw = () => {
      context.clearRect(0, 0, viewport.width, viewport.height);
      context.lineWidth = 0.6;
      for (const segment of linkSegments(particles)) {
        context.strokeStyle = linkColor(segment.alpha);
        context.beginPath();
        context.moveTo(segment.x1, segment.y1);
        context.lineTo(segment.x2, segment.y2);
        context.stroke();
      }
      for (const particle of particles) {
        context.fillStyle = particleColor(particle);
        context.beginPath();
        context.arc(particle.x, particle.y, particle.radius, 0, Math.PI * 2);
        context.fill();
      }
    };

    const tick = (now: number) => {
      const delta = last ? now - last : 1000 / 60;
      last = now;
      advance(particles, viewport, pointer, delta);
      draw();
      frame = window.requestAnimationFrame(tick);
    };

    const start = () => {
      if (running) return;
      running = true;
      last = 0;
      frame = window.requestAnimationFrame(tick);
    };

    // 真正取消帧循环，而不是在回调里提前返回：提前返回仍会每帧唤醒主线程。
    const stop = () => {
      if (!running) return;
      running = false;
      window.cancelAnimationFrame(frame);
      frame = 0;
    };

    const onPointerMove = (event: PointerEvent) => {
      // 只有精细指针才启用水印交互；触摸设备不套用桌面 hover 体验。
      if (event.pointerType !== "mouse") return;
      pointer.x = event.clientX;
      pointer.y = event.clientY;
      pointer.active = true;
    };
    const onPointerLeave = () => {
      pointer.active = false;
    };
    // 光标离开视口或标签页隐藏时停掉，回来后重新开始。
    const onVisibility = () => {
      if (document.visibilityState === "hidden") stop();
      else start();
    };
    // 指针在触屏上不可用，此时不应留下一个停住不动的“虚拟光标”。
    const supportsHover = window.matchMedia?.("(hover: hover)").matches ?? true;

    resize();
    draw();
    if (supportsHover) {
      window.addEventListener("pointermove", onPointerMove, { passive: true });
      window.addEventListener("pointerleave", onPointerLeave);
    }
    window.addEventListener("resize", resize);
    window.addEventListener("visibilitychange", onVisibility);
    start();

    return () => {
      stop();
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerleave", onPointerLeave);
      window.removeEventListener("resize", resize);
      window.removeEventListener("visibilitychange", onVisibility);
      context.clearRect(0, 0, viewport.width, viewport.height);
    };
  }, [active]);

  const paused = tier === "static" || !motionSafe;

  return (
    <div
      className="sl-fluid-bg"
      data-tier={tier}
      data-paused={paused ? "true" : "false"}
      aria-hidden="true"
    >
      <div className="sl-fluid-bg__blobs">
        {BLOBS.map((blob) => (
          <span
            key={blob.className}
            className="sl-fblob-shell"
            style={{ ...blob.style, width: blob.size, height: blob.size }}
          >
            <span className={`sl-fblob ${blob.className}`} />
          </span>
        ))}
      </div>
      {active ? (
        <canvas
          ref={canvasRef}
          className="sl-fconstellation"
          data-testid="calm-constellation"
        />
      ) : null}
      <div className="sl-fgrain" />
    </div>
  );
}
