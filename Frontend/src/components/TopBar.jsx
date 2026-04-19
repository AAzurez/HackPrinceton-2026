import { Activity, Bolt, Sparkles } from "lucide-react";
import GridShiftLogo from "./GridShiftLogo";

function formatTime(value) {
  if (!value) return "Not yet optimized";
  return value.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

export default function TopBar({
  onOptimize,
  isRunning,
  lastOptimizedAt,
  backendConnected,
  modelLoaded,
  backendMessage,
}) {
  return (
    <header className="pt-3">
      <div className="flex flex-col gap-3 xl:flex-row xl:items-end xl:justify-between">
        <div className="max-w-3xl">
          <div className="flex items-center gap-3">
            <GridShiftLogo className="h-10 w-10 shrink-0" />
            <h1 className="text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
              GridShift
            </h1>
          </div>
          <p className="mt-1 text-sm leading-relaxed text-muted">
            Grid-aware scheduling for flexible data center workloads.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <span className="chip border-teal/30 bg-teal/10 text-teal">
            <Activity className="h-3.5 w-3.5" />
            PJM STRESS FEED ACTIVE
          </span>
          <span
            className={`chip ${
              backendConnected
                ? "border-teal/30 bg-teal/10 text-teal"
                : "border-warn/35 bg-warn/20 text-[#866528]"
            }`}
          >
            {backendConnected
              ? `BACKEND ${modelLoaded ? "ONLINE" : "CONNECTED"}`
              : "BACKEND OFFLINE"}
          </span>
          <span className="chip border-accent/30 bg-accent/10 text-accent">
            <Sparkles className="h-3.5 w-3.5" />
            OPTIMIZER READY
          </span>
          <button
            type="button"
            onClick={onOptimize}
            className="btn-primary"
            disabled={isRunning}
          >
            <Bolt className="h-4 w-4" />
            {isRunning ? "OPTIMIZING..." : "OPTIMIZE SCHEDULE"}
          </button>
        </div>
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-4 text-[11px] uppercase tracking-[0.18em] text-muted">
        <span>Last Run: {formatTime(lastOptimizedAt)}</span>
        <span className="h-1 w-1 rounded-full bg-muted" />
        <span>{backendMessage}</span>
      </div>
    </header>
  );
}
