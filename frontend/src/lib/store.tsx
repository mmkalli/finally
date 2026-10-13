"use client";

// Shared client state (PLAN §10 "Data Flow"). Two contexts so that the
// 500ms price ticks only re-render components that read live prices:
//   - MarketContext: latest SSE prices, connection status, price history
//   - AppContext: portfolio, watchlist, P&L snapshots, selection, actions

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { api, PRICE_STREAM_URL } from "./api";
import { computeLivePortfolio } from "./portfolio";
import { PriceHistoryStore, type PricePoint } from "./priceHistory";
import type {
  ChatResponse,
  Portfolio,
  PortfolioSnapshot,
  PriceEvent,
  PriceUpdate,
  TradeRequest,
  TradeResponse,
  WatchlistEntry,
} from "./types";
import { usePriceStream, type ConnectionStatus } from "./usePriceStream";

// ---------------------------------------------------------------- market

interface MarketState {
  /** Latest update per ticker, merged from every SSE event since page load. */
  prices: Record<string, PriceUpdate>;
  connection: ConnectionStatus;
  history: PriceHistoryStore;
}

const MarketContext = createContext<MarketState | null>(null);

function MarketProvider({ children }: { children: ReactNode }) {
  const [history] = useState(() => new PriceHistoryStore());
  const [prices, setPrices] = useState<Record<string, PriceUpdate>>({});

  const onEvent = useCallback(
    (event: PriceEvent) => {
      history.append(event);
      setPrices((prev) => ({ ...prev, ...event }));
    },
    [history],
  );
  const connection = usePriceStream(PRICE_STREAM_URL, onEvent);

  const value = useMemo(() => ({ prices, connection, history }), [prices, connection, history]);
  return <MarketContext.Provider value={value}>{children}</MarketContext.Provider>;
}

export function useMarket(): MarketState {
  const ctx = useContext(MarketContext);
  if (!ctx) throw new Error("useMarket must be used inside <AppProviders>");
  return ctx;
}

const NO_POINTS: readonly PricePoint[] = [];

/** Price history for one ticker since page load; re-renders only when that ticker updates. */
export function usePriceHistory(ticker: string | null): readonly PricePoint[] {
  const { history } = useMarket();
  return useSyncExternalStore(
    history.subscribe,
    () => (ticker ? history.get(ticker) : NO_POINTS),
    () => NO_POINTS,
  );
}

// ---------------------------------------------------------------- app

interface AppState {
  /** Last `/api/portfolio` (or trade/reset) response; null until loaded. */
  portfolio: Portfolio | null;
  watchlist: WatchlistEntry[];
  snapshots: PortfolioSnapshot[];
  /** Ticker shown in the main chart; defaults to the first watched ticker. */
  selectedTicker: string | null;
  selectTicker: (ticker: string) => void;
  /** Message from the most recent failed refresh, if any. */
  loadError: string | null;
  /** Bumped after each reset, so panels with local state (chat) can clear it. */
  resetCount: number;

  refreshPortfolio: () => Promise<void>;
  refreshWatchlist: () => Promise<void>;
  refreshHistory: () => Promise<void>;

  /** Executes a trade and applies the returned portfolio. Throws ApiError on rejection. */
  trade: (req: TradeRequest) => Promise<TradeResponse>;
  /** Throws ApiError on rejection. */
  addTicker: (ticker: string) => Promise<void>;
  /** Throws ApiError on rejection. */
  removeTicker: (ticker: string) => Promise<void>;
  /** Sends a chat message and refetches whatever its `ok` actions changed. */
  sendChat: (message: string) => Promise<ChatResponse>;
  reset: () => Promise<void>;
}

const AppContext = createContext<AppState | null>(null);

const errorMessage = (e: unknown) => (e instanceof Error ? e.message : String(e));

