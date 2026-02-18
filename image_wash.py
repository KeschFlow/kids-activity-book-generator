from __future__ import annotations

import io
import os
import tempfile
import hashlib
from dataclasses import dataclass
from typing import Optional, Tuple

from PIL import Image, ImageOps, ImageFile

# Robust gegen kaputte/abgeschnittene JPEGs
ImageFile.LOAD_TRUNCATED_IMAGES = True

@dataclass(frozen=True)
class WashedImage:
    bytes: bytes
    ext: str
    sha256: str
    size: Tuple[int, int]

def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def wash_image_bytes(
    raw: bytes,
    prefer_jpeg: bool = True,
    jpeg_quality: int = 92,
) -> WashedImage:
    """
    Normalisiert Bildbytes:
    - Fix EXIF orientation
    - Strip metadata
    - Re-encode (JPEG/PNG)
    Ergebnis ist "sauber" -> keine SOS-Logs.
    """
    if not raw:
        raise ValueError("empty image")

    with Image.open(io.BytesIO(raw)) as im:
        im = ImageOps.exif_transpose(im)

        # Alpha? -> PNG, sonst JPEG
        has_alpha = ("A" in im.getbands()) or (im.mode in ("RGBA", "LA"))
        if has_alpha or not prefer_jpeg:
            out = io.BytesIO()
            im = im.convert("RGBA") if has_alpha else im.convert("RGB")
            im.save(out, format="PNG", optimize=True)
            b = out.getvalue()
            return WashedImage(bytes=b, ext="png", sha256=_sha(b), size=im.size)

        out = io.BytesIO()
        im = im.convert("RGB")
        # progressive=False verhindert manche kaputte Marker-Setups
        im.save(out, format="JPEG", quality=jpeg_quality, optimize=True, progressive=False)
        b = out.getvalue()
        return WashedImage(bytes=b, ext="jpg", sha256=_sha(b), size=im.size)

def wash_to_tempfile(raw: bytes) -> str:
    """
    Spült Upload direkt auf Disk (OOM-Schutz).
    Gibt Pfad zurück.
    """
    w = wash_image_bytes(raw)
    fd, path = tempfile.mkstemp(prefix="eddie_wash_", suffix=f".{w.ext}")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(w.bytes)
    return path
