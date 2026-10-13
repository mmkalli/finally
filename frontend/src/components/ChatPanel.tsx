"use client";

import { useState } from "react";
import { Panel, Placeholder } from "./Panel";

// Stub — fi-vyz builds the conversation: input, history, loading indicator and
// inline action results, via useAppState().sendChat. Clear local history when
// useAppState().resetCount changes.
export function ChatPanel() {
  const [open, setOpen] = useState(true);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Open AI chat"
        className="shrink-0 rounded border border-border bg-surface px-1 text-xs font-semibold tracking-wider text-muted uppercase [writing-mode:vertical-rl] hover:text-foreground"
      >
        AI Chat
      </button>
    );
  }

  return (
    <Panel
      title="FinAlly AI"
      className="w-80 shrink-0 xl:w-96"
      data-testid="chat-panel"
      actions={
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="Collapse AI chat"
          className="text-muted hover:text-foreground"
        >
          »
        </button>
      }
    >
      <Placeholder>Ask FinAlly about your portfolio</Placeholder>
    </Panel>
  );
}
