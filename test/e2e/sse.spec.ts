import { test, expect } from "@playwright/test";
import { expectPricesToChange, openFreshApp } from "./helpers";

const SAMPLE = ["AAPL", "MSFT", "TSLA", "NVDA"];

test.describe("SSE resilience", () => {
  test.beforeEach(async ({ page }) => {
    await openFreshApp(page);
  });

  test("status is green while streaming and recovers after a reload", async ({ page }) => {
    const status = page.getByTestId("connection-status");
    await expect(status).toHaveAttribute("data-status", "open");
    await expectPricesToChange(page, SAMPLE);

    await page.reload();
    await expect(status).toHaveAttribute("data-status", "open", { timeout: 15_000 });
    await expectPricesToChange(page, SAMPLE);
  });

  test("status leaves green when the stream drops and returns when it is back", async ({ page }) => {
    const status = page.getByTestId("connection-status");
    await expect(status).toHaveAttribute("data-status", "open");

    // Block the stream and force EventSource to reconnect by reloading with the route in place.
    await page.route("**/api/stream/prices", (route) => route.abort());
    await page.reload();
    await expect(status).not.toHaveAttribute("data-status", "open", { timeout: 15_000 });

    await page.unroute("**/api/stream/prices");
    // EventSource retries on its own (default ~3s); give it room.
    await expect(status).toHaveAttribute("data-status", "open", { timeout: 30_000 });
    await expectPricesToChange(page, SAMPLE, 15_000);
  });
});
