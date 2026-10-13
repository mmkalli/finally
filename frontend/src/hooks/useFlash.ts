"use client";

import { useEffect, useRef, useState } from "react";
import { FLASH_MS, flashClassFor, type FlashClass } from "@/utils/flash";

/** Returns a flash class briefly after `price` moves; the CSS transition then fades it out. */
export function useFlash(price: number | null | undefined): FlashClass | null {
  const prev = useRef(price);
  const [cls, setCls] = useState<FlashClass | null>(null);

  useEffect(() => {
    const next = flashClassFor(prev.current, price);
    prev.current = price;
    if (!next) return;
    setCls(next);
    const t = setTimeout(() => setCls(null), FLASH_MS);
    return () => clearTimeout(t);
  }, [price]);

  return cls;
}
