"use client";

import { useState } from "react";
import { formatCurrency, formatQuantity } from "@/lib/format";
import { useAppState } from "@/lib/store";
import type { TradeSide } from "@/lib/types";
import { Panel } from "./Panel";

type Status = { kind: "ok" | "error"; text: string } | null;

const errorMessage = (e: unknown) => (e instanceof Error ? e.message : String(e));

const inputClass =
  "tabular rounded border border-border bg-background px-2 py-1 text-sm placeholder:text-muted focus:border-primary focus:outline-none";

/** Market-order entry: ticker, quantity, Buy/Sell. Fills instantly; API errors show inline. */
export function TradeBar({ className }: { className?: string }) {
  const { selectedTicker, trade } = useAppState();
  const [ticker, setTicker] = useState(selectedTicker ?? "");
  const [quantity, setQuantity] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<Status>(null);

  // Follow the watchlist selection into the ticker field.
  const [lastSelected, setLastSelected] = useState(selectedTicker);
  if (selectedTicker !== lastSelected) {
    setLastSelected(selectedTicker);
    if (selectedTicker) setTicker(selectedTicker);
  }

  const submit = async (side: TradeSide) => {
    if (busy) return;
    const symbol = ticker.trim().toUpperCase();
    const qty = Number(quantity);
    if (!symbol) {
      setStatus({ kind: "error", text: "Enter a ticker" });
      return;
    }
    if (!quantity.trim() || !Number.isFinite(qty) || qty <= 0) {
      setStatus({ kind: "error", text: "Enter a quantity greater than 0" });
      return;
    }

    setBusy(true);
    try {
      const { trade: fill } = await trade({ ticker: symbol, quantity: qty, side });
      const verb = fill.side === "buy" ? "Bought" : "Sold";
      setStatus({
        kind: "ok",
        text: `${verb} ${formatQuantity(fill.quantity)} ${fill.ticker} @ ${formatCurrency(fill.price)}`,
      });
    } catch (err) {
      setStatus({ kind: "error", text: errorMessage(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title="Trade" className={className} data-testid="trade-bar">
      <form
        onSubmit={(e) => e.preventDefault()}
        className="flex flex-wrap items-center gap-2"
        aria-label="Trade"
      >
        <input
          data-testid="trade-ticker"
          aria-label="Ticker"
          placeholder="Ticker"
          value={ticker}
          onChange={(e) => setTicker(e.target.value.toUpperCase())}
          maxLength={10}
          autoComplete="off"
          spellCheck={false}
          className={`${inputClass} w-24 uppercase placeholder:normal-case`}
        />
        <input
          data-testid="trade-quantity"
          aria-label="Quantity"
          placeholder="Qty"
          type="number"
          inputMode="decimal"
          min="0"
          step="any"
          value={quantity}
          onChange={(e) => setQuantity(e.target.value)}
          className={`${inputClass} w-24`}
        />
        <button
          type="button"
          data-testid="trade-buy"
          disabled={busy}
          onClick={() => submit("buy")}
          className="rounded bg-up/85 px-4 py-1 text-sm font-semibold text-background hover:bg-up disabled:opacity-50"
        >
          Buy
        </button>
        <button
          type="button"
          data-testid="trade-sell"
          disabled={busy}
          onClick={() => submit("sell")}
          className="rounded bg-down/85 px-4 py-1 text-sm font-semibold text-background hover:bg-down disabled:opacity-50"
        >
          Sell
        </button>
        {status && (
          <p
            data-testid={status.kind === "error" ? "trade-error" : "trade-status"}
            role={status.kind === "error" ? "alert" : "status"}
            className={`min-w-0 text-xs ${status.kind === "error" ? "text-down" : "text-up"}`}
          >
            {status.text}
          </p>
        )}
      </form>
    </Panel>
  );
}
