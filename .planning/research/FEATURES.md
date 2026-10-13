# Feature Research

**Domain:** AI-assisted simulated trading workstation (Bloomberg-style terminal + LLM copilot), capstone demo
**Researched:** 2026-10-13
**Confidence:** MEDIUM. Based on established trading-UI conventions (Bloomberg, TradingView, Robinhood, Finviz heatmaps, ChatGPT-style tool-call UX) and the locked PLAN.md. No live web verification; conventions are well-established but exact values (timings, thresholds) are recommendations, not standards.

**Scope note:** PLAN.md is a locked contract. This file does not propose new features. It specifies the behaviour details users take for granted inside the spec's features, and flags what to skip.

## Feature Landscape

### Table Stakes (must be polished for the demo)

| Feature | Behaviour users take for granted | Complexity | Notes |
|---------|----------------------------------|------------|-------|
| Price flash on tick | Green background on uptick, red on downtick, fade ~500ms. Flash only when price actually changed (`direction` up/down; none for `flat`). A new tick during an active flash must restart the animation, not stack | LOW | Re-trigger by toggling class via a key/ref or `animation` restart, not setState timers per cell. Apply to the price cell only, not the whole row. Respect `prefers-reduced-motion` (optional) |
| Number formatting | Prices 2dp with thousands separators; `+`/`-` sign on change and P&L; `%` 2dp; cash/total as `$10,000.00`; quantities up to 4dp, trimmed trailing zeros; negatives red, positives green, zero neutral gray. Right-aligned, tabular-nums (monospace digits) so columns do not jitter | LOW | One shared `format.ts`. `font-variant-numeric: tabular-nums` is the cheapest big polish win. Use Intl.NumberFormat |
| Watchlist row | Ticker, price, change %, sparkline; hover state; selected-row highlight (accent yellow/blue); click selects for main chart; remove (x) control on hover | LOW-MED | Selected ticker defaults to first watchlist ticker on load so main chart is never empty |
| Empty / loading states | Before first SSE event: skeleton or `--` placeholders, not `NaN`/`$0.00`. Price fields `null` for unpriced ticker render `--`. Sparkline with <2 points shows flat/empty baseline, with a "collecting..." hint on main chart. Positions empty: "No positions yet. Buy a ticker or ask the AI." Heatmap empty: same message. P&L chart with 1 snapshot: render the single point and a flat line, not blank | MED | Highest-risk area for a first-launch demo: everything is empty at t=0. Seed one snapshot at startup (backend) so P&L chart is never blank |
| Connection status dot | Green/yellow/red per EventSource readyState with tooltip text (Live / Reconnecting / Disconnected). Stale data should not look live: dim prices when not OPEN | LOW | Mapped from `readyState` per spec |
| Header live totals | Total value, cash, optionally day/total P&L, updating every tick with no layout shift (fixed-width tabular numerals) | LOW | Computed client-side from last portfolio + SSE prices per spec |
| Main chart | Selected ticker price line, axis with price labels, tooltip on hover, ticker + current price + change % title, colour by net direction since load. Handles switching ticker instantly (history store is per-ticker) | MED | Recharts LineChart/AreaChart; disable animation (`isAnimationActive={false}`) or streaming ticks will visibly re-animate every 500ms. Cap points per ticker (e.g. 600-1000) to bound memory |
| Sparklines | Tiny, no axes, no tooltip, fixed width, colour by direction; no animation | LOW | Same animation caveat. Fills progressively; that is expected and is part of the demo charm |
| Trade bar | Ticker + qty inputs, Buy/Sell buttons; Enter submits; ticker auto-uppercases; clicking a watchlist row pre-fills ticker; inputs keep ticker after trade and clear qty; button disabled while request in flight (prevents double-fill); inline error text from API `error` field next to bar; brief success feedback (e.g. "Bought 10 AAPL @ $195.03") that auto-clears | LOW-MED | No confirmation dialog (spec). Success toast/inline line is table stakes because instant fill with no feedback feels broken. Errors keyed off `code` for friendlier text if desired but spec message is sufficient |
| Positions table | Ticker, qty, avg cost, current price, unrealized P&L ($), P&L %; P&L coloured; sorted stable (by market value desc or ticker); updates live without reorder jitter; row click selects ticker in chart | LOW | Live values recomputed client-side; fall back to avg_cost price if no cache price (spec) |
| Portfolio heatmap (treemap) | Rectangles sized by market value, colour scale gray (0%) to full green/red at +-10% clamped, ticker + P&L % label inside rectangle (hidden if rectangle too small), `data-pnl` attribute, smooth colour not abrupt | MED | Recharts Treemap with custom content renderer (needed for colour, label, `data-pnl`). Treemap needs positive values; filter zero-value. Disable animation. Single position still renders full area |
| P&L chart | Total value line over time from snapshots, time axis, tooltip, reference line at $10,000 start, refetched after trades | LOW-MED | Reference line at starting cash gives instant read of up/down; cheap |
| AI chat panel | Docked sidebar, collapsible; user right-aligned/assistant left-aligned bubbles; auto-scroll to newest; Enter sends, Shift+Enter newline; input disabled and typing/loading indicator while waiting; error bubble on network failure; history restored on reload | MED | History on reload needs a way to load chat messages. PLAN.md defines no GET chat endpoint, so either keep chat session-local (state lost on reload) or ask for a minimal addition. Flag as open question, do not silently add |
| Inline action results in chat | Each action in `actions` renders under the assistant message as a compact card/chip: trade ok = green check "Bought 10 AAPL @ $195.03"; watchlist ok = "Added PYPL to watchlist"; error = red x with the API error message. Order preserved; one failure does not hide successes | MED | This is the "wow" moment. Because the LLM message is written before execution (spec), the UI must treat `actions` as truth and visually separate them from the prose |
| Post-action refresh | After trade/chat-with-ok-actions/reset: portfolio replaced, watchlist refetched, P&L history refetched; positions and heatmap update immediately | LOW | Spec'd data-flow; make it one shared `refreshAll()` |
| Chat unconfigured / error messaging | No API key returns 200 with a message and empty actions: render as normal assistant message. Mock mode responses render identically | LOW | Nothing special in the UI beyond not treating it as an error |
| Layout and theme | Dense grid, dark `#0d1117`, borders muted gray, accent colours per spec, no page scroll on desktop (panels scroll internally), min viable at tablet width | MED | Layout polish is the first thing a demo audience notices. Fix panel heights; internal scroll |

