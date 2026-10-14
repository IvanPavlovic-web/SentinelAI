"""
project.py — CS50P Final Project
SentinelAI: Edge Video Intelligence & Incident Detection Platform

This module contains the pure, dependency-free "brain" of SentinelAI's
incident-detection pipeline: the STAR-Risk scoring algorithm, the incident
hysteresis check, a motion-anomaly estimator used as an input to STAR-Risk,
and a video-chunking helper used by the backend's worker pool to split long
videos into parallelizable segments.

Everything in this file uses only the Python standard library so that it can
be graded/run with `python project.py` and `pytest test_project.py` with no
extra dependencies. The real FastAPI/OpenCV/Celery backend (in backend/app/)
imports these exact functions from here instead of re-implementing them, so
there is a single source of truth for the algorithm.
"""

from __future__ import annotations

import argparse
import math
import sys


# --------------------------------------------------------------------------
# STAR-Risk: Severity / Temporal / Anomaly / Risk scoring
# --------------------------------------------------------------------------

_ZONE_SEVERITY_MAP = {
    "low": 0.25,
    "medium": 0.50,
    "high": 0.75,
    "critical": 1.00,
}


def calculate_star_risk(
    zone_severity: str | None,
    dwell_seconds: float,
    minimum_dwell_seconds: float,
    motion_anomaly: float,
    after_hours: bool,
    confidence_history: list[float],
    previous_risk: float = 0.0,
    alpha: float = 0.45,
) -> float:
    """Compute the STAR-Risk score (0..100) for a single tracked object.

    STAR-Risk = Zone severity, Temporal context, Anomaly (motion), Risk
    persistence (confidence). The formula is an exponentially-smoothed
    weighted sum:

        raw_risk = 100 * (0.35*Z + 0.25*D + 0.20*M + 0.10*T + 0.10*C)
        smoothed_risk = alpha*raw_risk + (1-alpha)*previous_risk

    Where:
        Z (zone severity, 0..1): None/not-in-zone -> 0.0. Otherwise the
            case-insensitive string "low"/"medium"/"high"/"critical" maps to
            0.25/0.50/0.75/1.00. Any other non-empty string is invalid.
        D (dwell score, 0..1): min(1.0, dwell_seconds / minimum_dwell_seconds).
            If minimum_dwell_seconds <= 0 this is defined as 0.0 (guarded,
            never divides by zero / never raises for this reason alone).
        M (motion anomaly, 0..1): precomputed externally (see
            calculate_motion_anomaly) and passed in directly here. Clamped
            to [0, 1] defensively.
        T (temporal score): 1.0 if after_hours else 0.0.
        C (confidence persistence score, 0..1): derived from
            confidence_history, a list of the most recent detection
            confidences (each expected in [0, 1]) for this track, oldest
            first. Rule (documented here, mirrored exactly in
            test_project.py):
              1. Take the last min(5, len(confidence_history)) entries.
              2. If that window is empty -> C = 0.0.
              3. Count how many of those entries are "high confidence"
                 (>= 0.6), scanning from the most recent backwards and
                 stopping at the first entry that is NOT high-confidence
                 (i.e. count *consecutive* recent high-confidence hits).
              4. C = (consecutive_high_count / window_size) * mean(window).
                 This rewards both a strong recent confidence streak and a
                 high average confidence; a single low-confidence frame at
                 the end zeroes the "streak" term for that evaluation while
                 the average term still reflects the detector's performance.

    Raises:
        ValueError: if alpha is not in [0, 1], if dwell_seconds < 0, if
            zone_severity is a non-empty string not in the known set, or if
            any confidence in confidence_history is outside [0, 1].
    """
    if not (0.0 <= alpha <= 1.0):
        raise ValueError("alpha must be in [0, 1]")
    if dwell_seconds < 0:
        raise ValueError("dwell_seconds must be >= 0")
    for c in confidence_history:
        if not (0.0 <= c <= 1.0):
            raise ValueError("confidence values must be within [0, 1]")

    # Z: zone severity
    if zone_severity is None:
        z = 0.0
    else:
        key = zone_severity.strip().lower()
        if key not in _ZONE_SEVERITY_MAP:
            raise ValueError(f"invalid zone_severity: {zone_severity!r}")
        z = _ZONE_SEVERITY_MAP[key]

    # D: dwell score, guarded against non-positive minimum_dwell_seconds
    if minimum_dwell_seconds > 0:
        d = min(1.0, dwell_seconds / minimum_dwell_seconds)
    else:
        d = 0.0

    # M: motion anomaly, clamped defensively
    m = max(0.0, min(1.0, motion_anomaly))

    # T: temporal score
    t = 1.0 if after_hours else 0.0

    # C: confidence persistence score (see docstring rule above)
    window = confidence_history[-5:] if confidence_history else []
    if not window:
        c_score = 0.0
    else:
        consecutive_high = 0
        for conf in reversed(window):
            if conf >= 0.6:
                consecutive_high += 1
            else:
                break
        avg_window = sum(window) / len(window)
        c_score = (consecutive_high / len(window)) * avg_window

    raw_risk = 100 * (0.35 * z + 0.25 * d + 0.20 * m + 0.10 * t + 0.10 * c_score)
    smoothed_risk = alpha * raw_risk + (1 - alpha) * previous_risk

    return max(0.0, min(100.0, smoothed_risk))


