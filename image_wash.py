from __future__ import annotations

import io
import os
import tempfile
import hashlib
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from PIL import Image, ImageOps, ImageFile

# Robust load (handles some broken JPEGs gracefully)
ImageFile.LOAD_TRUNCATED_IMAGES = True


@dataclass
class StoredUpload:
    key: str
    orig_name: str
    path: str
    w: int
    h: int
    fmt: str


def file_key(name: str, data: bytes) -> str:
    # Stable key per file content (sha256 full bytes once)
    h = hashlib.sha256()
    h.update(name.encode("utf-8", errors="ignore"))
    h.update(len(data).to_bytes(8, "little", signed=False))
    h.update(hashlib.sha256(data).digest())
    return h.hexdigest()


def sanitize_to_png_bytes(raw: bytes) -> Tuple[bytes, int, int, str]:
    """
    "Washes" any incoming image:
    - EXIF transpose
    - drop metadata
    - convert to RGB
    - re-encode as optimized PNG (kills JPEG SOS warnings permanently downstream)
    """
    with Image.open(io.BytesIO(raw)) as im:
        im = ImageOps.exif_transpose(im)
        fmt = (im.format or "").upper()
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        elif im.mode == "L":
            # keep L for size, but still safe
            pass

        w, h = im.size
        out = io.BytesIO()
        im.save(out, format="PNG", optimize=True)
        return out.getvalue(), w, h, fmt


def ensure_upload_store(session_state: dict):
    session_state.setdefault("upload_store", {})  # key -> StoredUpload
    session_state.setdefault("upload_tmpfiles", [])  # paths to cleanup


def clear_upload_store(session_state: dict):
    store: Dict[str, StoredUpload] = session_state.get("upload_store", {})
    tmpfiles = session_state.get("upload_tmpfiles", [])
    for p in tmpfiles:
        try:
            if isinstance(p, str) and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass
    store.clear()
    tmpfiles.clear()


def put_sanitized(session_state: dict, up_name: str, raw_bytes: bytes) -> StoredUpload:
    ensure_upload_store(session_state)
    key = file_key(up_name, raw_bytes)
    store: Dict[str, StoredUpload] = session_state["upload_store"]
    if key in store:
        return store[key]

    png_bytes, w, h, fmt = sanitize_to_png_bytes(raw_bytes)

    tf = tempfile.NamedTemporaryFile(prefix="upl_", suffix=".png", delete=False)
    tf.write(png_bytes)
    tf.flush()
    tf.close()

    su = StoredUpload(key=key, orig_name=up_name, path=tf.name, w=w, h=h, fmt=fmt)
    store[key] = su
    session_state["upload_tmpfiles"].append(tf.name)
    return su


def get_bytes(session_state: dict, up_name: str, raw_bytes: bytes) -> bytes:
    su = put_sanitized(session_state, up_name, raw_bytes)
    with open(su.path, "rb") as f:
        return f.read()
