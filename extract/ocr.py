"""PNG receipt -> text via Tesseract. Lidl receipts mix Bulgarian and English
(brand names like "SCHWEPPES"), so OCR runs with both languages ("bul+eng") —
bul-only mangles Latin words into Cyrillic. Light preprocessing helps the
thermal-print digit noise. Requires the system `tesseract` binary + `bul`/`eng`
data (installed in the Docker image).

OCR is the slow step, so results are cached by file **content hash** under
`data/ocr_cache/`. A scheduled rebuild (rclone sync -> build_db) then only OCRs
new or changed images; unchanged ones are read from the cache instantly. The
cache survives rebuilds (it lives in the mounted `data/`) and is safe to delete.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytesseract
from PIL import Image, ImageOps

from config import DATA_DIR

CACHE_DIR = DATA_DIR / "ocr_cache"


def _run_tesseract(path: Path) -> str:
    with Image.open(path) as src:
        img = ImageOps.exif_transpose(src)
    img = ImageOps.grayscale(img)
    w, h = img.size
    if max(w, h) < 2000:                      # upscale small scans
        img = img.resize((w * 2, h * 2), Image.Resampling.LANCZOS)
    img = ImageOps.autocontrast(img)
    return pytesseract.image_to_string(img, lang="bul+eng")


def ocr_image(path: str | Path, use_cache: bool = True) -> str:
    """OCR an image to text, caching the result by content hash.

    The cache key is the SHA-1 of the file bytes, so identical content always
    hits the cache regardless of filename/mtime, and any change re-OCRs.
    """
    path = Path(path)
    if not use_cache:
        return _run_tesseract(path)
    key = hashlib.sha1(path.read_bytes()).hexdigest()
    cached = CACHE_DIR / f"{key}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    text = _run_tesseract(path)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf-8")
    return text
