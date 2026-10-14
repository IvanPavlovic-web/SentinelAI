import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from "recharts";
import { apiClient } from "../api/client";
import type { Camera, DashboardSummary, Incident, PaginatedIncidents } from "../types";
import StatTile from "../components/StatTile";

const priorityPill: Record<string, string> = {
  critical: "text-status-critical border-status-critical/40 bg-status-critical/10",
  high: "text-status-high border-status-high/40 bg-status-high/10",
  medium: "text-status-medium border-status-medium/40 bg-status-medium/10",
  low: "text-status-low border-status-low/40 bg-status-low/10",
};

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

  // latest_job_status comes back inline with the list (see Cameras.tsx for
  // the same fix), so this needs one request instead of one per camera.
  const { data: cameras } = useQuery({
    queryKey: ["cameras"],
    queryFn: async () => (await apiClient.get<Camera[]>("/api/cameras")).data,
    refetchInterval: 10000,
  });

  const priorityData = summary
    ? Object.entries(summary.incidents_by_priority).map(([priority, count]) => ({ priority, count }))
    : [];

  return (
    <div className="space-y-7">
      <div>
        <p className="text-[11px] uppercase tracking-widest2 text-ops-accent font-medium mb-1">Operations</p>
        <h1 className="font-display text-2xl font-semibold">Dashboard</h1>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
        <StatTile label="Cameras" value={summary?.total_cameras ?? "-"} />
        <StatTile
          label="Live Now"
          value={summary?.active_cameras ?? "-"}
          accent={summary && summary.active_cameras > 0 ? "green" : "default"}
        />
        <StatTile label="Open Incidents" value={summary?.open_incidents ?? "-"} accent="red" />
        <StatTile label="Incidents (24h)" value={summary?.incidents_last_24h ?? "-"} accent="amber" />
      </div>

      <div className="bg-ops-panel border border-ops-border rounded-lg p-5">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400">Cameras</h2>
          <Link to="/cameras" className="text-xs text-ops-accent hover:underline">
            Manage cameras
          </Link>
        </div>
        {(!cameras || cameras.length === 0) && (
          <p className="text-sm text-slate-500">
            No cameras connected yet. Add one under Cameras to start live monitoring.
          </p>
        )}
        {cameras && cameras.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {cameras.map((camera) => {
              const isLive = camera.latest_job_status === "pending" || camera.latest_job_status === "processing";
              return (
                <Link
                  key={camera.id}
                  to={`/cameras/${camera.id}`}
                  className="flex items-center gap-2 text-xs font-mono px-3 py-1.5 rounded-full border border-ops-border bg-ops-panel2 hover:border-ops-accent/40"
                >
                  <span className={`w-1.5 h-1.5 rounded-full ${isLive ? "bg-status-ok animate-pulse" : "bg-ops-borderStrong"}`} />
                  <span className="text-slate-200">{camera.name}</span>
                </Link>
              );
            })}
          </div>
        )}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3.5">
        <StatTile label="Total Videos" value={summary?.total_videos ?? "-"} />
        <StatTile label="Jobs Processing" value={summary?.jobs_processing ?? "-"} accent="amber" />
        <StatTile label="Jobs Completed" value={summary?.jobs_completed ?? "-"} accent="green" />
        <StatTile label="Jobs Failed" value={summary?.jobs_failed ?? "-"} accent="red" />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
        <div className="bg-ops-panel border border-ops-border rounded-lg p-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400 mb-4">Incidents by Priority</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={priorityData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#262626" vertical={false} />
              <XAxis dataKey="priority" stroke="#737373" fontSize={11} tickLine={false} axisLine={{ stroke: "#262626" }} />
              <YAxis stroke="#737373" fontSize={11} allowDecimals={false} tickLine={false} axisLine={false} />
              <Tooltip
                cursor={{ fill: "rgba(255,255,255,0.06)" }}
                contentStyle={{ background: "#111111", border: "1px solid #262626", borderRadius: 8, fontSize: 12 }}
                labelStyle={{ color: "#e5e5e5" }}
              />
              <Bar dataKey="count" fill="#ffffff" radius={[4, 4, 0, 0]} maxBarSize={48} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-ops-panel border border-ops-border rounded-lg p-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400 mb-4">Recent Incidents</h2>
          {incidents?.items.length === 0 && (
            <p className="text-sm text-slate-500">No incidents yet. The dashboard fills in once a camera or video is analyzed.</p>
          )}
          <ul className="space-y-1">
            {incidents?.items.map((incident: Incident) => (
              <li
                key={incident.id}
                className="flex items-center justify-between gap-3 py-2.5 border-b border-ops-border last:border-0"
              >
                <span className="text-sm text-slate-300 truncate min-w-0">{incident.summary}</span>
                <div className="flex items-center gap-2 shrink-0">
                  <span
                    className={`text-[10px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded border ${
                      priorityPill[incident.priority] ?? priorityPill.low
                    }`}
                  >
                    {incident.priority}
                  </span>
                  <span className="tabular text-sm font-medium text-ops-accent">{incident.risk_score.toFixed(1)}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
