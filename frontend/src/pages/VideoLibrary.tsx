import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { apiClient } from "../api/client";
import type { VideoSource, VideoUploadResponse } from "../types";

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = -1;
  do {
    value /= 1024;
    unit += 1;
  } while (value >= 1024 && unit < units.length - 1);
  return `${value.toFixed(1)} ${units[unit]}`;
}

export default function VideoLibrary() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [progress, setProgress] = useState(0);
  const [uploadSize, setUploadSize] = useState<{ loaded: number; total: number } | null>(null);

  const { data: videos, isLoading } = useQuery({
    queryKey: ["videos"],
    queryFn: async () => (await apiClient.get<VideoSource[]>("/api/videos")).data,
    refetchInterval: 8000,
  });

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiClient.post<VideoUploadResponse>("/api/videos/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
        // No axios timeout is set globally, and large footage (multi-GB,
        // multi-hour recordings) can legitimately take a long time to
        // transfer — progress feedback matters more here than a timeout.
        onUploadProgress: (evt) => {
          if (evt.total) {
            setProgress(Math.round((evt.loaded / evt.total) * 100));
            setUploadSize({ loaded: evt.loaded, total: evt.total });
          }
        },
      });
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ["videos"] });
      // Jump straight to the video's live analysis view — processing has
      // already been queued by the upload endpoint, so the user watches
      // detection happen in real time instead of waiting on this list.
      navigate(`/videos/${res.data.video_source.id}`);
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        "Upload failed. Check file type and try again.";
      setError(detail);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: async (videoId: number) => apiClient.delete(`/api/videos/${videoId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["videos"] });
    },
  });

  const handleDelete = (video: VideoSource) => {
    if (window.confirm(`Delete "${video.original_filename}"? This cannot be undone.`)) {
      deleteMutation.mutate(video.id);
    }
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    setProgress(0);
    setUploadSize(null);
    try {
      await uploadMutation.mutateAsync(file);
    } finally {
      setUploading(false);
      setProgress(0);
      setUploadSize(null);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-[11px] uppercase tracking-widest2 text-ops-accent font-medium mb-1">Ingestion</p>
          <h1 className="font-display text-2xl font-semibold">Video Library</h1>
        </div>
        <label
          className={`cursor-pointer rounded-md bg-ops-accent text-ops-bg font-semibold text-sm px-4 py-2 transition-colors hover:bg-ops-accentDim ${
            uploading ? "opacity-60 pointer-events-none" : ""
          }`}
        >
          {uploading ? "Uploading…" : "Upload Video"}
          <input
            ref={fileInputRef}
            type="file"
            accept=".mp4,.avi,.mov,.mkv,.ts,.mxf,.webm"
            className="hidden"
            onChange={handleFileChange}
            disabled={uploading}
          />
        </label>
      </div>

      {uploading && (
        <div className="bg-ops-panel border border-ops-border rounded-lg px-5 py-4">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-2">
            <span>Transferring to server — no file-size limit applies</span>
            <span className="tabular">
              {uploadSize ? `${formatBytes(uploadSize.loaded)} / ${formatBytes(uploadSize.total)}` : ""}
            </span>
          </div>
          <div className="h-1.5 rounded-full bg-ops-panel2 overflow-hidden">
            <div
              className="h-full bg-ops-accent transition-[width] duration-200"
              style={{ width: `${progress}%` }}
            />
          </div>
        </div>
      )}

      {error && <p className="text-sm text-status-critical">{error}</p>}

      <div className="bg-ops-panel border border-ops-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-ops-panel2 text-slate-400 text-left">
            <tr>
              <th className="px-4 py-3 text-xs uppercase tracking-widest2 font-medium">Filename</th>
              <th className="px-4 py-3 text-xs uppercase tracking-widest2 font-medium">Size</th>
              <th className="px-4 py-3 text-xs uppercase tracking-widest2 font-medium">Duration</th>
              <th className="px-4 py-3 text-xs uppercase tracking-widest2 font-medium">Resolution</th>
              <th className="px-4 py-3 text-xs uppercase tracking-widest2 font-medium">Uploaded</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-4 py-3 text-slate-500" colSpan={6}>
                  Loading…
                </td>
              </tr>
            )}
            {videos?.map((video) => (
              <tr key={video.id} className="border-t border-ops-border hover:bg-white/[0.02]">
                <td className="px-4 py-3">{video.original_filename}</td>
                <td className="px-4 py-3 tabular text-slate-400">
                  {video.file_size_bytes ? formatBytes(video.file_size_bytes) : "-"}
                </td>
                <td className="px-4 py-3 tabular">{video.duration_seconds ? `${video.duration_seconds.toFixed(0)}s` : "-"}</td>
                <td className="px-4 py-3 tabular">
                  {video.width && video.height ? `${video.width}x${video.height}` : "-"}
                </td>
                <td className="px-4 py-3 text-slate-400">{new Date(video.created_at).toLocaleString()}</td>
                <td className="px-4 py-3 text-right whitespace-nowrap">
                  <Link to={`/videos/${video.id}`} className="text-ops-accent hover:underline">
                    View
                  </Link>
                  <button
                    onClick={() => handleDelete(video)}
                    disabled={deleteMutation.isPending}
                    className="ml-3 text-status-critical hover:underline disabled:opacity-50"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {videos?.length === 0 && (
              <tr>
                <td className="px-4 py-3 text-slate-500" colSpan={6}>
                  No videos uploaded yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
