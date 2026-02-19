# =========================================================
<<<<<<< HEAD
# app.py — Eddies Questbook Edition — BRAND & PRE-READER (v4.7.3 FIXED)
#
# Fix v4.7.3:
# - FIX: image_wash API mismatch (wash_image_bytes only)
# - FIX: UploadedFile handling (always bytes)
# - FIX: Cover collage uses sanitized bytes
# - STABLE: Streamlit Cloud safe + cache guard + no session_state/value conflicts
=======
# app.py — Eddies Questbook Edition — BRAND & PRE-READER (v4.7.4 FIXED)
#
# Fix v4.7.4:
# - FIX: image_wash API mismatch (use wash_image_bytes -> bytes, no .bytes, no wash_image())
# - FIX: Streamlit stable caching (session_state LRU)
# - FIX: Upload read safety + deterministic signature
# - KEEP: Eddie brand mark: tongue / dog
# - KEEP: Pre-reader overlay (icons)
# - KEEP: KDP safe margins + bleed
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
# =========================================================

from __future__ import annotations

import io
import os
import gc
import tempfile
import hashlib
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from collections import OrderedDict

import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFile

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
import os

def _draw_logo(c, x_center, y_center, width):
    path = "eddie_logo.png"
    if not os.path.exists(path):
        return
    try:
        img = ImageReader(path)
        w = width
        h = width
        c.drawImage(
            img,
            x_center - w/2,
            y_center - h/2,
            width=w,
            height=h,
            mask="auto"
        )
    except Exception:
        pass
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth

<<<<<<< HEAD
# --- Upload sanitizer (must expose wash_image_bytes(b: bytes) -> bytes) ---
=======
# --- Upload sanitizer (your file) ---
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
import image_wash as iw

ImageFile.LOAD_TRUNCATED_IMAGES = True

# =========================================================
# QUEST SYSTEM
# =========================================================
try:
    import quest_data as qd
except Exception as e:
    qd = None
    _QD_IMPORT_ERROR = str(e)
else:
    _QD_IMPORT_ERROR = ""

# =========================================================
# CONFIG
# =========================================================
APP_TITLE = "Eddies BRAND Engine"
APP_ICON = "🐶"

EDDIE_PURPLE = "#7c3aed"

DPI = 300
TRIM_IN = 8.5
TRIM = TRIM_IN * inch
BLEED = 0.125 * inch
SAFE_INTERIOR = 0.375 * inch

INK_BLACK = colors.Color(0, 0, 0)
INK_GRAY_70 = colors.Color(0.30, 0.30, 0.30)

PAPER_FACTORS = {
    "Schwarzweiß – Weiß": 0.002252,
    "Schwarzweiß – Creme": 0.0025,
    "Farbe – Weiß (Standard)": 0.002252,
    "Farbe – Weiß (Premium)": 0.002347,
}

SPINE_TEXT_MIN_PAGES = 79
KDP_MIN_PAGES = 24

<<<<<<< HEAD
MAX_SKETCH_CACHE = 256
BUILD_TAG = "v4.7.3-fixed-wash-bytes"
=======
MAX_SKETCH_CACHE = 256  # per-session LRU entries
MAX_WASH_CACHE = 64     # per-session LRU entries (washed jpeg bytes)

BUILD_TAG = "v4.7.4-fixed-bytes"

>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102

# =========================================================
# PAGE GEOMETRY
# =========================================================
@dataclass(frozen=True)
class PageBox:
    trim_w: float
    trim_h: float
    bleed: float
    full_w: float
    full_h: float


def page_box(trim_w: float, trim_h: float, kdp_bleed: bool) -> PageBox:
    bleed = BLEED if kdp_bleed else 0.0
    return PageBox(
        trim_w=trim_w,
        trim_h=trim_h,
        bleed=bleed,
        full_w=trim_w + 2.0 * bleed,
        full_h=trim_h + 2.0 * bleed,
    )


def _kdp_inside_gutter_in(pages: int) -> float:
    if pages <= 150:
        return 0.375
    if pages <= 300:
        return 0.500
    if pages <= 500:
        return 0.625
    if pages <= 700:
        return 0.750
    return 0.875


def safe_margins_for_page(pages: int, kdp: bool, page_index_0: int, pb: PageBox) -> Tuple[float, float, float]:
    if not kdp:
        s = SAFE_INTERIOR
        return s, s, s

    outside = pb.bleed + (0.375 * inch)
    safe_tb = pb.bleed + (0.375 * inch)
    gutter = pb.bleed + (_kdp_inside_gutter_in(pages) * inch)

    is_odd = ((page_index_0 + 1) % 2 == 1)
    safe_left = gutter if is_odd else outside
    safe_right = outside if is_odd else gutter
    return safe_left, safe_right, safe_tb


def _draw_kdp_debug_guides(c: canvas.Canvas, pb: PageBox, safe_l: float, safe_r: float, safe_tb: float):
    c.saveState()
    c.setLineWidth(0.5)
    c.setDash(3, 3)
    if pb.bleed > 0:
        c.setStrokeColor(DEBUG_BLEED_COLOR)
        c.rect(pb.bleed, pb.bleed, pb.full_w - 2 * pb.bleed, pb.full_h - 2 * pb.bleed, stroke=1, fill=0)
    c.setStrokeColor(DEBUG_SAFE_COLOR)
    c.rect(safe_l, safe_tb, pb.full_w - safe_l - safe_r, pb.full_h - 2 * safe_tb, stroke=1, fill=0)
    c.setDash()
    c.restoreState()


# =========================================================
# FONTS & TEXT TOOLS
# =========================================================
def _try_register_fonts() -> Dict[str, str]:
    normal_p = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_p = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if os.path.exists(normal_p):
<<<<<<< HEAD
        try: pdfmetrics.registerFont(TTFont("EDDIES_FONT", normal_p))
        except Exception: pass
    if os.path.exists(bold_p):
        try: pdfmetrics.registerFont(TTFont("EDDIES_FONT_BOLD", bold_p))
        except Exception: pass
=======
        try:
            pdfmetrics.registerFont(TTFont("EDDIES_FONT", normal_p))
        except Exception:
            pass

    if os.path.exists(bold_p):
        try:
            pdfmetrics.registerFont(TTFont("EDDIES_FONT_BOLD", bold_p))
        except Exception:
            pass

