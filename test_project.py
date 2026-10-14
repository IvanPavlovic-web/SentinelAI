"""
test_project.py - pytest tests for SentinelAI's project.py (CS50P final project).

Run with:  python -m pytest test_project.py -v
"""

import pytest

from project import (
    calculate_risk,
    is_incident_triggered,
    calculate_motion_anomaly,
    split_video_chunks,
)


# --------------------------------------------------------------------------
# calculate_risk
# --------------------------------------------------------------------------

def test_calculate_risk():
    # High severity zone, full dwell, high anomaly, after hours, strong
    # confidence streak -> should produce a high risk score.
    risk_high = calculate_risk(
        zone_severity="critical",
        dwell_seconds=20.0,
        minimum_dwell_seconds=10.0,
        motion_anomaly=1.0,
        after_hours=True,
        confidence_history=[0.8, 0.85, 0.9, 0.95, 0.99],
        previous_risk=0.0,
        alpha=1.0,
    )
    # raw = 100*(0.35*1 + 0.25*1 + 0.20*1 + 0.10*1 + 0.10*C)
    # C: window=5 all>=0.6 consecutive=5, avg=0.898 -> C=0.898
    # raw = 100*(0.35+0.25+0.20+0.10+0.0898) = 100*0.9898 = 98.98
    assert risk_high == pytest.approx(98.98, abs=0.1)

    # No zone, no dwell, no anomaly, daytime, no confidence history -> 0 risk.
    risk_low = calculate_risk(
        zone_severity=None,
        dwell_seconds=0.0,
        minimum_dwell_seconds=10.0,
        motion_anomaly=0.0,
        after_hours=False,
        confidence_history=[],
        previous_risk=0.0,
        alpha=1.0,
    )
    assert risk_low == 0.0
    assert risk_high > risk_low


def test_calculate_risk_alpha_boundaries():
    # alpha=0 -> result is exactly previous_risk regardless of inputs.
    risk = calculate_risk(
        zone_severity="high",
        dwell_seconds=50.0,
        minimum_dwell_seconds=5.0,
        motion_anomaly=1.0,
        after_hours=True,
        confidence_history=[0.9, 0.9, 0.9],
        previous_risk=42.0,
        alpha=0.0,
    )
    assert risk == pytest.approx(42.0)

    # alpha=1 -> result is exactly the raw risk, previous_risk ignored.
    risk_full = calculate_risk(
        zone_severity=None,
        dwell_seconds=0.0,
        minimum_dwell_seconds=10.0,
        motion_anomaly=0.0,
        after_hours=False,
        confidence_history=[],
        previous_risk=99.0,
        alpha=1.0,
    )
    assert risk_full == 0.0


def test_calculate_risk_zero_and_negative_minimum_dwell():
    # minimum_dwell_seconds <= 0 is guarded: dwell score becomes 0, no error.
    risk = calculate_risk(
        zone_severity=None,
        dwell_seconds=5.0,
        minimum_dwell_seconds=0.0,
        motion_anomaly=0.0,
        after_hours=False,
        confidence_history=[],
        alpha=1.0,
    )
    assert risk == 0.0

    risk_neg = calculate_risk(
        zone_severity=None,
        dwell_seconds=5.0,
        minimum_dwell_seconds=-3.0,
        motion_anomaly=0.0,
        after_hours=False,
        confidence_history=[],
        alpha=1.0,
    )
    assert risk_neg == 0.0


def test_calculate_risk_exact_dwell_boundary():
    # dwell_seconds exactly equal to minimum_dwell_seconds -> dwell score = 1.0 (capped).
    risk_exact = calculate_risk(
        zone_severity=None,
        dwell_seconds=10.0,
        minimum_dwell_seconds=10.0,
        motion_anomaly=0.0,
        after_hours=False,
        confidence_history=[],
        alpha=1.0,
    )
    # raw = 100 * 0.25*1.0 = 25.0
    assert risk_exact == pytest.approx(25.0)

    # dwell_seconds beyond minimum -> still capped at 1.0 (same result).
    risk_over = calculate_risk(
        zone_severity=None,
        dwell_seconds=50.0,
        minimum_dwell_seconds=10.0,
        motion_anomaly=0.0,
        after_hours=False,
        confidence_history=[],
        alpha=1.0,
    )
    assert risk_over == pytest.approx(25.0)


def test_calculate_risk_invalid_inputs():
    with pytest.raises(ValueError):
        calculate_risk(
            zone_severity="not-a-real-zone",
            dwell_seconds=1.0,
            minimum_dwell_seconds=10.0,
            motion_anomaly=0.0,
            after_hours=False,
            confidence_history=[],
        )

    with pytest.raises(ValueError):
        calculate_risk(
            zone_severity=None,
            dwell_seconds=-1.0,
            minimum_dwell_seconds=10.0,
            motion_anomaly=0.0,
            after_hours=False,
            confidence_history=[],
        )

    with pytest.raises(ValueError):
        calculate_risk(
            zone_severity=None,
            dwell_seconds=1.0,
            minimum_dwell_seconds=10.0,
            motion_anomaly=0.0,
            after_hours=False,
            confidence_history=[1.5],
        )

    with pytest.raises(ValueError):
        calculate_risk(
            zone_severity=None,
            dwell_seconds=1.0,
            minimum_dwell_seconds=10.0,
            motion_anomaly=0.0,
            after_hours=False,
            confidence_history=[],
            alpha=1.5,
        )


