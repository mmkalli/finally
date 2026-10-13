/** Price flash (PLAN.md §2): which CSS class to briefly apply when a price changes. */

/** How long the flash class stays on; removing it lets the 500ms CSS background transition fade it out. */
export const FLASH_MS = 300;

export type FlashClass = "flash-up" | "flash-down";

export function flashClassFor(
  prev: number | null | undefined,
  next: number | null | undefined,
): FlashClass | null {
  if (prev == null || next == null || prev === next) return null;
  return next > prev ? "flash-up" : "flash-down";
}
