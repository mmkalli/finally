"use client";

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { describeAction } from "@/lib/chatActions";
import { useAppState } from "@/lib/store";
import type { ChatAction } from "@/lib/types";
import { Panel } from "./Panel";

// AI chat sidebar (PLAN §9, §10). History is local to this page load (there is
// no chat-history endpoint) and is cleared on reset. useAppState().sendChat
// refetches portfolio/watchlist/history after any `ok` actions.
export function ChatPanel() {
  const { resetCount } = useAppState();
  const [open, setOpen] = useState(true);

  // Collapsing hides the panel rather than unmounting it, so the conversation survives.
  return (
    <>
      {!open && (
        <button
          type="button"
          onClick={() => setOpen(true)}
          aria-label="Open AI chat"
          data-testid="chat-open"
          className="shrink-0 rounded border border-border bg-surface px-1 text-xs font-semibold tracking-wider text-muted uppercase [writing-mode:vertical-rl] hover:text-foreground"
        >
          AI Chat
        </button>
      )}
      <Panel
        title="FinAlly AI"
        className={`w-80 shrink-0 xl:w-96 ${open ? "" : "hidden!"}`}
        bodyClassName="flex min-h-0 flex-1 flex-col"
        data-testid="chat-panel"
        actions={
          <button
            type="button"
            onClick={() => setOpen(false)}
            aria-label="Collapse AI chat"
            data-testid="chat-collapse"
            className="text-muted hover:text-foreground"
          >
            »
          </button>
        }
      >
        {/* Keyed by resetCount so a reset starts a fresh conversation. */}
        <Conversation key={resetCount} />
      </Panel>
    </>
  );
}

interface ChatEntry {
  id: number;
  role: "user" | "assistant";
  content: string;
  actions?: ChatAction[];
  /** The request itself failed (network/server error), not an action. */
  failed?: boolean;
}

const errorMessage = (e: unknown) => (e instanceof Error ? e.message : String(e));

function Conversation() {
  const { sendChat } = useAppState();
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(false);
  const nextId = useRef(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [entries, pending]);

  const append = (entry: Omit<ChatEntry, "id">) =>
    setEntries((prev) => [...prev, { ...entry, id: nextId.current++ }]);

  async function submit() {
    const message = draft.trim();
    if (!message || pending) return;

    append({ role: "user", content: message });
    setDraft("");
    setPending(true);
    try {
      const res = await sendChat(message);
      append({ role: "assistant", content: res.message, actions: res.actions });
    } catch (e) {
      append({
        role: "assistant",
        content: `Couldn't reach FinAlly: ${errorMessage(e)}`,
        failed: true,
      });
    } finally {
      setPending(false);
      inputRef.current?.focus();
    }
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    void submit();
  };

  // Enter sends; Shift+Enter inserts a newline.
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      void submit();
    }
  };

  return (
    <>
      <div
        ref={scrollRef}
        role="log"
        aria-live="polite"
        data-testid="chat-messages"
        className="min-h-0 flex-1 space-y-3 overflow-y-auto p-2"
      >
        {entries.length === 0 && !pending && (
          <div className="flex h-full flex-col items-center justify-center gap-1 text-center text-sm text-muted">
            <p>Ask FinAlly about your portfolio.</p>
            <p className="text-xs">
              Try &ldquo;How diversified am I?&rdquo; or &ldquo;Buy 5 NVDA&rdquo;.
            </p>
          </div>
        )}

        {entries.map((entry) => (
          <Message key={entry.id} entry={entry} />
        ))}

        {pending && (
          <div
            data-testid="chat-loading"
            className="flex items-center gap-1 text-xs text-muted"
            aria-label="FinAlly is thinking"
          >
            <span className="size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.3s]" />
            <span className="size-1.5 animate-bounce rounded-full bg-primary [animation-delay:-0.15s]" />
            <span className="size-1.5 animate-bounce rounded-full bg-primary" />
            <span className="ml-1">FinAlly is thinking…</span>
          </div>
        )}
      </div>

      <form onSubmit={onSubmit} className="flex shrink-0 gap-2 border-t border-border p-2">
        <textarea
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          rows={2}
          placeholder="Ask FinAlly…"
          aria-label="Chat message"
          data-testid="chat-input"
          className="min-w-0 flex-1 resize-none rounded border border-border bg-background px-2 py-1 text-sm placeholder:text-muted focus:border-primary focus:outline-none"
        />
        <button
          type="submit"
          disabled={pending || !draft.trim()}
          data-testid="chat-send"
          className="self-end rounded bg-secondary px-3 py-1.5 text-sm font-semibold text-white hover:brightness-125 disabled:cursor-not-allowed disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </>
  );
}

function Message({ entry }: { entry: ChatEntry }) {
  const isUser = entry.role === "user";
  const bubble = isUser
    ? "ml-6 bg-primary/15 border-primary/40"
    : entry.failed
      ? "mr-6 bg-down/10 border-down/40 text-down"
      : "mr-6 bg-surface-raised border-border";

  return (
    <div
      data-testid={entry.failed ? "chat-error" : "chat-message"}
      data-role={entry.role}
      className={`rounded border px-2 py-1.5 text-sm ${bubble}`}
    >
      <div className="mb-0.5 text-[10px] font-semibold tracking-wider text-muted uppercase">
        {isUser ? "You" : "FinAlly"}
      </div>
      <p className="break-words whitespace-pre-wrap">{entry.content}</p>

      {entry.actions && entry.actions.length > 0 && (
        <ul className="mt-1.5 space-y-1">
          {entry.actions.map((action, i) => (
            <ActionResult key={i} action={action} />
          ))}
        </ul>
      )}
    </div>
  );
}

function ActionResult({ action }: { action: ChatAction }) {
  const ok = action.status === "ok";
  return (
    <li
      data-testid="chat-action"
      data-type={action.type}
      data-status={action.status}
      data-ticker={action.ticker}
      className={`flex items-start gap-1.5 rounded px-1.5 py-1 text-xs ${
        ok ? "bg-up/10 text-up" : "bg-down/10 text-down"
      }`}
    >
      <span aria-hidden>{ok ? "✓" : "✕"}</span>
      <span>{describeAction(action)}</span>
    </li>
  );
}
