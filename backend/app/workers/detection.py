"""Object detection applied to a single frame. Shared by both the
file-upload pipeline (process_chunk, batches of sampled frames) and the
live-camera pipeline (one frame at a time, in real time), so there is
exactly one detection implementation regardless of where the video comes
from.

There is no synthetic/fallback detector here: if the YOLO model can't be
loaded (missing weights, no internet to download them, a bad
YOLO_MODEL_PATH), the job fails cleanly with that error instead of
inventing detections. A result the pipeline produces is always something
the model actually saw in the footage.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings
from app.core.logging import get_logger
from app.workers.visual_attributes import classify_dominant_color

logger = get_logger(__name__)

# COCO class id -> name, for the classes this product cares about.
COCO_RELEVANT_CLASSES = {0: "person", 2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}


@dataclass
class RawDetection:
    frame_number: int
    timestamp: float
    x1: float
    y1: float
    x2: float
    y2: float
    confidence: float
    object_class: str
    dominant_color: str = "unknown"


def load_yolo_model(model_path: str):
    """Loads the YOLO detection model. Raises if it can't be loaded
    (missing YOLO_MODEL_PATH, no internet to download the weights, a bad
    path) -- the caller is expected to let that propagate and fail the job
    with that error, rather than silently detecting nothing or inventing
    something."""
    if not model_path:
        raise RuntimeError("YOLO_MODEL_PATH is not configured")
    from ultralytics import YOLO  # noqa: PLC0415

    return YOLO(model_path)


def load_weapon_model(repo_id: str, filename: str, repo_type: str = "model"):
    """Loads a second, dedicated weapon-detection YOLO model. COCO (what
    YOLO_MODEL_PATH is normally pretrained on) has no gun/knife/rifle
    classes at all, so weapon detection requires a model actually trained
    for it -- this downloads and caches one from the Hugging Face Hub
    (repo_type="model" or "space", since some community weapon-detection
    checkpoints are only published inside a Space's files). Returns None
    (weapon detection simply skipped for this session) on any failure: no
    internet, gated/missing repo, huggingface_hub not installed, etc. This
    one case degrades to "no weapon detections" rather than failing the
    whole job, since the main COCO model is still fully functional and
    produces entirely real results on its own -- unlike the old stub
    detector, skipping here never substitutes fabricated data for real."""
    if not repo_id or not filename:
        return None
    try:
        from huggingface_hub import hf_hub_download  # noqa: PLC0415
        from ultralytics import YOLO  # noqa: PLC0415

        weights_path = hf_hub_download(repo_id=repo_id, filename=filename, repo_type=repo_type)
        return YOLO(weights_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Weapon-detection model unavailable (%s); weapon detections disabled for this session.", exc)
        return None


def detect_weapons(weapon_model, frame, frame_number: int, timestamp: float) -> list[RawDetection]:
    """Runs the dedicated weapon-detection model on one frame. Its class
    names come from whatever dataset it was trained on, not COCO, so any
    label it emits is normalized to WEAPON_CLASS_NAMES (falling back to
    WEAPON_MODEL_FALLBACK_CLASS) -- the rest of the pipeline (tracking,
    events.py's weapon flag) only ever needs to know those canonical
    names."""
    try:
        detections: list[RawDetection] = []
        pred = weapon_model(frame, verbose=False, conf=settings.WEAPON_MODEL_CONFIDENCE)[0]
        names = pred.names
        for box in pred.boxes:
            cls_id = int(box.cls[0])
            raw_name = str(names.get(cls_id, settings.WEAPON_MODEL_FALLBACK_CLASS)).strip().lower()
            object_class = raw_name if raw_name in settings.weapon_class_names_set else settings.WEAPON_MODEL_FALLBACK_CLASS
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
            conf = float(box.conf[0])
            detections.append(
                RawDetection(
                    frame_number=frame_number,
                    timestamp=timestamp,
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    confidence=conf,
                    object_class=object_class,
                    dominant_color=classify_dominant_color(frame, x1, y1, x2, y2),
                )
            )
        return detections
    except Exception as exc:  # noqa: BLE001 - a failed inference produces no detections, never a fabricated one
        logger.warning("Weapon-detection inference failed for frame %s: %s", frame_number, exc)
        return []


def detect_frame(model, frame, frame_number: int, timestamp: float, weapon_model=None) -> list[RawDetection]:
    """Runs detection on a single already-read frame and returns picklable
    RawDetection rows with dominant color attached. The one call site every
    caller (file chunks, live frames) should use. When `weapon_model` is
    given, its detections (see detect_weapons) are appended, so a frame
    can report e.g. both "person" and "gun". A failed inference on this
    one frame produces no detections for it (logged), not a substitute
    one -- an empty result is still an honest result."""
    detections: list[RawDetection] = []
    try:
        pred = model(frame, verbose=False)[0]
        for box in pred.boxes:
            cls_id = int(box.cls[0])
            if cls_id not in COCO_RELEVANT_CLASSES:
                continue
            x1, y1, x2, y2 = [float(v) for v in box.xyxy[0]]
            conf = float(box.conf[0])
            detections.append(
                RawDetection(
                    frame_number=frame_number,
                    timestamp=timestamp,
                    x1=x1, y1=y1, x2=x2, y2=y2,
                    confidence=conf,
                    object_class=COCO_RELEVANT_CLASSES[cls_id],
                    dominant_color=classify_dominant_color(frame, x1, y1, x2, y2),
                )
            )
    except Exception as exc:  # noqa: BLE001 - a failed inference produces no detections, never a fabricated one
        logger.warning("Detection failed for frame %s: %s", frame_number, exc)

    if weapon_model is not None:
        detections.extend(detect_weapons(weapon_model, frame, frame_number, timestamp))

    return detections


def process_chunk(
    file_path: str,
    start_seconds: float,
    end_seconds: float,
    fps: float,
    sample_rate: int,
    model_path: str,
) -> list[dict]:
    """Runs in a worker process (ProcessPoolExecutor). Opens its own
    cv2.VideoCapture handle, samples frames within [start, end), detects
    each sampled frame, and returns plain dicts (picklable across the
    process boundary). If the model itself can't be loaded, this raises
    and the exception propagates through the future back to the caller,
    which fails the whole job with that error."""
    import cv2  # local import: only needed in worker processes
    from dataclasses import asdict

    model = load_yolo_model(model_path)
    weapon_model = (
        load_weapon_model(settings.WEAPON_MODEL_REPO_ID, settings.WEAPON_MODEL_FILENAME, settings.WEAPON_MODEL_REPO_TYPE)
        if settings.WEAPON_MODEL_ENABLED
        else None
    )

    cap = cv2.VideoCapture(file_path)
    start_frame = int(start_seconds * fps)
    end_frame = int(end_seconds * fps)
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)

    results: list[dict] = []
    frame_number = start_frame
    while frame_number < end_frame:
        ok, frame = cap.read()
        if not ok:
            break
        if (frame_number - start_frame) % sample_rate == 0:
            timestamp = frame_number / fps if fps > 0 else frame_number
            detections = detect_frame(model, frame, frame_number, timestamp, weapon_model=weapon_model)

            if frame_number == start_frame:
                evidence_dir = Path(settings.UPLOAD_DIR) / "evidence"
                evidence_dir.mkdir(parents=True, exist_ok=True)
                try:
                    cv2.imwrite(str(evidence_dir / f"chunk_{start_frame}.jpg"), frame)
                except Exception:  # noqa: BLE001
                    pass
            results.extend(asdict(d) for d in detections)
        frame_number += 1

    cap.release()
    return results
