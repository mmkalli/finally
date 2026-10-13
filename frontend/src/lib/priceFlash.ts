"use client";

import { useEffect, useRef, useState } from "react";

/** CSS classes from globals.css; each runs a ~500ms background fade. */
export type FlashClass = "flash-up" | "flash-down";

/** How long the flash class stays applied; matches the keyframe duration. */
export const FLASH_MS = 500;

export interface FlashState {
  /** Class to apply now, or null once the flash has faded. */
  className: FlashClass | null;
  /**
   * Bumped on every flash. Use it as the React `key` of the flashing element,
   * so back-to-back ticks in the same direction restart the animation.
   */
  id: number;
}

export const NO_FLASH: FlashState = { className: null, id: 0 };

/** The flash for a move from `prev` to `next`; null if either is unknown or the price is unchanged. */
export function flashClassFor(
  prev: number | null | undefined,
  next: number | null | undefined,
): FlashClass | null {
  if (prev == null || next == null || next === prev) return null;
  return next > prev ? "flash-up" : "flash-down";
}

/** State after the price moves from `prev` to `next`; unchanged if there is nothing to flash. */
export function nextFlash(
  state: FlashState,
  prev: number | null | undefined,
  next: number | null | undefined,
): FlashState {
  const className = flashClassFor(prev, next);
  return className ? { className, id: state.id + 1 } : state;
}

/**
 * Flashes green/red when `price` rises/falls, clearing the class after
 * FLASH_MS. The first known price never flashes.
 */
export function usePriceFlash(price: number | null | undefined): FlashState {
  const [flash, setFlash] = useState<FlashState>(NO_FLASH);
  const prevPrice = useRef(price);

  useEffect(() => {
    const prev = prevPrice.current;
    prevPrice.current = price;
    if (!flashClassFor(prev, price)) return;
    setFlash((state) => nextFlash(state, prev, price));
    const timer = setTimeout(() => setFlash((state) => ({ ...state, className: null })), FLASH_MS);
    return () => clearTimeout(timer);
  }, [price]);

  return flash;
}
