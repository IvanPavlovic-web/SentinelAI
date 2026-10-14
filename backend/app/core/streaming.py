"""HTTP Range-request video streaming.

Browsers require byte-range support (HTTP 206 Partial Content) to seek/scrub
within a <video> element and to avoid downloading the whole file up front.
Starlette's plain FileResponse doesn't negotiate Range requests, so this is
a small, deliberately self-contained implementation rather than a dependency
for something this bounded.
"""
from __future__ import annotations

import os
import re

from fastapi import HTTPException, Request, status
from starlette.responses import Response, StreamingResponse

CHUNK_SIZE = 1024 * 1024  # 1MB
RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def stream_video_file(file_path: str, request: Request, media_type: str = "video/mp4") -> Response:
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video file not found on disk")

    file_size = os.path.getsize(file_path)
    range_header = request.headers.get("range")

    if range_header is None:
        def full_file_iterator():
            with open(file_path, "rb") as f:
                while chunk := f.read(CHUNK_SIZE):
                    yield chunk

        return StreamingResponse(
            full_file_iterator(),
            media_type=media_type,
            headers={"Accept-Ranges": "bytes", "Content-Length": str(file_size)},
        )

    match = RANGE_RE.match(range_header)
    if not match:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid Range header")

    start_str, end_str = match.groups()
    start = int(start_str) if start_str else 0
    end = int(end_str) if end_str else file_size - 1
    end = min(end, file_size - 1)
    if start > end or start >= file_size:
        raise HTTPException(status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE, detail="Invalid Range")

    length = end - start + 1

    def range_iterator():
        with open(file_path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        range_iterator(),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(length),
        },
    )
