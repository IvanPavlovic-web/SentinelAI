export type UserRole = "admin" | "analyst" | "viewer";

export interface User {
  id: number;
  email: string;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export interface Camera {
  id: number;
  name: string;
  location: string | null;
  rtsp_url: string | null;
  is_active: boolean;
  owner_id: number | null;
  created_at: string;
  updated_at: string;
  latest_job_status: JobStatus | null;
}

export interface VideoSource {
  id: number;
  camera_id: number | null;
  original_filename: string;
  stored_filename: string;
  file_size_bytes: number | null;
  duration_seconds: number | null;
  fps: number | null;
  width: number | null;
  height: number | null;
  created_at: string;
}

export type JobStatus = "pending" | "processing" | "completed" | "failed" | "stopped";

export interface VideoUploadResponse {
  video_source: VideoSource;
  processing_job: ProcessingJob;
}

export interface ProcessingJob {
  id: number;
  video_source_id: number | null;
  camera_id: number | null;
  is_live: boolean;
  stop_requested: boolean;
  status: JobStatus;
  progress_percent: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  has_annotated_video: boolean;
}

export interface CameraSnapshotInfo {
  exists: boolean;
  last_updated: string | null;
}

export interface CameraConnectionTestResult {
  ok: boolean;
  detail?: string;
  width?: number;
  height?: number;
  fps?: number;
}

export type ZoneSeverity = "low" | "medium" | "high" | "critical";

export interface Zone {
  id: number;
  camera_id: number;
  name: string;
  severity: ZoneSeverity;
  polygon: [number, number][];
  minimum_dwell_seconds: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface Rule {
  id: number;
  zone_id: number;
  name: string;
  object_classes: string;
  after_hours_only: boolean;
  risk_threshold: number;
  consecutive_required: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type IncidentStatus = "open" | "acknowledged" | "resolved" | "dismissed";
export type IncidentPriority = "low" | "medium" | "high" | "critical";

export interface IncidentEvidence {
  id: number;
  frame_path: string;
  frame_number: number | null;
  timestamp_seconds: number | null;
  created_at: string;
}

export interface Incident {
  id: number;
  processing_job_id: number;
  camera_id: number | null;
  zone_id: number | null;
  tracked_object_id: number | null;
  rule_id: number | null;
  object_class: string;
  risk_score: number;
  status: IncidentStatus;
  priority: IncidentPriority;
  summary: string;
  resolution_notes: string | null;
  resolved_by: number | null;
  resolved_at: string | null;
  detected_at: string;
  alert_sent: boolean;
  alert_channels: string | null;
  evidence: IncidentEvidence[];
}

export interface PaginatedIncidents {
  items: Incident[];
  total: number;
  page: number;
  page_size: number;
}

export interface DashboardSummary {
  total_cameras: number;
  active_cameras: number;
  total_videos: number;
  jobs_pending: number;
  jobs_processing: number;
  jobs_completed: number;
  jobs_failed: number;
  open_incidents: number;
  incidents_last_24h: number;
  incidents_by_priority: Record<string, number>;
}

export type EventSeverity = "low" | "medium" | "high" | "critical";

export interface ActivityEvent {
  id: number;
  track_number: number | null;
  object_class: string;
  timestamp_seconds: number;
  event_type: "status" | "anomaly" | "escalation" | "weapon" | string;
  severity: EventSeverity;
  description: string;
  risk_score: number;
}

export interface JobProgressMessage {
  job_id: number;
  status: JobStatus;
  progress_percent: number;
  error_message: string | null;
  total_tracked_objects: number;
  class_counts: Record<string, number>;
  recent_events: ActivityEvent[];
}

export interface TrackedObjectSummary {
  track_number: number;
  object_class: string;
  first_seen_at: string;
  last_seen_at: string;
  max_confidence: number | null;
  observation_count: number;
  final_risk_score: number;
  dominant_color: string;
}

export interface JobDetectionsSummary {
  job_id: number;
  total_tracked_objects: number;
  class_counts: Record<string, number>;
  tracks: TrackedObjectSummary[];
}

export interface PerformancePoint {
  job_id: number;
  created_at: string;
  processing_fps: number;
  avg_latency_ms: number;
  p95_latency_ms: number;
  avg_cpu_percent: number;
  avg_ram_mb: number;
  incident_count: number;
}

export interface AuditLog {
  id: number;
  user_id: number | null;
  action: string;
  resource_type: string | null;
  resource_id: number | null;
  details: string | null;
  ip_address: string | null;
  created_at: string;
}

export interface PaginatedAuditLogs {
  items: AuditLog[];
  total: number;
  page: number;
  page_size: number;
}
