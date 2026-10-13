import type { ReactNode } from "react";

export function Panel({
  title,
  aside,
  children,
  className = "",
  bodyClassName = "",
}: {
  title: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
}) {
  return (
    <section className={`flex h-full min-h-0 flex-col border border-line bg-panel ${className}`}>
      <header className="flex h-8 shrink-0 items-center justify-between gap-2 border-b border-line px-3">
        <h2 className="truncate text-[12px] font-semibold text-ink">{title}</h2>
        {aside && <div className="flex items-center gap-2 text-[11px] text-muted">{aside}</div>}
      </header>
      <div className={`min-h-0 flex-1 ${bodyClassName}`}>{children}</div>
    </section>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <div className="flex h-full items-center justify-center p-4 text-center text-[12px] text-muted">{children}</div>;
}
