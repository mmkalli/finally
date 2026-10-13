import { apiTrade, expect, test } from "./fixtures";

// Mirror of the heatmap colour contract (PLAN §10): gray at 0%, full green/red at ±10%, clamped.
const NEUTRAL = [0x4b, 0x55, 0x63];
const PROFIT = [0x16, 0xa3, 0x4a];
const LOSS = [0xdc, 0x26, 0x26];

function expectedFill(pnlPercent: number): string {
  const t = Math.max(-1, Math.min(1, pnlPercent / 10));
  if (t === 0) return "#4b5563";
  const to = t > 0 ? PROFIT : LOSS;
  return (
    "#" +
    NEUTRAL.map((c, i) =>
      Math.round(c + (to[i] - c) * Math.abs(t))
        .toString(16)
        .padStart(2, "0"),
    ).join("")
  );
}

test("heatmap shows one cell per position, coloured by P&L", async ({ app: page, request }) => {
  await expect(page.getByTestId("portfolio-heatmap")).toContainText("No positions");

  await apiTrade(request, { ticker: "AAPL", quantity: 10, side: "buy" });
  await apiTrade(request, { ticker: "TSLA", quantity: 3, side: "buy" });
  await apiTrade(request, { ticker: "JPM", quantity: 1, side: "buy" });
  await page.reload();

  const cells = page.getByTestId("heatmap-cell");
  await expect(cells).toHaveCount(3);
  await expect(page.locator('[data-testid="heatmap-cell"][data-ticker="AAPL"]')).toBeVisible();

  // data-pnl and fill re-render together on every price tick; read them in one go.
  const rendered = await cells.evaluateAll((rects) =>
    rects.map((r) => ({
      ticker: r.getAttribute("data-ticker"),
      pnl: Number(r.getAttribute("data-pnl")),
      fill: r.getAttribute("fill"),
      width: Number(r.getAttribute("width")),
    })),
  );
  for (const cell of rendered) {
    expect(Number.isFinite(cell.pnl), `${cell.ticker} data-pnl`).toBe(true);
    expect(cell.fill, `${cell.ticker} fill`).toBe(expectedFill(cell.pnl));
    expect(cell.width).toBeGreaterThan(0);
  }

  // Positions table lists the same tickers.
  await expect(page.getByTestId("position-row")).toHaveCount(3);
});

test("P&L chart plots portfolio snapshots", async ({ app: page, request }) => {
  await apiTrade(request, { ticker: "NVDA", quantity: 2, side: "buy" });
  await apiTrade(request, { ticker: "NVDA", quantity: 1, side: "sell" });

  // Each trade records a snapshot immediately.
  const history = await (await request.get("/api/portfolio/history")).json();
  expect(history.snapshots.length).toBeGreaterThanOrEqual(2);

  await page.reload();
  const plot = page.getByTestId("pnl-chart-plot");
  await expect(plot).toBeVisible();
  await expect
    .poll(async () => Number(await plot.getAttribute("data-points")))
    .toBeGreaterThanOrEqual(2);
  // A flat line has a zero-height box, which Playwright counts as hidden; check the path instead.
  await expect(plot.locator(".recharts-line-curve")).toHaveAttribute("d", /^M[\d.]+,[\d.]+[CL]/);
});

test("a trade in the UI refreshes the P&L chart", async ({ app: page }) => {
  const plot = page.getByTestId("pnl-chart-plot");
  // The plot only exists once there is at least one snapshot.
  const pointCount = async () =>
    (await plot.count()) ? Number(await plot.getAttribute("data-points")) : 0;
  const before = await pointCount();

  await page.getByTestId("trade-ticker").fill("META");
  await page.getByTestId("trade-quantity").fill("1");
  await page.getByTestId("trade-buy").click();
  await expect(page.getByTestId("trade-status")).toBeVisible();

  // The trade records a snapshot and the chart refetches history, without a reload.
  await expect.poll(pointCount).toBeGreaterThan(before);
  await expect(page.getByTestId("portfolio-heatmap").getByTestId("heatmap-cell")).toHaveCount(1);
});
