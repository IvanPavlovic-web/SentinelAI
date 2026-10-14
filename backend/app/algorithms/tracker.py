"""A lightweight multi-object tracker using IoU overlap + centroid distance
matching between frames. Intentionally simple (no deep re-ID embeddings)
so it runs fast on CPU-only hardware; see README for the design rationale.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Detection:
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    object_class: str
    dominant_color: str = "unknown"

    @property
    def centroid(self) -> tuple[float, float]:
        return ((self.x1 + self.x2) / 2.0, (self.y1 + self.y2) / 2.0)


@dataclass
class Track:
    track_id: int
    object_class: str
    last_bbox: tuple[float, float, float, float]
    centroids: list[tuple[float, float]] = field(default_factory=list)
    timestamps: list[float] = field(default_factory=list)
    confidences: list[float] = field(default_factory=list)
    colors: list[str] = field(default_factory=list)
    missed_frames: int = 0
    active: bool = True

    @property
    def dominant_color(self) -> str:
        """The most frequently observed color across this track's history
        so far — far more stable for narration than any single frame's
        color, which can flicker with lighting/shadow."""
        if not self.colors:
            return "unknown"
        return max(set(self.colors), key=self.colors.count)


def _iou(a: tuple[float, float, float, float], b: tuple[float, float, float, float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b

    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area

    if union <= 0:
        return 0.0
    return inter_area / union


def _centroid_distance(c1: tuple[float, float], c2: tuple[float, float]) -> float:
    return ((c1[0] - c2[0]) ** 2 + (c1[1] - c2[1]) ** 2) ** 0.5


class CentroidIoUTracker:
    """Assigns and maintains integer track IDs across frames.

    Matching strategy per frame:
      1. Build a cost matrix between existing active tracks and new
         detections using a weighted combination of (1 - IoU) and
         normalized centroid distance.
      2. Greedily assign the best (lowest-cost) pairs above an IoU floor
         or below a distance ceiling.
      3. Unmatched existing tracks accumulate `missed_frames`; once this
         exceeds `max_missed_frames` the track is expired (deactivated).
      4. Unmatched detections spawn new tracks with fresh IDs.
    """

    def __init__(
        self,
        iou_threshold: float = 0.3,
        max_centroid_distance: float = 100.0,
        max_missed_frames: int = 10,
    ) -> None:
        self.iou_threshold = iou_threshold
        self.max_centroid_distance = max_centroid_distance
        self.max_missed_frames = max_missed_frames
        self._tracks: dict[int, Track] = {}
        self._next_id = 1

    @property
    def tracks(self) -> dict[int, Track]:
        return self._tracks

    def _active_tracks(self) -> list[Track]:
        return [t for t in self._tracks.values() if t.active]

    def update(self, detections: list[Detection], timestamp: float) -> dict[int, Detection]:
        """Process one frame's detections. Returns {track_id: matched Detection}."""
        active = self._active_tracks()
        matched_track_ids: set[int] = set()
        matched_detection_idx: set[int] = set()
        result: dict[int, Detection] = {}

        # Build candidate pairs sorted by a blended cost (lower is better).
        candidates: list[tuple[float, Track, int, Detection]] = []
        for track in active:
            for idx, det in enumerate(detections):
                if det.object_class != track.object_class:
                    continue
                bbox = (det.x1, det.y1, det.x2, det.y2)
                iou = _iou(track.last_bbox, bbox)
                dist = _centroid_distance(track.centroids[-1], det.centroid) if track.centroids else 0.0
                if iou < self.iou_threshold and dist > self.max_centroid_distance:
                    continue
                cost = (1 - iou) + (dist / max(self.max_centroid_distance, 1.0))
                candidates.append((cost, track, idx, det))

        candidates.sort(key=lambda c: c[0])

        for cost, track, idx, det in candidates:
            if track.track_id in matched_track_ids or idx in matched_detection_idx:
                continue
            matched_track_ids.add(track.track_id)
            matched_detection_idx.add(idx)
            track.last_bbox = (det.x1, det.y1, det.x2, det.y2)
            track.centroids.append(det.centroid)
            track.timestamps.append(timestamp)
            track.confidences.append(det.confidence)
            if det.dominant_color != "unknown":
                track.colors.append(det.dominant_color)
            track.missed_frames = 0
            result[track.track_id] = det

        # Unmatched active tracks: increment missed-frame counter, expire if needed.
        for track in active:
            if track.track_id not in matched_track_ids:
                track.missed_frames += 1
                if track.missed_frames > self.max_missed_frames:
                    track.active = False

        # Unmatched detections: spawn new tracks.
        for idx, det in enumerate(detections):
            if idx in matched_detection_idx:
                continue
            track_id = self._next_id
            self._next_id += 1
            new_track = Track(
                track_id=track_id,
                object_class=det.object_class,
                last_bbox=(det.x1, det.y1, det.x2, det.y2),
            )
            new_track.centroids.append(det.centroid)
            new_track.timestamps.append(timestamp)
            new_track.confidences.append(det.confidence)
            if det.dominant_color != "unknown":
                new_track.colors.append(det.dominant_color)
            self._tracks[track_id] = new_track
            result[track_id] = det

        return result
