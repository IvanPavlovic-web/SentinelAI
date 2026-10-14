"""Visual attribute extraction for rich scene narration.

Turns a raw bounding box into the kind of detail a human would actually
say out loud — "a red car", "in the right side of the frame", "moving
left" — using classical, dependency-free CV (HSV color binning,
frame-relative geometry, centroid-history direction) rather than a second
heavy model. Deliberately simple and fast since this runs per sampled
detection across the whole video.
"""
from __future__ import annotations

import math


def classify_dominant_color(frame, x1: float, y1: float, x2: float, y2: float) -> str:
    """Names the dominant color of a bounding-box crop via the median hue/
    saturation/value of a downsampled patch. HSV median is far more robust
    to lighting/shadow than averaging raw RGB, and far cheaper than
    clustering for a crop this small."""
    import cv2
    import numpy as np

    if frame is None:
        return "unknown"

    height, width = frame.shape[:2]
    ix1, iy1 = max(0, int(x1)), max(0, int(y1))
    ix2, iy2 = min(width, int(x2)), min(height, int(y2))
    if ix2 <= ix1 or iy2 <= iy1:
        return "unknown"

    crop = frame[iy1:iy2, ix1:ix2]
    if crop.size == 0:
        return "unknown"

    small = cv2.resize(crop, (16, 16), interpolation=cv2.INTER_AREA)
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    h = float(np.median(hsv[:, :, 0]))
    s = float(np.median(hsv[:, :, 1]))
    v = float(np.median(hsv[:, :, 2]))
    return _hsv_to_color_name(h, s, v)


def _hsv_to_color_name(h: float, s: float, v: float) -> str:
    """h in OpenCV's 0-179 range, s/v in 0-255."""
    if v < 40:
        return "black"
    if s < 35 and v > 195:
        return "white"
    if s < 45:
        return "gray"
    if h < 8 or h >= 172:
        return "red"
    if h < 20:
        return "orange"
    if h < 33:
        return "yellow"
    if h < 45:
        return "lime green"
    if h < 78:
        return "green"
    if h < 100:
        return "cyan"
    if h < 135:
        return "blue"
    if h < 155:
        return "purple"
    return "pink"


def frame_position_label(cx: float, cy: float, width: float, height: float) -> str:
    """Describes where in the frame a centroid sits, in the way a person
    would point at a screen: thirds horizontally and vertically."""
    if width <= 0 or height <= 0:
        return "the frame"

    hx = "left" if cx < width / 3 else "right" if cx > 2 * width / 3 else "center"
    vy = "top" if cy < height / 3 else "bottom" if cy > 2 * height / 3 else "middle"

    if hx == "center" and vy == "middle":
        return "the center of the frame"
    if vy == "middle":
        return f"the {hx} side of the frame"
    if hx == "center":
        return f"the {vy} of the frame"
    return f"the {vy}-{hx} of the frame"


def movement_label(centroids: list[tuple[float, float]], timestamps: list[float], window: int = 8) -> str:
    """Describes current movement direction/speed from the most recent
    positions in a track's history, in plain language: stationary, or
    moving left/right/up/down, with a qualitative speed word."""
    if len(centroids) < 2 or len(timestamps) < 2:
        return "just appeared"

    recent_c = centroids[-window:]
    recent_t = timestamps[-window:]
    (x0, y0), (x1, y1) = recent_c[0], recent_c[-1]
    dt = recent_t[-1] - recent_t[0]
    if dt <= 0:
        return "stationary"

    dx, dy = x1 - x0, y1 - y0
    distance = math.hypot(dx, dy)
    speed = distance / dt  # pixels/second

    if distance < 6:
        return "stationary"

    direction = (
        ("right" if dx > 0 else "left")
        if abs(dx) >= abs(dy)
        else ("downward, toward the bottom of the frame" if dy > 0 else "upward, toward the top of the frame")
    )
    pace = "quickly" if speed > 250 else "slowly" if speed < 60 else ""
    return f"moving {pace} {direction}".replace("  ", " ").strip()
