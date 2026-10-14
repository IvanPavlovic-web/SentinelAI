import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { apiClient } from "../api/client";
import type { VideoSource } from "../types";

export default function VideoLibrary() {
  const queryClient = useQueryClient();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: videos, isLoading } = useQuery({
    queryKey: ["videos"],
    queryFn: async () => (await apiClient.get<VideoSource[]>("/api/videos")).data,
    refetchInterval: 8000,
  });

  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiClient.post("/api/videos/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["videos"] });
    },
    onError: () => setError("Upload failed. Check file type/size and try again."),
  });

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadMutation.mutateAsync(file);
    } finally {
      setUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">Video Library</h1>
        <label className="cursor-pointer rounded bg-amber-500 text-slate-950 font-semibold text-sm px-4 py-2 hover:bg-amber-400">
          {uploading ? "Uploading..." : "Upload Video"}
          <input
            ref={fileInputRef}
            type="file"
            accept=".mp4,.avi,.mov,.mkv"
            className="hidden"
            onChange={handleFileChange}
            disabled={uploading}
          />
        </label>
      </div>

      {error && <p className="text-sm text-red-400">{error}</p>}

      <div className="bg-ops-panel border border-ops-border rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-slate-400 text-left">
            <tr>
              <th className="px-4 py-3">Filename</th>
              <th className="px-4 py-3">Duration</th>
              <th className="px-4 py-3">Resolution</th>
              <th className="px-4 py-3">Uploaded</th>
              <th className="px-4 py-3" />
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="px-4 py-3 text-slate-500" colSpan={5}>
                  Loading...
                </td>
              </tr>
            )}
            {videos?.map((video) => (
              <tr key={video.id} className="border-t border-ops-border hover:bg-slate-900/40">
                <td className="px-4 py-3">{video.original_filename}</td>
                <td className="px-4 py-3">{video.duration_seconds ? `${video.duration_seconds.toFixed(0)}s` : "-"}</td>
                <td className="px-4 py-3">
                  {video.width && video.height ? `${video.width}x${video.height}` : "-"}
                </td>
                <td className="px-4 py-3 text-slate-400">{new Date(video.created_at).toLocaleString()}</td>
                <td className="px-4 py-3 text-right">
                  <Link to={`/videos/${video.id}`} className="text-amber-400 hover:underline">
                    View
                  </Link>
                </td>
              </tr>
            ))}
            {videos?.length === 0 && (
              <tr>
                <td className="px-4 py-3 text-slate-500" colSpan={5}>
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
