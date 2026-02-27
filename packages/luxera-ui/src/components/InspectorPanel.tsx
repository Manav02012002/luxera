import type { ReactNode } from "react";

type InspectorPanelProps = {
  title?: string;
  children: ReactNode;
};

export function InspectorPanel({ title = "Inspector", children }: InspectorPanelProps) {
  return (
    <div>
      <div className="lux-panel-title">{title}</div>
      <div className="p-3">{children}</div>
    </div>
  );
}
