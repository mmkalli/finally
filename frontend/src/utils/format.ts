const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export const fmtUsd = (n: number) => usd.format(n);

/** Price without the currency sign, always 2 dp. */
export const fmtPrice = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const sign = (n: number) => (n > 0 ? "+" : n < 0 ? "−" : "");

export const fmtSignedUsd = (n: number) => sign(n) + usd.format(Math.abs(n));

export const fmtPct = (n: number | null | undefined) => (n == null ? "—" : `${sign(n)}${Math.abs(n).toFixed(2)}%`);

/** Up to 4 dp, trailing zeros dropped (fractional shares). */
export const fmtQty = (n: number) => n.toLocaleString("en-US", { maximumFractionDigits: 4 });

export const fmtClock = (ms: number) =>
  new Date(ms).toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });

/** Text colour class for a signed number. */
export const signClass = (n: number | null | undefined) =>
  n == null || Math.abs(n) < 0.005 ? "text-muted" : n > 0 ? "text-up" : "text-down";
