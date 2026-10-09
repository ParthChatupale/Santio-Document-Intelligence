import type { Rect } from './types.ts';

export interface Viewport {
  width: number; height: number;
  convertToViewportPoint(x: number, y: number): [number, number];
}
export function projectRect(rect: Rect, view: number[], viewport: Viewport) {
  const [x0, y0, x1, y1] = view;
  const first = viewport.convertToViewportPoint(x0 + rect.left * (x1 - x0), y0 + (1 - rect.bottom) * (y1 - y0));
  const second = viewport.convertToViewportPoint(x0 + rect.right * (x1 - x0), y0 + (1 - rect.top) * (y1 - y0));
  return {left: Math.min(first[0], second[0]), top: Math.min(first[1], second[1]),
    width: Math.abs(first[0] - second[0]), height: Math.abs(first[1] - second[1])};
}
