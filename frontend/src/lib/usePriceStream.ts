"use client";

import { useEffect, useRef, useState } from "react";
import type { PriceEvent } from "./types";

/** Header status dot: open → green, connecting → yellow, closed → red (PLAN §10). */
export type ConnectionStatus = "open" | "connecting" | "closed";

/** If the browser gives up (readyState CLOSED), open a fresh EventSource after this delay. */
export const RECONNECT_DELAY_MS = 3000;

// EventSource.CONNECTING / OPEN / CLOSED, inlined so this module loads outside a browser.
export function connectionStatusFromReadyState(readyState: number): ConnectionStatus {
  if (readyState === 1) return "open";
  if (readyState === 0) return "connecting";
  return "closed";
}

/** Parses one SSE `data:` payload; null if it isn't a JSON object. */
export function parsePriceEvent(data: string): PriceEvent | null {
  try {
    const parsed: unknown = JSON.parse(data);
    return parsed && typeof parsed === "object" && !Array.isArray(parsed)
      ? (parsed as PriceEvent)
      : null;
  } catch {
    return null;
  }
}

/**
 * Subscribes to the SSE price stream and calls `onEvent` for every event.
 * EventSource retries transient failures itself (status "connecting"); if it
 * closes for good, this hook reports "closed" and reconnects after a delay.
 */
export function usePriceStream(
  url: string,
  onEvent: (event: PriceEvent) => void,
): ConnectionStatus {
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const onEventRef = useRef(onEvent);

  useEffect(() => {
    onEventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    let source: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = () => {
      const es = new EventSource(url);
      source = es;
      es.onopen = () => setStatus("open");
      es.onmessage = (e: MessageEvent<string>) => {
        const event = parsePriceEvent(e.data);
        if (event) onEventRef.current(event);
      };
      es.onerror = () => {
        const next = connectionStatusFromReadyState(es.readyState);
        setStatus(next);
        if (next === "closed") {
          es.close();
          retryTimer = setTimeout(() => {
            setStatus("connecting");
            connect();
          }, RECONNECT_DELAY_MS);
        }
      };
    };

    connect();
    return () => {
      clearTimeout(retryTimer);
      source?.close();
    };
  }, [url]);

  return status;
}
