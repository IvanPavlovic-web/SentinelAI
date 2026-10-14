import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { apiClient } from "../api/client";
import type { DashboardSummary, Incident, PaginatedIncidents } from "../types";
import StatTile from "../components/StatTile";

export default function Dashboard() {
  const { data: summary } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: async () => (await apiClient.get<DashboardSummary>("/api/dashboard/summary")).data,
    refetchInterval: 10000,
  });

  const { data: incidents } = useQuery({
    queryKey: ["recent-incidents"],
    queryFn: async () =>
      (await apiClient.get<PaginatedIncidents>("/api/incidents", { params: { page: 1, page_size: 5 } })).data,
    refetchInterval: 10000,
  });

  const priorityData = summary
    ? Object.entries(summary.incidents_by_priority).map(([priority, count]) => ({ priority, count }))
    : [];

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Operations Dashboard</h1>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile label="Active Cameras" value={summary?.active_cameras ?? "-"} />
        <StatTile label="Total Videos" value={summary?.total_videos ?? "-"} />
        <StatTile label="Open Incidents" value={summary?.open_incidents ?? "-"} accent="red" />
        <StatTile label="Incidents (24h)" value={summary?.incidents_last_24h ?? "-"} accent="amber" />
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatTile label="Jobs Pending" value={summary?.jobs_pending ?? "-"} />
        <StatTile label="Jobs Processing" value={summary?.jobs_processing ?? "-"} accent="amber" />
        <StatTile label="Jobs Completed" value={summary?.jobs_completed ?? "-"} accent="green" />
        <StatTile label="Jobs Failed" value={summary?.jobs_failed ?? "-"} accent="red" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-ops-panel border border-ops-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Incidents by Priority</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={priorityData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1f2937" />
              <XAxis dataKey="priority" stroke="#94a3b8" fontSize={12} />
              <YAxis stroke="#94a3b8" fontSize={12} allowDecimals={false} />
              <Tooltip contentStyle={{ background: "#121823", border: "1px solid #1f2937" }} />
              <Bar dataKey="count" fill="#f59e0b" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-ops-panel border border-ops-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Recent Incidents</h2>
          <ul className="space-y-2 text-sm">
            {incidents?.items.length === 0 && <p className="text-slate-500">No incidents yet.</p>}
            {incidents?.items.map((incident: Incident) => (
              <li key={incident.id} className="flex justify-between border-b border-ops-border pb-2">
                <span className="text-slate-300">{incident.summary.slice(0, 60)}...</span>
                <span className="text-amber-400 font-semibold">{incident.star_risk_score.toFixed(1)}</span>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
