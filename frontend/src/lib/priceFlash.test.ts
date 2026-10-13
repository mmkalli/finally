import { describe, expect, it } from "vitest";
import { flashClassFor, nextFlash, NO_FLASH } from "./priceFlash";

describe("flashClassFor", () => {
  it("flashes green on an uptick", () => {
    expect(flashClassFor(190, 190.05)).toBe("flash-up");
  });

  it("flashes red on a downtick", () => {
    expect(flashClassFor(190, 189.95)).toBe("flash-down");
  });

  it("does not flash when the price is unchanged", () => {
    expect(flashClassFor(190, 190)).toBeNull();
  });

  it("does not flash for the first known price", () => {
    expect(flashClassFor(undefined, 190)).toBeNull();
    expect(flashClassFor(null, 190)).toBeNull();
  });

  it("does not flash when the price becomes unknown", () => {
    expect(flashClassFor(190, null)).toBeNull();
  });
});

describe("nextFlash", () => {
  it("applies the class and bumps the id on a change", () => {
    expect(nextFlash(NO_FLASH, 100, 101)).toEqual({ className: "flash-up", id: 1 });
    expect(nextFlash(NO_FLASH, 100, 99)).toEqual({ className: "flash-down", id: 1 });
  });

  it("bumps the id on consecutive ticks in the same direction, restarting the animation", () => {
    const first = nextFlash(NO_FLASH, 100, 101);
    const second = nextFlash(first, 101, 102);
    expect(second).toEqual({ className: "flash-up", id: 2 });
  });

  it("switches class when the direction reverses", () => {
    const up = nextFlash(NO_FLASH, 100, 101);
    expect(nextFlash(up, 101, 100.5)).toEqual({ className: "flash-down", id: 2 });
  });

  it("returns the same state when nothing changed", () => {
    const state = { className: null, id: 3 } as const;
    expect(nextFlash(state, 100, 100)).toBe(state);
    expect(nextFlash(state, undefined, 100)).toBe(state);
  });
});
