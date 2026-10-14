import { useQuery } from "@tanstack/react-query";
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from "recharts";
import { apiClient } from "../api/client";
import type { PerformancePoint } from "../types";

export default function Performance() {
  const { data } = useQuery({
    queryKey: ["dashboard-performance"],
    queryFn: async () =>
      (await apiClient.get<{ points: PerformancePoint[] }>("/api/dashboard/performance")).data.points,
    refetchInterval: 15000,
  });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Pipeline Performance</h1>

      <div className="bg-ops-panel border border-ops-border rounded-lg p-4">
        <h2 className="text-sm font-semibold text-slate-300 mb-3">Processing FPS & Latency</h2>
        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={data ?? []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="job_id" stroke="#94a3b8" fontSize={12} />
            <YAxis stroke="#94a3b8" fontSize={12} />
            <Tooltip contentStyle={{ background: "#121823", border: "1px solid #1f2937" }} />
            <Legend />
            <Line type="monotone" dataKey="processing_fps" stroke="#f59e0b" name="FPS" strokeWidth={2} />
            <Line type="monotone" dataKey="avg_latency_ms" stroke="#60a5fa" name="Avg Latency (ms)" strokeWidth={2} />
            <Line type="monotone" dataKey="p95_latency_ms" stroke="#ef4444" name="P95 Latency (ms)" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="bg-ops-panel border border-ops-border rounded-lg p-4">
        <h2 className="text-sm font-semibold text-slate-300 mb-3">Resource Usage</h2>
        <ResponsiveContainer width="100%" height={260}>
          <LineChart data={data ?? []}>
            <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
            <XAxis dataKey="job_id" stroke="#94a3b8" fontSize={12} />
            <YAxis stroke="#94a3b8" fontSize={12} />
            <Tooltip contentStyle={{ background: "#121823", border: "1px solid #1f2937" }} />
            <Legend />
            <Line type="monotone" dataKey="avg_cpu_percent" stroke="#34d399" name="Avg CPU %" strokeWidth={2} />
            <Line type="monotone" dataKey="avg_ram_mb" stroke="#a78bfa" name="Avg RAM (MB)" strokeWidth={2} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
