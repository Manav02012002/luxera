import {
  AppShell,
  ConsolePanel,
  InspectorPanel,
  MetricCard,
  Sidebar,
  SidebarSection,
  ToolbarButton,
} from "@luxera/luxera-ui";

const projectItems = ["Project", "Geometry", "Luminaires", "Calculation", "Reports"];

export default function App() {
  return (
    <AppShell
      sidebar={
        <Sidebar title="Project">
          <SidebarSection title="Navigator">
            {projectItems.map((item) => (
              <ToolbarButton key={item} className="w-full text-left">
                {item}
              </ToolbarButton>
            ))}
          </SidebarSection>
        </Sidebar>
      }
      viewport={
        <div>
          <div className="lux-panel-title">Viewport</div>
          <div className="m-4 h-[calc(100%-2rem)] rounded-lg border border-border bg-panelSoft/60 p-4">
            <div className="h-full rounded-[10px] border border-border/80 bg-[linear-gradient(rgba(145,164,185,0.07)_1px,transparent_1px),linear-gradient(90deg,rgba(145,164,185,0.07)_1px,transparent_1px),linear-gradient(180deg,rgba(18,26,35,0.8),rgba(15,22,30,0.95))] bg-[length:24px_24px,24px_24px,auto]" />
          </div>
        </div>
      }
      inspector={
        <InspectorPanel title="Inspector">
          <div className="space-y-3">
            <MetricCard label="Selection" value="No active element" />
            <MetricCard label="Coordinates" value="X 0.00  Y 0.00  Z 0.00" />
            <MetricCard label="Context" value="Ready" />
          </div>
        </InspectorPanel>
      }
      console={<ConsolePanel title="Console" />}
    />
  );
}
