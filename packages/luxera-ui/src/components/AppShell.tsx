import type { ReactNode } from "react";

type AppShellProps = {
  sidebar: ReactNode;
  viewport: ReactNode;
  inspector: ReactNode;
  console: ReactNode;
};

export function AppShell(props: AppShellProps) {
  return (
    <div className="h-screen w-screen bg-base text-text">
      <div className="grid h-full grid-cols-[240px_1fr_320px] grid-rows-[1fr_220px] gap-3 p-3">
        <aside className="lux-panel row-span-2">{props.sidebar}</aside>
        <main className="lux-panel">{props.viewport}</main>
        <aside className="lux-panel">{props.inspector}</aside>
        <section className="lux-panel col-span-2">{props.console}</section>
      </div>
    </div>
  );
}
