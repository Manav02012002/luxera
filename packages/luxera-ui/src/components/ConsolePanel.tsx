import type { ReactNode } from "react";

type ConsolePanelProps = {
  title?: string;
  children?: ReactNode;
};

export function ConsolePanel({ title = "Console", children }: ConsolePanelProps) {
  return (
    <div>
      <div className="lux-panel-title">{title}</div>
      <div className="m-4 h-[calc(100%-2rem)] rounded-lg border border-border bg-[#0d1218] p-3 text-sm text-muted">
        {children}
      </div>
    </div>
  );
}
