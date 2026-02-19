# =========================================================
# app.py — Eddies Questbook Edition — BRAND & PRE-READER (v4.7.3 SAFE)
#
# Fixes:
# - image_wash interface: uses iw.wash_image_bytes(bytes) (matches your image_wash.py)
# - reportlab safe: no setFillAlpha dependency
# - cover collage ImageReader uses bytes (not PIL object)
# - stable caching per-session (no global leaks)
#
# Features:
# - Branding: "tongue" (purple tongue mark) or "dog" (simple dog head)
# - Pre-Reader Mode: icons + ultra-short text
# - KDP safe margins + bleed
# =========================================================

from __future__ import annotations

import io
import os
import gc
import hashlib
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
from collections import OrderedDict

import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageFile, ImageOps, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth

import image_wash as iw  # your file with wash_image_bytes

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
MAX_SKETCH_CACHE = 256
BUILD_TAG = "v4.7.3-safe"

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
    if pages <= 150: return 0.375
    if pages <= 300: return 0.500
    if pages <= 500: return 0.625
    if pages <= 700: return 0.750
    return 0.875

def safe_margins_for_page(pages: int, kdp: bool, page_index_0: int, pb: PageBox) -> tuple[float, float, float]:
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

# =========================================================
# FONTS & TEXT TOOLS
# =========================================================
def _try_register_fonts() -> Dict[str, str]:
    normal_p = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_p = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if os.path.exists(normal_p):
        try: pdfmetrics.registerFont(TTFont("EDDIES_FONT", normal_p))
        except Exception: pass
    if os.path.exists(bold_p):
        try: pdfmetrics.registerFont(TTFont("EDDIES_FONT_BOLD", bold_p))
        except Exception: pass
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

def _kid_short(s: str, max_words: int = 4) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    s = s.replace("•", " ").replace("→", " ").replace("-", " ")
    words = [w for w in s.split() if w and len(w) > 1]
    return " ".join(words[:max_words])

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
    while sc["needed"] > max_card_h and ts > 9:
        ts -= 1
        bs = max(8, bs - 1)
        ls = max(8, ls - 1)
        sc = compute(ts, bs, ls)
    return sc

def _stable_seed(s: str) -> int:
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:8], "big")

# =========================================================
# BRAND MARKS
# =========================================================
def _draw_eddie(c: canvas.Canvas, cx: float, cy: float, r: float, style: str = "tongue"):
    c.saveState()

    if style == "tongue":
        t_w = r * 0.55
        t_h = r * 0.70
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

    # dog head (simple) + tongue
    c.setStrokeColor(INK_BLACK)
    c.setFillColor(colors.white)
    c.setLineWidth(max(1.2, r * 0.06))
    c.circle(cx, cy, r, stroke=1, fill=1)

    # ears lines
    c.line(cx - r*0.55, cy + r*0.55, cx - r*0.15, cy + r*0.95)
    c.line(cx - r*0.15, cy + r*0.95, cx - r*0.05, cy + r*0.45)

    c.line(cx + r*0.55, cy + r*0.55, cx + r*0.15, cy + r*0.95)
    c.line(cx + r*0.15, cy + r*0.95, cx + r*0.05, cy + r*0.45)

    c.setFillColor(colors.HexColor(EDDIE_PURPLE))
    c.roundRect(cx - r*0.12, cy - r*0.45, r*0.24, r*0.28, r*0.10, stroke=0, fill=1)

    c.restoreState()

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
    c.circle(x+size*0.35, y+size*0.50, size*0.05, stroke=1, fill=1)
    c.circle(x+size*0.65, y+size*0.50, size*0.05, stroke=1, fill=1)
    c.restoreState()

