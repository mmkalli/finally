import { test, expect } from "@playwright/test";
import { openFreshApp, parseColor, placeTrade } from "./helpers";

test.describe("Portfolio visualisation", () => {
  test.beforeEach(async ({ page }) => {
    await openFreshApp(page);
  });

  test("heatmap rectangles carry data-pnl and a fill colour matching its sign", async ({ page }) => {
    const tickers = ["AAPL", "NVDA", "TSLA", "META"];
    for (const t of tickers) {
      await placeTrade(page, t, 2, "buy");
      await expect(page.getByTestId(`position-row-${t}`)).toBeVisible();
    }

    const heatmap = page.getByTestId("heatmap");
    await expect(heatmap).toBeVisible();
    const cells = heatmap.locator("[data-pnl]");
    await expect(cells).toHaveCount(tickers.length);

    // The neutral grey isn't pure grey (it can lean blue/green), so near 0% only relative order is
    // meaningful: "greenness" (g - r) must not decrease as P&L increases. From ±1% the sign must show.
    // Sample several times so the colours are checked as live P&L moves.
    for (let i = 0; i < 8; i++) {
      const samples = await cells.evaluateAll((els) =>
        els.map((el) => {
          const shape = el.matches("rect, path") ? el : el.querySelector("rect, path") ?? el;
          const attrFill = shape.getAttribute("fill");
          const fill = attrFill && attrFill !== "none" && !attrFill.startsWith("url(") ? attrFill : getComputedStyle(shape).fill;
          return { pnl: el.getAttribute("data-pnl"), fill };
        }),
      );
      const parsed = samples.map(({ pnl, fill }) => {
        const value = Number(pnl);
        expect(Number.isFinite(value), `data-pnl=${pnl}`).toBe(true);
        const rgb = parseColor(fill ?? "");
        expect(rgb, `unparseable fill ${fill}`).not.toBeNull();
        const [r, g] = rgb!;
        if (value >= 1) expect(g, `pnl ${value} should be green, fill ${fill}`).toBeGreaterThan(r);
        if (value <= -1) expect(r, `pnl ${value} should be red, fill ${fill}`).toBeGreaterThan(g);
        return { value, fill, greenness: g - r };
      });
      for (const a of parsed) {
        for (const b of parsed) {
          if (a.value > b.value + 0.05) {
            expect(a.greenness, `pnl ${a.value} (${a.fill}) vs ${b.value} (${b.fill})`).toBeGreaterThanOrEqual(b.greenness);
          }
        }
      }
      await page.waitForTimeout(600);
    }
  });

  test("P&L chart plots portfolio snapshots", async ({ page }) => {
    await placeTrade(page, "AAPL", 2, "buy");
    await expect(page.getByTestId("position-row-AAPL")).toBeVisible();
    await placeTrade(page, "GOOGL", 2, "buy");
    await expect(page.getByTestId("position-row-GOOGL")).toBeVisible();

    const res = await page.request.get("/api/portfolio/history");
    expect((await res.json()).snapshots.length).toBeGreaterThanOrEqual(2);

    const chart = page.getByTestId("pnl-chart");
    await expect(chart).toBeVisible();
    await expect(chart.locator("svg").first()).toBeVisible();
    // A line with >= 2 points has an "L" segment in its path.
    await expect
      .poll(async () => (await chart.locator("path.recharts-curve, .recharts-line path").first().getAttribute("d")) ?? "")
      .toMatch(/L/);
  });
});