def is_incident_triggered(
    risk_history: list[float],
    threshold: float,
    consecutive_required: int = 3,
) -> bool:
    """Return True iff the last `consecutive_required` entries of
    risk_history are all >= threshold.

    This provides hysteresis so a single noisy spike does not create an
    incident; the risk must stay elevated for several consecutive
    evaluations in a row (the most recent ones).

    Raises:
        ValueError: if consecutive_required < 1.
    """
    if consecutive_required < 1:
        raise ValueError("consecutive_required must be >= 1")

    if len(risk_history) < consecutive_required:
        return False

    recent = risk_history[-consecutive_required:]
    return all(r >= threshold for r in recent)


def calculate_motion_anomaly(
    centroids: list[tuple[float, float]],
    timestamps: list[float],
) -> float:
    """Estimate a 0..1 motion-anomaly score from a track's centroid path.

    Looks at two signals between consecutive motion "steps":
      - Direction reversals: the dot product of consecutive velocity
        vectors is negative relative to their magnitudes (i.e. the object
        sharply changed direction, cos(theta) < 0).
      - Speed bursts: the ratio of consecutive step speeds exceeds 2.5x
        (a sudden acceleration/deceleration spike).

    The raw anomaly count (reversals + bursts) is normalized by the number
    of comparable step-pairs and capped at 1.0. A static or near-static
    track (effectively no movement) returns 0.0. Fewer than 3 points is not
    enough to compute a direction change, so it returns 0.0.

    Raises:
        ValueError: if len(centroids) != len(timestamps).
    """
    if len(centroids) != len(timestamps):
        raise ValueError("centroids and timestamps must have equal length")

    if len(centroids) < 3:
        return 0.0

    # Per-step velocity vectors (dx, dy) and speeds.
    velocities: list[tuple[float, float]] = []
    speeds: list[float] = []
    for i in range(1, len(centroids)):
        dt = timestamps[i] - timestamps[i - 1]
        if dt <= 0:
            # Non-increasing timestamps: treat as no displacement for safety.
            velocities.append((0.0, 0.0))
            speeds.append(0.0)
            continue
        dx = (centroids[i][0] - centroids[i - 1][0]) / dt
        dy = (centroids[i][1] - centroids[i - 1][1]) / dt
        velocities.append((dx, dy))
        speeds.append(math.hypot(dx, dy))

    if all(s == 0.0 for s in speeds):
        return 0.0

    SPEED_BURST_RATIO = 2.5
    anomaly_events = 0
    comparable_pairs = 0

    for i in range(1, len(velocities)):
        v_prev = velocities[i - 1]
        v_curr = velocities[i]
        speed_prev = speeds[i - 1]
        speed_curr = speeds[i]

        if speed_prev == 0.0 and speed_curr == 0.0:
            # Both static: nothing to compare.
            continue

        comparable_pairs += 1

        # Direction reversal check via normalized dot product.
        mag_prev = speed_prev
        mag_curr = speed_curr
        if mag_prev > 0 and mag_curr > 0:
            dot = v_prev[0] * v_curr[0] + v_prev[1] * v_curr[1]
            cos_theta = dot / (mag_prev * mag_curr)
            if cos_theta < 0:
                anomaly_events += 1

        # Sudden speed burst check (either direction of ratio).
        if speed_prev > 0 and speed_curr > 0:
            ratio = max(speed_curr / speed_prev, speed_prev / speed_curr)
            if ratio >= SPEED_BURST_RATIO:
                anomaly_events += 1

    if comparable_pairs == 0:
        return 0.0

    score = anomaly_events / comparable_pairs
    return max(0.0, min(1.0, score))