### Differentiators (valuable, within or adjacent to the spec; cheap wins first)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Staged "AI action" reveal | Action chips appear one after another with a short slide/fade, and the affected row (position/cash) briefly highlights in the table/header. Makes the AI trade feel causal | LOW-MED | Pure CSS; no spec change. Best ROI for the wow moment |
| Suggested prompt chips in empty chat | Clickable examples ("Buy 5 NVDA", "How concentrated is my portfolio?", "Add PYPL to my watchlist") so a first-time user can trigger the wow moment in one click. Must stay valid for LLM_MOCK patterns (`buy <qty> <TICKER>`) | LOW | Chips only fill/send text; no new backend |
| Header P&L figure + arrow | Total unrealized P&L with colour and caret next to total value | LOW | Data already in portfolio response |
| Flash on header total / position P&L | Same flash utility reused beyond watchlist | LOW | Reuse the hook |
| Heatmap/ table hover tooltip | Shows qty, value, P&L on hover | LOW | Recharts Tooltip with custom content |
| Chat markdown-lite rendering | Bold, lists, line breaks in assistant prose (portfolio analysis reads better) | LOW | Small renderer; sanitise, do not use raw HTML |
| Keyboard focus niceties | `/` focuses chat input, Esc blurs | LOW | Optional |
| Reset button (UI for existing `POST /api/reset`) | Demo re-runs from a clean state without restarting Docker | LOW | Endpoint is in the spec, a UI trigger is not mandated; small header menu item. Recommended for demos; needs the post-reset refresh |
| Flash-quiet "stale" indicator | Dim prices and show "Reconnecting..." when dot is yellow/red | LOW | Complements the dot |

### Anti-Features (deliberately NOT built)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Trade confirmation dialogs (manual or AI) | Feels "safe" | Spec explicitly forbids; kills the instant-fill demo | Inline success line + chat action chips |
| Limit/stop orders, order book, fees | Real terminals have them | Spec: market orders only; large portfolio-math surface | None |
| Realized P&L column / trade history table | Natural next column | Spec: intentionally untracked and undisplayed | Unrealized only |
| Token-by-token chat streaming | Looks slick | Spec: single complete JSON response; structured output cannot stream meaningfully | Typing/loading indicator |
| Price-history API / backfilled chart history | Chart empty at load looks bad | Spec: client-side accumulation only | Progressive fill + "collecting data" hint; sparklines filling in is the intended effect |
| Candlesticks, timeframes (1D/1W), indicators, drawing tools | TradingView-style expectations | Needs OHLC data the stream does not provide; large scope | Simple line/area chart |
| Auth, accounts, multi-user, settings pages | Standard app scaffolding | Single hardcoded user by design | None |
| WebSockets, polling the API for live values | Familiar | SSE + client recompute is the spec'd flow | EventSource |
| Drag-resize / customisable panel layouts | Terminal feel | Heavy dependency and state; little demo payoff | Fixed, well-tuned grid |
| Confetti / sound effects on trades | Fun | Gimmicky; risks looking unprofessional on a Bloomberg-style UI | Subtle highlight of affected rows |
| LLM tool-use loop / multiple LLM calls per message | "Smarter" agent | Spec: exactly one call; failures surfaced via `actions` | Rely on stored actions in next-turn history |
| Light theme toggle, i18n, mobile layout | Completeness | Spec: dark, desktop-first, tablet functional | None |
| News feed, fundamentals, alerts, watchlist reordering/groups | Terminal staples | Outside spec; no data source | None |

