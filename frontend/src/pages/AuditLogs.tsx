import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import type { PaginatedAuditLogs } from "../types";

export default function AuditLogs() {
  const [page, setPage] = useState(1);

  const { data } = useQuery({
    queryKey: ["audit-logs", page],
    queryFn: async () =>
      (await apiClient.get<PaginatedAuditLogs>("/api/audit-logs", { params: { page, page_size: 25 } })).data,
  });

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[11px] uppercase tracking-widest2 text-ops-accent font-medium mb-1">Admin</p>
        <h1 className="font-display text-2xl font-semibold">Audit Logs</h1>
      </div>

      <div className="bg-ops-panel border border-ops-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-ops-panel2 text-slate-400 text-left">
            <tr>
              <th className="px-4 py-3">Action</th>
              <th className="px-4 py-3">Resource</th>
              <th className="px-4 py-3">Details</th>
              <th className="px-4 py-3">IP</th>
              <th className="px-4 py-3">Time</th>
            </tr>
          </thead>
          <tbody>
            {data?.items.map((log) => (
              <tr key={log.id} className="border-t border-ops-border hover:bg-white/[0.02]">
                <td className="px-4 py-3 text-ops-accent">{log.action}</td>
                <td className="px-4 py-3">
                  {log.resource_type ?? "-"} {log.resource_id ? `#${log.resource_id}` : ""}
                </td>
                <td className="px-4 py-3 text-slate-400">{log.details ?? "-"}</td>
                <td className="px-4 py-3 text-slate-500">{log.ip_address ?? "-"}</td>
                <td className="px-4 py-3 text-slate-400">{new Date(log.created_at).toLocaleString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm">
        <button
          disabled={page <= 1}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          className="rounded bg-ops-borderStrong px-3 py-1 disabled:opacity-40"
        >
          Previous
        </button>
        <span className="text-slate-400">
          Page {page} of {totalPages}
        </span>
        <button
          disabled={page >= totalPages}
          onClick={() => setPage((p) => p + 1)}
          className="rounded bg-ops-borderStrong px-3 py-1 disabled:opacity-40"
        >
          Next
        </button>
      </div>
    </div>
  );
}
