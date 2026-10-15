"""Local, deterministic OCR for scanned pages and photos (Tesseract).

Runs the locally installed Tesseract binary; nothing leaves the machine.
Pages are prepared first (orientation from EXIF and Tesseract's orientation
detection, grayscale, contrast normalisation, light denoising, upscaling of
low-resolution input), and every OCR word keeps its position and
confidence so extraction can flag uncertain readings for review.

Quality notes describe how readable the *image* was. They are not a measure
of medical accuracy: every extracted value still needs a person to confirm
it against the original page.

The prepared image is a working copy only: the original upload is never
modified or replaced.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter, ImageOps

from src.observability.logging import get_logger

logger = get_logger(__name__)

_WINDOWS_DEFAULTS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"E:\Program Files\Tesseract-OCR\tesseract.exe",
)
OCR_TIMEOUT_SECONDS = float(os.getenv("OCR_TIMEOUT_SECONDS", "60"))
# A full page under ~1600 px on its long edge is below ~150 dpi, where
# small print stops reading reliably: such pages are upscaled for OCR (to
# about TARGET_LONG_EDGE) and flagged as low resolution.
MIN_LONG_EDGE = 1600
TARGET_LONG_EDGE = 2600
# Ink-to-paper brightness gap below which a scan counts as faded.
MIN_INK_CONTRAST = 110
# Tesseract's orientation confidence is unitless; below this, keep as-is.
MIN_ORIENTATION_CONFIDENCE = 2.0


def tesseract_path() -> str | None:
    configured = os.getenv("TESSERACT_CMD", "").strip()
    if configured:
        return configured if Path(configured).exists() else None
    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in _WINDOWS_DEFAULTS:
        if Path(candidate).exists():
            return candidate
    return None


def ocr_available() -> bool:
    return tesseract_path() is not None


@dataclass
class OcrWord:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    confidence: float  # 0-100, Tesseract's own estimate for this word


@dataclass
class OcrPage:
    words: list[OcrWord]
    width: float           # size of the coordinate space of `words`
    height: float
    rotation_applied: int  # degrees clockwise applied before reading
    mean_confidence: float | None
    quality: str           # good | fair | poor | unreadable
    notes: list[str] = field(default_factory=list)


def _run(args: list[str]) -> str:
    binary = tesseract_path()
    if not binary:
        raise RuntimeError("Tesseract is not installed")
    result = subprocess.run(
        [binary, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=OCR_TIMEOUT_SECONDS,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"tesseract exited {result.returncode}")
    return result.stdout


def _orientation(path: Path, dpi: int) -> int:
    """Degrees to rotate clockwise so the text is upright (0 when unsure)."""
    try:
        output = _run([str(path), "stdout", "--psm", "0", "--dpi", str(dpi)])
    except Exception:  # too little text for orientation detection is normal
        return 0
    rotate, confidence = 0, 0.0
    for line in output.splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "Rotate":
            rotate = int(value.strip() or 0)
        elif key.strip() == "Orientation confidence":
            confidence = float(value.strip() or 0)
    return rotate if rotate in (90, 180, 270) and confidence >= MIN_ORIENTATION_CONFIDENCE else 0


def _sharpness(gray: np.ndarray) -> float:
    """Variance of a Laplacian: low values mean a blurry capture."""
    g = gray.astype(np.float32)
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())


def prepare_for_ocr(image: Image.Image) -> tuple[Image.Image, float, list[str]]:
    """Grayscale, contrast-normalised, lightly denoised working copy.

    Returns the prepared image, the factor it was scaled by, and notes on
    what was found (low resolution / contrast / sharpness).
    """
    notes: list[str] = []
    gray = ImageOps.exif_transpose(image).convert("L")
    width, height = gray.size
    scale = 1.0
    if max(width, height) < MIN_LONG_EDGE:
        notes.append("Low resolution")
        scale = min(3.5, TARGET_LONG_EDGE / max(width, height))
        gray = gray.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
    pixels = np.asarray(gray)
    # Documents are mostly paper: compare the darkest ink with the paper
    # (median), not overall spread, which is low even on a crisp page.
    ink_contrast = float(np.median(pixels) - np.percentile(pixels, 0.2))
    if ink_contrast < MIN_INK_CONTRAST:
        notes.append("Low contrast")
        if scale == 1.0:
            # Faded print reads better a little larger once stretched.
            scale = 1.5
            gray = gray.resize((int(width * scale), int(height * scale)), Image.Resampling.LANCZOS)
            pixels = np.asarray(gray)
    if _sharpness(pixels) < 40:
        notes.append("Blurry or out of focus")
    gray = ImageOps.autocontrast(gray, cutoff=1)
    smoothed = gray.filter(ImageFilter.MedianFilter(3))
    # Only denoise when there is speckle to remove; median filtering clean
    # text would erode thin strokes.
    if np.abs(np.asarray(gray, dtype=np.int16) - np.asarray(smoothed, dtype=np.int16)).mean() > 6:
        gray = smoothed
        notes.append("Noise reduced")
    return gray, scale, notes


def _quality(words: list[OcrWord], notes: list[str]) -> tuple[str, float | None]:
    if len(words) < 5:
        return "unreadable", None
    total = sum(len(w.text) for w in words)
    mean = sum(w.confidence * len(w.text) for w in words) / max(total, 1)
    low = sum(1 for w in words if w.confidence < 60) / len(words)
    if mean < 50 or low > 0.5:
        return "poor", round(mean, 1)
    if mean < 75 or low > 0.2 or "Blurry or out of focus" in notes:
        return "fair", round(mean, 1)
    return "good", round(mean, 1)


def ocr_image(image: Image.Image, *, dpi: int = 300) -> OcrPage:
    """OCR an upright-or-rotated page image.

    Word coordinates are returned in the coordinate space of the *upright*
    input image (before OCR upscaling), so callers can map them onto the
    page preview.
    """
    upright = ImageOps.exif_transpose(image).convert("RGB")
    prepared, scale, notes = prepare_for_ocr(upright)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "page.png"
        prepared.save(path)
        rotation = _orientation(path, dpi)
        if rotation:
            prepared = prepared.rotate(-rotation, expand=True)
            upright = upright.rotate(-rotation, expand=True)
            prepared.save(path)
            notes.append(f"Rotated {rotation}° to read")
        output = _run([str(path), "stdout", "--psm", "3", "--dpi", str(dpi), "tsv"])

    words: list[OcrWord] = []
    for line in output.splitlines()[1:]:
        cells = line.split("\t")
        if len(cells) != 12 or not cells[11].strip():
            continue
        try:
            left, top, w, h = (float(v) for v in cells[6:10])
            confidence = float(cells[10])
        except ValueError:
            continue
        if confidence < 0:
            continue
        words.append(OcrWord(
            left / scale, top / scale, (left + w) / scale, (top + h) / scale,
            cells[11].strip(), confidence,
        ))
    quality, mean = _quality(words, notes)
    if quality == "unreadable":
        notes.append("No readable text found")
    elif quality == "poor":
        notes.append("Low OCR confidence")
    logger.info(
        "ocr_page",
        extra={"words": len(words), "quality": quality, "mean_confidence": mean, "rotation": rotation},
    )
    return OcrPage(
        words=words,
        width=float(upright.width),
        height=float(upright.height),
        rotation_applied=rotation,
        mean_confidence=mean,
        quality=quality,
        notes=notes,
    )
