/**
 * B02 · calm 背景的粒子数学（纯函数，可单独测试）。
 *
 * 参考实现的系数是“每帧”离散增量，直接照搬到 120Hz 屏会让运动速度翻倍。
 * 这里统一按第 07 章 §7.7 的建议做 dt 归一化，并按同一章的警告重新标定：
 * 单位帧系数在 k 个参考步长上等价于 `v += a * k`，而每秒衰减率要换算成
 * `Math.pow(decay, k)`，不能只给速度乘 dt。
 */

export const DESKTOP_PARTICLES = 55;
export const MOBILE_PARTICLES = 24;
export const MOBILE_BREAKPOINT = 768;

export const LINK_DISTANCE = 130;
export const LINK_ALPHA = 0.2;
export const LINK_WIDTH = 0.6;

export const REPEL_RADIUS = 36;
export const REPEL_COEFFICIENT = 0.04;
export const SWIRL_RADIUS = 220;
export const SWIRL_TANGENTIAL = 0.05;
export const SWIRL_RADIAL = -0.02;
export const SWIRL_RING = 90;
export const VELOCITY_DECAY = 0.985;

export const MIN_RADIUS = 0.6;
export const MAX_RADIUS = 2.2;
export const MAX_FRAME_MS = 50;
export const REFERENCE_FRAME_MS = 1000 / 60;

/** 桌面/移动端粒子数只在初始化时决定一次，与参考实现一致。 */
export function particleCountFor(width: number): number {
  return width < MOBILE_BREAKPOINT ? MOBILE_PARTICLES : DESKTOP_PARTICLES;
}

export interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  /** 0 = 蓝，1 = 珊瑚；主体偏蓝。 */
  hue: number;
  brightness: number;
  twinkle: number;
}

export interface Viewport {
  width: number;
  height: number;
}

/**
 * dt 归一化系数。大间隔必须设上限，否则切回标签页时粒子会瞬移出去。
 * 非有限值一律回落到一个参考步长。
 */
export function stepScale(deltaMs: number): number {
  if (!Number.isFinite(deltaMs) || deltaMs <= 0) return 1;
  return Math.min(deltaMs, MAX_FRAME_MS) / REFERENCE_FRAME_MS;
}

function random(min: number, max: number): number {
  return min + Math.random() * (max - min);
}

export function createParticle(viewport: Viewport): Particle {
  return {
    x: random(0, viewport.width),
    y: random(0, viewport.height),
    vx: random(-0.12, 0.12),
    vy: random(-0.12, 0.12),
    radius: random(MIN_RADIUS, MAX_RADIUS),
    hue: Math.random() < 0.15 ? 1 : 0,
    brightness: Math.random() < 0.2 ? 1 : 0.6,
    twinkle: random(0, Math.PI * 2),
  };
}

export function createParticles(viewport: Viewport): Particle[] {
  return Array.from({ length: particleCountFor(viewport.width) }, () =>
    createParticle(viewport),
  );
}

export interface Pointer {
  x: number;
  y: number;
  active: boolean;
}

/** 越界时带边距循环，而不是撞墙反弹。 */
function wrap(value: number, limit: number, margin: number): number {
  if (value < -margin) return limit + margin;
  if (value > limit + margin) return -margin;
  return value;
}

/**
 * 推进一帧。`pointer.active` 为假时跳过光标力，这样触摸设备不会凭空出现
 * 一个悬在角落的“虚拟光标”。
 */
export function advance(
  particles: Particle[],
  viewport: Viewport,
  pointer: Pointer,
  deltaMs: number,
): void {
  const k = stepScale(deltaMs);
  const decay = Math.pow(VELOCITY_DECAY, k);
  for (const particle of particles) {
    if (pointer.active) {
      const dx = particle.x - pointer.x;
      const dy = particle.y - pointer.y;
      const distance = Math.hypot(dx, dy);
      if (distance > 0 && distance < SWIRL_RADIUS) {
        if (distance < REPEL_RADIUS) {
          // 力随接近中心增强。
          const push = (1 - distance / REPEL_RADIUS) * REPEL_COEFFICIENT * k;
          particle.vx += (dx / distance) * push;
          particle.vy += (dy / distance) * push;
        }
        const tangential = SWIRL_TANGENTIAL * k;
        particle.vx += (-dy / distance) * tangential;
        particle.vy += (dx / distance) * tangential;
        // 向约 90px 的环带靠拢：环外拉回，环内推出。
        const radial = ((distance - SWIRL_RING) / SWIRL_RING) * SWIRL_RADIAL * k;
        particle.vx += (dx / distance) * radial;
        particle.vy += (dy / distance) * radial;
      }
    }
    particle.vx *= decay;
    particle.vy *= decay;
    particle.x = wrap(particle.x + particle.vx * k, viewport.width, 8);
    particle.y = wrap(particle.y + particle.vy * k, viewport.height, 8);
    particle.twinkle += 0.02 * k;
  }
}

export interface Segment {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  alpha: number;
}

/** 两点距离小于 130px 时连线，透明度随距离线性变淡。 */
export function linkSegments(particles: Particle[]): Segment[] {
  const segments: Segment[] = [];
  for (let i = 0; i < particles.length; i += 1) {
    const a = particles[i];
    for (let j = i + 1; j < particles.length; j += 1) {
      const b = particles[j];
      const distance = Math.hypot(a.x - b.x, a.y - b.y);
      if (distance >= LINK_DISTANCE) continue;
      segments.push({
        x1: a.x,
        y1: a.y,
        x2: b.x,
        y2: b.y,
        alpha: LINK_ALPHA * (1 - distance / LINK_DISTANCE),
      });
    }
  }
  return segments;
}

export function particleColor(particle: Particle): string {
  const hue = particle.hue > 0.5 ? "244, 180, 150" : "120, 165, 245";
  const alpha = (0.35 + 0.25 * Math.sin(particle.twinkle)) * particle.brightness;
  return `rgba(${hue}, ${Math.max(0, Math.min(1, alpha)).toFixed(3)})`;
}

export function linkColor(alpha: number): string {
  return `rgba(130, 170, 235, ${alpha.toFixed(3)})`;
}
