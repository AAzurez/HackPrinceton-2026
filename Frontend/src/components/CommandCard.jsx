import { CircleCheck, Cpu, Radio, Zap } from "lucide-react";

function formatTime(value) {
  if (!value) return "--";
  return value.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function CommandCard({
  scenarioOptions,
  selectedScenario,
  onScenarioChange,
  onOptimize,
  isRunning,
  lastOptimizedAt,
  backendConnected,
  modelLoaded,
}) {
  return (
    <aside className="panel-shell h-full overflow-hidden space-y-4 p-4 sm:p-5">
      <div>
        <p className="section-label">Command</p>
        <h3 className="mt-1 text-lg font-semibold tracking-tight text-ink">Control Panel</h3>
      </div>

      <label className="block">
        <span className="section-label">Scenario Selector</span>
        <select
          value={selectedScenario}
          onChange={(event) => onScenarioChange(event.target.value)}
          className="mt-2 w-full rounded-2xl border border-edge bg-[rgba(255,250,244,0.92)] px-4 py-3 text-sm text-ink outline-none transition focus:border-accent/60 focus:ring-2 focus:ring-accent/20"
        >
          {scenarioOptions.map((scenario) => (
            <option key={scenario} value={scenario} className="bg-cream text-ink">
              {scenario}
            </option>
          ))}
        </select>
      </label>

      <div className="grid gap-2 rounded-2xl border border-edge/80 bg-[rgba(255,249,240,0.84)] p-3">
        <div className="flex items-center justify-between text-xs uppercase tracking-[0.16em] text-muted">
          <span>Model Status</span>
          <span
            className={`inline-flex items-center gap-1.5 ${
              backendConnected ? "text-teal" : "text-[#866528]"
            }`}
          >
            <CircleCheck className="h-3.5 w-3.5" />
            {backendConnected ? (modelLoaded ? "Ready" : "Connected") : "Offline"}
          </span>
        </div>
        <div className="grid gap-1 text-sm text-[#665B87]">
          <div className="flex items-center gap-2">
            <Cpu className="h-4 w-4 text-accent" />
            <span>
              {modelLoaded
                ? "Chronos-2 Fine-Tuned Adapter Loaded"
                : "Chronos-2 Adapter Not Loaded"}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Radio className="h-4 w-4 text-accent" />
            <span>
              {backendConnected
                ? "PJM Stress Feed + Local Profile Sim"
                : "Waiting for backend connection"}
            </span>
          </div>
        </div>
      </div>

      <button
        type="button"
        onClick={onOptimize}
        className="btn-secondary w-full"
        disabled={isRunning}
      >
        <Zap className="h-4 w-4" />
        {isRunning ? "RUNNING OPTIMIZER..." : "OPTIMIZE SCHEDULE"}
      </button>

      <div className="rounded-2xl border border-edge/70 bg-[rgba(252,245,236,0.92)] p-3 text-xs uppercase tracking-[0.16em] text-muted">
        Last execution: <span className="text-ink">{formatTime(lastOptimizedAt)}</span>
      </div>
    </aside>
  );
}
