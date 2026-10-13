import { formatCurrency, formatQuantity } from "./format";
import type { ChatAction } from "./types";

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/**
 * One-line summary of a chat action's outcome, shown inline in the chat (PLAN §8, §10):
 * "Bought 10 AAPL @ $195.03", "Added PYPL to watchlist", "Sell 5 TSLA failed: <error>".
 */
export function describeAction(action: ChatAction): string {
  if (action.type === "trade") {
    const what = `${formatQuantity(action.quantity)} ${action.ticker}`;
    if (action.status === "ok") {
      const verb = action.side === "buy" ? "Bought" : "Sold";
      const price = action.price != null ? ` @ ${formatCurrency(action.price)}` : "";
      return `${verb} ${what}${price}`;
    }
    return `${capitalize(action.side)} ${what} failed: ${action.error ?? "unknown error"}`;
  }

  if (action.status === "ok") {
    return action.action === "add"
      ? `Added ${action.ticker} to watchlist`
      : `Removed ${action.ticker} from watchlist`;
  }
  const preposition = action.action === "add" ? "to" : "from";
  return `${capitalize(action.action)} ${action.ticker} ${preposition} watchlist failed: ${
    action.error ?? "unknown error"
  }`;
}
