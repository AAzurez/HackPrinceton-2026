import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

export default function MetricCard({
  label,
  value,
  delta,
  tone = "accent",
  icon: Icon,
  collapsible = true,
  defaultCollapsed = false,
}) {
  const [isCollapsed, setIsCollapsed] = useState(Boolean(defaultCollapsed));

  const toneMap = {
    accent: "text-accent border-accent/30 bg-accent/10",
    positive: "text-teal border-teal/30 bg-teal/10",
    warning: "text-[#8D6A2B] border-warn/35 bg-warn/20",
  };

  return (
    <article className="panel-shell h-full overflow-hidden p-3">
      <div className="flex items-start justify-between gap-4">
        <p className="section-label text-[0.62rem]">{label}</p>
        <div className="flex items-center gap-2">
          {Icon ? (
            <span className={`chip ${toneMap[tone] || toneMap.accent}`}>
              <Icon className="h-3.5 w-3.5" />
            </span>
          ) : null}
          {collapsible ? (
            <button
              type="button"
              onClick={() => setIsCollapsed((prev) => !prev)}
              className="inline-flex items-center justify-center rounded-full border border-edge bg-[rgba(255,250,244,0.94)] p-1.5 text-muted transition hover:border-accent/40 hover:text-accent"
              aria-label={isCollapsed ? `Expand ${label}` : `Collapse ${label}`}
              title={isCollapsed ? "Expand" : "Collapse"}
            >
              {isCollapsed ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronUp className="h-3.5 w-3.5" />}
            </button>
          ) : null}
        </div>
      </div>
      {!isCollapsed ? (
        <>
          <p className="mt-1 text-xl font-semibold tracking-tight text-ink">{value}</p>
          {delta ? (
            <p
              className="mt-1 truncate text-[10px] uppercase tracking-[0.1em] text-muted"
              title={delta}
            >
              {delta}
            </p>
          ) : null}
        </>
      ) : null}
    </article>
  );
}