def test_calculate_risk_zone_case_insensitive():
    r_lower = calculate_risk(
        zone_severity="high",
        dwell_seconds=0.0,
        minimum_dwell_seconds=10.0,
        motion_anomaly=0.0,
        after_hours=False,
        confidence_history=[],
        alpha=1.0,
    )
    r_mixed = calculate_risk(
        zone_severity="HiGh",
        dwell_seconds=0.0,
        minimum_dwell_seconds=10.0,
        motion_anomaly=0.0,
        after_hours=False,
        confidence_history=[],
        alpha=1.0,
    )
    assert r_lower == r_mixed == pytest.approx(100 * 0.35 * 0.75)


# --------------------------------------------------------------------------
# is_incident_triggered
# --------------------------------------------------------------------------

def test_is_incident_triggered():
    # Exactly at required count, all >= threshold -> True.
    assert is_incident_triggered([50, 80, 90, 95], 80, consecutive_required=3) is True

    # Just under required count of qualifying entries -> False.
    assert is_incident_triggered([95, 95, 40, 95], 80, consecutive_required=3) is False

    # Empty list -> False.
    assert is_incident_triggered([], 80) is False

    # Fewer entries than required -> False.
    assert is_incident_triggered([90, 95], 80, consecutive_required=3) is False


def test_is_incident_triggered_hysteresis_exact_vs_short():
    threshold = 70.0
    # Exactly consecutive_required qualifying values at the tail -> True.
    history_exact = [10, 20, 71, 72, 73]
    assert is_incident_triggered(history_exact, threshold, consecutive_required=3) is True

    # One short of required (only last 2 qualify, 3rd-from-last doesn't) -> False.
    history_short = [10, 69, 71, 72]
    assert is_incident_triggered(history_short, threshold, consecutive_required=3) is False


def test_is_incident_triggered_invalid_consecutive_required():
    with pytest.raises(ValueError):
        is_incident_triggered([90, 90, 90], 80, consecutive_required=0)
    with pytest.raises(ValueError):
        is_incident_triggered([90, 90, 90], 80, consecutive_required=-1)


# --------------------------------------------------------------------------
# calculate_motion_anomaly
# --------------------------------------------------------------------------

def test_calculate_motion_anomaly():
    # Static track (no movement) -> 0.0
    static_centroids = [(10.0, 10.0)] * 5
    static_timestamps = [0.0, 1.0, 2.0, 3.0, 4.0]
    assert calculate_motion_anomaly(static_centroids, static_timestamps) == 0.0

    # Smooth, steady linear movement -> no reversals/bursts -> 0.0
    smooth_centroids = [(float(i), float(i)) for i in range(6)]
    smooth_timestamps = [float(i) for i in range(6)]
    assert calculate_motion_anomaly(smooth_centroids, smooth_timestamps) == 0.0

    # Fewer than 3 points -> 0.0
    assert calculate_motion_anomaly([(0, 0), (1, 1)], [0.0, 1.0]) == 0.0


def test_calculate_motion_anomaly_direction_reversal():
    # Moves right, then sharply reverses left -> at least one reversal detected.
    centroids = [(0.0, 0.0), (10.0, 0.0), (0.0, 0.0), (10.0, 0.0)]
    timestamps = [0.0, 1.0, 2.0, 3.0]
    score = calculate_motion_anomaly(centroids, timestamps)
    assert score > 0.0


def test_calculate_motion_anomaly_speed_burst():
    # Slow steady movement then a sudden large jump (speed burst).
    centroids = [(0.0, 0.0), (1.0, 0.0), (2.0, 0.0), (50.0, 0.0)]
    timestamps = [0.0, 1.0, 2.0, 3.0]
    score = calculate_motion_anomaly(centroids, timestamps)
    assert score > 0.0


def test_calculate_motion_anomaly_mismatched_lengths():
    with pytest.raises(ValueError):
        calculate_motion_anomaly([(0, 0), (1, 1), (2, 2)], [0.0, 1.0])


# --------------------------------------------------------------------------
# split_video_chunks
# --------------------------------------------------------------------------

def test_split_video_chunks():
    chunks = split_video_chunks(130.0, 30)
    assert len(chunks) == 5
    assert chunks[0] == (0.0, 30.0)
    assert chunks[1] == (30.0, 60.0)
    assert chunks[2] == (60.0, 90.0)
    assert chunks[3] == (90.0, 120.0)
    assert chunks[4] == (120.0, 130.0)  # last chunk shorter (10s)


def test_split_video_chunks_exact_division():
    chunks = split_video_chunks(90.0, 30)
    assert chunks == [(0.0, 30.0), (30.0, 60.0), (60.0, 90.0)]
    # No gaps/overlaps: each chunk's end == next chunk's start.
    for (_, end), (start, _) in zip(chunks, chunks[1:]):
        assert end == start


def test_split_video_chunks_invalid_inputs():
    with pytest.raises(ValueError):
        split_video_chunks(0.0, 10)
    with pytest.raises(ValueError):
        split_video_chunks(-5.0, 10)
    with pytest.raises(ValueError):
        split_video_chunks(100.0, 0)
    with pytest.raises(ValueError):
        split_video_chunks(100.0, -10)


def test_split_video_chunks_chunk_larger_than_duration():
    # Single chunk shorter than requested chunk size.
    chunks = split_video_chunks(5.0, 30)
    assert chunks == [(0.0, 5.0)]
