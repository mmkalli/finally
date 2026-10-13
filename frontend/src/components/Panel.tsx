import type { ReactNode } from "react";

interface PanelProps {
  title: string;
  /** Extra controls shown on the right of the title bar. */
  actions?: ReactNode;
  className?: string;
  /** Classes for the body (defaults to padded, scrollable). */
  bodyClassName?: string;
  children: ReactNode;
  "data-testid"?: string;
}

/** Bordered terminal-style panel with a compact title bar, shared by every section. */
export function Panel({
  title,
  actions,
  className = "",
  bodyClassName = "min-h-0 flex-1 overflow-auto p-2",
  children,
  "data-testid": testId,
}: PanelProps) {
  return (
    <section
      aria-label={title}
      data-testid={testId}
      className={`flex min-h-0 flex-col rounded border border-border bg-surface ${className}`}
    >
      <header className="flex h-8 shrink-0 items-center justify-between border-b border-border px-2">
        <h2 className="text-xs font-semibold tracking-wider text-muted uppercase">{title}</h2>
        {actions}
      </header>
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

/** Centered muted text for empty or not-yet-built panel bodies. */
export function Placeholder({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-full min-h-16 items-center justify-center text-sm text-muted">
      {children}
    </div>
  );
}
