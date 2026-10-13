"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { usePriceStore, usePriceStream } from "@/hooks/usePriceStream";
import { ApiError, api } from "@/utils/api";
import { computeLivePortfolio } from "@/utils/portfolio";
import { PriceStore } from "@/utils/priceStore";
import type { Portfolio, Snapshot, WatchlistEntry } from "@/utils/types";
import { ChatPanel, type ChatEntry } from "./ChatPanel";
import { Header } from "./Header";
import { Heatmap } from "./Heatmap";
import { MainChart } from "./MainChart";
import { PnlChart } from "./PnlChart";
import { PositionsTable } from "./PositionsTable";
import { TradeBar } from "./TradeBar";
import { Watchlist } from "./Watchlist";

const errorText = (e: unknown) => (e instanceof Error ? e.message : "Something went wrong.");

/**
 * The single page. Data flow follows PLAN.md §10: portfolio, watchlist and history are fetched on load
 * and replaced only after trades / chat actions / reset; live values come from the SSE store.
 */
export function Workstation() {
  const [store] = useState(() => new PriceStore());
  const status = usePriceStream(store);
  const { latest, history } = usePriceStore(store);

  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [snapshots, setSnapshots] = useState<Snapshot[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [selected, setSelected] = useState<string | null>(null);
  const [tradeTicker, setTradeTicker] = useState("");

  const [chat, setChat] = useState<ChatEntry[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatOpen, setChatOpen] = useState(true);
  const chatId = useRef(0);

  const loadPortfolio = useCallback(() => api.portfolio().then(setPortfolio), []);
  const loadWatchlist = useCallback(() => api.watchlist().then((r) => setWatchlist(r.tickers)), []);
  const loadHistory = useCallback(() => api.history().then((r) => setSnapshots(r.snapshots)), []);

  const loadAll = useCallback(() => {
    setLoadError(null);
    Promise.all([loadPortfolio(), loadWatchlist(), loadHistory()]).catch((e) => setLoadError(errorText(e)));
  }, [loadPortfolio, loadWatchlist, loadHistory]);

  useEffect(loadAll, [loadAll]);

  // Default selection: first watched symbol once the watchlist arrives.
  useEffect(() => {
    if (!selected && watchlist.length) {
      setSelected(watchlist[0].ticker);
      setTradeTicker((t) => t || watchlist[0].ticker);
    }
  }, [selected, watchlist]);

  const select = useCallback((t: string) => {
    setSelected(t);
    setTradeTicker(t);
  }, []);

  const livePortfolio = useMemo(() => {
    if (!portfolio) return null;
    const prices: Record<string, number> = {};
    for (const [t, u] of Object.entries(latest)) prices[t] = u.price;
    return computeLivePortfolio(portfolio, prices);
  }, [portfolio, latest]);

  const trade = useCallback(
    async (ticker: string, quantity: number, side: "buy" | "sell") => {
      try {
        const res = await api.trade(ticker, quantity, side);
        setPortfolio(res.portfolio);
        loadHistory().catch(() => {});
        return { trade: res.trade };
      } catch (e) {
        return { error: errorText(e) };
      }
    },
    [loadHistory],
  );

  const addTicker = useCallback(
    async (ticker: string) => {
      try {
        await api.addTicker(ticker);
        await loadWatchlist();
        select(ticker);
        return null;
      } catch (e) {
        return errorText(e);
      }
    },
    [loadWatchlist, select],
  );

  const removeTicker = useCallback(
    async (ticker: string) => {
      try {
        await api.removeTicker(ticker);
        await loadWatchlist();
        return null;
      } catch (e) {
        if (e instanceof ApiError && e.code === "NOT_FOUND") {
          await loadWatchlist().catch(() => {});
          return null;
        }
        return errorText(e);
      }
    },
    [loadWatchlist],
  );

  const sendChat = useCallback(
    async (text: string) => {
      setChat((c) => [...c, { id: ++chatId.current, role: "user", content: text }]);
      setChatLoading(true);
      try {
        const res = await api.chat(text);
        setChat((c) => [
          ...c,
          { id: ++chatId.current, role: "assistant", content: res.message, actions: res.actions ?? [] },
        ]);
        const ok = (res.actions ?? []).filter((a) => a.status === "ok");
        const refreshes: Promise<unknown>[] = [];
        if (ok.length) refreshes.push(loadPortfolio());
        if (ok.some((a) => a.type === "trade")) refreshes.push(loadHistory());
        if (ok.some((a) => a.type === "watchlist")) refreshes.push(loadWatchlist());
        await Promise.all(refreshes).catch(() => {});
      } catch (e) {
        setChat((c) => [
          ...c,
          { id: ++chatId.current, role: "assistant", content: `Message not sent: ${errorText(e)}`, failed: true },
        ]);
      } finally {
        setChatLoading(false);
      }
    },
    [loadPortfolio, loadHistory, loadWatchlist],
  );

  const reset = useCallback(async () => {
    if (!window.confirm("Reset the account to $10,000 cash and the default watchlist? Positions, trades and chat are cleared.")) return;
    try {
      setPortfolio(await api.reset());
      setChat([]);
      setSelected(null);
      setTradeTicker("");
      await Promise.all([loadWatchlist(), loadHistory()]);
    } catch (e) {
      setLoadError(errorText(e));
    }
  }, [loadWatchlist, loadHistory]);

  return (
    <div className="flex min-h-screen flex-col lg:h-screen">
      <Header portfolio={livePortfolio} status={status} onReset={reset} />

      {loadError && (
        <div role="alert" className="flex items-center gap-3 border-b border-down/40 bg-down/10 px-4 py-1.5 text-[12px] text-down">
          <span>Couldn&apos;t load your account: {loadError}</span>
          <button type="button" onClick={loadAll} className="rounded-sm border border-down/50 px-2 py-0.5 hover:bg-down/20">
            Retry
          </button>
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <main className="grid min-h-0 min-w-0 flex-1 gap-1 p-1 md:grid-cols-[minmax(260px,300px)_1fr]">
          <div className="h-[420px] min-h-0 md:h-auto">
            <Watchlist
              entries={watchlist}
              prices={latest}
              history={history}
              selected={selected}
              onSelect={select}
              onAdd={addTicker}
              onRemove={removeTicker}
            />
          </div>

          <div className="flex min-h-0 min-w-0 flex-col gap-1">
            <div className="h-[300px] min-h-[220px] lg:h-auto lg:flex-[1.25]">
              <MainChart
                ticker={selected}
                points={selected ? history[selected] : undefined}
                latest={selected ? latest[selected] : undefined}
              />
            </div>
            <TradeBar ticker={tradeTicker} onTickerChange={setTradeTicker} onTrade={trade} />
            <div className="grid min-h-0 gap-1 sm:grid-cols-2 lg:flex-1">
              <div className="h-[240px] min-h-[180px] sm:h-auto">
                <Heatmap positions={livePortfolio?.positions ?? []} />
              </div>
              <div className="h-[240px] min-h-[180px] sm:h-auto">
                <PnlChart snapshots={snapshots} />
              </div>
            </div>
            <div className="h-[220px] min-h-[140px] lg:h-auto lg:flex-[0.8]">
              <PositionsTable positions={livePortfolio?.positions ?? []} onSelect={select} />
            </div>
          </div>
        </main>

        <div className="h-[520px] lg:h-auto lg:min-h-0 [&>aside]:h-full">
          <ChatPanel
            messages={chat}
            loading={chatLoading}
            open={chatOpen}
            onToggle={() => setChatOpen((o) => !o)}
            onSend={sendChat}
          />
        </div>
      </div>
    </div>
  );
}
