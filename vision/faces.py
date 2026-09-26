"""faces.py — find faces (YuNet) and describe each as 128 numbers (SFace), both from OpenCV's model zoo.

Two faces of one person score a cosine similarity above about 0.36 in SFace's own tests.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

cv2.setNumThreads(2)  # several classifier shards share the cores
MODELS = Path(__file__).resolve().parent.parent / "models"
_det = None
_rec = None


def _load():
    global _det, _rec
    if _det is None:
        _det = cv2.FaceDetectorYN.create(str(MODELS / "yunet.onnx"), "", (320, 320), 0.8, 0.3, 50)
        _rec = cv2.FaceRecognizerSF.create(str(MODELS / "sface.onnx"), "")


def find(rgb: np.ndarray, max_side: int = 640) -> list[dict]:
    """Faces in an RGB array: x, y, w, h (pixels of the input), det score, unit embedding."""
    _load()
    h, w = rgb.shape[:2]
    k = min(1.0, max_side / max(h, w))
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if k < 1:
        bgr = cv2.resize(bgr, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA)
    _det.setInputSize((bgr.shape[1], bgr.shape[0]))
    _, dets = _det.detect(bgr)
    out = []
    if dets is None:
        return out
    for d in dets:
        aligned = _rec.alignCrop(bgr, d)
        e = _rec.feature(aligned).flatten().astype(np.float32)
        e /= np.linalg.norm(e) + 1e-9
        x, y, fw, fh = (d[:4] / k).tolist()
        out.append({"x": x, "y": y, "w": fw, "h": fh, "score": float(d[14]), "emb": e})
    return out
