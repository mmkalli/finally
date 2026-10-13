// Heatmap colour scale (PLAN §10): neutral gray at 0% P&L, blending linearly
// to full green/red at ±10%, clamped beyond that.

export const HEATMAP_SATURATION_PCT = 10;
export const HEATMAP_NEUTRAL = "#4b5563";
export const HEATMAP_PROFIT = "#16a34a";
export const HEATMAP_LOSS = "#dc2626";

type RGB = [number, number, number];

const hexToRgb = (hex: string): RGB => {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
};

const rgbToHex = (rgb: RGB) =>
  "#" + rgb.map((c) => Math.round(c).toString(16).padStart(2, "0")).join("");

/** Signed intensity in [-1, 1]: pnl_percent scaled by the ±10% saturation point. */
export function pnlIntensity(pnlPercent: number): number {
  if (!Number.isFinite(pnlPercent)) return 0;
  return Math.max(-1, Math.min(1, pnlPercent / HEATMAP_SATURATION_PCT));
}

/** Fill colour (#rrggbb) for a heatmap cell with the given `pnl_percent`. */
export function pnlColor(pnlPercent: number): string {
  const t = pnlIntensity(pnlPercent);
  if (t === 0) return HEATMAP_NEUTRAL;
  const from = hexToRgb(HEATMAP_NEUTRAL);
  const to = hexToRgb(t > 0 ? HEATMAP_PROFIT : HEATMAP_LOSS);
  const k = Math.abs(t);
  return rgbToHex(from.map((c, i) => c + (to[i] - c) * k) as RGB);
}
