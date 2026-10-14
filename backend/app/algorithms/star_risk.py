"""Re-exports the pure STAR-Risk algorithm functions from the repository
root's project.py (the CS50P-graded module), so the FastAPI backend and the
CS50 CLI share a single source of truth for the algorithm instead of having
two diverging implementations.

We locate the repo root relative to this file (backend/app/algorithms/ ->
../../.. -> repo root) and add it to sys.path if project.py isn't already
importable (e.g. when running backend/ as its own package without the repo
root on PYTHONPATH).
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]

if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from project import (  # noqa: E402  (import after sys.path manipulation, by design)
    calculate_motion_anomaly,
    calculate_star_risk,
    is_incident_triggered,
    split_video_chunks,
)

__all__ = [
    "calculate_motion_anomaly",
    "calculate_star_risk",
    "is_incident_triggered",
    "split_video_chunks",
]
