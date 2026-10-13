"use client";

import { useState, type FormEvent } from "react";
import { formatPercent, formatPrice } from "@/lib/format";
import { usePriceFlash } from "@/lib/priceFlash";
import { useAppState, useLiveWatchlist } from "@/lib/store";
import type { WatchlistEntry } from "@/lib/types";
import { Panel } from "./Panel";
import { Sparkline } from "./Sparkline";

const errorMessage = (e: unknown) => (e instanceof Error ? e.message : String(e));

function changeColor(change: number | null): string {
  if (change == null || change === 0) return "text-flat";
  return change > 0 ? "text-up" : "text-down";
}

function WatchlistRow({
  entry,
  selected,
  onSelect,
  onRemove,
}: {
  entry: WatchlistEntry;
  selected: boolean;
  onSelect: (ticker: string) => void;
  onRemove: (ticker: string) => void;
}) {
  const { ticker, price, change_percent } = entry;
  const flash = usePriceFlash(price);

  return (
    <tr
      data-testid={`watchlist-row-${ticker}`}
      data-ticker={ticker}
      aria-selected={selected}
      tabIndex={0}
      onClick={() => onSelect(ticker)}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(ticker);
        }
      }}
      className={`group cursor-pointer border-b border-border/50 outline-none hover:bg-surface-raised focus-visible:bg-surface-raised ${
        selected ? "bg-surface-raised shadow-[inset_2px_0_0_var(--color-accent)]" : ""
      }`}
    >
      <td className="py-1 pr-2 pl-2 font-semibold">{ticker}</td>
      <td
        key={flash.id}
        data-testid="watchlist-price"
        className={`tabular rounded-sm px-1 py-1 text-right ${flash.className ?? ""}`}
      >
        {price == null ? "—" : formatPrice(price)}
      </td>
      <td
        data-testid="watchlist-change"
        className={`tabular px-1 py-1 text-right ${changeColor(change_percent)}`}
      >
        {change_percent == null ? "—" : formatPercent(change_percent)}
      </td>
      <td className="px-1 py-1">
        <Sparkline ticker={ticker} />
      </td>
      <td className="py-1 pr-1 text-right">
        <button
          type="button"
          data-testid={`watchlist-remove-${ticker}`}
          aria-label={`Remove ${ticker} from watchlist`}
          title={`Remove ${ticker}`}
          onClick={(e) => {
            e.stopPropagation();
            onRemove(ticker);
          }}
          className="px-1 text-muted opacity-0 group-hover:opacity-100 group-focus-visible:opacity-100 hover:text-down focus-visible:opacity-100"
        >
          ×
        </button>
      </td>
    </tr>
  );
}

function AddTickerForm({ onError }: { onError: (message: string | null) => void }) {
  const { addTicker, selectTicker } = useAppState();
  const [ticker, setTicker] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const symbol = ticker.trim().toUpperCase();
    if (!symbol || busy) return;
    setBusy(true);
    try {
      await addTicker(symbol);
      setTicker("");
      onError(null);
      selectTicker(symbol);
    } catch (err) {
      onError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="flex gap-1">
      <input
        data-testid="watchlist-add-input"
        aria-label="Ticker to add"
        placeholder="Add ticker"
        value={ticker}
        onChange={(e) => setTicker(e.target.value.toUpperCase())}
        maxLength={10}
        autoComplete="off"
        spellCheck={false}
        className="tabular min-w-0 flex-1 rounded border border-border bg-background px-2 py-1 text-sm uppercase placeholder:normal-case placeholder:text-muted focus:border-primary focus:outline-none"
      />
      <button
        type="submit"
        data-testid="watchlist-add-button"
        disabled={busy || !ticker.trim()}
        className="rounded bg-secondary px-3 py-1 text-sm font-semibold hover:brightness-125 disabled:opacity-50"
      >
        Add
      </button>
    </form>
  );
}

export function Watchlist({ className }: { className?: string }) {
  const watchlist = useLiveWatchlist();
  const { selectedTicker, selectTicker, removeTicker } = useAppState();
  const [error, setError] = useState<string | null>(null);

  const remove = async (ticker: string) => {
    try {
      await removeTicker(ticker);
      setError(null);
      if (ticker === selectedTicker) {
        const next = watchlist.find((entry) => entry.ticker !== ticker);
        if (next) selectTicker(next.ticker);
      }
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <Panel
      title="Watchlist"
      className={className}
      data-testid="watchlist"
      bodyClassName="flex min-h-0 flex-1 flex-col"
    >
      <div className="min-h-0 flex-1 overflow-auto">
        <table className="w-full border-collapse text-sm">
          <thead className="sticky top-0 bg-surface text-xs text-muted">
            <tr className="border-b border-border">
              <th className="py-1 pl-2 text-left font-normal">Ticker</th>
              <th className="px-1 py-1 text-right font-normal">Price</th>
              <th className="px-1 py-1 text-right font-normal">Chg %</th>
              <th className="px-1 py-1 font-normal">
                <span className="sr-only">Sparkline</span>
              </th>
              <th className="py-1 pr-1">
                <span className="sr-only">Remove</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {watchlist.map((entry) => (
              <WatchlistRow
                key={entry.ticker}
                entry={entry}
                selected={entry.ticker === selectedTicker}
                onSelect={selectTicker}
                onRemove={remove}
              />
            ))}
          </tbody>
        </table>
        {watchlist.length === 0 && (
          <p className="p-4 text-center text-sm text-muted">No tickers watched</p>
        )}
      </div>
      <div className="shrink-0 border-t border-border p-2">
        <AddTickerForm onError={setError} />
        {error && (
          <p data-testid="watchlist-error" role="alert" className="mt-1 text-xs text-down">
            {error}
          </p>
        )}
      </div>
    </Panel>
  );
}
