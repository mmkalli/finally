"use client";

import { ChatPanel } from "@/components/ChatPanel";
import { Header } from "@/components/Header";
import { MainChart } from "@/components/MainChart";
import { PnlChart } from "@/components/PnlChart";
import { PortfolioHeatmap } from "@/components/PortfolioHeatmap";
import { PositionsTable } from "@/components/PositionsTable";
import { TradeBar } from "@/components/TradeBar";
import { Watchlist } from "@/components/Watchlist";
import { AppProviders } from "@/lib/store";

// Layout shell (PLAN §10). Each panel lives in its own component file and
// reads shared state from @/lib/store; this file only places them.
export default function Home() {
  return (
    <AppProviders>
      <div className="flex h-screen flex-col overflow-hidden">
        <Header />
        <div className="flex min-h-0 flex-1 gap-2 p-2">
          <main className="grid min-h-0 min-w-0 flex-1 grid-cols-1 gap-2 overflow-y-auto lg:grid-cols-[minmax(280px,1fr)_2fr] lg:grid-rows-[minmax(0,3fr)_minmax(0,2fr)] lg:overflow-hidden">
            <Watchlist className="lg:row-span-2" />
            <div className="flex min-h-0 flex-col gap-2">
              <MainChart className="min-h-64 flex-1" />
              <TradeBar />
            </div>
            <div className="grid min-h-0 grid-cols-1 gap-2 xl:grid-cols-3">
              <PortfolioHeatmap className="min-h-48" />
              <PnlChart className="min-h-48" />
              <PositionsTable className="min-h-48" />
            </div>
          </main>
          <ChatPanel />
        </div>
      </div>
    </AppProviders>
  );
}
