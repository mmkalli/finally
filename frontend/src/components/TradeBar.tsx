"use client";

import { useState, type FormEvent } from "react";
import { fmtPrice, fmtQty } from "@/utils/format";
import type { Trade } from "@/utils/types";

export function TradeBar({
  ticker,
  onTickerChange,
  onTrade,
}: {
  ticker: string;
  onTickerChange: (t: string) => void;
  onTrade: (ticker: string, quantity: number, side: "buy" | "sell") => Promise<{ trade?: Trade; error?: string }>;
}) {
  const [qty, setQty] = useState("1");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [last, setLast] = useState<Trade | null>(null);

  const submit = async (side: "buy" | "sell") => {
    const t = ticker.trim().toUpperCase();
    const q = Number(qty);
    if (!t) return setError("Enter a symbol to trade.");
    if (!qty.trim() || !Number.isFinite(q) || q <= 0) return setError("Enter a quantity greater than 0.");
    setBusy(true);
    const res = await onTrade(t, q, side);
    setBusy(false);
    setError(res.error ?? null);
    setLast(res.trade ?? null);
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit("buy");
  };

  return (
    <form
      onSubmit={onSubmit}
      className="flex flex-wrap items-center gap-2 border border-line bg-panel px-3 py-2"
      aria-label="Market order"
    >
      <span className="text-[12px] font-semibold text-ink">Trade</span>
      <input
        data-testid="trade-ticker"
        aria-label="Symbol"
        value={ticker}
        onChange={(e) => onTickerChange(e.target.value.toUpperCase())}
        placeholder="Symbol"
        maxLength={8}
        className="num w-24 rounded-sm border border-line bg-bg px-2 py-1 text-[12px] uppercase placeholder:normal-case placeholder:text-faint focus:border-primary focus:outline-none"
      />
      <input
        data-testid="trade-quantity"
        aria-label="Quantity"
        type="number"
        inputMode="decimal"
        min="0"
        step="any"
        value={qty}
        onChange={(e) => setQty(e.target.value)}
        placeholder="Qty"
        className="num w-24 rounded-sm border border-line bg-bg px-2 py-1 text-right text-[12px] placeholder:text-faint focus:border-primary focus:outline-none"
      />
      <button
        data-testid="trade-buy"
        type="button"
        disabled={busy}
        onClick={() => submit("buy")}
        className="rounded-sm bg-submit px-4 py-1 text-[12px] font-semibold text-white hover:brightness-125 disabled:opacity-50"
      >
        Buy
      </button>
      <button
        data-testid="trade-sell"
        type="button"
        disabled={busy}
        onClick={() => submit("sell")}
        className="rounded-sm border border-submit px-4 py-1 text-[12px] font-semibold text-ink hover:bg-submit/30 disabled:opacity-50"
      >
        Sell
      </button>
      <span className="text-[11px] text-faint">Market order, fills at the last price</span>
      <div className="ml-auto min-w-0 text-[12px]" aria-live="polite">
        {error ? (
          <span data-testid="trade-error" role="alert" className="text-down">
            {error}
          </span>
        ) : last ? (
          <span data-testid="trade-confirmation" className="num text-muted">
            {last.side === "buy" ? "Bought" : "Sold"} {fmtQty(last.quantity)} {last.ticker} @ {fmtPrice(last.price)}
          </span>
        ) : null}
      </div>
    </form>
  );
}
