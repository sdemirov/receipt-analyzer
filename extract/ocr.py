"""PNG receipt -> text via Tesseract. Lidl receipts mix Bulgarian and English
(brand names like "SCHWEPPES"), so OCR runs with both languages ("bul+eng") —
bul-only mangles Latin words into Cyrillic. Light preprocessing helps the
thermal-print digit noise. Requires the system `tesseract` binary + `bul`/`eng`
data (installed in the Docker image)."""
from __future__ import annotations

from pathlib import Path

import pytesseract
from PIL import Image, ImageOps


def ocr_image(path: str | Path) -> str:
    with Image.open(path) as src:
        img = ImageOps.exif_transpose(src)
    img = ImageOps.grayscale(img)
    w, h = img.size
    if max(w, h) < 2000:                      # upscale small scans
        img = img.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
    img = ImageOps.autocontrast(img)
    return pytesseract.image_to_string(img, lang="bul+eng")
