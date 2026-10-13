"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { fmtPrice, fmtQty } from "@/utils/format";
import type { ChatAction } from "@/utils/types";

export interface ChatEntry {
  id: number;
  role: "user" | "assistant";
  content: string;
  actions?: ChatAction[];
  failed?: boolean;
}

const SUGGESTIONS = ["How is my portfolio doing?", "Buy 5 NVDA", "Add PYPL to my watchlist"];

export function ChatPanel({
  messages,
  loading,
  open,
  onToggle,
  onSend,
}: {
  messages: ChatEntry[];
  loading: boolean;
  open: boolean;
  onToggle: () => void;
  onSend: (text: string) => void;
}) {
  const [input, setInput] = useState("");
  const scroller = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scroller.current?.scrollTo({ top: scroller.current.scrollHeight });
  }, [messages, loading]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    onSend(text);
    setInput("");
  };

  if (!open) {
    return (
      <aside className="flex w-10 shrink-0 flex-col items-center border-l border-line bg-panel py-2">
        <button
          type="button"
          data-testid="chat-toggle"
          onClick={onToggle}
          aria-label="Open AI chat"
          aria-expanded={false}
          className="flex flex-col items-center gap-2 rounded-sm px-1 py-2 text-[11px] text-muted hover:bg-raised hover:text-ink"
        >
          <span className="h-2 w-2 rounded-full bg-accent" />
          <span className="[writing-mode:vertical-rl]">FinAlly chat</span>
        </button>
      </aside>
    );
  }

  return (
    <aside
      data-testid="chat-panel"
      className="flex w-full shrink-0 flex-col border-l border-line bg-panel lg:w-[340px] xl:w-[380px]"
    >
      <header className="flex h-8 shrink-0 items-center justify-between border-b border-line px-3">
        <h2 className="text-[12px] font-semibold">
          Fin<span className="text-accent">Ally</span> assistant
        </h2>
        <button
          type="button"
          data-testid="chat-toggle"
          onClick={onToggle}
          aria-label="Collapse AI chat"
          aria-expanded
          className="rounded-sm px-2 text-[14px] leading-6 text-muted hover:bg-raised hover:text-ink"
        >
          ›
        </button>
      </header>

      <div ref={scroller} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3" aria-live="polite">
        {messages.length === 0 && (
          <div className="space-y-2 text-[12px] text-muted">
            <p>Ask about your positions, or tell me what to trade. Trades run as soon as I reply.</p>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => onSend(s)}
                  className="rounded-sm border border-line px-2 py-1 text-[11px] text-ink hover:border-primary"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m) => (
          <Message key={m.id} entry={m} />
        ))}
        {loading && (
          <div data-testid="chat-loading" className="thinking flex items-center gap-1 text-[12px] text-muted">
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            <span className="h-1.5 w-1.5 rounded-full bg-accent" />
            <span className="sr-only">FinAlly is thinking</span>
          </div>
        )}
      </div>

      <form onSubmit={submit} className="flex shrink-0 gap-1 border-t border-line p-2">
        <input
          data-testid="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Message FinAlly"
          aria-label="Message FinAlly"
          className="min-w-0 flex-1 rounded-sm border border-line bg-bg px-2 py-1.5 text-[12px] placeholder:text-faint focus:border-primary focus:outline-none"
        />
        <button
          data-testid="chat-send"
          type="submit"
          disabled={loading || !input.trim()}
          className="rounded-sm bg-submit px-3 py-1.5 text-[12px] font-semibold text-white hover:brightness-125 disabled:opacity-40"
        >
          Send
        </button>
      </form>
    </aside>
  );
}

function Message({ entry }: { entry: ChatEntry }) {
  const mine = entry.role === "user";
  return (
    <div data-testid="chat-message" data-role={entry.role} className={`flex flex-col ${mine ? "items-end" : "items-start"}`}>
      <div
        className={`max-w-[92%] whitespace-pre-wrap rounded-sm px-2.5 py-1.5 text-[12.5px] leading-relaxed ${
          mine
            ? "bg-primary/15 text-ink"
            : entry.failed
              ? "border border-down/50 text-down"
              : "border-l-2 border-accent bg-raised text-ink"
        }`}
      >
        {entry.content}
      </div>
      {entry.actions && entry.actions.length > 0 && (
        <ul className="mt-1 w-full max-w-[92%] space-y-1">
          {entry.actions.map((a, i) => (
            <ActionResult key={i} action={a} />
          ))}
        </ul>
      )}
    </div>
  );
}

function describe(a: ChatAction): string {
  if (a.type === "trade") {
    const verb = a.status === "ok" ? (a.side === "buy" ? "Bought" : "Sold") : a.side === "buy" ? "Buy" : "Sell";
    const qty = a.quantity != null ? fmtQty(a.quantity) + " " : "";
    const at = a.status === "ok" && a.price != null ? ` @ ${fmtPrice(a.price)}` : "";
    return `${verb} ${qty}${a.ticker}${at}`;
  }
  if (a.status === "ok") return a.action === "remove" ? `Removed ${a.ticker} from watchlist` : `Added ${a.ticker} to watchlist`;
  return `${a.action === "remove" ? "Remove" : "Add"} ${a.ticker}`;
}

function ActionResult({ action }: { action: ChatAction }) {
  const ok = action.status === "ok";
  return (
    <li
      data-testid="chat-action"
      data-status={action.status}
      className={`flex items-start gap-2 rounded-sm border px-2 py-1 text-[11.5px] ${
        ok ? "border-up/40 bg-up/10" : "border-down/40 bg-down/10"
      }`}
    >
      <span className={`font-semibold ${ok ? "text-up" : "text-down"}`} aria-hidden>
        {ok ? "✓" : "✕"}
      </span>
      <span className="num min-w-0">
        <span className="text-ink">{describe(action)}</span>
        {!ok && action.error && <span className="block font-sans text-down">{action.error}</span>}
      </span>
    </li>
  );
}
