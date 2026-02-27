import type { ReactNode } from "react";

type SidebarProps = {
  title?: string;
  children: ReactNode;
};

export function Sidebar({ title = "Project", children }: SidebarProps) {
  return (
    <div>
      <div className="lux-panel-title">{title}</div>
      <div className="p-3">{children}</div>
    </div>
  );
}

type SidebarSectionProps = {
  title: string;
  children: ReactNode;
};

export function SidebarSection({ title, children }: SidebarSectionProps) {
  return (
    <section className="mb-4">
      <h3 className="mb-2 text-[11px] uppercase tracking-[0.12em] text-muted">{title}</h3>
      <div className="space-y-2">{children}</div>
    </section>
  );
}
