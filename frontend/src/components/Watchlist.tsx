"use client";

import { useState, type FormEvent } from "react";
import { useFlash } from "@/hooks/useFlash";
import { fmtPct, fmtPrice, signClass } from "@/utils/format";
import type { PricePoint } from "@/utils/priceStore";
import type { PriceMap, WatchlistEntry } from "@/utils/types";
import { Panel } from "./Panel";
import { Sparkline } from "./Sparkline";

export function Watchlist({
  entries,
  prices,
  history,
  selected,
  onSelect,
  onAdd,
  onRemove,
}: {
  entries: WatchlistEntry[];
  prices: PriceMap;
  history: Record<string, PricePoint[]>;
  selected: string | null;
  onSelect: (ticker: string) => void;
  onAdd: (ticker: string) => Promise<string | null>;
  onRemove: (ticker: string) => Promise<string | null>;
}) {
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const t = input.trim().toUpperCase();
    if (!t) return;
    setBusy(true);
    const err = await onAdd(t);
    setBusy(false);
    setError(err);
    if (!err) setInput("");
  };

  const remove = async (t: string) => setError(await onRemove(t));

  return (
    <Panel title="Watchlist" aside={<span className="num">{entries.length}</span>} bodyClassName="flex flex-col">
      <div className="grid grid-cols-[1fr_auto_auto] gap-x-3 border-b border-line px-3 py-1 text-[10px] text-faint">
        <span>Symbol</span>
        <span className="w-[84px] text-right">Last / chg</span>
        <span className="w-[84px] text-right">Since load</span>
      </div>
      <ul className="min-h-0 flex-1 overflow-y-auto">
        {entries.map((e) => (
          <Row
            key={e.ticker}
            entry={e}
            live={prices[e.ticker]}
            points={history[e.ticker]}
            selected={selected === e.ticker}
            onSelect={onSelect}
            onRemove={remove}
          />
        ))}
        {entries.length === 0 && (
          <li className="p-4 text-center text-[12px] text-muted">Add a symbol below to start watching it.</li>
        )}
      </ul>
      <form onSubmit={submit} className="shrink-0 border-t border-line p-2">
        <div className="flex gap-1">
          <input
            data-testid="watchlist-add-input"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Add symbol, e.g. PYPL"
            aria-label="Symbol to add"
            maxLength={8}
            className="num min-w-0 flex-1 rounded-sm border border-line bg-bg px-2 py-1 text-[12px] uppercase placeholder:normal-case placeholder:text-faint focus:border-primary focus:outline-none"
          />
          <button
            data-testid="watchlist-add-button"
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-sm bg-primary px-3 py-1 text-[12px] font-medium text-white hover:brightness-110 disabled:opacity-40"
          >
            Add
          </button>
        </div>
        {error && (
          <p data-testid="watchlist-error" className="mt-1 text-[11px] text-down" role="alert">
            {error}
          </p>
        )}
      </form>
    </Panel>
  );
}

function Row({
  entry,
  live,
  points,
  selected,
  onSelect,
  onRemove,
}: {
  entry: WatchlistEntry;
  live: PriceMap[string] | undefined;
  points: PricePoint[] | undefined;
  selected: boolean;
  onSelect: (t: string) => void;
  onRemove: (t: string) => void;
}) {
  const price = live?.price ?? entry.price;
  const change = live?.change_percent ?? entry.change_percent;
  const flash = useFlash(price);
  const t = entry.ticker;

  return (
    <li
      data-testid={`watchlist-row-${t}`}
      aria-selected={selected}
      onClick={() => onSelect(t)}
      className={`group relative grid cursor-pointer grid-cols-[1fr_auto_auto] items-center gap-x-3 border-b border-line/60 py-1.5 pl-3 pr-3 hover:bg-raised ${
        selected ? "bg-raised" : ""
      }`}
    >
      {selected && <span className="absolute inset-y-0 left-0 w-[3px] bg-accent" aria-hidden />}
      <div className="flex min-w-0 items-center gap-1">
        <button
          type="button"
          className="truncate text-left text-[13px] font-semibold text-ink focus-visible:outline-offset-2"
          onClick={(ev) => {
            ev.stopPropagation();
            onSelect(t);
          }}
        >
          {t}
        </button>
        <button
          type="button"
          data-testid={`watchlist-remove-${t}`}
          aria-label={`Remove ${t} from watchlist`}
          title={`Remove ${t}`}
          onClick={(ev) => {
            ev.stopPropagation();
            onRemove(t);
          }}
          className="ml-auto h-5 w-5 shrink-0 rounded-sm text-[14px] leading-none text-faint opacity-40 hover:bg-line hover:text-down focus-visible:opacity-100 group-hover:opacity-100"
        >
          ×
        </button>
      </div>
      <div className="w-[84px] text-right leading-tight">
        <div data-testid={`price-${t}`} className={`num flash-cell rounded-sm px-1 text-[13px] text-ink ${flash ?? ""}`}>
          {fmtPrice(price)}
        </div>
        <div className={`num px-1 text-[11px] ${signClass(change)}`}>{fmtPct(change)}</div>
      </div>
      <Sparkline points={points} />
    </li>
  );
}
