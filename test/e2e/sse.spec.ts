import { expect, test, type Page } from "./fixtures";

async function expectPricesMoving(page: Page) {
  const price = page.getByTestId("watchlist-row-MSFT").getByTestId("watchlist-price");
  await expect(price).toHaveText(/^\d[\d,]*\.\d{2}$/);
  const first = await price.innerText();
  await expect.poll(() => price.innerText(), { timeout: 15_000 }).not.toBe(first);
}

test("stream reconnects and prices resume after a reload", async ({ app: page }) => {
  const status = page.getByTestId("connection-status");
  await expect(status).toHaveAttribute("data-status", "open");
  await expectPricesMoving(page);

  await page.reload();
  await expect(status).toHaveAttribute("data-status", "open");
  await expectPricesMoving(page);
});