def _icon_check(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    c.setStrokeColor(INK_BLACK); c.setLineWidth(max(1.2, size*0.08))
    c.rect(x+size*0.15, y+size*0.20, size*0.70, size*0.60, stroke=1, fill=0)
    c.line(x+size*0.30, y+size*0.45, x+size*0.45, y+size*0.30)
    c.line(x+size*0.45, y+size*0.30, x+size*0.70, y+size*0.65)
    c.restoreState()

# =========================================================
# SKETCH + CACHE
# =========================================================
def _sketch_compute(img_bytes: bytes, target_w: int, target_h: int) -> bytes:
    arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise RuntimeError("OpenCV konnte das Bild nicht decodieren.")
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
    pil = pil.point(lambda p: 255 if p > 200 else 0).convert("1")

    out = io.BytesIO()
    pil.save(out, format="PNG", optimize=True)
    return out.getvalue()

def _get_sketch_cached(img_bytes: bytes, target_w: int, target_h: int) -> bytes:
    cache: "OrderedDict[tuple[str, int, int], bytes]" = st.session_state.setdefault("sketch_cache", OrderedDict())
    h = hashlib.sha256(img_bytes).hexdigest()
    key = (h, int(target_w), int(target_h))
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    out = _sketch_compute(img_bytes, target_w, target_h)
    cache[key] = out
    cache.move_to_end(key)
    while len(cache) > MAX_SKETCH_CACHE:
        cache.popitem(last=False)
    return out

# =========================================================
# OVERLAY
# =========================================================
def _draw_quest_overlay(c: canvas.Canvas, pb: PageBox, safe_left: float, safe_right: float, safe_tb: float,
                       hour: int, mission, debug: bool, pre_reader: bool):
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
    c.setFillColor(fill)
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(1)
    c.rect(x0, y_header_bottom, w, header_h, fill=1, stroke=1)

    c.setFillColor(tc)
    _set_font(c, True, 14)
    c.drawString(x0 + 0.18 * inch, y_header_bottom + header_h - 0.50 * inch,
                 f"{qd.fmt_hour(hour)}  {zone.icon}  {zone.name}")
    _set_font(c, False, 10)
    c.drawString(x0 + 0.18 * inch, y_header_bottom + 0.18 * inch,
                 f"{zone.quest_type} • {zone.atmosphere}")

    # card
    cy = y0
    max_ch = (y_header_bottom - cy) - (0.15 * inch)
    pad_x = 0.18 * inch

    if pre_reader:
        card_h = min(max_ch, 2.50 * inch)
    else:
        sc = _autoscale_mission_text(mission, w, x0, pad_x, max_ch)
        card_h = min(max_ch, max(1.85 * inch, sc["needed"]))

    c.setFillColor(colors.white)
    c.setStrokeColor(INK_BLACK)
    c.rect(x0, cy, w, card_h, fill=1, stroke=1)

    y_top = cy + card_h - 0.20 * inch
    c.setFillColor(INK_BLACK)

    if pre_reader:
        _set_font(c, True, 14)
        title = _kid_short(getattr(mission, "title", "MISSION"), 3)
        c.drawString(x0 + pad_x, y_top - 10, title or "MISSION")
        _set_font(c, True, 11)
        c.drawRightString(x0 + w - pad_x, y_top - 10, f"+{getattr(mission, 'xp', 0)} XP")

        row_h = 0.46 * inch
        icon = 0.34 * inch
        start_y = y_top - 0.50 * inch

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
        c.drawString(x0 + pad_x, cy + 0.12*inch, "Eltern: kurz vorlesen – Kind macht’s nach.")
    else:
        sc = _autoscale_mission_text(mission, w, x0, pad_x, max_ch)
        _set_font(c, True, sc["ts"])
        c.drawString(x0 + pad_x, y_top - sc["tl"] + 2, f"MISSION: {getattr(mission,'title','')}")
        _set_font(c, True, max(8, sc["ts"] - 2))
        c.drawRightString(x0 + w - pad_x, y_top - sc["tl"] + 2, f"+{getattr(mission,'xp',0)} XP")

        y_text = y_top - sc["tl"] - 0.10 * inch
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
        pr = _fit_lines(_wrap_text_hard(getattr(mission, "proof", ""), FONTS["normal"], sc["bs"], w - 1.5 * inch), 1)[0]
        c.drawString(bx + box + 0.75 * inch, cy + 0.20 * inch, pr)

    if debug:
        c.saveState()
        c.setLineWidth(0.5)
        c.setDash(3, 3)
        c.setStrokeColor(colors.red)
        if pb.bleed > 0:
            c.rect(pb.bleed, pb.bleed, pb.full_w - 2*pb.bleed, pb.full_h - 2*pb.bleed, stroke=1, fill=0)
        c.restoreState()

    c.restoreState()

# =========================================================
# HELPERS
# =========================================================
def _pil_to_png_bytes(img: Image.Image) -> bytes:
    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()

def _wash_upload_to_bytes(up) -> bytes:
    # up is UploadedFile
    raw = up.getvalue()
    washed = iw.wash_image_bytes(raw)  # returns clean JPEG bytes
    return washed

def _make_collage_from_uploads(uploads, size_px: int = 1800) -> Optional[bytes]:
    files = list(uploads or [])
    if not files:
        return None

    # pick up to 4
    pick = files[:4]
    grid = 2
    gap = max(12, size_px // 140)
    cell = (size_px - gap * (grid + 1)) // grid

    canvas_img = Image.new("RGB", (size_px, size_px), (255, 255, 255))

    k = 0
    for r in range(grid):
        for c_ in range(grid):
            if k >= len(pick):
                break
            up = pick[k]; k += 1
            try:
                washed = _wash_upload_to_bytes(up)
                im = Image.open(io.BytesIO(washed)).convert("RGB")
                w, h = im.size
                s = min(w, h)
                im = im.crop(((w - s)//2, (h - s)//2, (w + s)//2, (h + s)//2))
                im = im.resize((cell, cell), Image.LANCZOS)
            except Exception:
                im = Image.new("RGB", (cell, cell), (245, 245, 245))

            x = gap + c_ * (cell + gap)
            y = gap + r * (cell + gap)
            canvas_img.paste(im, (x, y))

    # subtle border
    d = ImageDraw.Draw(canvas_img)
    d.rectangle([0, 0, size_px-1, size_px-1], outline=(20, 20, 20), width=max(3, size_px // 300))
    return _pil_to_png_bytes(canvas_img)

# =========================================================
# BUILDERS
# =========================================================
def build_interior(name: str, uploads, pages: int, kdp: bool, intro: bool, outro: bool,
                   start_hour: int, diff: int, debug_guides: bool,
                   eddie_guide: bool, eddie_style: str, pre_reader: bool) -> bytes:
    pb = page_box(TRIM, TRIM, kdp_bleed=kdp)
    target_w = int(pb.full_w * DPI / inch)
    target_h = int(pb.full_h * DPI / inch)

    files = list(uploads or [])
    if not files:
        raise RuntimeError("Keine Bilder hochgeladen.")

    photo_count = max(1, int(pages) - int(intro) - int(outro))
    final = (files * (photo_count // len(files) + 1))[:photo_count]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pb.full_w, pb.full_h))
    seed_base = _stable_seed(name)

    current_page_idx = 0

    # Intro
    if intro:
        sl, sr, stb = safe_margins_for_page(pages, kdp, current_page_idx, pb)
        c.setFillColor(colors.white)
        c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)
        c.setFillColor(INK_BLACK)
        _set_font(c, True, 34)
        c.drawCentredString(pb.full_w/2, pb.full_h - stb - 2.0*inch, "Willkommen bei Eddies")
        _set_font(c, False, 22)
        c.drawCentredString(pb.full_w/2, pb.full_h - stb - 2.6*inch, f"& {name}")
        _draw_eddie(c, pb.full_w/2, pb.full_h/2, 1.3*inch, style=eddie_style)
        _set_font(c, False, 12)
        c.setFillColor(INK_GRAY_70)
        c.drawCentredString(pb.full_w/2, stb + 0.8*inch, "24 Stunden • 24 Mini-Quests • Haken setzen")
        if debug_guides:
            c.saveState()
            c.setDash(3,3); c.setStrokeColor(colors.green); c.setLineWidth(0.6)
            c.rect(sl, stb, pb.full_w - sl - sr, pb.full_h - 2*stb, stroke=1, fill=0)
            c.restoreState()
        c.showPage()
        current_page_idx += 1

    for i, up in enumerate(final):
        # sanitize -> sketch
        washed_bytes = _wash_upload_to_bytes(up)
        sketch_png = _get_sketch_cached(washed_bytes, target_w, target_h)

        c.drawImage(ImageReader(io.BytesIO(sketch_png)), 0, 0, pb.full_w, pb.full_h)

        sl, sr, stb = safe_margins_for_page(pages, kdp, current_page_idx, pb)

        h_val = (start_hour + i) % 24
        seed = int(seed_base ^ (i << 1) ^ h_val) & 0xFFFFFFFF
        mission = qd.pick_mission_for_time(h_val, diff, seed)

        _draw_quest_overlay(c, pb, sl, sr, stb, h_val, mission, debug=debug_guides, pre_reader=pre_reader)

        if eddie_guide:
            r = 0.18 * inch
            _draw_eddie(c, (pb.full_w - sr) - r, stb + r, r, style=eddie_style)

        c.showPage()
        current_page_idx += 1

        del washed_bytes, sketch_png
        gc.collect()

    # Outro
    if outro:
        c.setFillColor(colors.white)
        c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)
        _draw_eddie(c, pb.full_w/2, pb.full_h/2 + 0.6*inch, 1.5*inch, style=eddie_style)
        c.setFillColor(INK_BLACK)
        _set_font(c, True, 30)
        c.drawCentredString(pb.full_w/2, pb.full_h/2 - 1.5*inch, "Quest abgeschlossen!")
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()

def build_cover(name: str, pages: int, paper: str, uploads, eddie_style: str) -> bytes:
    sw = float(pages) * PAPER_FACTORS.get(paper, 0.002252) * inch
    sw = max(sw, 0.001 * inch)
    sw = round(sw / (0.001 * inch)) * (0.001 * inch)

    cw, ch = (2 * TRIM) + sw + (2 * BLEED), TRIM + (2 * BLEED)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(cw, ch))

    # base
    c.setFillColor(colors.white)
    c.rect(0, 0, cw, ch, fill=1, stroke=0)

    # spine
    c.setFillColor(INK_BLACK)
    c.rect(BLEED + TRIM, BLEED, sw, TRIM, fill=1, stroke=0)

    if pages >= SPINE_TEXT_MIN_PAGES:
        c.saveState()
        c.setFillColor(colors.white)
        _set_font(c, True, 10)
        c.translate(BLEED + TRIM + sw / 2, BLEED + TRIM / 2)
        c.rotate(90)
        c.drawCentredString(0, -4, f"EDDIES & {name}".upper())
        c.restoreState()

    # back
    bx = BLEED
    c.setFillColor(colors.white)
    c.rect(bx, BLEED, TRIM, TRIM, fill=1, stroke=0)
    _draw_eddie(c, bx + TRIM*0.18, BLEED + TRIM*0.82, TRIM*0.08, style=eddie_style)
    c.setFillColor(INK_GRAY_70)
    _set_font(c, False, 12)
    c.drawString(bx + TRIM*0.12, BLEED + TRIM*0.12, "24 Missionen • 24 Stunden • Print-first")

    # front area
    fx = BLEED + TRIM + sw
    c.setFillColor(colors.white)
    c.rect(fx, BLEED, TRIM, TRIM, fill=1, stroke=0)

    # collage behind title area (optional)
    collage = _make_collage_from_uploads(uploads, size_px=1600) if uploads else None
    if collage:
        # place collage centered, but not full cover (keeps it clean)
        coll_w = TRIM * 0.78
        coll_h = coll_w
        cx = fx + (TRIM - coll_w) / 2
        cy = BLEED + TRIM*0.14
        c.drawImage(ImageReader(io.BytesIO(collage)), cx, cy, coll_w, coll_h, mask="auto")

        # white title plate (no alpha dependency)
        c.setFillColor(colors.white)
        c.setStrokeColor(INK_BLACK)
        c.setLineWidth(1)
        c.roundRect(fx + TRIM*0.08, BLEED + TRIM*0.72, TRIM*0.84, TRIM*0.22, TRIM*0.04, fill=1, stroke=1)

    # title
    c.setFillColor(INK_BLACK)
    _set_font(c, True, 46)
    c.drawCentredString(fx + TRIM/2, BLEED + TRIM*0.86, "EDDIES")
    _set_font(c, False, 18)
    c.drawCentredString(fx + TRIM/2, BLEED + TRIM*0.79, f"& {name}")

    # brand mark on top
    _draw_eddie(c, fx + TRIM/2, BLEED + TRIM*0.62, TRIM*0.16, style=eddie_style)

    c.save()
    buf.seek(0)
    return buf.getvalue()

# =========================================================
# UI
# =========================================================
st.set_page_config(page_title=APP_TITLE, layout="centered", page_icon=APP_ICON)

st.markdown(f"<h1 style='text-align:center;'>{APP_TITLE}</h1>", unsafe_allow_html=True)
st.caption(f"Build: {BUILD_TAG}")

if qd is None:
    st.error("quest_data.py konnte nicht geladen werden. Fix das zuerst, sonst gibt’s keine Missionen.")
    st.code(_QD_IMPORT_ERROR or "Unbekannter Import-Fehler", language="text")
    st.stop()

# session init
st.session_state.setdefault("sketch_cache", OrderedDict())
st.session_state.setdefault("assets", None)

with st.container(border=True):
    c1, c2 = st.columns(2)
    name = c1.text_input("Name", "Eddie")
    age = c1.number_input("Alter", 3, 99, 5)

    pages = c2.number_input("Seiten", KDP_MIN_PAGES, 300, KDP_MIN_PAGES, 2)
    pages = int(pages)
    if pages % 2 != 0:
        pages += 1
    paper = c2.selectbox("Papier", list(PAPER_FACTORS.keys()), 0)

    st.divider()

    c3, c4 = st.columns(2)
    eddie_style = c3.selectbox("Eddie-Icon", ["tongue", "dog"], index=0, help="'tongue' = Brand-Mark (ohne Smiley).")
    pre_reader_mode = c4.toggle("👶 Pre-Reader Mode", value=(age <= 6), help="Icons statt Textwüste.")

    kdp = st.toggle("KDP Mode (Bleed + Margins)", True)
    debug_guides = st.toggle("🧪 Preflight Debug (Schnitt/Safe)", False)

    uploads = st.file_uploader(
        "Fotos (werden gewaschen & skizziert)",
        accept_multiple_files=True,
        type=["jpg", "png", "jpeg", "webp"]
    )

can_build = bool(uploads and name)

if st.button("🚀 GENERIEREN", disabled=not can_build):
    with st.spinner("Waschen... Skizzieren... Layouten..."):
        diff = 1 if age <= 4 else 2 if age <= 6 else 3 if age <= 9 else 4

        pdf_int = build_interior(
            name=name,
            uploads=uploads,
            pages=pages,
            kdp=bool(kdp),
            intro=True,
            outro=True,
            start_hour=6,
            diff=diff,
            debug_guides=bool(debug_guides),
            eddie_guide=True,
            eddie_style=eddie_style,
            pre_reader=bool(pre_reader_mode),
        )

        pdf_cov = build_cover(
            name=name,
            pages=pages,
            paper=paper,
            uploads=uploads,
            eddie_style=eddie_style,
        )

        st.session_state.assets = {"int": pdf_int, "cov": pdf_cov, "name": name}
        st.success("Fertig! PDFs sind bereit.")

if st.session_state.assets:
    a = st.session_state.assets
    colA, colB = st.columns(2)
    colA.download_button("📘 Interior PDF", a["int"], file_name=f"Int_{a['name']}.pdf")
    colB.download_button("🎨 Cover PDF", a["cov"], file_name=f"Cov_{a['name']}.pdf")
