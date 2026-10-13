"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import type { PriceStore } from "@/utils/priceStore";
import type { ConnectionStatus, PriceMap } from "@/utils/types";

const STATUS: Record<number, ConnectionStatus> = { 0: "connecting", 1: "open", 2: "closed" };

/**
 * Connects to `/api/stream/prices` and feeds the store. The status maps EventSource.readyState
 * to the header dot (PLAN.md §10). EventSource retries on its own while CONNECTING; if the browser
 * gives up (CLOSED) we open a fresh one after a short pause.
 */
export function usePriceStream(store: PriceStore): ConnectionStatus {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");

  useEffect(() => {
    let es: EventSource | null = null;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let disposed = false;

    const sync = () => es && setStatus(STATUS[es.readyState] ?? "closed");

    const connect = () => {
      es = new EventSource("/api/stream/prices");
      sync();
      es.onopen = sync;
      es.onmessage = (ev) => {
        try {
          store.apply(JSON.parse(ev.data) as PriceMap);
        } catch {
          // ignore malformed frames
        }
        sync();
      };
      es.onerror = () => {
        sync();
        if (es?.readyState === EventSource.CLOSED && !disposed) {
          es.close();
          retry = setTimeout(connect, 3000);
        }
      };
    };

    connect();
    // readyState changes don't all raise events; keep the dot honest.
    const poll = setInterval(sync, 1000);
    return () => {
      disposed = true;
      clearInterval(poll);
      clearTimeout(retry);
      es?.close();
    };
  }, [store]);

  return status;
}

/** Re-render on every store update. */
export function usePriceStore(store: PriceStore): PriceStore {
  useSyncExternalStore(store.subscribe, store.getVersion, store.getVersion);
  return store;
}
