"""PNG receipt -> text via Tesseract (Bulgarian). Light preprocessing helps the
thermal-print digit noise. Requires the system `tesseract` binary + `bul` data
(installed in the Docker image)."""
from __future__ import annotations

from pathlib import Path

import pytesseract
from PIL import Image, ImageOps


def ocr_image(path: str | Path) -> str:
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    img = ImageOps.grayscale(img)
    w, h = img.size
    if max(w, h) < 2000:                      # upscale small scans
        img = img.resize((w * 2, h * 2))
    img = ImageOps.autocontrast(img)
    return pytesseract.image_to_string(img, lang="bul")
