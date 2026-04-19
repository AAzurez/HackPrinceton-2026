import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

export default function LoadComparisonChart({ data }) {
  return (
    <section className="panel-shell flex h-full flex-col p-4 sm:p-5">
      <div className="mb-2 flex items-end justify-between gap-3">
        <div>
          <p className="section-label">Forecast Curves</p>
          <h3 className="mt-1 text-lg font-semibold tracking-tight text-ink">
            Baseline vs Optimized Load
          </h3>
        </div>
      </div>

      <div className="h-full min-h-0 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 12, right: 16, left: -8, bottom: 0 }}>
            <CartesianGrid stroke="#D7CBEA" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="hour"
              stroke="#8A7FA9"
              tick={{ fill: "#867A9F", fontSize: 11 }}
              interval={2}
            />
            <YAxis stroke="#8A7FA9" tick={{ fill: "#867A9F", fontSize: 11 }} width={36} />
            <Tooltip
              cursor={{ stroke: "#9C8AE8", strokeWidth: 1, strokeDasharray: "4 4" }}
              contentStyle={{
                borderRadius: "12px",
                border: "1px solid rgba(182, 164, 229, 0.45)",
                background: "rgba(255, 248, 240, 0.95)",
                color: "#473E62",
              }}
            />
            <Legend
              wrapperStyle={{
                color: "#7D739A",
                fontSize: "12px",
                letterSpacing: "0.04em",
                paddingTop: "10px",
              }}
            />
            <Line
              type="monotone"
              dataKey="baselineLoad"
              stroke="#8F77E8"
              strokeWidth={2}
              dot={false}
              name="Baseline Load (MW)"
            />
            <Line
              type="monotone"
              dataKey="optimizedLoad"
              stroke="#E5C06A"
              strokeWidth={2.6}
              dot={false}
              name="Optimized Load (MW)"
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
