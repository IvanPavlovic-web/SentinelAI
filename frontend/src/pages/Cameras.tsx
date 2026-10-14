import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiClient } from "../api/client";
import type { Camera, CameraConnectionTestResult } from "../types";

export default function Cameras() {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [location, setLocation] = useState("");
  const [rtspUrl, setRtspUrl] = useState("");
  const [testResult, setTestResult] = useState<CameraConnectionTestResult | null>(null);

  // Each camera's latest_job_status comes back inline with the list itself
  // (GET /api/cameras/{id}/jobs isn't called per row here), so the status
  // chip below needs exactly one request regardless of camera count.
  const { data: cameras, isLoading } = useQuery({
    queryKey: ["cameras"],
    queryFn: async () => (await apiClient.get<Camera[]>("/api/cameras")).data,
    refetchInterval: 8000,
  });

  const testMutation = useMutation({
    mutationFn: async () => (await apiClient.post<CameraConnectionTestResult>("/api/cameras/test-connection", { rtsp_url: rtspUrl })).data,
    onSuccess: (result) => setTestResult(result),
    onError: () => setTestResult({ ok: false, detail: "Connection test failed." }),
  });

  const createMutation = useMutation({
    mutationFn: async () => apiClient.post("/api/cameras", { name, location: location || null, rtsp_url: rtspUrl || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      setName("");
      setLocation("");
      setRtspUrl("");
      setTestResult(null);
    },
  });

  const startMutation = useMutation({
    mutationFn: async (cameraId: number) => apiClient.post(`/api/cameras/${cameraId}/start`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
  });

  const stopMutation = useMutation({
    mutationFn: async (cameraId: number) => apiClient.post(`/api/cameras/${cameraId}/stop`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: async (cameraId: number) => apiClient.delete(`/api/cameras/${cameraId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["cameras"] }),
  });

  const statusFor = (camera: Camera): { label: string; dotClass: string } => {
    if (camera.latest_job_status === "pending" || camera.latest_job_status === "processing") {
      return { label: "Live", dotClass: "bg-status-ok animate-pulse" };
    }
    if (camera.latest_job_status === "failed") {
      return { label: "Error", dotClass: "bg-status-critical" };
    }
    return { label: "Idle", dotClass: "bg-ops-borderStrong" };
  };

  return (
    <div className="space-y-6">
      <div>
        <p className="text-[11px] uppercase tracking-widest2 text-ops-accent font-medium mb-1">Monitoring</p>
        <h1 className="font-display text-2xl font-semibold">Cameras</h1>
      </div>

      <div className="bg-ops-panel border border-ops-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-ops-panel2 text-slate-400 text-left">
            <tr>
              <th className="px-4 py-3 text-xs uppercase tracking-widest2 font-medium">Status</th>
              <th className="px-4 py-3 text-xs uppercase tracking-widest2 font-medium">Name</th>
              <th className="px-4 py-3 text-xs uppercase tracking-widest2 font-medium">Location</th>
              <th className="px-4 py-3 text-xs uppercase tracking-widest2 font-medium">Stream</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-4 py-3 text-slate-500" colSpan={5}>
                  Loading cameras...
                </td>
              </tr>
            )}
            {cameras?.map((camera) => {
              const { label, dotClass } = statusFor(camera);
              const isLive = camera.latest_job_status === "pending" || camera.latest_job_status === "processing";
              return (
                <tr key={camera.id} className="border-t border-ops-border hover:bg-white/[0.02]">
                  <td className="px-4 py-3">
                    <span className="flex items-center gap-2 text-xs font-mono uppercase tracking-wide">
                      <span className={`w-1.5 h-1.5 rounded-full ${dotClass}`} />
                      {label}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <Link to={`/cameras/${camera.id}`} className="text-ops-accent hover:underline">
                      {camera.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-slate-400">{camera.location ?? "-"}</td>
                  <td className="px-4 py-3 text-slate-500 font-mono text-xs truncate max-w-[220px]">
                    {camera.rtsp_url ?? "not configured"}
                  </td>
                  <td className="px-4 py-3 text-right whitespace-nowrap">
                    {isLive ? (
                      <button
                        onClick={() => stopMutation.mutate(camera.id)}
                        disabled={stopMutation.isPending}
                        className="text-status-critical hover:underline disabled:opacity-50"
                      >
                        Stop
                      </button>
                    ) : (
                      <button
                        onClick={() => startMutation.mutate(camera.id)}
                        disabled={startMutation.isPending || !camera.rtsp_url}
                        className="text-ops-accent hover:underline disabled:opacity-40"
                        title={!camera.rtsp_url ? "Add a stream URL first" : undefined}
                      >
                        Start
                      </button>
                    )}
                    <button
                      onClick={() => {
                        if (window.confirm(`Remove camera "${camera.name}"? This cannot be undone.`)) deleteMutation.mutate(camera.id);
                      }}
                      className="ml-3 text-slate-500 hover:text-status-critical"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              );
            })}
            {cameras?.length === 0 && (
              <tr>
                <td className="px-4 py-3 text-slate-500" colSpan={5}>
                  No cameras added yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="bg-ops-panel border border-ops-border rounded-lg p-5 max-w-xl">
        <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400 mb-4">Connect a camera</h2>
        <p className="text-xs text-slate-500 mb-4">
          Enter your camera's RTSP stream URL. Most home IP cameras (Reolink, TP-Link Tapo, Hikvision, Wyze with RTSP
          firmware, and similar) expose one, typically in the form
          <code className="mx-1 text-slate-400">rtsp://user:password@camera-ip:554/stream1</code>
          and listed in the camera's own app under network or advanced settings.
        </p>
        <div className="space-y-3">
          <input
            placeholder="Camera name (e.g. Front Door)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="w-full rounded bg-ops-panel2 border border-ops-border px-3 py-2 text-sm"
          />
          <input
            placeholder="Location (optional)"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
            className="w-full rounded bg-ops-panel2 border border-ops-border px-3 py-2 text-sm"
          />
          <input
            placeholder="rtsp://..."
            value={rtspUrl}
            onChange={(e) => {
              setRtspUrl(e.target.value);
              setTestResult(null);
            }}
            className="w-full rounded bg-ops-panel2 border border-ops-border px-3 py-2 text-sm font-mono"
          />
          <div className="flex items-center gap-3">
            <button
              onClick={() => testMutation.mutate()}
              disabled={!rtspUrl || testMutation.isPending}
              className="rounded border border-ops-border text-sm px-3 py-2 hover:bg-white/[0.03] disabled:opacity-40"
            >
              {testMutation.isPending ? "Testing..." : "Test connection"}
            </button>
            <button
              onClick={() => createMutation.mutate()}
              disabled={!name || createMutation.isPending}
              className="rounded bg-ops-accent text-ops-bg font-semibold text-sm px-4 py-2 hover:bg-ops-accentDim disabled:opacity-50"
            >
              Add camera
            </button>
          </div>
          {testResult && (
            <p className={`text-xs ${testResult.ok ? "text-status-ok" : "text-status-critical"}`}>
              {testResult.ok
                ? `Connected (${testResult.width ?? "?"}x${testResult.height ?? "?"} @ ${testResult.fps?.toFixed(0) ?? "?"} fps).`
                : testResult.detail ?? "Could not connect."}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}