>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    f_n = "EDDIES_FONT" if "EDDIES_FONT" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    f_b = "EDDIES_FONT_BOLD" if "EDDIES_FONT_BOLD" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    return {"normal": f_n, "bold": f_b}


FONTS = _try_register_fonts()


def _set_font(c: canvas.Canvas, bold: bool, size: int, leading: Optional[float] = None) -> float:
    c.setFont(FONTS["bold"] if bold else FONTS["normal"], size)
    return float(leading if leading is not None else size * 1.22)


def _wrap_text_hard(text: str, font: str, size: int, max_w: float) -> List[str]:
    text = (text or "").strip()
    if not text:
        return [""]
<<<<<<< HEAD
=======

>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    words = text.split()
    lines: List[str] = []
    cur = ""

    def fits(s: str) -> bool:
        return stringWidth(s, font, size) <= max_w

    for w in words:
        trial = (cur + " " + w).strip()
        if cur and fits(trial):
            cur = trial
        elif not cur and fits(w):
            cur = w
        else:
            if cur:
                lines.append(cur)
            if not fits(w):
                chunk = ""
                for ch in w:
                    if fits(chunk + ch):
                        chunk += ch
                    else:
                        if chunk:
                            lines.append(chunk)
                        chunk = ch
                cur = chunk
            else:
                cur = w

    if cur:
        lines.append(cur)
    return lines


def _fit_lines(lines: List[str], max_lines: int) -> List[str]:
    if len(lines) <= max_lines:
        return lines
    out = lines[:max_lines]
    last = out[-1].rstrip()
    out[-1] = (last[:-3].rstrip() if len(last) > 3 else last) + "…"
    return out

<<<<<<< HEAD
=======

>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
def _kid_short(s: str, max_words: int = 4) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = s.replace("•", " ").replace("→", " ").replace("-", " ")
    words = [w for w in s.split() if w and len(w) > 1]
    return " ".join(words[:max_words])

<<<<<<< HEAD
=======

>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
def _autoscale_mission_text(mission, w: float, x0: float, pad_x: float, max_card_h: float) -> Dict[str, Any]:
    base_top, base_bottom = 0.36 * inch, 0.40 * inch
    gap_title, gap_sections = 0.10 * inch, 0.06 * inch

    body_max_w_move = (x0 + w - pad_x) - (x0 + 1.05 * inch)
    body_max_w_think = (x0 + w - pad_x) - (x0 + 0.90 * inch)

    def compute(ts: int, bs: int, ls: int) -> Dict[str, Any]:
        tl = ts * 1.22
        bl = bs * 1.28
        ll = ls * 1.22
        ml = _wrap_text_hard(getattr(mission, "movement", ""), FONTS["normal"], bs, body_max_w_move)
        tl_lines = _wrap_text_hard(getattr(mission, "thinking", ""), FONTS["normal"], bs, body_max_w_think)
        needed = base_top + tl + gap_title + (ll * 2) + ((len(ml) + len(tl_lines)) * bl) + gap_sections + base_bottom
        return {"ts": ts, "bs": bs, "ls": ls, "tl": tl, "bl": bl, "ll": ll, "ml": ml, "tl_lines": tl_lines, "needed": needed}

    ts, bs, ls = 13, 10, 10
    sc = compute(ts, bs, ls)
    while sc["needed"] > max_card_h and (ts > 10 or bs > 8 or ls > 8):
<<<<<<< HEAD
        if ts > 10: ts -= 1
        if bs > 8: bs -= 1
        if ls > 8: ls -= 1
        sc = compute(ts, bs, ls)
