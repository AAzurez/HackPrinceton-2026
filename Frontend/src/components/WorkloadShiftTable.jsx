function priorityClass(priority) {
  return priority === "critical"
    ? "border-warn/35 bg-warn/20 text-[#866528]"
    : "border-accent/30 bg-accent/10 text-accent";
}

function movedClass(moved) {
  return moved
    ? "border-teal/30 bg-teal/10 text-teal"
    : "border-edge bg-[rgba(255,250,244,0.94)] text-muted";
}

export default function WorkloadShiftTable({ rows }) {
  return (
    <section className="panel-shell flex h-full min-h-0 flex-col p-4 sm:p-5">
      <div className="mb-2">
        <p className="section-label">Scheduling Delta</p>
        <h3 className="mt-1 text-lg font-semibold tracking-tight text-ink">Workload Shift Table</h3>
      </div>

      <div className="min-h-0 flex-1 overflow-auto">
        <table className="min-w-full text-left text-sm">
          <thead className="text-xs uppercase tracking-[0.16em] text-muted">
            <tr className="border-b border-edge/70">
              <th className="pb-3 pr-4">Workload</th>
              <th className="pb-3 pr-4">Priority</th>
              <th className="pb-3 pr-4">Start (Old -> New)</th>
              <th className="pb-3 pr-4">Power</th>
              <th className="pb-3 pr-4">Status</th>
              <th className="pb-3">Reason</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-b border-edge/45 text-[#625882]">
                <td className="py-3.5 pr-4 font-medium text-ink">{row.name}</td>
                <td className="py-3.5 pr-4">
                  <span className={`chip ${priorityClass(row.priority)}`}>{row.priority}</span>
                </td>
                <td className="py-3.5 pr-4">
                  {String(row.originalHour).padStart(2, "0")}:00 ->{" "}
                  {String(row.newHour).padStart(2, "0")}:00
                </td>
                <td className="py-3.5 pr-4">{row.powerMw.toFixed(1)} MW</td>
                <td className="py-3.5 pr-4">
                  <span className={`chip ${movedClass(row.moved)}`}>
                    {row.moved ? "Shifted" : "Kept"}
                  </span>
                </td>
                <td className="max-w-[20rem] py-3.5 text-xs leading-relaxed text-muted">
                  {row.reason}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
