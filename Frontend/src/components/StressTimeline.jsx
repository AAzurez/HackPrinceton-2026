import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

function stressColor(value) {
  if (value >= 0.9) return "#DEB45A";
  if (value >= 0.7) return "#CF9EF2";
  if (value >= 0.5) return "#B9ABF2";
  return "#B2C4F4";
}

export default function StressTimeline({ data }) {
  return (
    <section className="panel-shell flex h-full flex-col p-4 sm:p-5">
      <p className="section-label">Grid Signal</p>
      <h3 className="mt-1 text-lg font-semibold tracking-tight text-ink">Hourly Grid Stress</h3>

      <div className="mt-2 h-full min-h-0 w-full">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 10, left: -12, bottom: 0 }}>
            <CartesianGrid stroke="#D7CBEA" strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="hour"
              stroke="#8A7FA9"
              tick={{ fill: "#867A9F", fontSize: 11 }}
              interval={2}
            />
            <YAxis
              stroke="#8A7FA9"
              tick={{ fill: "#867A9F", fontSize: 11 }}
              domain={[0, 1]}
              width={30}
            />
            <Tooltip
              formatter={(value) => [Number(value).toFixed(2), "Grid Stress"]}
              contentStyle={{
                borderRadius: "12px",
                border: "1px solid rgba(182, 164, 229, 0.45)",
                background: "rgba(255, 248, 240, 0.95)",
                color: "#473E62",
              }}
            />
            <Bar dataKey="gridStress" radius={[5, 5, 0, 0]}>
              {data.map((entry) => (
                <Cell key={entry.hour} fill={stressColor(entry.gridStress)} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
