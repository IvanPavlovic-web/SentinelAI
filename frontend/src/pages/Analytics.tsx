import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, AreaChart, Area } from "recharts";
import { apiClient } from "../api/client";
import type { IncidentAnalytics } from "../types";

const gridStroke = "#262626";
const axisStroke = "#737373";
const tooltipStyle = { background: "#111111", border: "1px solid #262626", borderRadius: 8, fontSize: 12 };
const tooltipLabelStyle = { color: "#e5e5e5" };

const DAY_RANGES = [7, 14, 30];

function formatHour(hour: number): string {
  return `${hour.toString().padStart(2, "0")}:00`;
}

/** The API only returns rows that actually have incidents, so hours/days
 * with zero are missing entirely; filled back in here so the chart reads
 * as a real 24h/N-day axis instead of a sparse, confusing one. */
function fillHours(data: IncidentAnalytics["by_hour"]): { hour: string; count: number }[] {
  const byHour = new Map(data.map((d) => [d.hour, d.count]));
  return Array.from({ length: 24 }, (_, h) => ({ hour: formatHour(h), count: byHour.get(h) ?? 0 }));
}

function fillDays(data: IncidentAnalytics["by_day"], days: number): { date: string; count: number }[] {
  const byDate = new Map(data.map((d) => [d.date, d.count]));
  const out: { date: string; count: number }[] = [];
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() - i);
    const key = d.toISOString().slice(0, 10);
    out.push({ date: key.slice(5), count: byDate.get(key) ?? 0 });
  }
  return out;
}

export default function Analytics() {
  const [days, setDays] = useState(14);

  const { data } = useQuery({
    queryKey: ["incident-analytics", days],
    queryFn: async () => (await apiClient.get<IncidentAnalytics>("/api/dashboard/analytics", { params: { days } })).data,
    refetchInterval: 30000,
  });

  const hourlyData = data ? fillHours(data.by_hour) : [];
  const dailyData = data ? fillDays(data.by_day, days) : [];
  const totalIncidents = data?.by_object_class.reduce((sum, c) => sum + c.count, 0) ?? 0;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-widest2 text-ops-accent font-medium mb-1">Trends</p>
          <h1 className="font-display text-2xl font-semibold">Analytics</h1>
        </div>
        <div className="flex items-center gap-1.5 text-xs">
          {DAY_RANGES.map((d) => (
            <button
              key={d}
              onClick={() => setDays(d)}
              className={`px-3 py-1.5 rounded border ${
                days === d
                  ? "border-ops-accent text-ops-accent bg-ops-accent/10"
                  : "border-ops-border text-slate-400 hover:text-slate-200"
              }`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>

      {totalIncidents === 0 && (
        <div className="bg-ops-panel border border-ops-border rounded-lg p-5">
          <p className="text-sm text-slate-500">
            No incidents recorded yet. Charts fill in once cameras or videos start producing incidents.
          </p>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5">
        <div className="bg-ops-panel border border-ops-border rounded-lg p-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400 mb-4">
            Incidents by hour of day <span className="text-slate-600 normal-case tracking-normal">(UTC, all-time)</span>
          </h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={hourlyData}>
              <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} vertical={false} />
              <XAxis dataKey="hour" stroke={axisStroke} fontSize={10} interval={2} tickLine={false} axisLine={{ stroke: gridStroke }} />
              <YAxis stroke={axisStroke} fontSize={11} allowDecimals={false} tickLine={false} axisLine={false} />
              <Tooltip cursor={{ fill: "rgba(255,255,255,0.06)" }} contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} />
              <Bar dataKey="count" fill="#ffffff" radius={[3, 3, 0, 0]} maxBarSize={18} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="bg-ops-panel border border-ops-border rounded-lg p-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400 mb-4">
            Daily trend <span className="text-slate-600 normal-case tracking-normal">(last {days} days)</span>
          </h2>
          <ResponsiveContainer width="100%" height={220}>
            <AreaChart data={dailyData}>
              <defs>
                <linearGradient id="dailyFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#ffffff" stopOpacity={0.25} />
                  <stop offset="100%" stopColor="#ffffff" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke={gridStroke} vertical={false} />
              <XAxis dataKey="date" stroke={axisStroke} fontSize={10} tickLine={false} axisLine={{ stroke: gridStroke }} />
              <YAxis stroke={axisStroke} fontSize={11} allowDecimals={false} tickLine={false} axisLine={false} />
              <Tooltip contentStyle={tooltipStyle} labelStyle={tooltipLabelStyle} />
              <Area type="monotone" dataKey="count" stroke="#ffffff" strokeWidth={2} fill="url(#dailyFill)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3.5">
        <div className="bg-ops-panel border border-ops-border rounded-lg p-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400 mb-4">By camera</h2>
          {(!data || data.by_camera.length === 0) && <p className="text-sm text-slate-500">No data yet.</p>}
          <ul className="space-y-2">
            {data?.by_camera.map((c) => (
              <li key={c.camera_id} className="flex items-center justify-between gap-3 text-sm py-1.5 border-b border-ops-border last:border-0">
                <span className="text-slate-300 truncate min-w-0">{c.camera_name}</span>
                <span className="flex items-center gap-3 shrink-0 tabular">
                  <span className="text-slate-500 text-xs">avg risk {c.avg_risk_score.toFixed(1)}</span>
                  <span className="text-ops-accent font-semibold">{c.count}</span>
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="bg-ops-panel border border-ops-border rounded-lg p-5">
          <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400 mb-4">By object class</h2>
          {(!data || data.by_object_class.length === 0) && <p className="text-sm text-slate-500">No data yet.</p>}
          <div className="flex flex-wrap gap-2">
            {data?.by_object_class.map((c) => (
              <span
                key={c.object_class}
                className="flex items-center gap-1.5 text-xs font-mono px-2.5 py-1 rounded-full border border-ops-border bg-ops-panel2"
              >
                <span className="uppercase tracking-wide text-slate-300">{c.object_class}</span>
                <span className="tabular text-ops-accent font-semibold">{c.count}</span>
              </span>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
