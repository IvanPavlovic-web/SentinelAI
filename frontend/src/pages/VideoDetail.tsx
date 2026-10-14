import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, authenticatedStreamUrl } from "../api/client";
import type {
  ActivityEvent,
  Incident,
  JobDetectionsSummary,
  JobProgressMessage,
  ProcessingJob,
  VideoSource,
} from "../types";
import { useWebSocket } from "../hooks/useWebSocket";

const statusLabel: Record<string, string> = {
  pending: "Queued",
  processing: "Analyzing…",
  completed: "Completed",
  failed: "Failed",
};

const severityStyle: Record<string, string> = {
  critical: "text-status-critical border-status-critical/40 bg-status-critical/10 font-bold",
  high: "text-status-high border-status-high/40 bg-status-high/10",
  medium: "text-status-medium border-status-medium/40 bg-status-medium/10",
  low: "text-status-low border-ops-border bg-transparent",
};

const eventTypeIcon: Record<string, string> = {
  weapon: "⚠",
  anomaly: "◆",
  escalation: "▲",
  status: "·",
};

function formatClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export default function VideoDetail() {
  const { id } = useParams();
  const videoId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logEndRef = useRef<HTMLDivElement>(null);

  const { data: video } = useQuery({
    queryKey: ["video", videoId],
    queryFn: async () => (await apiClient.get<VideoSource>(`/api/videos/${videoId}`)).data,
    enabled: !!videoId,
  });

  // Every job ever run for this video, newest first: lets the page find
  // and subscribe to live progress right after upload, without requiring
  // the user to click "Reprocess" first.
  const { data: jobs } = useQuery({
    queryKey: ["video-jobs", videoId],
    queryFn: async () => (await apiClient.get<ProcessingJob[]>(`/api/videos/${videoId}/jobs`)).data,
    enabled: !!videoId,
    refetchInterval: (query) => {
      const latest = query.state.data?.[0];
      return latest && (latest.status === "pending" || latest.status === "processing") ? 4000 : false;
    },
  });

  const reprocessMutation = useMutation({
    mutationFn: async () => apiClient.post<ProcessingJob>(`/api/videos/${videoId}/process`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["video-jobs", videoId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async () => apiClient.delete(`/api/videos/${videoId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["videos"] });
      navigate("/videos");
    },
  });

  const activeJob = jobs?.[0];
  const isLive = activeJob?.status === "pending" || activeJob?.status === "processing";

  const { lastMessage: jobUpdate, connected } = useWebSocket<JobProgressMessage>(
    activeJob ? `/ws/jobs/${activeJob.id}` : null
  );

  // Once a job finishes, pull the full per-track breakdown (confidence,
  // observation count, risk score). The WebSocket only carries the
  // lightweight running class-count totals while processing.
  const { data: detections } = useQuery({
    queryKey: ["job-detections", activeJob?.id],
    queryFn: async () =>
      (await apiClient.get<JobDetectionsSummary>(`/api/jobs/${activeJob!.id}/detections`)).data,
    enabled: !!activeJob && activeJob.status === "completed",
  });

  // Full canonical event log once the job completes (the WebSocket only
  // ever carries the newest ~15 events while processing).
  const { data: finalEvents } = useQuery({
    queryKey: ["job-events", activeJob?.id],
    queryFn: async () => (await apiClient.get<ActivityEvent[]>(`/api/jobs/${activeJob!.id}/events`)).data,
    enabled: !!activeJob && activeJob.status === "completed",
  });

  // While a job is live, accumulate every event seen over the WebSocket
  // (deduped by id) rather than just showing the latest tick's slice, so
  // the feed on the right reads as a continuous narration instead of
  // losing earlier lines.
  const [liveEvents, setLiveEvents] = useState<ActivityEvent[]>([]);
  useEffect(() => {
    setLiveEvents([]);
  }, [activeJob?.id]);
  useEffect(() => {
    if (!jobUpdate?.recent_events?.length) return;
    setLiveEvents((prev) => {
      const byId = new Map(prev.map((e) => [e.id, e]));
      for (const e of jobUpdate.recent_events) byId.set(e.id, e);
      return Array.from(byId.values()).sort((a, b) => a.timestamp_seconds - b.timestamp_seconds || a.id - b.id);
    });
  }, [jobUpdate]);

  const events = activeJob?.status === "completed" ? finalEvents ?? [] : liveEvents;

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [events.length]);

  const { data: incidents } = useQuery({
    queryKey: ["incidents-for-job", activeJob?.id],
    queryFn: async () =>
      (
        await apiClient.get<{ items: Incident[] }>("/api/incidents", {
          params: { processing_job_id: activeJob!.id, page_size: 50 },
        })
      ).data.items,
    enabled: !!activeJob,
    refetchInterval: isLive ? 5000 : false,
  });

  useEffect(() => {
    if (activeJob?.status === "completed" || activeJob?.status === "failed") {
      queryClient.invalidateQueries({ queryKey: ["video", videoId] });
    }
  }, [activeJob?.status, queryClient, videoId]);

  const liveStatus = jobUpdate?.status ?? activeJob?.status;
  const liveProgress = jobUpdate?.progress_percent ?? activeJob?.progress_percent ?? 0;
  const liveCounts = jobUpdate?.class_counts ?? detections?.class_counts ?? {};
  const liveTotal = jobUpdate?.total_tracked_objects ?? detections?.total_tracked_objects ?? 0;
  const classEntries = Object.entries(liveCounts).sort((a, b) => b[1] - a[1]);

  const worstSeverity = events.reduce<string>((worst, e) => {
    const rank: Record<string, number> = { low: 0, medium: 1, high: 2, critical: 3 };
    return rank[e.severity] > rank[worst] ? e.severity : worst;
  }, "low");

  // Prefer the annotated preview (detection boxes/track IDs burned in) once
  // it exists for the latest completed job; otherwise fall back to the raw
  // upload so the preview is never empty, even before the first analysis
  // finishes.
  const hasAnnotated = activeJob?.status === "completed" && activeJob.has_annotated_video;
  const previewSrc = videoId
    ? hasAnnotated
      ? authenticatedStreamUrl(`/api/jobs/${activeJob!.id}/annotated-video`)
      : authenticatedStreamUrl(`/api/videos/${videoId}/stream`)
    : undefined;

  const handleDelete = () => {
    if (window.confirm(`Delete "${video?.original_filename ?? "this video"}"? This cannot be undone.`)) {
      deleteMutation.mutate();
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-widest2 text-ops-accent font-medium mb-1">Video Detail</p>
          <h1 className="font-display text-2xl font-semibold truncate">{video?.original_filename ?? "Video"}</h1>
        </div>
        <button
          onClick={handleDelete}
          disabled={deleteMutation.isPending}
          className="shrink-0 rounded-md border border-status-critical/40 text-status-critical text-sm font-medium px-3 py-1.5 hover:bg-status-critical/10 disabled:opacity-50"
        >
          {deleteMutation.isPending ? "Deleting…" : "Delete Video"}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-ops-panel border border-ops-border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400">Preview</h2>
              {hasAnnotated && (
                <span className="text-[10px] font-mono uppercase tracking-wide text-ops-accent border border-ops-accent/40 rounded px-1.5 py-0.5">
                  AI detection overlay
                </span>
              )}
            </div>
            {previewSrc ? (
              <video key={previewSrc} controls className="w-full rounded bg-black aspect-video" src={previewSrc} />
            ) : (
              <div className="aspect-video bg-black rounded flex items-center justify-center text-slate-600 text-sm">
                No video available.
              </div>
            )}
            {!hasAnnotated && (
              <p className="mt-2 text-xs text-slate-500">
                {isLive
                  ? "Showing the original upload while analysis runs. This will switch to the detection overlay once processing completes."
                  : "Showing the original upload. Run analysis to see detection boxes burned in."}
              </p>
            )}
            <div className="mt-3 flex items-center gap-4 text-sm text-slate-400 tabular">
              <span>Duration: {video?.duration_seconds?.toFixed(0) ?? "-"}s</span>
              <span>FPS: {video?.fps?.toFixed(1) ?? "-"}</span>
              <span>Resolution: {video?.width && video?.height ? `${video.width}x${video.height}` : "-"}</span>
            </div>
            <button
              onClick={() => reprocessMutation.mutate()}
              disabled={isLive}
              className="mt-4 rounded bg-ops-accent text-ops-bg font-semibold text-sm px-4 py-2 hover:bg-ops-accentDim disabled:opacity-50"
            >
              {isLive ? "Analyzing…" : "Reprocess Video"}
            </button>
          </div>

          <div className="bg-ops-panel border border-ops-border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400">Analysis Status</h2>
              {isLive && (
                <span className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wide text-ops-accent">
                  <span className="w-1.5 h-1.5 rounded-full bg-ops-accent animate-pulse" />
                  {connected ? "live" : "connecting…"}
                </span>
              )}
            </div>
            {!activeJob && <p className="text-sm text-slate-500">No analysis job yet.</p>}
            {activeJob && (
              <>
                <div className="flex items-center justify-between text-sm mb-2">
                  <span className={liveStatus === "failed" ? "text-status-critical font-semibold" : "text-slate-200"}>
                    {statusLabel[liveStatus ?? "pending"]}
                  </span>
                  <span className="tabular text-slate-400">{liveProgress.toFixed(0)}%</span>
                </div>
                <div className="h-1.5 rounded-full bg-ops-panel2 overflow-hidden">
                  <div
                    className={`h-full transition-[width] duration-300 ${
                      liveStatus === "failed" ? "bg-status-critical" : "bg-ops-accent"
                    }`}
                    style={{ width: `${Math.max(liveStatus === "failed" ? 100 : liveProgress, 2)}%` }}
                  />
                </div>
                {liveStatus === "failed" && (jobUpdate?.error_message ?? activeJob.error_message) && (
                  <p className="mt-2 text-xs text-status-critical">
                    {jobUpdate?.error_message ?? activeJob.error_message}
                  </p>
                )}
              </>
            )}
          </div>

          <div className="bg-ops-panel border border-ops-border rounded-lg p-4">
            <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400 mb-3">
              Detected {liveTotal > 0 && <span className="tabular text-ops-accent">({liveTotal})</span>}
            </h2>
            {classEntries.length === 0 && (
              <p className="text-sm text-slate-500">
                {isLive
                  ? "Watching for people and vehicles in the footage…"
                  : "Nothing detected yet. Run analysis to find out what's in this video."}
              </p>
            )}
            {classEntries.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {classEntries.map(([objectClass, count]) => (
                  <span
                    key={objectClass}
                    className="flex items-center gap-1.5 text-xs font-mono px-2.5 py-1 rounded-full border border-ops-border bg-ops-panel2"
                  >
                    <span className="uppercase tracking-wide text-slate-300">{objectClass}</span>
                    <span className="tabular text-ops-accent font-semibold">{count}</span>
                  </span>
                ))}
              </div>
            )}

            {detections && detections.tracks.length > 0 && (
              <table className="w-full text-sm mt-4">
                <thead className="text-slate-500 text-left text-xs uppercase tracking-widest2">
                  <tr>
                    <th className="py-2 pr-2">Track</th>
                    <th className="py-2 pr-2">Class</th>
                    <th className="py-2 pr-2">Color</th>
                    <th className="py-2 pr-2">Confidence</th>
                    <th className="py-2 pr-2">Observations</th>
                    <th className="py-2">Risk</th>
                  </tr>
                </thead>
                <tbody>
                  {detections.tracks.map((t) => (
                    <tr key={t.track_number} className="border-t border-ops-border">
                      <td className="py-2 pr-2 tabular">#{t.track_number}</td>
                      <td className="py-2 pr-2 capitalize">{t.object_class}</td>
                      <td className="py-2 pr-2 capitalize text-slate-400">
                        {t.dominant_color !== "unknown" ? t.dominant_color : "-"}
                      </td>
                      <td className="py-2 pr-2 tabular">
                        {t.max_confidence !== null ? `${(t.max_confidence * 100).toFixed(0)}%` : "-"}
                      </td>
                      <td className="py-2 pr-2 tabular">{t.observation_count}</td>
                      <td className="py-2 tabular text-ops-accent">{t.final_risk_score.toFixed(1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>

        {/* Right column: live activity narration, the primary surface for
            "what's happening right now", with incidents below it. */}
        <div className="space-y-4">
          <div className="bg-ops-panel border border-ops-border rounded-lg p-4 flex flex-col max-h-[640px]">
            <div className="flex items-center justify-between mb-3 shrink-0">
              <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400">Activity Log</h2>
              {worstSeverity !== "low" && (
                <span className={`text-[10px] font-mono uppercase tracking-wide px-1.5 py-0.5 rounded border ${severityStyle[worstSeverity]}`}>
                  {worstSeverity}
                </span>
              )}
            </div>
            <div className="overflow-y-auto flex-1 space-y-1.5 pr-1">
              {events.length === 0 && (
                <p className="text-sm text-slate-500">
                  {isLive ? "Watching the footage. Narration will appear here as the AI finds things." : "No activity recorded yet."}
                </p>
              )}
              {events.map((e) => (
                <div key={e.id} className={`rounded-md border px-2.5 py-1.5 text-xs ${severityStyle[e.severity]}`}>
                  <div className="flex items-center justify-between gap-2 mb-0.5">
                    <span className="font-mono tabular text-slate-400">{formatClock(e.timestamp_seconds)}</span>
                    <span className="font-mono uppercase tracking-wide text-[10px] opacity-80">
                      {eventTypeIcon[e.event_type] ?? "·"} {e.severity}
                    </span>
                  </div>
                  <p className="leading-snug">{e.description}</p>
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>

          <div className="bg-ops-panel border border-ops-border rounded-lg p-4">
            <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400 mb-3">Incidents</h2>
            <ul className="space-y-2 text-sm">
              {incidents?.length === 0 && <p className="text-slate-500">No incidents detected.</p>}
              {incidents?.map((incident) => (
                <li key={incident.id} className="border-b border-ops-border pb-2 last:border-0">
                  <p className="text-slate-300">{incident.summary}</p>
                  <p className="text-xs text-status-critical font-semibold">Risk: {incident.risk_score.toFixed(1)}</p>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}