=======
        if ts > 10:
            ts -= 1
        if bs > 8:
            bs -= 1
        if ls > 8:
            ls -= 1
        sc = compute(ts, bs, ls)

    # hard clamp lines if still too tall
    if sc["needed"] > max_card_h:
        rem = max_card_h - (base_top + sc["tl"] + gap_title + (sc["ll"] * 2) + gap_sections + base_bottom)
        max_b = max(2, int(rem // sc["bl"]))
        move_allow = max(1, max_b // 2)
        think_allow = max(1, max_b - move_allow)
        sc["ml"] = _fit_lines(sc["ml"], move_allow)
        sc["tl_lines"] = _fit_lines(sc["tl_lines"], think_allow)

>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    return sc


def _stable_seed(s: str) -> int:
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:8], "big")


# =========================================================
<<<<<<< HEAD
# BRAND MARK
# =========================================================
def _draw_eddie(c: canvas.Canvas, cx: float, cy: float, r: float, style: str = "tongue"):
=======
# BRAND ICONS
# =========================================================
def _draw_eddie(c: canvas.Canvas, cx: float, cy: float, r: float, style: str = "tongue"):
    """
    style:
      - "tongue": minimal brand mark (lila Zunge)
      - "dog": mini dog-head outline (simple)
    """
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    c.saveState()

    if style == "tongue":
        t_w = r * 0.55
        t_h = r * 0.70
<<<<<<< HEAD
        c.setFillColor(colors.HexColor(EDDIE_PURPLE))
        c.setStrokeColor(INK_BLACK)
        c.setLineWidth(max(1.2, r * 0.06))
        x0 = cx - t_w / 2
        y0 = cy - t_h / 2
        c.roundRect(x0, y0, t_w, t_h, r * 0.18, stroke=1, fill=1)
        c.setLineWidth(max(0.8, r * 0.03))
        c.line(cx, y0 + t_h * 0.15, cx, y0 + t_h * 0.45)
        c.restoreState()
        return

    # "dog" – very simple head + tongue (no smiley face)
=======

        c.setFillColor(colors.HexColor(EDDIE_PURPLE))
        c.setStrokeColor(INK_BLACK)
        c.setLineWidth(max(1.2, r * 0.06))

        x0 = cx - t_w / 2
        y0 = cy - t_h / 2

        c.roundRect(x0, y0, t_w, t_h, r * 0.18, stroke=1, fill=1)
        c.setLineWidth(max(0.8, r * 0.03))
        c.line(cx, y0 + t_h * 0.15, cx, y0 + t_h * 0.45)

        c.restoreState()
        return

    # "dog" head + tongue
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    c.setStrokeColor(INK_BLACK)
    c.setFillColor(colors.white)
    c.setLineWidth(max(1.2, r * 0.06))
    c.circle(cx, cy, r, stroke=1, fill=1)

<<<<<<< HEAD
    # ears
    c.line(cx - r*0.75, cy + r*0.35, cx - r*0.25, cy + r*0.95)
    c.line(cx + r*0.75, cy + r*0.35, cx + r*0.25, cy + r*0.95)

    # tongue
    c.setFillColor(colors.HexColor(EDDIE_PURPLE))
    c.roundRect(cx - r*0.12, cy - r*0.55, r*0.24, r*0.30, r*0.10, stroke=0, fill=1)

    c.restoreState()

# =========================================================
# PRE-READER ICONS
# =========================================================
def _icon_run(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    c.setStrokeColor(INK_BLACK); c.setLineWidth(max(1.2, size*0.10))
    c.circle(x+size*0.30, y+size*0.72, size*0.12, stroke=1, fill=0)
    c.line(x+size*0.30, y+size*0.60, x+size*0.30, y+size*0.30)
    c.line(x+size*0.30, y+size*0.50, x+size*0.55, y+size*0.40)
    c.line(x+size*0.30, y+size*0.50, x+size*0.05, y+size*0.40)
    c.line(x+size*0.30, y+size*0.30, x+size*0.15, y+size*0.10)
    c.line(x+size*0.30, y+size*0.30, x+size*0.50, y+size*0.12)
    c.restoreState()

def _icon_brain(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    c.setStrokeColor(INK_BLACK); c.setLineWidth(max(1.2, size*0.08))
    c.roundRect(x+size*0.15, y+size*0.20, size*0.70, size*0.60, size*0.18, stroke=1, fill=0)
    c.line(x+size*0.50, y+size*0.20, x+size*0.50, y+size*0.80)
    c.restoreState()

def _icon_check(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    c.setStrokeColor(INK_BLACK); c.setLineWidth(max(1.2, size*0.08))
    c.rect(x+size*0.15, y+size*0.20, size*0.70, size*0.60, stroke=1, fill=0)
    c.line(x+size*0.30, y+size*0.45, x+size*0.45, y+size*0.30)
    c.line(x+size*0.45, y+size*0.30, x+size*0.70, y+size*0.65)
    c.restoreState()

# =========================================================
# BYTES HELPERS (THIS FIXES YOUR ERROR)
# =========================================================
def _upload_to_bytes(up) -> bytes:
    # Streamlit UploadedFile: .getvalue() is stable
    try:
        return up.getvalue()
    except Exception:
        return bytes(up)

def _wash_upload_to_bytes(up) -> bytes:
    raw = _upload_to_bytes(up)
    # image_wash returns JPEG bytes
    washed = iw.wash_image_bytes(raw)
    if not isinstance(washed, (bytes, bytearray)):
        raise RuntimeError("image_wash.wash_image_bytes() muss bytes zurückgeben.")
    return bytes(washed)

# =========================================================
# SKETCH CACHE
=======
    c.line(cx - r * 0.55, cy + r * 0.55, cx - r * 0.15, cy + r * 0.95)
    c.line(cx - r * 0.15, cy + r * 0.95, cx - r * 0.05, cy + r * 0.45)

    c.line(cx + r * 0.55, cy + r * 0.55, cx + r * 0.15, cy + r * 0.95)
    c.line(cx + r * 0.15, cy + r * 0.95, cx + r * 0.05, cy + r * 0.45)

    c.setFillColor(colors.HexColor(EDDIE_PURPLE))
    c.roundRect(cx - r * 0.12, cy - r * 0.45, r * 0.24, r * 0.28, r * 0.10, stroke=0, fill=1)
    c.restoreState()


def _icon_run(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(max(1.2, size * 0.10))
    c.circle(x + size * 0.30, y + size * 0.72, size * 0.12, stroke=1, fill=0)
    c.line(x + size * 0.30, y + size * 0.60, x + size * 0.30, y + size * 0.30)
    c.line(x + size * 0.30, y + size * 0.50, x + size * 0.55, y + size * 0.40)
    c.line(x + size * 0.30, y + size * 0.50, x + size * 0.05, y + size * 0.40)
    c.line(x + size * 0.30, y + size * 0.30, x + size * 0.15, y + size * 0.10)
    c.line(x + size * 0.30, y + size * 0.30, x + size * 0.50, y + size * 0.12)
    c.restoreState()


def _icon_brain(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(max(1.2, size * 0.08))
    c.roundRect(x + size * 0.15, y + size * 0.20, size * 0.70, size * 0.60, size * 0.18, stroke=1, fill=0)
    c.line(x + size * 0.50, y + size * 0.20, x + size * 0.50, y + size * 0.80)
    c.circle(x + size * 0.35, y + size * 0.50, size * 0.05, stroke=1, fill=1)
    c.circle(x + size * 0.65, y + size * 0.50, size * 0.05, stroke=1, fill=1)
    c.restoreState()


def _icon_check(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(max(1.2, size * 0.08))
    c.rect(x + size * 0.15, y + size * 0.20, size * 0.70, size * 0.60, stroke=1, fill=0)
    c.line(x + size * 0.30, y + size * 0.45, x + size * 0.45, y + size * 0.30)
    c.line(x + size * 0.45, y + size * 0.30, x + size * 0.70, y + size * 0.65)
    c.restoreState()


# =========================================================
# CACHES (session_state LRU)
# =========================================================
def _get_lru(name: str, max_items: int) -> "OrderedDict":
    od = st.session_state.get(name)
    if not isinstance(od, OrderedDict):
        od = OrderedDict()
        st.session_state[name] = od
    # store max for later use
    st.session_state[f"{name}__max"] = max_items
    return od


def _lru_put(od: "OrderedDict", key, value, max_items: int):
    od[key] = value
    od.move_to_end(key)
    while len(od) > max_items:
        od.popitem(last=False)


# =========================================================
# UPLOAD WASH (BYTES) — FIXED
# =========================================================
def _read_upload_bytes(up) -> bytes:
    # streamlit UploadedFile supports getvalue()
    try:
        return up.getvalue()
    except Exception:
        try:
            return bytes(up.read())
        except Exception:
            return b""


def _wash_bytes(raw: bytes) -> bytes:
    """
    Uses your image_wash.py:
      wash_image_bytes(b: bytes) -> bytes (JPEG)
    Compatible fallback if function name changes.
    """
    if not raw:
        raise ValueError("empty upload bytes")

    # Primary: your implementation
    if hasattr(iw, "wash_image_bytes"):
        return iw.wash_image_bytes(raw)

    # Fallback: try other names (defensive)
    if hasattr(iw, "wash_bytes"):
        return iw.wash_bytes(raw)

    raise RuntimeError("image_wash.py: wash_image_bytes() not found")


def _wash_upload_to_bytes(up) -> bytes:
    raw = _read_upload_bytes(up)
    h = hashlib.sha256(raw).hexdigest()

    wash_cache = _get_lru("wash_cache", MAX_WASH_CACHE)
    if h in wash_cache:
        wash_cache.move_to_end(h)
        return wash_cache[h]

    washed = _wash_bytes(raw)  # bytes
    _lru_put(wash_cache, h, washed, MAX_WASH_CACHE)
    return washed


# =========================================================
# SKETCH (always scales to target)
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
# =========================================================
def _sketch_compute(img_bytes: bytes, target_w: int, target_h: int) -> bytes:
    arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
<<<<<<< HEAD
        raise RuntimeError("OpenCV decode failed (arr=None)")
=======
        raise RuntimeError("OpenCV decode failed")
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102

    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    inverted = 255 - gray
    blurred = cv2.GaussianBlur(inverted, (21, 21), 0)
    denom = np.clip(255 - blurred, 1, 255)
    sketch = cv2.divide(gray, denom, scale=256.0)
    norm = cv2.normalize(sketch, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    pil = Image.fromarray(norm).convert("L")
    sw, sh = pil.size
    s = min(sw, sh)
    pil = pil.crop(((sw - s) // 2, (sh - s) // 2, (sw + s) // 2, (sh + s) // 2))
    pil = pil.resize((target_w, target_h), Image.LANCZOS)
    pil_1bit = pil.point(lambda p: 255 if p > 200 else 0).convert("1")

    out = io.BytesIO()
    pil_1bit.save(out, format="PNG", optimize=True)
    outv = out.getvalue()

    del arr, gray, inverted, blurred, denom, sketch, norm, pil, pil_1bit
    gc.collect()
    return outv


def _get_sketch_cached(img_bytes: bytes, target_w: int, target_h: int) -> bytes:
<<<<<<< HEAD
    cache: "OrderedDict[Tuple[str,int,int], bytes]" = st.session_state.setdefault("sketch_cache", OrderedDict())
=======
    cache = _get_lru("sketch_cache", MAX_SKETCH_CACHE)
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    h = hashlib.sha256(img_bytes).hexdigest()
    key = (h, int(target_w), int(target_h))
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    out = _sketch_compute(img_bytes, target_w, target_h)
    _lru_put(cache, key, out, MAX_SKETCH_CACHE)
    return out

<<<<<<< HEAD
=======

>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
# =========================================================
# OVERLAY (classic + pre-reader)
# =========================================================
def _draw_quest_overlay(
    c: canvas.Canvas,
    pb: PageBox,
    safe_left: float,
    safe_right: float,
    safe_tb: float,
    hour: int,
    mission,
<<<<<<< HEAD
=======
    debug: bool,
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    pre_reader: bool,
):
    header_h = 0.75 * inch
    x0 = safe_left
    x1 = pb.full_w - safe_right
    y0 = safe_tb
    y1 = pb.full_h - safe_tb
    w = max(1.0, x1 - x0)
    y_header_bottom = y1 - header_h

    zone = qd.get_zone_for_hour(hour)
    zone_rgb = qd.get_hour_color(hour)
    fill = colors.Color(zone_rgb[0], zone_rgb[1], zone_rgb[2])

    luminance = (0.2126 * zone_rgb[0] + 0.7152 * zone_rgb[1] + 0.0722 * zone_rgb[2])
    tc = colors.white if luminance < 0.45 else INK_BLACK

    c.saveState()

<<<<<<< HEAD
    # header
=======
    # Header
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    c.setFillColor(fill)
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(1)
    c.rect(x0, y_header_bottom, w, header_h, fill=1, stroke=1)

    c.setFillColor(tc)
    _set_font(c, True, 14)
    c.drawString(x0 + 0.18 * inch, y_header_bottom + header_h - 0.50 * inch, f"{qd.fmt_hour(hour)}  {zone.icon}  {zone.name}")
    _set_font(c, False, 10)
    c.drawString(x0 + 0.18 * inch, y_header_bottom + 0.18 * inch, f"{zone.quest_type} • {zone.atmosphere}")

<<<<<<< HEAD
    # card
=======
    # Card
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    cy = y0
    max_ch = (y_header_bottom - cy) - (0.15 * inch)
    pad_x = 0.18 * inch

    if pre_reader:
<<<<<<< HEAD
        card_h = min(max_ch, 2.55 * inch)
=======
        card_h = min(max_ch, 2.45 * inch)
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    else:
        sc = _autoscale_mission_text(mission, w, x0, pad_x, max_ch)
        card_h = min(max_ch, max(1.85 * inch, sc["needed"]))

    c.setFillColor(colors.white)
    c.setStrokeColor(INK_BLACK)
    c.rect(x0, cy, w, card_h, fill=1, stroke=1)

<<<<<<< HEAD
    y_top = cy + card_h - 0.20 * inch

    if pre_reader:
        c.setFillColor(INK_BLACK)
        _set_font(c, True, 14)
        title = _kid_short(getattr(mission, "title", "MISSION"), 3) or "MISSION"
        c.drawString(x0 + pad_x, y_top - 10, title)
        _set_font(c, True, 11)
        c.drawRightString(x0 + w - pad_x, y_top - 10, f"+{getattr(mission, 'xp', 0)} XP")
=======
    y_top = cy + card_h - 0.18 * inch
    c.setFillColor(INK_BLACK)

    if pre_reader:
        # PRE-READER (icons)
        _set_font(c, True, 14)
        title = _kid_short(getattr(mission, "title", "MISSION"), 3)
        c.drawString(x0 + pad_x, y_top - 10, title)
        _set_font(c, True, 11)
        c.drawRightString(x0 + w - pad_x, y_top - 10, f"+{int(getattr(mission, 'xp', 0))} XP")
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102

        row_h = 0.46 * inch
        icon = 0.34 * inch
        start_y = y_top - 0.50 * inch

<<<<<<< HEAD
        move = _kid_short(getattr(mission, "movement", ""), 3) or "Bewegen!"
        think = _kid_short(getattr(mission, "thinking", ""), 3) or "Denken!"
        proof = _kid_short(getattr(mission, "proof", ""), 2) or "Haken!"

        _icon_run(c, x0 + pad_x, start_y - icon*0.2, icon)
        _set_font(c, False, 12)
        c.drawString(x0 + pad_x + icon + 0.2*inch, start_y, move)

        _icon_brain(c, x0 + pad_x, start_y - row_h - icon*0.2, icon)
        c.drawString(x0 + pad_x + icon + 0.2*inch, start_y - row_h, think)

        _icon_check(c, x0 + pad_x, start_y - 2*row_h - icon*0.2, icon)
        c.drawString(x0 + pad_x + icon + 0.2*inch, start_y - 2*row_h, proof)

        _set_font(c, False, 8)
        c.setFillColor(INK_GRAY_70)
        c.drawString(x0 + pad_x, cy + 0.12*inch, "Eltern: Kurz vorlesen – Kind macht’s nach.")
    else:
        c.setFillColor(INK_BLACK)
        _set_font(c, True, sc["ts"])
        c.drawString(x0 + pad_x, y_top - sc["tl"] + 2, f"MISSION: {getattr(mission,'title','')}")
        _set_font(c, True, max(8, sc["ts"] - 2))
        c.drawRightString(x0 + w - pad_x, y_top - sc["tl"] + 2, f"+{getattr(mission,'xp',0)} XP")

        y_text = y_top - sc["tl"] - 0.05 * inch
=======
        move = _kid_short(getattr(mission, "movement", ""), 3)
        think = _kid_short(getattr(mission, "thinking", ""), 3)
        proof = _kid_short(getattr(mission, "proof", ""), 2)

        _icon_run(c, x0 + pad_x, start_y - icon * 0.2, icon)
        _set_font(c, False, 12)
        c.drawString(x0 + pad_x + icon + 0.20 * inch, start_y, move or "Bewegen!")

        _icon_brain(c, x0 + pad_x, start_y - row_h - icon * 0.2, icon)
        _set_font(c, False, 12)
        c.drawString(x0 + pad_x + icon + 0.20 * inch, start_y - row_h, think or "Denken!")

        _icon_check(c, x0 + pad_x, start_y - 2 * row_h - icon * 0.2, icon)
        _set_font(c, False, 12)
        c.drawString(x0 + pad_x + icon + 0.20 * inch, start_y - 2 * row_h, proof or "Haken!")

        _set_font(c, False, 8)
        c.setFillColor(INK_GRAY_70)
        c.drawString(x0 + pad_x, cy + 0.12 * inch, "Eltern: kurz vorlesen – Kind macht’s nach.")

    else:
        # CLASSIC TEXT
        _set_font(c, True, sc["ts"])
        c.drawString(x0 + pad_x, y_top - sc["tl"] + 2, f"MISSION: {getattr(mission, 'title', '')}")
        _set_font(c, True, max(8, sc["ts"] - 2))
        c.drawRightString(x0 + w - pad_x, y_top - sc["tl"] + 2, f"+{int(getattr(mission, 'xp', 0))} XP")

        y_text = y_top - sc["tl"] - 0.10 * inch
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102

        _set_font(c, True, sc["ls"])
        c.drawString(x0 + pad_x, y_text - sc["ll"] + 2, "BEWEGUNG:")
        _set_font(c, False, sc["bs"])
        yy = y_text - sc["ll"] + 2
        for l in sc["ml"]:
            c.drawString(x0 + 1.05 * inch, yy, l)
            yy -= sc["bl"]

        y_text = yy - 0.06 * inch
        _set_font(c, True, sc["ls"])
        c.drawString(x0 + pad_x, y_text - sc["ll"] + 2, "DENKEN:")
        _set_font(c, False, sc["bs"])
        yy = y_text - sc["ll"] + 2
        for l in sc["tl_lines"]:
            c.drawString(x0 + 0.90 * inch, yy, l)
            yy -= sc["bl"]

        bx, box = x0 + pad_x, 0.20 * inch
        c.rect(bx, cy + 0.18 * inch, box, box, fill=0, stroke=1)
        _set_font(c, True, sc["ls"])
        c.drawString(bx + box + 0.15 * inch, cy + 0.20 * inch, "PROOF:")
        _set_font(c, False, sc["bs"])
<<<<<<< HEAD
        pr = _fit_lines(_wrap_text_hard(getattr(mission, "proof", ""), FONTS["normal"], sc["bs"], w - 1.5 * inch), 1)[0]
        c.drawString(bx + box + 0.75 * inch, cy + 0.20 * inch, pr)

    c.restoreState()

# =========================================================
# COVER COLLAGE (sanitized bytes)
=======
        pr_raw = getattr(mission, "proof", "")
        if pr_raw:
            pr = _fit_lines(_wrap_text_hard(pr_raw, FONTS["normal"], sc["bs"], w - 1.5 * inch), 1)[0]
            c.drawString(bx + box + 0.75 * inch, cy + 0.20 * inch, pr)

    if debug:
        _draw_kdp_debug_guides(c, pb, safe_left, safe_right, safe_tb)

    c.restoreState()


# =========================================================
# COVER COLLAGE (simple, stable)
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
# =========================================================
def _cover_collage_png(uploads, size_px: int, seed: int) -> Optional[bytes]:
    files = list(uploads or [])
    if not files:
        return None

    rng = np.random.default_rng(seed & 0xFFFFFFFF)
    idx = np.arange(len(files))
    rng.shuffle(idx)
    pick = [files[i] for i in idx[: min(4, len(files))]]

    grid = 2
    gap = max(10, size_px // 120)
    cell = (size_px - gap * (grid + 1)) // grid
    canvas_img = Image.new("RGB", (size_px, size_px), (255, 255, 255))

    k = 0
    for r in range(grid):
        for c_ in range(grid):
            if k >= len(pick):
                break
<<<<<<< HEAD
            up = pick[k]; k += 1
            try:
                washed = _wash_upload_to_bytes(up)
=======
            up = pick[k]
            k += 1
            try:
                washed = _wash_upload_to_bytes(up)  # bytes (jpeg)
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
                sk = _sketch_compute(washed, cell, cell)
                tile = Image.open(io.BytesIO(sk)).convert("RGB")
            except Exception:
                tile = Image.new("RGB", (cell, cell), (255, 255, 255))

            x = gap + c_ * (cell + gap)
            y = gap + r * (cell + gap)
            canvas_img.paste(tile, (x, y))
            del tile
            gc.collect()

    d = ImageDraw.Draw(canvas_img)
    d.rectangle([0, 0, size_px - 1, size_px - 1], outline=(0, 0, 0), width=max(2, size_px // 250))
    out = io.BytesIO()
    canvas_img.save(out, format="PNG", optimize=True)
    return out.getvalue()

<<<<<<< HEAD
=======

>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
# =========================================================
# BUILDERS
# =========================================================
def build_interior(
    name: str,
    uploads,
<<<<<<< HEAD
    pages: int,
=======
    total_pages: int,
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    kdp: bool,
    intro: bool,
    outro: bool,
    start_hour: int,
    diff: int,
<<<<<<< HEAD
=======
    debug_guides: bool,
    eddie_guide: bool,
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    eddie_style: str,
    pre_reader: bool,
) -> bytes:
    pb = page_box(TRIM, TRIM, kdp_bleed=kdp)

    files = list(uploads or [])
    if not files:
        raise RuntimeError("Keine Bilder hochgeladen.")

<<<<<<< HEAD
    photo_count = max(1, pages - (int(intro) + int(outro)))
=======
    if total_pages < KDP_MIN_PAGES:
        total_pages = KDP_MIN_PAGES
    if total_pages % 2 != 0:
        total_pages += 1

    photo_count = max(1, total_pages - (int(intro) + int(outro)))
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    final = (files * (photo_count // len(files) + 1))[:photo_count]

    target_w = int(round(pb.full_w * DPI / 72.0))
    target_h = int(round(pb.full_h * DPI / 72.0))

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pb.full_w, pb.full_h))

    seed_base = _stable_seed(name)
<<<<<<< HEAD
    target_w = int(pb.full_w * DPI / inch)
    target_h = int(pb.full_h * DPI / inch)

    page_idx = 0

    # Intro
    if intro:
        sl, sr, stb = safe_margins_for_page(pages, kdp, page_idx, pb)
        c.setFillColor(colors.white); c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)
        c.setFillColor(INK_BLACK)
        _set_font(c, True, 34); c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 2.0 * inch, "Willkommen bei Eddies")
        _set_font(c, False, 22); c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 2.6 * inch, f"& {name}")
        _draw_eddie(c, pb.full_w / 2, pb.full_h / 2, 1.3 * inch, style=eddie_style)
        c.showPage()
        page_idx += 1

    # Content
    for i, up in enumerate(final):
        washed_bytes = _wash_upload_to_bytes(up)
        png_bytes = _get_sketch_cached(washed_bytes, target_w, target_h)

        c.drawImage(ImageReader(io.BytesIO(png_bytes)), 0, 0, pb.full_w, pb.full_h)

        sl, sr, stb = safe_margins_for_page(pages, kdp, page_idx, pb)
        h_val = (start_hour + i) % 24
        seed = int(seed_base ^ (i << 1) ^ h_val) & 0xFFFFFFFF
        mission = qd.pick_mission_for_time(h_val, diff, seed)

        _draw_quest_overlay(c, pb, sl, sr, stb, h_val, mission, pre_reader=pre_reader)

        # guide mark bottom-right (small)
        r = 0.18 * inch
        _draw_eddie(c, (pb.full_w - sr) - r, stb + r, r, style=eddie_style)

=======

    current_page_idx = 0

    # Intro
    if intro:
        sl, sr, stb = safe_margins_for_page(total_pages, kdp, current_page_idx, pb)
        c.setFillColor(colors.white)
        c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)

        c.setFillColor(INK_BLACK)
        _set_font(c, True, 34)
        c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 2.0 * inch, "Willkommen bei Eddies")
        _set_font(c, False, 22)
        c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 2.6 * inch, f"& {name}")

        _draw_eddie(c, pb.full_w / 2, pb.full_h / 2, 1.25 * inch, style=eddie_style)

        c.setFillColor(INK_GRAY_70)
        _set_font(c, False, 13)
        c.drawCentredString(pb.full_w / 2, stb + 0.75 * inch, "24 Stunden • 24 Mini-Quests • Haken setzen")

        if debug_guides:
            _draw_kdp_debug_guides(c, pb, sl, sr, stb)

>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
        c.showPage()
        page_idx += 1

<<<<<<< HEAD
=======
    # Content pages
    for i, up in enumerate(final):
        # margins depend on actual pdf page index
        sl, sr, stb = safe_margins_for_page(total_pages, kdp, current_page_idx, pb)

        washed_bytes = _wash_upload_to_bytes(up)  # FIXED BYTES
        png_bytes = _get_sketch_cached(washed_bytes, target_w, target_h)

        c.drawImage(ImageReader(io.BytesIO(png_bytes)), 0, 0, pb.full_w, pb.full_h)

        hour = (start_hour + i) % 24
        seed = int(seed_base ^ (i << 1) ^ hour) & 0xFFFFFFFF
        mission = qd.pick_mission_for_time(hour, diff, seed)

        _draw_quest_overlay(
            c=c,
            pb=pb,
            safe_left=sl,
            safe_right=sr,
            safe_tb=stb,
            hour=hour,
            mission=mission,
            debug=debug_guides,
            pre_reader=pre_reader,
        )

        if eddie_guide:
            r = 0.18 * inch
            _draw_eddie(c, (pb.full_w - sr) - r, stb + r, r, style=eddie_style)

        c.showPage()
        current_page_idx += 1

>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
        del washed_bytes, png_bytes
        gc.collect()

    # Outro
    if outro:
<<<<<<< HEAD
        sl, sr, stb = safe_margins_for_page(pages, kdp, page_idx, pb)
        c.setFillColor(colors.white); c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)
        _draw_eddie(c, pb.full_w / 2, pb.full_h / 2 + 0.6 * inch, 1.5 * inch, style=eddie_style)
        c.setFillColor(INK_BLACK); _set_font(c, True, 30)
        c.drawCentredString(pb.full_w / 2, pb.full_h / 2 - 1.5 * inch, "Quest abgeschlossen!")
=======
        sl, sr, stb = safe_margins_for_page(total_pages, kdp, current_page_idx, pb)
        c.setFillColor(colors.white)
        c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)

        _draw_eddie(c, pb.full_w / 2, pb.full_h / 2 + 0.6 * inch, 1.5 * inch, style=eddie_style)

        c.setFillColor(INK_BLACK)
        _set_font(c, True, 30)
        c.drawCentredString(pb.full_w / 2, pb.full_h / 2 - 1.5 * inch, "Quest abgeschlossen!")

        if debug_guides:
            _draw_kdp_debug_guides(c, pb, sl, sr, stb)

>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()

<<<<<<< HEAD
def build_cover(name: str, pages: int, paper: str, uploads, eddie_style: str) -> bytes:
=======

def build_cover(name: str, pages: int, paper: str, uploads=None, eddie_style: str = "tongue") -> bytes:
    # spine width in inches factor
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    sw = float(pages) * PAPER_FACTORS.get(paper, 0.002252) * inch
    sw = max(sw, 0.001 * inch)
    sw = round(sw / (0.001 * inch)) * (0.001 * inch)

    cw, ch = (2 * TRIM) + sw + (2 * BLEED), TRIM + (2 * BLEED)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(cw, ch))

<<<<<<< HEAD
    # base
=======
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    c.setFillColor(colors.white)
    c.rect(0, 0, cw, ch, fill=1, stroke=0)

    # spine
    c.setFillColor(INK_BLACK)
    c.rect(BLEED + TRIM, BLEED, sw, TRIM, fill=1, stroke=0)

    # spine text
    if pages >= SPINE_TEXT_MIN_PAGES:
        c.saveState()
<<<<<<< HEAD
        c.setFillColor(colors.white); _set_font(c, True, 10)
=======
        c.setFillColor(colors.white)
        _set_font(c, True, 10)
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
        c.translate(BLEED + TRIM + sw / 2, BLEED + TRIM / 2)
        c.rotate(90)
        c.drawCentredString(0, -4, f"EDDIES & {name}".upper())
        c.restoreState()

    # back
    bx = BLEED
    c.setFillColor(colors.white)
    c.rect(bx, BLEED, TRIM, TRIM, fill=1, stroke=0)
<<<<<<< HEAD
    _draw_eddie(c, bx + TRIM*0.12, BLEED + TRIM*0.86, TRIM*0.045, style=eddie_style)
    c.setFillColor(INK_GRAY_70); _set_font(c, False, 11)
    c.drawString(bx + TRIM*0.12, BLEED + TRIM*0.10, "24 Missionen • 24 Stunden • Print-first")

=======

    _draw_eddie(c, bx + TRIM * 0.12, BLEED + TRIM * 0.86, TRIM * 0.06, style=eddie_style)
    c.setFillColor(INK_GRAY_70)
    _set_font(c, False, 12)
    c.drawString(bx + TRIM * 0.12, BLEED + TRIM * 0.12, "24 Missionen • 24 Stunden • KDP-ready optional")

>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    # front
    fx = BLEED + TRIM + sw
    c.setFillColor(colors.white)
    c.rect(fx, BLEED, TRIM, TRIM, fill=1, stroke=0)

<<<<<<< HEAD
    # collage (sketch tiles)
=======
    # collage behind title block
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
    collage_px = int((TRIM * DPI / inch) * 0.72)
    collage = _cover_collage_png(uploads, collage_px, _stable_seed(name + "|cover"))
    if collage:
        collage_w = TRIM * 0.72
        collage_h = collage_w
        cx = fx + (TRIM - collage_w) / 2
        cy = BLEED + TRIM * 0.16
        c.drawImage(ImageReader(io.BytesIO(collage)), cx, cy, collage_w, collage_h, mask="auto")

<<<<<<< HEAD
        # title plate
=======
        # plate
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
        c.setFillColor(colors.white)
        c.setStrokeColor(INK_BLACK)
        c.setLineWidth(1)
        c.roundRect(fx + TRIM * 0.10, BLEED + TRIM * 0.74, TRIM * 0.80, TRIM * 0.20, TRIM * 0.04, fill=1, stroke=1)

    # title
    c.setFillColor(INK_BLACK)
    _set_font(c, True, 44)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.86, "EDDIES")
    _set_font(c, False, 18)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.79, f"& {name}")

    # brand mark (NO SMILEY)
<<<<<<< HEAD
    _draw_logo(c, fx + TRIM / 2, BLEED + TRIM * 0.58, TRIM * 0.28)
=======
    _draw_eddie(c, fx + TRIM / 2, BLEED + TRIM * 0.62, TRIM * 0.14, style=eddie_style)
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102

    c.save()
    buf.seek(0)
    return buf.getvalue()

<<<<<<< HEAD
=======

>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
# =========================================================
# UI
# =========================================================
st.set_page_config(page_title=APP_TITLE, layout="centered", page_icon=APP_ICON)

<<<<<<< HEAD
# session init (no warnings)
st.session_state.setdefault("sketch_cache", OrderedDict())
st.session_state.setdefault("assets", None)
st.session_state.setdefault("pages", KDP_MIN_PAGES)
st.session_state.setdefault("paper", list(PAPER_FACTORS.keys())[0])

st.markdown(f"<h1 style='text-align:center;'>{APP_TITLE}</h1>", unsafe_allow_html=True)
st.caption(f"Build: {BUILD_TAG}")

if qd is None:
    st.error("quest_data.py fehlt oder crasht. Ohne das gibt’s keine Missionen.")
    st.code(_QD_IMPORT_ERROR or "Unknown import error", language="text")
    st.stop()

with st.container(border=True):
    col1, col2 = st.columns(2)

    with col1:
        name = st.text_input("Name", value="Eddie")
        age = st.number_input("Alter", min_value=3, max_value=99, value=5)

    with col2:
        pages = st.number_input("Seiten", min_value=KDP_MIN_PAGES, max_value=300, step=2, key="pages")
        if int(pages) % 2 != 0:
            pages = int(pages) + 1
        paper = st.selectbox("Papier", list(PAPER_FACTORS.keys()), key="paper")

    st.divider()

    col3, col4 = st.columns(2)
    with col3:
        eddie_style = st.selectbox("Eddie-Icon", ["tongue", "dog"], index=0, help="Keine Smiley-Fresse. Entweder nur Zunge (Brand) oder Dog-Outline.")
    with col4:
        pre_reader_mode = st.toggle("👶 Pre-Reader Mode", value=(age <= 6), help="Icons + ultrakurze Wörter statt Textwand.")

    kdp = st.toggle("KDP Mode (Bleed + Margins)", True)
    uploads = st.file_uploader("Fotos (werden gewaschen & skizziert)", accept_multiple_files=True, type=["jpg", "jpeg", "png", "webp"])

can_build = bool(uploads and name)

if st.button("🚀 GENERIEREN", disabled=not can_build):
    with st.spinner("Waschen → Skizzieren → PDF bauen …"):
=======
st.markdown(f"<h1 style='text-align:center;'>{APP_TITLE}</h1>", unsafe_allow_html=True)
st.caption(f"Build: {BUILD_TAG}")

if qd is None:
    st.error("quest_data.py konnte nicht geladen werden. Fix das zuerst, sonst gibt’s keine Missionen.")
    st.code(_QD_IMPORT_ERROR or "Unbekannter Import-Fehler", language="text")
    st.stop()

# session state init
st.session_state.setdefault("assets", None)
st.session_state.setdefault("upload_sig", "")
_get_lru("sketch_cache", MAX_SKETCH_CACHE)
_get_lru("wash_cache", MAX_WASH_CACHE)


def _uploads_signature(uploads_list) -> str:
    h = hashlib.sha256()
    for up in uploads_list or []:
        try:
            buf = up.getbuffer()
            ln = len(buf)
            h.update((up.name or "").encode("utf-8", errors="ignore"))
            h.update(ln.to_bytes(8, "little", signed=False))
            if ln > 4096:
                sample = bytes(buf[:2048]) + bytes(buf[-2048:])
            else:
                sample = bytes(buf)
            h.update(hashlib.sha256(sample).digest())
        except Exception:
            b = _read_upload_bytes(up)
            h.update((getattr(up, "name", "") or "").encode("utf-8", errors="ignore"))
            h.update(len(b).to_bytes(8, "little", signed=False))
            h.update(hashlib.sha256(b[:2048]).digest())
    return h.hexdigest()


with st.container(border=True):
    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input("Name", value="Eddie")
        age = st.number_input("Alter", min_value=3, max_value=99, value=5, step=1)
    with c2:
        pages = st.number_input("Seiten", min_value=KDP_MIN_PAGES, max_value=300, value=KDP_MIN_PAGES, step=2)
        paper = st.selectbox("Papier", list(PAPER_FACTORS.keys()), index=0)

    st.divider()

    c3, c4 = st.columns(2)
    with c3:
        eddie_style = st.selectbox("Eddie-Icon", ["tongue", "dog"], index=0, help="'tongue' ist nur die lila Zunge.")
    with c4:
        pre_reader_mode = st.toggle("👶 Pre-Reader Mode", value=(age <= 6), help="Icons statt Textwüste.")

    kdp = st.toggle("KDP Mode (Bleed + Margins)", True)
    debug_guides = st.toggle("🧪 Preflight Debug (Bleed/Safe)", False)
    eddie_guide = st.toggle("Eddie-Guide auf jeder Seite", True)

    uploads = st.file_uploader(
        "Fotos (werden gewaschen & skizziert)",
        accept_multiple_files=True,
        type=["jpg", "jpeg", "png", "webp"],
    )

n_uploads = len(uploads) if uploads else 0
st.markdown(f"**📸 Hochgeladen:** `{n_uploads}` Bild(er)")

can_build = bool(uploads and name)

if can_build:
    intro, outro = True, True
    content_pages = max(1, int(pages) - int(intro) - int(outro))
    reuse_factor = (content_pages / n_uploads) if n_uploads else 0

    cA, cB, cC = st.columns(3)
    cA.metric("📸 Uploads", n_uploads)
    cB.metric("📄 Content-Seiten", content_pages)
    cC.metric("🔁 Reuse-Faktor", f"{reuse_factor:.1f}×" if n_uploads else "—")

    st.info("✅ Druck-Target ist immer 300 DPI: Bilder werden automatisch passend skaliert (auch Upscaling).")
else:
    st.info("⬆️ Lade Fotos hoch – danach ist der Build freigeschaltet.")

if st.button("🚀 GENERIEREN", disabled=not can_build):
    # reset caches if uploads changed
    upload_sig = _uploads_signature(uploads)
    if st.session_state.upload_sig != upload_sig:
        st.session_state.upload_sig = upload_sig
        st.session_state["sketch_cache"].clear()
        st.session_state["wash_cache"].clear()

    with st.spinner("Waschen… Skizzieren… Layout… PDF Build…"):
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
        diff = 1 if age <= 4 else 2 if age <= 6 else 3 if age <= 9 else 4

        pdf_int = build_interior(
            name=name,
            uploads=uploads,
            pages=int(pages),
            kdp=bool(kdp),
            intro=True,
            outro=True,
            start_hour=6,
            diff=diff,
<<<<<<< HEAD
            eddie_style=eddie_style,
=======
            debug_guides=bool(debug_guides),
            eddie_guide=bool(eddie_guide),
            eddie_style=str(eddie_style),
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102
            pre_reader=bool(pre_reader_mode),
        )
        pdf_cov = build_cover(name=name, pages=int(pages), paper=str(paper), uploads=uploads, eddie_style=eddie_style)

<<<<<<< HEAD
        st.session_state.assets = {"int": pdf_int, "cov": pdf_cov, "name": name}
        st.success("✅ Fertig! PDFs sind bereit.")

if st.session_state.assets:
    a = st.session_state.assets
    c1, c2 = st.columns(2)
    c1.download_button("📘 Interior PDF", a["int"], file_name=f"Int_{a['name']}.pdf")
    c2.download_button("🎨 Cover PDF", a["cov"], file_name=f"Cov_{a['name']}.pdf")
=======
        cov_pdf = build_cover(
            name=name,
            pages=int(pages),
            paper=str(paper),
            uploads=uploads,
            eddie_style=str(eddie_style),
        )

        st.session_state.assets = {"int": int_pdf, "cov": cov_pdf, "name": name}
        st.success("KDP-Assets bereit!")

if st.session_state.assets:
    a = st.session_state.assets
    col1, col2 = st.columns(2)
    with col1:
        st.download_button("📘 Interior PDF", a["int"], file_name=f"Int_{a['name']}.pdf")
    with col2:
        st.download_button("🎨 Cover PDF", a["cov"], file_name=f"Cov_{a['name']}.pdf")
>>>>>>> e0814e8dce4b0bab8a19de2545f2153c17875102

st.markdown("<div style='text-align:center; color:grey;'>Eddies World © 2026</div>", unsafe_allow_html=True)