function AppStateProvider({ children }: { children: ReactNode }) {
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [watchlist, setWatchlist] = useState<WatchlistEntry[]>([]);
  const [snapshots, setSnapshots] = useState<PortfolioSnapshot[]>([]);
  const [chosenTicker, setChosenTicker] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [resetCount, setResetCount] = useState(0);

  // Refreshes record failures in loadError rather than throwing, so callers can fire and forget.
  const refreshPortfolio = useCallback(async () => {
    try {
      setPortfolio(await api.getPortfolio());
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }, []);

  const refreshWatchlist = useCallback(async () => {
    try {
      setWatchlist((await api.getWatchlist()).tickers);
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }, []);

  const refreshHistory = useCallback(async () => {
    try {
      setSnapshots((await api.getPortfolioHistory()).snapshots);
    } catch (e) {
      setLoadError(errorMessage(e));
    }
  }, []);

  useEffect(() => {
    void Promise.all([refreshPortfolio(), refreshWatchlist(), refreshHistory()]);
  }, [refreshPortfolio, refreshWatchlist, refreshHistory]);

  const trade = useCallback(
    async (req: TradeRequest) => {
      const res = await api.trade(req);
      setPortfolio(res.portfolio);
      void refreshHistory();
      return res;
    },
    [refreshHistory],
  );

  const addTicker = useCallback(
    async (ticker: string) => {
      await api.addToWatchlist(ticker);
      await refreshWatchlist();
    },
    [refreshWatchlist],
  );

  const removeTicker = useCallback(
    async (ticker: string) => {
      await api.removeFromWatchlist(ticker);
      await refreshWatchlist();
    },
    [refreshWatchlist],
  );

  const sendChat = useCallback(
    async (message: string) => {
      const res = await api.chat(message);
      const ok = res.actions.filter((a) => a.status === "ok");
      if (ok.some((a) => a.type === "trade")) {
        void refreshPortfolio();
        void refreshHistory();
      }
      if (ok.some((a) => a.type === "watchlist")) void refreshWatchlist();
      return res;
    },
    [refreshPortfolio, refreshWatchlist, refreshHistory],
  );

  const reset = useCallback(async () => {
    setPortfolio(await api.reset());
    setChosenTicker(null);
    setResetCount((n) => n + 1);
    await Promise.all([refreshWatchlist(), refreshHistory()]);
  }, [refreshWatchlist, refreshHistory]);

  const selectedTicker = chosenTicker ?? watchlist[0]?.ticker ?? null;

  const value = useMemo<AppState>(
    () => ({
      portfolio,
      watchlist,
      snapshots,
      selectedTicker,
      selectTicker: setChosenTicker,
      loadError,
      resetCount,
      refreshPortfolio,
      refreshWatchlist,
      refreshHistory,
      trade,
      addTicker,
      removeTicker,
      sendChat,
      reset,
    }),
    [
      portfolio,
      watchlist,
      snapshots,
      selectedTicker,
      loadError,
      resetCount,
      refreshPortfolio,
      refreshWatchlist,
      refreshHistory,
      trade,
      addTicker,
      removeTicker,
      sendChat,
      reset,
    ],
  );
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useAppState(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useAppState must be used inside <AppProviders>");
  return ctx;
}

// ---------------------------------------------------------------- derived

/** The portfolio re-valued at live SSE prices (header total, positions table, heatmap). */
export function useLivePortfolio(): Portfolio | null {
  const { portfolio } = useAppState();
  const { prices } = useMarket();
  return useMemo(
    () => (portfolio ? computeLivePortfolio(portfolio, prices) : null),
    [portfolio, prices],
  );
}

/** Watchlist entries with price fields overlaid from the live SSE stream. */
export function useLiveWatchlist(): WatchlistEntry[] {
  const { watchlist } = useAppState();
  const { prices } = useMarket();
  return useMemo(
    () => watchlist.map((entry) => ({ ...entry, ...prices[entry.ticker] })),
    [watchlist, prices],
  );
}

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <MarketProvider>
      <AppStateProvider>{children}</AppStateProvider>
    </MarketProvider>
  );
}
