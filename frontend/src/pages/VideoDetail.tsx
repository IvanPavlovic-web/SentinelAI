import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import type { Incident, ProcessingJob, VideoSource } from "../types";
import { useWebSocket } from "../hooks/useWebSocket";

export default function VideoDetail() {
  const { id } = useParams();
  const videoId = Number(id);
  const queryClient = useQueryClient();

  const { data: video } = useQuery({
    queryKey: ["video", videoId],
    queryFn: async () => (await apiClient.get<VideoSource>(`/api/videos/${videoId}`)).data,
    enabled: !!videoId,
  });

  const { data: incidents } = useQuery({
    queryKey: ["incidents-for-video", videoId],
    queryFn: async () =>
      (await apiClient.get<{ items: Incident[] }>("/api/incidents", { params: { page_size: 50 } })).data.items,
    enabled: !!videoId,
  });

  const reprocessMutation = useMutation({
    mutationFn: async () => apiClient.post<ProcessingJob>(`/api/videos/${videoId}/process`),
    onSuccess: (res) => {
      queryClient.setQueryData(["latest-job", videoId], res.data);
    },
  });

  const latestJob = reprocessMutation.data?.data;
  const { lastMessage: jobUpdate } = useWebSocket<{ status: string; progress_percent: number }>(
    latestJob ? `/ws/jobs/${latestJob.id}` : null
  );

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[11px] uppercase tracking-widest2 text-ops-accent font-medium mb-1">Video Detail</p>
        <h1 className="font-display text-2xl font-semibold truncate">{video?.original_filename ?? "Video"}</h1>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="md:col-span-2 bg-ops-panel border border-ops-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Preview</h2>
          <div className="aspect-video bg-black rounded flex items-center justify-center text-slate-600 text-sm">
            Video playback is served from backend uploads/ (configure a static mount or signed URL in production).
          </div>
          <div className="mt-4 flex items-center gap-4 text-sm text-slate-400">
            <span>Duration: {video?.duration_seconds?.toFixed(0) ?? "-"}s</span>
            <span>FPS: {video?.fps?.toFixed(1) ?? "-"}</span>
            <span>
              Resolution: {video?.width && video?.height ? `${video.width}x${video.height}` : "-"}
            </span>
          </div>
          <button
            onClick={() => reprocessMutation.mutate()}
            className="mt-4 rounded bg-ops-accent text-ops-bg font-semibold text-sm px-4 py-2 hover:bg-ops-accentDim"
          >
            Reprocess Video
          </button>
          {jobUpdate && (
            <p className="mt-2 text-sm text-slate-400">
              Job status: <span className="text-ops-accent">{jobUpdate.status}</span> (
              {jobUpdate.progress_percent.toFixed(0)}%)
            </p>
          )}
        </div>

        <div className="bg-ops-panel border border-ops-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Incidents</h2>
          <ul className="space-y-2 text-sm">
            {incidents?.length === 0 && <p className="text-slate-500">No incidents detected.</p>}
            {incidents?.map((incident) => (
              <li key={incident.id} className="border-b border-ops-border pb-2">
                <p className="text-slate-300">{incident.summary}</p>
                <p className="text-xs text-status-critical font-semibold">Risk: {incident.star_risk_score.toFixed(1)}</p>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
