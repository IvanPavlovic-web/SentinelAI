import { useQuery } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";
import { apiClient } from "../api/client";
import type { PerformancePoint } from "../types";

const gridStroke = "#262626";
const axisStroke = "#737373";
const tooltipStyle = { background: "#111111", border: "1px solid #262626", borderRadius: 8, fontSize: 12 };
const tooltipLabelStyle = { color: "#e5e5e5" };

export default function Performance() {
  const { data } = useQuery({
    queryKey: ["dashboard-performance"],
    queryFn: async () =>
      (await apiClient.get<{ points: PerformancePoint[] }>("/api/dashboard/performance")).data.points,
    refetchInterval: 15000,
  });

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[11px] uppercase tracking-widest2 text-ops-accent font-medium mb-1">Pipeline</p>
        <h1 className="font-display text-2xl font-semibold">Performance</h1>
      </div>

      <div className="bg-ops-panel border border-ops-border rounded-lg p-5">
        <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400 mb-4">Processing FPS &amp; Latency</h2>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data ?? []}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
            <XAxis dataKey="job_id" stroke={axisStroke} fontSize={12} />
            <YAxis stroke={axisStroke} fontSize={12} />
            <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} />
            <Legend wrapperStyle={{ fontSize: 12, color: "#a3a3a3" }} />
            {/* Distinguished by brightness + stroke pattern, not hue, to stay strictly black/white/gray. */}
            <Line type="monotone" dataKey="processing_fps" stroke="#ffffff" name="FPS" strokeWidth={2} dot={false} />
            <Line
              type="monotone"
              dataKey="avg_latency_ms"
              stroke="#a3a3a3"
              name="Avg Latency (ms)"
              strokeWidth={2}
              strokeDasharray="6 3"
              dot={false}
            />
            <Line
              type="monotone"
              dataKey="p95_latency_ms"
              stroke="#595959"
              name="P95 Latency (ms)"
              strokeWidth={2}
              strokeDasharray="2 2"
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-ops-panel border border-ops-border rounded-lg p-5">
        <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400 mb-4">Resource Usage</h2>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data ?? []}>
            <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} />
            <XAxis dataKey="job_id" stroke={axisStroke} fontSize={12} />
            <YAxis stroke={axisStroke} fontSize={12} />
            <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} />
            <Legend wrapperStyle={{ fontSize: 12, color: "#a3a3a3" }} />
            <Line type="monotone" dataKey="avg_cpu_percent" stroke="#ffffff" name="Avg CPU %" strokeWidth={2} dot={false} />
            <Line
              type="monotone"
              dataKey="avg_ram_mb"
              stroke="#a3a3a3"
              name="Avg RAM (MB)"
              strokeWidth={2}
              strokeDasharray="6 3"
              dot={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
