
from __future__ import annotations
from typing import Any, Dict
import numpy as np

try:
    import cv2
except Exception:  # pragma: no cover
    cv2 = None


def analyze_planogram_photo(image_bytes: bytes, expected_planogram: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """First OpenCV skeleton: detects shelf-like horizontal/vertical structures.

    Install:
      pip install opencv-python-headless numpy
    """
    if cv2 is None:
        return {"ok": False, "message": "opencv-python-headless is not installed"}

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        return {"ok": False, "message": "image could not be decoded"}

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, threshold=80, minLineLength=60, maxLineGap=12)

    horizontal, vertical = [], []
    if lines is not None:
        for x1, y1, x2, y2 in lines[:, 0]:
            dx, dy = abs(x2 - x1), abs(y2 - y1)
            if dx > dy * 4:
                horizontal.append([int(x1), int(y1), int(x2), int(y2)])
            elif dy > dx * 4:
                vertical.append([int(x1), int(y1), int(x2), int(y2)])

    score = min(100, int((len(horizontal) * 2 + len(vertical)) / 2))
    return {
        "ok": True,
        "compliance_score": score,
        "detected_horizontal_lines": len(horizontal),
        "detected_vertical_lines": len(vertical),
        "shelf_candidates": horizontal[:40],
        "vertical_candidates": vertical[:40],
        "next_step": "Perspective correction and product block segmentation can be added after real shelf photos are collected.",
    }