def split_video_chunks(
    duration_seconds: float,
    chunk_seconds: int,
) -> list[tuple[float, float]]:
    """Split [0, duration_seconds] into (start, end) chunks of chunk_seconds,
    with the final chunk possibly shorter when duration is not evenly
    divisible. Covers 0..duration_seconds exactly, with no gaps/overlaps.

    Raises:
        ValueError: if duration_seconds <= 0 or chunk_seconds <= 0.
    """
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be > 0")
    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be > 0")

    chunks: list[tuple[float, float]] = []
    start = 0.0
    while start < duration_seconds:
        end = min(start + chunk_seconds, duration_seconds)
        chunks.append((start, end))
        start = end
    return chunks


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def _run_demo_risk() -> None:
    """Scripted demo: a track that loiters in a high-security zone after
    hours, with increasingly erratic movement, until it crosses the
    incident threshold."""
    print("SentinelAI STAR-Risk demo — Track #14 in 'High Security Warehouse'\n")

    zone_severity = "high"
    minimum_dwell = 10.0
    threshold = 70.0

    # Synthetic per-second observations: (dwell_seconds, motion_anomaly, confidence)
    observations = [
        (2.0, 0.05, 0.55),
        (6.0, 0.10, 0.62),
        (11.0, 0.20, 0.70),
        (14.0, 0.55, 0.82),
        (18.0, 0.80, 0.91),
        (24.0, 0.90, 0.95),
    ]

    previous_risk = 0.0
    risk_history: list[float] = []
    confidence_history: list[float] = []

    for dwell, anomaly, confidence in observations:
        confidence_history.append(confidence)
        risk = calculate_star_risk(
            zone_severity=zone_severity,
            dwell_seconds=dwell,
            minimum_dwell_seconds=minimum_dwell,
            motion_anomaly=anomaly,
            after_hours=True,
            confidence_history=confidence_history,
            previous_risk=previous_risk,
        )
        risk_history.append(risk)
        previous_risk = risk
        print(f"  t={dwell:5.1f}s  anomaly={anomaly:.2f}  confidence={confidence:.2f}"
              f"  -> STAR-Risk={risk:5.1f}")

    triggered = is_incident_triggered(risk_history, threshold, consecutive_required=2)
    final_risk = risk_history[-1]

    print()
    if triggered:
        print(
            f"INCIDENT: Person track #14 entered the High Security Warehouse zone "
            f"after hours and loitered for {observations[-1][0]:.0f}s with erratic "
            f"movement, producing a STAR-Risk score of {final_risk:.1f} "
            f"(threshold {threshold:.0f})."
        )
    else:
        print(f"No incident triggered. Final STAR-Risk score: {final_risk:.1f}")


def _run_split_video(duration: float, chunk_size: int) -> None:
    chunks = split_video_chunks(duration, chunk_size)
    print(f"Splitting {duration:.1f}s video into {chunk_size}s chunks -> {len(chunks)} chunk(s):")
    for i, (start, end) in enumerate(chunks):
        print(f"  chunk {i}: [{start:.1f}s, {end:.1f}s)  duration={end - start:.1f}s")


def _run_serve() -> None:
    print("SentinelAI backend is a separate FastAPI package (backend/app) and is")
    print("not started from project.py, to keep this CS50 module stdlib-only.")
    print()
    print("To start the API server:")
    print("  cd backend")
    print("  python -m venv .venv && source .venv/bin/activate  (or .venv\\Scripts\\activate on Windows)")
    print("  pip install -r ../requirements.txt")
    print("  uvicorn app.main:app --reload")
    print()
    print("Then visit http://127.0.0.1:8000/docs for interactive API docs.")


def main():
    parser = argparse.ArgumentParser(
        prog="project.py",
        description="SentinelAI STAR-Risk CLI (CS50P final project core module).",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("demo-risk", help="Run a scripted STAR-Risk incident demo.")

    split_parser = subparsers.add_parser("split-video", help="Split a video duration into processing chunks.")
    split_parser.add_argument("--duration", type=float, required=True, help="Total video duration in seconds.")
    split_parser.add_argument("--chunk-size", type=int, required=True, help="Chunk size in seconds.")

    subparsers.add_parser("serve", help="Print instructions for starting the FastAPI backend.")

    args = parser.parse_args()

    if args.command == "demo-risk":
        _run_demo_risk()
    elif args.command == "split-video":
        _run_split_video(args.duration, args.chunk_size)
    elif args.command == "serve":
        _run_serve()
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
