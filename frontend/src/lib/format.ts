const usd = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** $1,234.56 */
export const formatCurrency = (n: number) => usd.format(n);

/** 1234.56 with thousands separators, no currency sign. */
export const formatPrice = (n: number) =>
  n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** +1.23% / -1.23% */
export const formatPercent = (n: number) => `${n > 0 ? "+" : ""}${n.toFixed(2)}%`;

/** Up to 4 dp, trailing zeros dropped: 10, 0.5, 1.2345 */
export const formatQuantity = (n: number) =>
  n.toLocaleString("en-US", { maximumFractionDigits: 4 });