## Feature Dependencies

```
SSE price stream (exists) ──> client price-history store ──> sparklines
                                                      └────> main chart
                                                      └────> price flash

Selected ticker state ──requires──> watchlist loaded ──> main chart title/data
Selected ticker state <──enhances── positions row click, trade bar prefill

GET /api/portfolio ──> positions table ──> heatmap (needs pnl_percent + live prices)
                  └──> header total/cash
Live SSE prices ──enhances──> positions table, heatmap, header (client recompute)

Trade execution (backend) ──> trade bar ──> refreshAll() ──> portfolio, P&L chart, watchlist
Snapshot task + post-trade snapshot ──> P&L chart (needs >=1 seeded snapshot to avoid blank)

Chat endpoint ──> chat panel ──> inline action chips ──> refreshAll() (if any action ok)
LLM_MOCK patterns ──enhances──> prompt chips, E2E tests
Chat history on reload ──requires──> chat history read path (NOT in PLAN.md; open question)

Reset endpoint ──> optional reset UI ──> refreshAll() + clear client history/selection
```

### Dependency Notes

- **Heatmap, positions, header all need the same live-value selector.** Build one pure function `(portfolio, prices) -> enriched positions + totals`; it is also the main frontend unit-test target in PLAN.md section 12.
- **Everything visual depends on the price-history store and format utilities**, so these come first in the frontend.
- **Chat inline results depend on trade/watchlist refresh**, so build `refreshAll()` before the chat panel.
- **P&L chart blank-at-launch** depends on a backend startup snapshot; this is a cross-cutting requirement between backend lifespan and frontend.
- **Chat history persistence** is the one place the spec's data flow has a gap (stored in DB, no read endpoint). Decide explicitly in requirements.

## MVP Definition

### Launch With (v1: demo-ready)

- [ ] Shared formatting + tabular numerals + red/green colour utilities
- [ ] Price-history store, flash hook, watchlist with sparklines, selection
- [ ] Main chart (animation off, point cap, empty hint)
- [ ] Header with live total/cash and connection dot
- [ ] Trade bar with in-flight disable, inline error, success line
- [ ] Positions table, treemap heatmap (`data-pnl`), P&L chart (reference line, seeded first point)
- [ ] Chat panel with loading state, inline action cards (ok/error), post-action refresh
- [ ] Defined empty/loading states for every panel (no `NaN`, no blank charts)

### Add After Validation (v1.x, cheap polish)

- [ ] Staged action-chip reveal and row highlight after AI trades
- [ ] Suggested prompt chips
- [ ] Reset button in UI
- [ ] Hover tooltips on heatmap, header P&L figure

### Future Consideration (v2+)

- [ ] Chat history restore across reloads (needs spec change)
- [ ] Candlesticks / timeframes (needs OHLC data)
- [ ] Customisable layout

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Watchlist flash + sparklines | HIGH | LOW | P1 |
| Number formatting / tabular nums | HIGH | LOW | P1 |
| Empty/loading states | HIGH | MEDIUM | P1 |
| Inline AI action cards | HIGH | MEDIUM | P1 |
| Trade bar feedback/errors | HIGH | LOW | P1 |
| Treemap heatmap | HIGH | MEDIUM | P1 |
| Main chart + P&L chart | HIGH | MEDIUM | P1 |
| Connection dot | MEDIUM | LOW | P1 |
| Positions table | MEDIUM | LOW | P1 |
| Staged AI action reveal | HIGH | LOW | P2 |
| Prompt chips | MEDIUM | LOW | P2 |
| Reset button | MEDIUM | LOW | P2 |
| Tooltips, markdown-lite | LOW | LOW | P3 |
| Chat history restore | MEDIUM | MEDIUM | P3 (spec gap) |

## Competitor Feature Analysis

| Feature | Bloomberg / TradingView | Robinhood-style apps | Our Approach |
|---------|-------------------------|----------------------|--------------|
| Price update | Cell flash, dense monospace grid | Smooth number roll, less dense | Cell flash ~500ms, dense grid |
| Heatmap | Finviz-style treemap by market cap | Rare | Treemap by position weight, +-10% clamped colour |
| Order entry | Order ticket with confirm | Review screen then submit | One-click market order, no confirm (spec) |
| AI assistant | Bloomberg ASKB-style Q&A, no trading | Limited | Chat that executes trades, shown as inline action cards |

## Sources

- planning/PLAN.md (locked spec), .planning/PROJECT.md
- General conventions of Bloomberg Terminal, TradingView, Finviz heatmap, Robinhood UI and chat tool-call UX (domain knowledge; not re-verified online, LOW-MEDIUM confidence on specific values like 500ms and point caps)
- Recharts behaviour notes (animation props, Treemap custom content): training knowledge; verify in stack/phase research

---
*Feature research for: AI-assisted simulated trading workstation*
*Researched: 2026-10-13*
