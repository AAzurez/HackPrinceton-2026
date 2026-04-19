import { MessageSquareText } from "lucide-react";

export default function AgentSummaryCard({ summary, movedCount, totalFlexibleJobs }) {
  return (
    <section className="panel-shell p-5 sm:p-6">
      <div className="flex items-center gap-2">
        <span className="chip border-accent/30 bg-accent/10 text-accent">
          <MessageSquareText className="h-3.5 w-3.5" />
          AGENT EXPLANATION
        </span>
      </div>

      <h3 className="mt-3 text-xl font-semibold tracking-tight text-ink">Why the schedule changed</h3>
      <p className="mt-3 text-sm leading-relaxed text-muted">{summary}</p>

      <div className="mt-4 rounded-2xl border border-edge/70 bg-[rgba(255,248,239,0.95)] p-4 text-xs uppercase tracking-[0.16em] text-muted">
        Flexible jobs shifted:{" "}
        <span className="text-ink">
          {movedCount}/{totalFlexibleJobs}
        </span>
      </div>
    </section>
  );
}
