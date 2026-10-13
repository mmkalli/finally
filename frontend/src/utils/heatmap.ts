/** Heatmap colour scale (PLAN.md §10): neutral gray at 0%, full saturation at ±10%, clamped beyond. */

export const HEATMAP_NEUTRAL = "#3b4452";
export const HEATMAP_GAIN = "#1f9e5a";
export const HEATMAP_LOSS = "#d2423f";
export const HEATMAP_SATURATION_PCT = 10;

const rgb = (c: string) => [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16));
const toHex = (v: number[]) => "#" + v.map((x) => Math.round(x).toString(16).padStart(2, "0")).join("");

/** Signed intensity in [-1, 1]. */
export function pnlIntensity(pnlPercent: number): number {
  if (!Number.isFinite(pnlPercent)) return 0;
  return Math.max(-1, Math.min(1, pnlPercent / HEATMAP_SATURATION_PCT));
}

export function heatmapColor(pnlPercent: number): string {
  const t = pnlIntensity(pnlPercent);
  if (t === 0) return HEATMAP_NEUTRAL;
  const from = rgb(HEATMAP_NEUTRAL);
  const to = rgb(t > 0 ? HEATMAP_GAIN : HEATMAP_LOSS);
  const k = Math.abs(t);
  return toHex(from.map((v, i) => v + (to[i] - v) * k));
}
