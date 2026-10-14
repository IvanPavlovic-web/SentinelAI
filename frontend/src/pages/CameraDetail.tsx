import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient, authenticatedStreamUrl } from "../api/client";
import type {
  ActivityEvent,
  Camera,
  CameraSnapshotInfo,
  Incident,
  JobProgressMessage,
  ProcessingJob,
  Rule,
  Zone,
  ZoneSeverity,
} from "../types";
import { useWebSocket } from "../hooks/useWebSocket";

const ZONE_SEVERITIES: ZoneSeverity[] = ["low", "medium", "high", "critical"];
const ZONE_SEVERITY_COLOR: Record<ZoneSeverity, string> = {
  low: "#64748b",
  medium: "#eab308",
  high: "#f97316",
  critical: "#ef4444",
};
const RULE_OBJECT_CLASSES = ["person", "car", "motorcycle", "bus", "truck", "knife", "gun", "pistol", "rifle"];

function formatRelativeTime(iso: string | null): string {
  if (!iso) return "never";
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (seconds < 5) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

/** Converts a click on the <img> (rendered with object-contain, which can
 * letterbox if the image's aspect ratio doesn't match its box) into a
 * point normalized to [0,1] in the image's own pixel space -- matching
 * the backend's zone-polygon coordinate convention. Returns null for a
 * click that landed in the letterboxed margin, not on the image itself. */
function imageClickToNormalizedPoint(e: React.MouseEvent<HTMLElement>, img: HTMLImageElement): [number, number] | null {
  const rect = img.getBoundingClientRect();
  const { naturalWidth, naturalHeight } = img;
  if (!naturalWidth || !naturalHeight || rect.width === 0 || rect.height === 0) return null;

  const containerRatio = rect.width / rect.height;
  const imageRatio = naturalWidth / naturalHeight;
  let contentWidth = rect.width;
  let contentHeight = rect.height;
  let offsetX = 0;
  let offsetY = 0;
  if (imageRatio > containerRatio) {
    contentHeight = rect.width / imageRatio;
    offsetY = (rect.height - contentHeight) / 2;
  } else {
    contentWidth = rect.height * imageRatio;
    offsetX = (rect.width - contentWidth) / 2;
  }

  const x = (e.clientX - rect.left - offsetX) / contentWidth;
  const y = (e.clientY - rect.top - offsetY) / contentHeight;
  if (x < 0 || x > 1 || y < 0 || y > 1) return null;
  return [x, y];
}

function polygonToSvgPoints(polygon: [number, number][]): string {
  return polygon.map(([x, y]) => `${(x * 100).toFixed(2)},${(y * 100).toFixed(2)}`).join(" ");
}

const severityStyle: Record<string, string> = {
  critical: "text-status-critical border-status-critical/40 bg-status-critical/10 font-bold",
  high: "text-status-high border-status-high/40 bg-status-high/10",
  medium: "text-status-medium border-status-medium/40 bg-status-medium/10",
  low: "text-status-low border-ops-border bg-transparent",
};

const eventTypeIcon: Record<string, string> = {
  weapon: "!",
  anomaly: "*",
  escalation: "^",
  status: ".",
};

function formatClock(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

const SNAPSHOT_REFRESH_MS = 1500;

export default function CameraDetail() {
  const { id } = useParams();
  const cameraId = Number(id);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logEndRef = useRef<HTMLDivElement>(null);
  const [snapshotTick, setSnapshotTick] = useState(0);

  const { data: camera } = useQuery({
    queryKey: ["camera", cameraId],
    queryFn: async () => {
      const cameras = (await apiClient.get<Camera[]>("/api/cameras")).data;
      return cameras.find((c) => c.id === cameraId) ?? null;
    },
    enabled: !!cameraId,
  });

  const { data: jobs } = useQuery({
    queryKey: ["camera-jobs", cameraId],
    queryFn: async () => (await apiClient.get<ProcessingJob[]>(`/api/cameras/${cameraId}/jobs`)).data,
    enabled: !!cameraId,
    refetchInterval: 5000,
  });

  const activeJob = jobs?.[0];
  const isLive = activeJob?.status === "pending" || activeJob?.status === "processing";

  useEffect(() => {
    if (!isLive) return;
    const interval = setInterval(() => setSnapshotTick((t) => t + 1), SNAPSHOT_REFRESH_MS);
    return () => clearInterval(interval);
  }, [isLive]);

  // Freshness metadata (separate from the image bytes) so "updated Xs ago"
  // keeps ticking and stays correct even when nothing is currently
  // monitoring -- many of these cameras are refresh-snapshot public
  // webcams that only update every few minutes (see README "Live
  // cameras"), so without this the view just looks frozen/broken.
  const { data: snapshotInfo } = useQuery({
    queryKey: ["camera-snapshot-info", cameraId, snapshotTick],
    queryFn: async () => (await apiClient.get<CameraSnapshotInfo>(`/api/cameras/${cameraId}/snapshot-info`)).data,
    enabled: !!cameraId,
    refetchInterval: isLive ? SNAPSHOT_REFRESH_MS : 10000,
  });
  const [, forceRelativeTimeTick] = useState(0);
  useEffect(() => {
    const interval = setInterval(() => forceRelativeTimeTick((t) => t + 1), 5000);
    return () => clearInterval(interval);
  }, []);

  // --- Zones (see app/routers/zones.py / rules.py) ---
  const { data: zones } = useQuery({
    queryKey: ["zones", cameraId],
    queryFn: async () => (await apiClient.get<Zone[]>("/api/zones", { params: { camera_id: cameraId } })).data,
    enabled: !!cameraId,
  });
  const { data: allRules } = useQuery({
    queryKey: ["rules", cameraId],
    queryFn: async () => (await apiClient.get<Rule[]>("/api/rules", { params: { camera_id: cameraId } })).data,
    enabled: !!cameraId,
  });
  const rulesByZone = (zoneId: number) => allRules?.filter((r) => r.zone_id === zoneId) ?? [];

  const [isDrawingZone, setIsDrawingZone] = useState(false);
  const [drawPoints, setDrawPoints] = useState<[number, number][]>([]);
  const snapshotImgRef = useRef<HTMLImageElement>(null);
  const [zoneName, setZoneName] = useState("");
  const [zoneSeverity, setZoneSeverity] = useState<ZoneSeverity>("medium");
  const [zoneMinDwell, setZoneMinDwell] = useState(10);
  const [ruleClasses, setRuleClasses] = useState<string[]>(["person"]);
  const [ruleAfterHoursOnly, setRuleAfterHoursOnly] = useState(false);
  const [ruleRiskThreshold, setRuleRiskThreshold] = useState(70);
  const [ruleConsecutive, setRuleConsecutive] = useState(3);

  const resetZoneDraft = () => {
    setIsDrawingZone(false);
    setDrawPoints([]);
    setZoneName("");
    setZoneSeverity("medium");
    setZoneMinDwell(10);
    setRuleClasses(["person"]);
    setRuleAfterHoursOnly(false);
    setRuleRiskThreshold(70);
    setRuleConsecutive(3);
  };

  const createZoneMutation = useMutation({
    mutationFn: async () => {
      const zone = (
        await apiClient.post<Zone>("/api/zones", {
          camera_id: cameraId,
          name: zoneName || "Zone",
          severity: zoneSeverity,
          polygon: drawPoints,
          minimum_dwell_seconds: zoneMinDwell,
        })
      ).data;
      if (ruleClasses.length > 0) {
        await apiClient.post("/api/rules", {
          zone_id: zone.id,
          name: `${zone.name} rule`,
          object_classes: ruleClasses.join(","),
          after_hours_only: ruleAfterHoursOnly,
          risk_threshold: ruleRiskThreshold,
          consecutive_required: ruleConsecutive,
        });
      }
      return zone;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["zones", cameraId] });
      resetZoneDraft();
    },
  });

  const deleteZoneMutation = useMutation({
    mutationFn: async (zoneId: number) => apiClient.delete(`/api/zones/${zoneId}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["zones", cameraId] }),
  });

  const handleImageClick = (e: React.MouseEvent<HTMLImageElement>) => {
    if (!isDrawingZone || !snapshotImgRef.current) return;
    const point = imageClickToNormalizedPoint(e, snapshotImgRef.current);
    if (point) setDrawPoints((prev) => [...prev, point]);
  };

  const toggleRuleClass = (cls: string) => {
    setRuleClasses((prev) => (prev.includes(cls) ? prev.filter((c) => c !== cls) : [...prev, cls]));
  };

  const startMutation = useMutation({
    mutationFn: async () => apiClient.post(`/api/cameras/${cameraId}/start`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["camera-jobs", cameraId] }),
  });

  const stopMutation = useMutation({
    mutationFn: async () => apiClient.post(`/api/cameras/${cameraId}/stop`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["camera-jobs", cameraId] }),
  });

  const deleteMutation = useMutation({
    mutationFn: async () => apiClient.delete(`/api/cameras/${cameraId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      navigate("/cameras");
    },
  });

  const { lastMessage: jobUpdate, connected } = useWebSocket<JobProgressMessage>(
    activeJob ? `/ws/jobs/${activeJob.id}` : null
  );

  const [liveEvents, setLiveEvents] = useState<ActivityEvent[]>([]);
  useEffect(() => {
    setLiveEvents([]);
  }, [activeJob?.id]);
  useEffect(() => {
    if (!jobUpdate?.recent_events?.length) return;
    setLiveEvents((prev) => {
      const byId = new Map(prev.map((e) => [e.id, e]));
      for (const e of jobUpdate.recent_events) byId.set(e.id, e);
      const merged = Array.from(byId.values()).sort((a, b) => a.timestamp_seconds - b.timestamp_seconds || a.id - b.id);
      return merged.slice(-200); // bounded for a continuously running session
    });
  }, [jobUpdate]);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [liveEvents.length]);

  const { data: incidents } = useQuery({
    queryKey: ["incidents-for-camera", cameraId],
    queryFn: async () =>
      (await apiClient.get<{ items: Incident[] }>("/api/incidents", { params: { camera_id: cameraId, page_size: 50 } })).data
        .items,
    enabled: !!cameraId,
    refetchInterval: isLive ? 5000 : false,
  });

  const classEntries = Object.entries(jobUpdate?.class_counts ?? {}).sort((a, b) => b[1] - a[1]);
  const snapshotSrc = `${authenticatedStreamUrl(`/api/cameras/${cameraId}/snapshot`)}&t=${snapshotTick}`;

  const handleDelete = () => {
    if (window.confirm(`Remove camera "${camera?.name ?? "this camera"}"? This cannot be undone.`)) {
      deleteMutation.mutate();
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-[11px] uppercase tracking-widest2 text-ops-accent font-medium mb-1">Camera</p>
          <h1 className="font-display text-2xl font-semibold truncate">{camera?.name ?? "Camera"}</h1>
        </div>
        <button
          onClick={handleDelete}
          disabled={deleteMutation.isPending}
          className="shrink-0 rounded-md border border-status-critical/40 text-status-critical text-sm font-medium px-3 py-1.5 hover:bg-status-critical/10 disabled:opacity-50"
        >
          {deleteMutation.isPending ? "Removing..." : "Remove Camera"}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2 space-y-4">
          <div className="bg-ops-panel border border-ops-border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400">Live view</h2>
              <div className="flex items-center gap-3">
                {snapshotInfo?.exists && (
                  <span
                    className="text-[10px] font-mono uppercase tracking-wide text-slate-500"
                    title={snapshotInfo.last_updated ?? undefined}
                  >
                    updated {formatRelativeTime(snapshotInfo.last_updated)}
                  </span>
                )}
                {isLive && (
                  <span className="flex items-center gap-1.5 text-[10px] font-mono uppercase tracking-wide text-ops-accent">
                    <span className="w-1.5 h-1.5 rounded-full bg-ops-accent animate-pulse" />
                    {connected ? "live" : "connecting"}
                  </span>
                )}
              </div>
            </div>
            {snapshotInfo?.exists ? (
              <div className="relative">
                <img
                  key={snapshotTick}
                  ref={snapshotImgRef}
                  src={snapshotSrc}
                  alt="Camera snapshot with detection overlay"
                  className={`w-full rounded bg-black aspect-video object-contain ${isDrawingZone ? "cursor-crosshair" : ""}`}
                  onClick={handleImageClick}
                  onError={(e) => {
                    (e.target as HTMLImageElement).style.opacity = "0.4";
                  }}
                />
                {/* Existing + in-progress zone polygons, drawn in the
                    image's own normalized [0,1] coordinate space via a
                    0-100 viewBox so they track object-contain letterboxing
                    without any extra JS layout math. */}
                <svg className="absolute inset-0 w-full h-full pointer-events-none" viewBox="0 0 100 100" preserveAspectRatio="xMidYMid meet">
                  {zones?.map((zone) => (
                    <polygon
                      key={zone.id}
                      points={polygonToSvgPoints(zone.polygon)}
                      fill={ZONE_SEVERITY_COLOR[zone.severity] + "22"}
                      stroke={ZONE_SEVERITY_COLOR[zone.severity]}
                      strokeWidth={0.3}
                      vectorEffect="non-scaling-stroke"
                    />
                  ))}
                  {isDrawingZone && drawPoints.length > 0 && (
                    <>
                      <polygon
                        points={polygonToSvgPoints(drawPoints)}
                        fill="#38bdf822"
                        stroke="#38bdf8"
                        strokeWidth={0.3}
                        vectorEffect="non-scaling-stroke"
                      />
                      {drawPoints.map(([x, y], i) => (
                        <circle key={i} cx={x * 100} cy={y * 100} r={0.8} fill="#38bdf8" />
                      ))}
                    </>
                  )}
                </svg>
              </div>
            ) : (
              <div className="aspect-video bg-black rounded flex items-center justify-center text-slate-600 text-sm">
                No snapshot yet. Start monitoring at least once to get a reference frame.
              </div>
            )}
            <p className="mt-2 text-xs text-slate-500">
              This is a refreshing snapshot, not a video stream (refresh rate depends on the source -- some public
              webcams only update every few minutes), with detection boxes burned in from the most recently analyzed
              frame.
            </p>
            <div className="mt-4 flex items-center gap-3">
              {isLive ? (
                <button
                  onClick={() => stopMutation.mutate()}
                  disabled={stopMutation.isPending}
                  className="rounded bg-status-critical text-ops-bg font-semibold text-sm px-4 py-2 hover:opacity-90 disabled:opacity-50"
                >
                  {stopMutation.isPending ? "Stopping..." : "Stop Monitoring"}
                </button>
              ) : (
                <button
                  onClick={() => startMutation.mutate()}
                  disabled={startMutation.isPending || !camera?.rtsp_url}
                  className="rounded bg-ops-accent text-ops-bg font-semibold text-sm px-4 py-2 hover:bg-ops-accentDim disabled:opacity-50"
                >
                  {startMutation.isPending ? "Starting..." : "Start Monitoring"}
                </button>
              )}
              <span className="text-xs text-slate-500 font-mono truncate">{camera?.rtsp_url ?? "no stream configured"}</span>
            </div>
            {activeJob?.status === "failed" && activeJob.error_message && (
              <p className="mt-2 text-xs text-status-critical">{activeJob.error_message}</p>
            )}
          </div>

          <div className="bg-ops-panel border border-ops-border rounded-lg p-4">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400">
                Zones {zones && zones.length > 0 && <span className="tabular text-ops-accent">({zones.length})</span>}
              </h2>
              {!isDrawingZone && snapshotInfo?.exists && (
                <button
                  onClick={() => setIsDrawingZone(true)}
                  className="text-xs text-ops-accent hover:underline"
                >
                  + Draw new zone
                </button>
              )}
            </div>

            {isDrawingZone && drawPoints.length < 3 && (
              <p className="text-xs text-slate-400 mb-3">
                Click on the image above to place points ({drawPoints.length} so far, need at least 3).{" "}
                <button onClick={resetZoneDraft} className="text-status-critical hover:underline">
                  Cancel
                </button>
              </p>
            )}

            {isDrawingZone && drawPoints.length >= 3 && (
              <div className="space-y-3 mb-4 border border-ops-border rounded p-3 bg-ops-panel2">
                <div className="flex items-center justify-between">
                  <p className="text-xs text-slate-400">
                    {drawPoints.length} points placed.{" "}
                    <button onClick={() => setDrawPoints([])} className="text-ops-accent hover:underline">
                      Clear
                    </button>
                  </p>
                  <button onClick={resetZoneDraft} className="text-xs text-status-critical hover:underline">
                    Cancel
                  </button>
                </div>
                <input
                  placeholder="Zone name (e.g. Entrance)"
                  value={zoneName}
                  onChange={(e) => setZoneName(e.target.value)}
                  className="w-full rounded bg-ops-panel border border-ops-border px-3 py-1.5 text-sm"
                />
                <div className="flex items-center gap-3">
                  <label className="text-xs text-slate-400">Severity</label>
                  <select
                    value={zoneSeverity}
                    onChange={(e) => setZoneSeverity(e.target.value as ZoneSeverity)}
                    className="rounded bg-ops-panel border border-ops-border px-2 py-1 text-xs"
                  >
                    {ZONE_SEVERITIES.map((s) => (
                      <option key={s} value={s}>
                        {s}
                      </option>
                    ))}
                  </select>
                  <label className="text-xs text-slate-400">Min dwell (s)</label>
                  <input
                    type="number"
                    min={0}
                    value={zoneMinDwell}
                    onChange={(e) => setZoneMinDwell(Number(e.target.value))}
                    className="w-16 rounded bg-ops-panel border border-ops-border px-2 py-1 text-xs"
                  />
                </div>
                <div>
                  <p className="text-xs text-slate-400 mb-1">Flag these classes in this zone:</p>
                  <div className="flex flex-wrap gap-1.5">
                    {RULE_OBJECT_CLASSES.map((cls) => (
                      <button
                        key={cls}
                        type="button"
                        onClick={() => toggleRuleClass(cls)}
                        className={`text-xs px-2 py-1 rounded-full border ${
                          ruleClasses.includes(cls)
                            ? "bg-ops-accent text-ops-bg border-ops-accent"
                            : "border-ops-border text-slate-400"
                        }`}
                      >
                        {cls}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-4 flex-wrap">
                  <label className="flex items-center gap-1.5 text-xs text-slate-400">
                    <input type="checkbox" checked={ruleAfterHoursOnly} onChange={(e) => setRuleAfterHoursOnly(e.target.checked)} />
                    After-hours only
                  </label>
                  <label className="flex items-center gap-1.5 text-xs text-slate-400">
                    Risk threshold
                    <input
                      type="number"
                      min={0}
                      max={100}
                      value={ruleRiskThreshold}
                      onChange={(e) => setRuleRiskThreshold(Number(e.target.value))}
                      className="w-14 rounded bg-ops-panel border border-ops-border px-2 py-1 text-xs"
                    />
                  </label>
                  <label className="flex items-center gap-1.5 text-xs text-slate-400">
                    Consecutive hits
                    <input
                      type="number"
                      min={1}
                      value={ruleConsecutive}
                      onChange={(e) => setRuleConsecutive(Number(e.target.value))}
                      className="w-14 rounded bg-ops-panel border border-ops-border px-2 py-1 text-xs"
                    />
                  </label>
                </div>
                <button
                  onClick={() => createZoneMutation.mutate()}
                  disabled={createZoneMutation.isPending || !zoneName}
                  className="rounded bg-ops-accent text-ops-bg font-semibold text-xs px-3 py-1.5 hover:bg-ops-accentDim disabled:opacity-50"
                >
                  {createZoneMutation.isPending ? "Saving..." : "Save zone"}
                </button>
              </div>
            )}

            {(!zones || zones.length === 0) && !isDrawingZone && (
              <p className="text-sm text-slate-500">
                No zones configured. Zones let incidents factor in where something was seen, not just what and how
                long.
              </p>
            )}
            <ul className="space-y-2">
              {zones?.map((zone) => (
                <li key={zone.id} className="flex items-start justify-between gap-2 text-sm border-b border-ops-border pb-2 last:border-0">
                  <div>
                    <span className="flex items-center gap-2">
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{ backgroundColor: ZONE_SEVERITY_COLOR[zone.severity] }}
                      />
                      <span className="text-slate-200">{zone.name}</span>
                      <span className="text-[10px] uppercase tracking-wide text-slate-500">{zone.severity}</span>
                    </span>
                    {rulesByZone(zone.id).map((rule) => (
                      <p key={rule.id} className="text-xs text-slate-500 mt-0.5">
                        Flags: {rule.object_classes} · risk ≥ {rule.risk_threshold} · {rule.consecutive_required}x
                        {rule.after_hours_only ? " · after-hours only" : ""}
                      </p>
                    ))}
                  </div>
                  <button
                    onClick={() => deleteZoneMutation.mutate(zone.id)}
                    className="text-xs text-slate-500 hover:text-status-critical shrink-0"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          </div>

          <div className="bg-ops-panel border border-ops-border rounded-lg p-4">
            <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400 mb-3">
              Detected now {jobUpdate && <span className="tabular text-ops-accent">({jobUpdate.total_tracked_objects})</span>}
            </h2>
            {classEntries.length === 0 ? (
              <p className="text-sm text-slate-500">
                {isLive ? "Watching for people and vehicles..." : "Start monitoring to see live detections."}
              </p>
            ) : (
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
          </div>
        </div>

        <div className="space-y-4">
          <div className="bg-ops-panel border border-ops-border rounded-lg p-4 flex flex-col max-h-[640px]">
            <h2 className="text-xs font-semibold uppercase tracking-widest2 text-slate-400 mb-3 shrink-0">Activity Log</h2>
            <div className="overflow-y-auto flex-1 space-y-1.5 pr-1">
              {liveEvents.length === 0 && (
                <p className="text-sm text-slate-500">
                  {isLive ? "Watching the feed. Narration will appear here as the AI finds things." : "No activity yet."}
                </p>
              )}
              {liveEvents.map((e) => (
                <div key={e.id} className={`rounded-md border px-2.5 py-1.5 text-xs ${severityStyle[e.severity]}`}>
                  <div className="flex items-center justify-between gap-2 mb-0.5">
                    <span className="font-mono tabular text-slate-400">{formatClock(e.timestamp_seconds)}</span>
                    <span className="font-mono uppercase tracking-wide text-[10px] opacity-80">
                      {eventTypeIcon[e.event_type] ?? "."} {e.severity}
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
