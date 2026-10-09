export type MotionPreference = 'system' | 'on' | 'off';

export function shouldAnimate(preference: MotionPreference, reduced: boolean) {
  return preference === 'on' || (preference === 'system' && !reduced);
}

/** Decorative backgrounds need no retina buffer; bound work on wide layouts. */
export function artworkResolution(width: number, height: number) {
  const w = Math.max(1, width), h = Math.max(1, height);
  const scale = Math.min(1, Math.sqrt(240_000 / (w * h)));
  return {width: Math.max(1, Math.floor(w * scale)), height: Math.max(1, Math.floor(h * scale))};
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
