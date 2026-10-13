import { describe, expect, it } from "vitest";
import { HEATMAP_LOSS, HEATMAP_NEUTRAL, HEATMAP_PROFIT, pnlColor, pnlIntensity } from "./heatmap";

const rgb = (hex: string) => {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 0xff, (n >> 8) & 0xff, n & 0xff];
};

describe("pnlIntensity", () => {
  it("is 0 at 0% and scales linearly to ±1 at ±10%", () => {
    expect(pnlIntensity(0)).toBe(0);
    expect(pnlIntensity(5)).toBe(0.5);
    expect(pnlIntensity(-2.5)).toBe(-0.25);
    expect(pnlIntensity(10)).toBe(1);
    expect(pnlIntensity(-10)).toBe(-1);
  });

  it("clamps beyond ±10%", () => {
    expect(pnlIntensity(37)).toBe(1);
    expect(pnlIntensity(-99)).toBe(-1);
  });

  it("treats non-finite input as neutral", () => {
    expect(pnlIntensity(NaN)).toBe(0);
    expect(pnlIntensity(Infinity)).toBe(0);
  });
});

describe("pnlColor", () => {
  it("is neutral gray at 0%", () => {
    expect(pnlColor(0)).toBe(HEATMAP_NEUTRAL);
    expect(pnlColor(-0)).toBe(HEATMAP_NEUTRAL);
  });

  it("is full green at +10% and full red at -10%", () => {
    expect(pnlColor(10)).toBe(HEATMAP_PROFIT);
    expect(pnlColor(-10)).toBe(HEATMAP_LOSS);
  });

  it("clamps to full saturation beyond ±10%", () => {
    expect(pnlColor(25)).toBe(HEATMAP_PROFIT);
    expect(pnlColor(-60)).toBe(HEATMAP_LOSS);
  });

  it("blends halfway at ±5%", () => {
    const mid = (a: string, b: string) => rgb(a).map((c, i) => Math.round((c + rgb(b)[i]) / 2));
    expect(rgb(pnlColor(5))).toEqual(mid(HEATMAP_NEUTRAL, HEATMAP_PROFIT));
    expect(rgb(pnlColor(-5))).toEqual(mid(HEATMAP_NEUTRAL, HEATMAP_LOSS));
  });

  it("gets steadily greener as profit grows", () => {
    const green = [1, 3, 6, 9].map((p) => rgb(pnlColor(p))[1]);
    expect(green).toEqual([...green].sort((a, b) => a - b));
    expect(new Set(green).size).toBe(green.length);
  });

  it("returns a #rrggbb string", () => {
    for (const p of [-12, -3.3, 0, 0.01, 7.77, 100]) expect(pnlColor(p)).toMatch(/^#[0-9a-f]{6}$/);
  });
});
