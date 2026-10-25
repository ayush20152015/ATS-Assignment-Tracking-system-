"""Load a student submission (image or PDF) into base64 JPEG pages for the vision model."""
from __future__ import annotations

import base64
import io
import os

import pymupdf
from PIL import Image

MAX_EDGE = 1600          # keep the payload well under the 10 MB request limit
JPEG_QUALITY = 80


def _encode(pil_image: Image.Image) -> str:
    pil_image = pil_image.convert("RGB")
    w, h = pil_image.size
    scale = min(1.0, MAX_EDGE / max(w, h))
    if scale < 1.0:
        pil_image = pil_image.resize((int(w * scale), int(h * scale)))
    buf = io.BytesIO()
    pil_image.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def load_submission(path: str) -> list[str]:
    """Return a list of base64 JPEG strings, one per page."""
    if os.path.splitext(path)[1].lower() == ".pdf":
        pages: list[str] = []
        with pymupdf.open(path) as doc:
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                pages.append(_encode(Image.open(io.BytesIO(pix.tobytes("png")))))
        return pages
    with Image.open(path) as img:
        return [_encode(img)]
