import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiClient } from "../api/client";
import type { Camera, Zone, ZoneSeverity } from "../types";

export default function Cameras() {
  const queryClient = useQueryClient();
  const [newCameraName, setNewCameraName] = useState("");
  const [newCameraLocation, setNewCameraLocation] = useState("");
  const [selectedCameraId, setSelectedCameraId] = useState<number | null>(null);
  const [zoneName, setZoneName] = useState("");
  const [zoneSeverity, setZoneSeverity] = useState<ZoneSeverity>("medium");
  const [zonePoints, setZonePoints] = useState("0.2,0.2 0.8,0.2 0.8,0.9 0.2,0.9");
  const [minDwell, setMinDwell] = useState(10);

  const { data: cameras } = useQuery({
    queryKey: ["cameras"],
    queryFn: async () => (await apiClient.get<Camera[]>("/api/cameras")).data,
  });

  const { data: zones } = useQuery({
    queryKey: ["zones", selectedCameraId],
    queryFn: async () =>
      (await apiClient.get<Zone[]>("/api/zones", { params: { camera_id: selectedCameraId } })).data,
    enabled: !!selectedCameraId,
  });

  const createCamera = useMutation({
    mutationFn: async () =>
      apiClient.post("/api/cameras", { name: newCameraName, location: newCameraLocation || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cameras"] });
      setNewCameraName("");
      setNewCameraLocation("");
    },
  });

  const createZone = useMutation({
    mutationFn: async () => {
      const polygon = zonePoints
        .trim()
        .split(/\s+/)
        .map((pair) => pair.split(",").map(Number) as [number, number]);
      return apiClient.post("/api/zones", {
        camera_id: selectedCameraId,
        name: zoneName,
        severity: zoneSeverity,
        polygon,
        minimum_dwell_seconds: minDwell,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["zones", selectedCameraId] });
      setZoneName("");
    },
  });

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold">Cameras & Zones</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-ops-panel border border-ops-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">Cameras</h2>
          <div className="space-y-2 mb-4">
            {cameras?.map((camera) => (
              <button
                key={camera.id}
                onClick={() => setSelectedCameraId(camera.id)}
                className={`w-full text-left px-3 py-2 rounded text-sm ${
                  selectedCameraId === camera.id ? "bg-amber-500/10 text-amber-400" : "hover:bg-slate-900/40"
                }`}
              >
                {camera.name} <span className="text-slate-500">({camera.location})</span>
              </button>
            ))}
          </div>
          <div className="border-t border-ops-border pt-3 space-y-2">
            <input
              placeholder="Camera name"
              value={newCameraName}
              onChange={(e) => setNewCameraName(e.target.value)}
              className="w-full rounded bg-slate-900 border border-ops-border px-3 py-2 text-sm"
            />
            <input
              placeholder="Location"
              value={newCameraLocation}
              onChange={(e) => setNewCameraLocation(e.target.value)}
              className="w-full rounded bg-slate-900 border border-ops-border px-3 py-2 text-sm"
            />
            <button
              onClick={() => createCamera.mutate()}
              disabled={!newCameraName}
              className="rounded bg-amber-500 text-slate-950 font-semibold text-sm px-4 py-2 hover:bg-amber-400 disabled:opacity-50"
            >
              Add Camera
            </button>
          </div>
        </div>

        <div className="bg-ops-panel border border-ops-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-slate-300 mb-3">
            Zones {selectedCameraId ? `for camera #${selectedCameraId}` : ""}
          </h2>
          {!selectedCameraId && <p className="text-slate-500 text-sm">Select a camera to manage zones.</p>}
          {selectedCameraId && (
            <>
              <ul className="space-y-2 mb-4 text-sm">
                {zones?.map((zone) => (
                  <li key={zone.id} className="border-b border-ops-border pb-2">
                    <span className="text-slate-200">{zone.name}</span>{" "}
                    <span className="text-amber-400 uppercase text-xs">{zone.severity}</span>
                  </li>
                ))}
              </ul>
              <div className="space-y-2 border-t border-ops-border pt-3">
                <input
                  placeholder="Zone name"
                  value={zoneName}
                  onChange={(e) => setZoneName(e.target.value)}
                  className="w-full rounded bg-slate-900 border border-ops-border px-3 py-2 text-sm"
                />
                <select
                  value={zoneSeverity}
                  onChange={(e) => setZoneSeverity(e.target.value as ZoneSeverity)}
                  className="w-full rounded bg-slate-900 border border-ops-border px-3 py-2 text-sm"
                >
                  <option value="low">Low</option>
                  <option value="medium">Medium</option>
                  <option value="high">High</option>
                  <option value="critical">Critical</option>
                </select>
                <input
                  placeholder="Polygon points (x,y x,y x,y ... normalized 0-1)"
                  value={zonePoints}
                  onChange={(e) => setZonePoints(e.target.value)}
                  className="w-full rounded bg-slate-900 border border-ops-border px-3 py-2 text-sm"
                />
                <input
                  type="number"
                  placeholder="Minimum dwell seconds"
                  value={minDwell}
                  onChange={(e) => setMinDwell(Number(e.target.value))}
                  className="w-full rounded bg-slate-900 border border-ops-border px-3 py-2 text-sm"
                />
                <button
                  onClick={() => createZone.mutate()}
                  disabled={!zoneName}
                  className="rounded bg-amber-500 text-slate-950 font-semibold text-sm px-4 py-2 hover:bg-amber-400 disabled:opacity-50"
                >
                  Add Zone
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
