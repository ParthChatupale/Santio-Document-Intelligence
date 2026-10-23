export const BACKGROUND_FPS = 24;

export function shouldAnimate(reduced: boolean, paused: boolean) {
  return !reduced && !paused;
}

/** Decorative rendering does not need retina resolution or an unbounded buffer. */
export function drawingSize(width: number, height: number, deviceRatio: number) {
  const ratio = Math.min(Math.max(deviceRatio || 1, 0.1), 1,
    Math.sqrt(600_000 / Math.max(1, width * height)));
  return [Math.max(1, Math.floor(width * ratio)), Math.max(1, Math.floor(height * ratio))] as const;
}

/** Limit GPU draws while retaining wall-time animation speed on any refresh rate. */
export class FrameLimiter {
  private previous: number | null = null;
  shouldRender(now: number, force = false) {
    const interval = 1000 / BACKGROUND_FPS;
    if (force || this.previous === null) { this.previous = now; return true; }
    const delta = now - this.previous;
    if (delta < interval) return false;
    this.previous = now - delta % interval;
    return true;
  }
  reset() { this.previous = null; }
}

/** Active wall time: slow frames keep recipe speed; hidden time is excluded. */
export class AnimationClock {
  seconds = 0;
  private previous: number | null = null;

  tick(timestamp: number, running: boolean) {
    if (!running) { this.pause(); return this.seconds; }
    if (this.previous !== null) this.seconds += Math.max(0, timestamp - this.previous) / 1000;
    this.previous = timestamp;
    return this.seconds;
  }

  pause() { this.previous = null; }
}
