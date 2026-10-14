import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import type { Incident, IncidentStatus, PaginatedIncidents } from "../types";

const priorityColor: Record<string, string> = {
  low: "text-slate-400",
  medium: "text-amber-400",
  high: "text-orange-400",
  critical: "text-red-500",
};

export default function Incidents() {
  const queryClient = useQueryClient();
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [priorityFilter, setPriorityFilter] = useState<string>("");
  const [selected, setSelected] = useState<Incident | null>(null);
  const [notes, setNotes] = useState("");

  const { data } = useQuery({
    queryKey: ["incidents", statusFilter, priorityFilter],
    queryFn: async () =>
      (
        await apiClient.get<PaginatedIncidents>("/api/incidents", {
          params: { status: statusFilter || undefined, priority: priorityFilter || undefined, page_size: 50 },
        })
      ).data,
    refetchInterval: 10000,
  });

  const updateStatus = useMutation({
    mutationFn: async ({ id, status }: { id: number; status: IncidentStatus }) =>
      apiClient.patch(`/api/incidents/${id}/status`, { status, resolution_notes: notes || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["incidents"] });
      setSelected(null);
      setNotes("");
    },
  });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Incidents</h1>

      <div className="flex gap-3">
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="rounded bg-slate-900 border border-ops-border px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="acknowledged">Acknowledged</option>
          <option value="resolved">Resolved</option>
          <option value="dismissed">Dismissed</option>
        </select>
        <select
          value={priorityFilter}
          onChange={(e) => setPriorityFilter(e.target.value)}
          className="rounded bg-slate-900 border border-ops-border px-3 py-2 text-sm"
        >
          <option value="">All priorities</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
          <option value="critical">Critical</option>
        </select>
      </div>

      <div className="bg-ops-panel border border-ops-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-slate-400 text-left">
            <tr>
              <th className="px-4 py-3">Object</th>
              <th className="px-4 py-3">Risk</th>
              <th className="px-4 py-3">Priority</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3">Detected</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {data?.items.map((incident) => (
              <tr key={incident.id} className="border-t border-ops-border hover:bg-slate-900/40">
                <td className="px-4 py-3">{incident.object_class}</td>
                <td className="px-4 py-3 font-semibold">{incident.star_risk_score.toFixed(1)}</td>
                <td className={`px-4 py-3 uppercase ${priorityColor[incident.priority]}`}>{incident.priority}</td>
                <td className="px-4 py-3">{incident.status}</td>
                <td className="px-4 py-3 text-slate-400">{new Date(incident.detected_at).toLocaleString()}</td>
                <td className="px-4 py-3 text-right">
                  <button onClick={() => setSelected(incident)} className="text-amber-400 hover:underline">
                    Review
                  </button>
                </td>
              </tr>
            ))}
            {data?.items.length === 0 && (
              <tr>
                <td className="px-4 py-3 text-slate-500" colSpan={6}>
                  No incidents found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-ops-panel border border-ops-border rounded-lg p-6 w-full max-w-md">
            <h2 className="text-lg font-bold mb-2">Incident #{selected.id}</h2>
            <p className="text-sm text-slate-300 mb-4">{selected.summary}</p>
            <textarea
              placeholder="Resolution notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className="w-full rounded bg-slate-900 border border-ops-border px-3 py-2 text-sm mb-4"
              rows={3}
            />
            <div className="flex gap-3 justify-end">
              <button onClick={() => setSelected(null)} className="text-sm text-slate-400 hover:text-slate-200">
                Cancel
              </button>
              <button
                onClick={() => updateStatus.mutate({ id: selected.id, status: "dismissed" })}
                className="rounded bg-slate-700 text-sm px-4 py-2 hover:bg-slate-600"
              >
                Dismiss
              </button>
              <button
                onClick={() => updateStatus.mutate({ id: selected.id, status: "resolved" })}
                className="rounded bg-amber-500 text-slate-950 font-semibold text-sm px-4 py-2 hover:bg-amber-400"
              >
                Resolve
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
