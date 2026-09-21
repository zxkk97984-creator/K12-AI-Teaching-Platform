import { describe, expect, it } from "vitest";
import {
  DESKTOP_PARTICLES,
  LINK_DISTANCE,
  MAX_FRAME_MS,
  MOBILE_PARTICLES,
  advance,
  createParticles,
  linkSegments,
  particleColor,
  particleCountFor,
  stepScale,
  type Particle,
} from "./particles";

const viewport = { width: 1280, height: 900 };
const idle = { x: 0, y: 0, active: false };

function at(x: number, y: number): Particle {
  return { x, y, vx: 0, vy: 0, radius: 1, hue: 0, brightness: 1, twinkle: 0 };
}

describe("B02 particles", () => {
  it("uses the calm particle counts from the reference", () => {
    expect(particleCountFor(1280)).toBe(DESKTOP_PARTICLES);
    expect(particleCountFor(768)).toBe(DESKTOP_PARTICLES);
    expect(particleCountFor(767)).toBe(MOBILE_PARTICLES);
  });

  it("creates the requested number of particles inside the viewport", () => {
    const particles = createParticles(viewport);
    expect(particles).toHaveLength(DESKTOP_PARTICLES);
    for (const particle of particles) {
      expect(particle.x).toBeGreaterThanOrEqual(0);
      expect(particle.x).toBeLessThanOrEqual(viewport.width);
      expect(particle.y).toBeGreaterThanOrEqual(0);
      expect(particle.y).toBeLessThanOrEqual(viewport.height);
    }
  });

  it("clamps and rejects non-finite frame intervals", () => {
    expect(stepScale(Number.NaN)).toBe(1);
    expect(stepScale(Number.POSITIVE_INFINITY)).toBe(1);
    expect(stepScale(0)).toBe(1);
    expect(stepScale(-5)).toBe(1);
    expect(stepScale(1000)).toBeCloseTo(MAX_FRAME_MS / (1000 / 60));
  });

  it("keeps 60Hz and 120Hz at the same speed", () => {
    // Without dt normalisation a 120Hz display would advance twice as far per
    // wall-clock second. Decay is applied per step, so the two paths agree to
    // within a small tolerance rather than exactly.
    const at60 = [at(100, 100)];
    const at120 = [at(100, 100)];
    for (const particle of at60) particle.vx = 2;
    for (const particle of at120) particle.vx = 2;

    for (let i = 0; i < 60; i += 1) advance(at60, viewport, idle, 1000 / 60);
    for (let i = 0; i < 120; i += 1) advance(at120, viewport, idle, 1000 / 120);

    // Compare distance travelled, not absolute position: both particles wrap.
    expect(at120[0].x - 100).toBeCloseTo(at60[0].x - 100, 0);
    expect(Math.abs(at120[0].x - at60[0].x)).toBeLessThan(3);
  });

  it("wraps out-of-bounds particles instead of bouncing them", () => {
    const particles = [at(-20, 500)];
    advance(particles, viewport, idle, 1000 / 60);
    expect(particles[0].x).toBeGreaterThan(viewport.width);
  });

  it("ignores a pointer that is not active", () => {
    const still = [at(70, 50)];
    const pushed = [at(70, 50)];
    advance(still, viewport, { x: 50, y: 50, active: false }, 1000 / 60);
    advance(pushed, viewport, { x: 50, y: 50, active: true }, 1000 / 60);
    expect(still[0].vx).toBe(0);
    expect(pushed[0].vx).not.toBe(0);
  });

  it("links only pairs closer than the threshold", () => {
    const near = linkSegments([at(0, 0), at(LINK_DISTANCE - 10, 0)]);
    expect(near).toHaveLength(1);
    expect(near[0].alpha).toBeGreaterThan(0);
    expect(linkSegments([at(0, 0), at(LINK_DISTANCE + 10, 0)])).toHaveLength(0);
  });

  it("keeps particle colour alpha inside a drawable range", () => {
    for (const particle of createParticles(viewport)) {
      const alpha = Number(particleColor(particle).match(/,\s([\d.]+)\)$/)?.[1]);
      expect(alpha).toBeGreaterThanOrEqual(0);
      expect(alpha).toBeLessThanOrEqual(1);
    }
  });
});
