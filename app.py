# =========================================================
# app.py — Eddies Questbook Edition — ULTIMATE (v4.5)
# Stable Streamlit Cloud build:
# - Upload wash (JPEG sanitize) + disk spool (OOM shield)
# - NO DPI warning gate (we always resize/upscale to target)
# - Mirror margins + dynamic gutter + 300 DPI render target
# - Front cover: auto collage from uploads (4-grid)
# - Streamlit yellow warning killed (no session_state/value conflict)
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
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth

import image_wash as iw

ImageFile.LOAD_TRUNCATED_IMAGES = True

# =========================================================
# QUEST SYSTEM (guarded import)
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
APP_TITLE = "Eddies ULTIMATE"
APP_ICON = "🐶"
EDDIE_PURPLE = "#7c3aed"

DPI = 300
TRIM_IN = 8.5
TRIM = TRIM_IN * inch
BLEED = 0.125 * inch
SAFE_INTERIOR = 0.375 * inch

INK_BLACK = colors.Color(0, 0, 0)
INK_GRAY_70 = colors.Color(0.30, 0.30, 0.30)

DEBUG_BLEED_COLOR = colors.red
DEBUG_SAFE_COLOR = colors.green

PAPER_FACTORS = {
    "Schwarzweiß – Weiß": 0.002252,
    "Schwarzweiß – Creme": 0.0025,
    "Farbe – Weiß (Standard)": 0.002252,
    "Farbe – Weiß (Premium)": 0.002347,
}
SPINE_TEXT_MIN_PAGES = 79
KDP_MIN_PAGES = 24
MAX_SKETCH_CACHE = 256  # per-session LRU entries

ZONE_STORY = {
    'wachturm': 'Startklar werden: Körper an, Kopf auf, Struktur rein.',
    'wilder_pfad': 'Draußen entdecken: Muster finden, Spuren lesen, neugierig bleiben.',
    'taverne': 'Energie tanken: bewusst essen, Körper wahrnehmen.',
    'werkstatt': 'Bauen & tüfteln: aus Ideen werden Dinge.',
    'arena': 'Action-Modus: Mut testen, Tempo fühlen, dranbleiben.',
    'ratssaal': 'Team-Moment: helfen, sprechen, Verbindung schaffen.',
    'quellen': 'Reset: sauber werden, runterfahren, bereit für Ruhe.',
    'trauminsel': 'Leise Phase: atmen, erinnern, Frieden sammeln.'
}

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
        trim_w=trim_w, trim_h=trim_h, bleed=bleed,
        full_w=trim_w + 2.0 * bleed, full_h=trim_h + 2.0 * bleed
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
# FONTS
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
    if not text: return [""]
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
            if cur: lines.append(cur)
            if not fits(w):
                chunk = ""
                for ch in w:
                    if fits(chunk + ch): chunk += ch
                    else:
                        if chunk: lines.append(chunk)
                        chunk = ch
                cur = chunk
            else:
                cur = w
    if cur: lines.append(cur)
    return lines

def _fit_lines(lines: List[str], max_lines: int) -> List[str]:
    if len(lines) <= max_lines: return lines
    out = lines[:max_lines]
    last = out[-1].rstrip()
    out[-1] = (last[:-3].rstrip() if len(last) > 3 else last) + "…"
    return out

def _autoscale_mission_text(mission, w: float, x0: float, pad_x: float, max_card_h: float) -> Dict[str, Any]:
    base_top, base_bottom = 0.36 * inch, 0.40 * inch
    gap_title, gap_sections = 0.10 * inch, 0.06 * inch
    body_max_w_move = (x0 + w - pad_x) - (x0 + 1.05 * inch)
    body_max_w_think = (x0 + w - pad_x) - (x0 + 0.90 * inch)

    def compute(ts: int, bs: int, ls: int) -> Dict[str, Any]:
        tl = ts * 1.22
        bl = bs * 1.28
        ll = ls * 1.22
        ml = _wrap_text_hard(mission.movement, FONTS["normal"], bs, body_max_w_move)
        tl_lines = _wrap_text_hard(mission.thinking, FONTS["normal"], bs, body_max_w_think)
        needed = base_top + tl + gap_title + (ll * 2) + ((len(ml) + len(tl_lines)) * bl) + gap_sections + base_bottom
        return {"ts": ts, "bs": bs, "ls": ls, "tl": tl, "bl": bl, "ll": ll, "ml": ml, "tl_lines": tl_lines, "needed": needed}

    ts, bs, ls = 13, 10, 10
    sc = compute(ts, bs, ls)
    while sc["needed"] > max_card_h and (ts > 11 or bs > 8 or ls > 8):
        if ts > 11: ts -= 1
        if bs > 8: bs -= 1
        if ls > 8: ls -= 1
        sc = compute(ts, bs, ls)

    if sc["needed"] > max_card_h:
        rem = max_card_h - (base_top + sc["tl"] + gap_title + (sc["ll"] * 2) + gap_sections + base_bottom)
        max_b = max(2, int(rem // sc["bl"]))
        move_allow = max(1, max_b // 2)
        think_allow = max(1, max_b - move_allow)
        sc["ml"] = _fit_lines(sc["ml"], move_allow)
        sc["tl_lines"] = _fit_lines(sc["tl_lines"], think_allow)
        sc["needed"] = base_top + sc["tl"] + gap_title + (sc["ll"] * 2) + ((len(sc["ml"]) + len(sc["tl_lines"])) * sc["bl"]) + gap_sections + base_bottom

    return sc

def _stable_seed(s: str) -> int:
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:8], "big")

# =========================================================
# SKETCH (always upscales to target)
# =========================================================
def _sketch_compute(img_bytes: bytes, target_w: int, target_h: int) -> bytes:
    arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise RuntimeError("Bild fehlerhaft")

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

    del arr, gray, inverted, blurred, denom, sketch, norm, pil, pil_1bit
    gc.collect()

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

def _draw_kdp_debug_guides(c: canvas.Canvas, pb: PageBox, safe_l: float, safe_r: float, safe_tb: float):
    c.saveState()
    c.setLineWidth(0.4)
    c.setDash(3, 3)
    if pb.bleed > 0:
        c.setStrokeColor(DEBUG_BLEED_COLOR)
        c.rect(pb.bleed, pb.bleed, pb.full_w - 2 * pb.bleed, pb.full_h - 2 * pb.bleed, stroke=1, fill=0)
    c.setStrokeColor(DEBUG_SAFE_COLOR)
    c.rect(safe_l, safe_tb, pb.full_w - safe_l - safe_r, pb.full_h - 2 * safe_tb, stroke=1, fill=0)
    c.setDash()
    c.restoreState()

# =========================================================
# OVERLAY
# =========================================================
def _draw_eddie(c: canvas.Canvas, cx: float, cy: float, r: float):
    c.saveState()
    c.setLineWidth(max(2, r * 0.06))
    c.setStrokeColor(INK_BLACK)
    c.setFillColor(colors.white)
    c.circle(cx, cy, r, stroke=1, fill=1)
    c.setFillColor(INK_BLACK)
    c.circle(cx - r * 0.28, cy + r * 0.15, r * 0.10, stroke=0, fill=1)
    c.circle(cx + r * 0.28, cy + r * 0.15, r * 0.10, stroke=0, fill=1)
    c.setLineWidth(max(2, r * 0.05))
    c.arc(cx - r * 0.35, cy - r * 0.10, cx + r * 0.35, cy + r * 0.20, 200, 140)
    c.setFillColor(colors.HexColor(EDDIE_PURPLE))
    c.roundRect(cx - r * 0.10, cy - r * 0.35, r * 0.20, r * 0.22, r * 0.08, stroke=0, fill=1)
    c.restoreState()

def _draw_quest_overlay(c: canvas.Canvas, pb: PageBox, safe_left: float, safe_right: float, safe_tb: float, hour: int, mission, debug: bool):
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
    c.drawString(x0 + 0.18 * inch, y_header_bottom + header_h - 0.50 * inch, f"{qd.fmt_hour(hour)}  {zone.icon}  {zone.name}")
    _set_font(c, False, 10)
    c.drawString(x0 + 0.18 * inch, y_header_bottom + 0.18 * inch, f"{zone.quest_type} • {zone.atmosphere}")

    cy = y0
    max_ch = (y_header_bottom - cy) - (0.15 * inch)
    pad_x = 0.18 * inch
    sc = _autoscale_mission_text(mission, w, x0, pad_x, max_ch)
    card_h = min(max_ch, max(1.85 * inch, sc["needed"]))

    c.setFillColor(colors.white)
    c.setStrokeColor(INK_BLACK)
    c.rect(x0, cy, w, card_h, fill=1, stroke=1)

    y_text = cy + card_h - 0.18 * inch
    c.setFillColor(INK_BLACK)
    _set_font(c, True, sc["ts"])
    c.drawString(x0 + pad_x, y_text - sc["tl"] + 2, f"MISSION: {mission.title}")
    _set_font(c, True, max(8, sc["ts"] - 2))
    c.drawRightString(x0 + w - pad_x, y_text - sc["tl"] + 2, f"+{mission.xp} XP")

    y_text -= sc["tl"] + 0.10 * inch
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
    pr = _fit_lines(_wrap_text_hard(mission.proof, FONTS["normal"], sc["bs"], w - 1.5 * inch), 1)[0]
    c.drawString(bx + box + 0.75 * inch, cy + 0.20 * inch, pr)

    if debug:
        _draw_kdp_debug_guides(c, pb, safe_left, safe_right, safe_tb)
    c.restoreState()

# =========================================================
# BUILDERS
# =========================================================
def _tmp(prefix: str, suffix: str, data: bytes) -> str:
    with tempfile.NamedTemporaryFile(prefix=prefix, suffix=suffix, delete=False) as tf:
        tf.write(data)
        return tf.name

def _cover_collage_png(uploads, size_px: int, seed: int) -> Optional[bytes]:
    files = list(uploads or [])
    if not files:
        return None

    # pick up to 4 deterministic
    rng = np.random.default_rng(seed & 0xFFFFFFFF)
    idx = np.arange(len(files))
    rng.shuffle(idx)
    pick = [files[i] for i in idx[:min(4, len(files))]]

    grid = 2
    gap = max(10, size_px // 120)
    cell = (size_px - gap * (grid + 1)) // grid
    canvas_img = Image.new("L", (size_px, size_px), 255)

    k = 0
    for r in range(grid):
        for c_ in range(grid):
            if k >= len(pick): break
            up = pick[k]; k += 1
            try:
                raw = up.getvalue()
                washed = iw.wash_image_bytes(raw).bytes
                # sketch each cell
                sk = _sketch_compute(washed, cell, cell)
                tile = Image.open(io.BytesIO(sk)).convert("L")
            except Exception:
                tile = Image.new("L", (cell, cell), 255)

            x = gap + c_ * (cell + gap)
            y = gap + r * (cell + gap)
            canvas_img.paste(tile, (x, y))
            del tile, raw, washed
            gc.collect()

    # subtle frame lines
    d = ImageDraw.Draw(canvas_img)
    d.rectangle([0, 0, size_px-1, size_px-1], outline=0, width=max(2, size_px // 250))
    out = io.BytesIO()
    canvas_img.save(out, format="PNG", optimize=True)
    return out.getvalue()

def build_interior(name: str, uploads, total_pages: int, kdp: bool, intro: bool, outro: bool, start_hour: int, diff: int, debug_guides: bool) -> bytes:
    pb = page_box(TRIM, TRIM, kdp_bleed=kdp)
    files = list(uploads or [])
    if not files:
        raise RuntimeError("Keine Bilder hochgeladen.")

    photo_count = max(1, total_pages - (int(intro) + int(outro)))
    final = (files * (photo_count // len(files) + 1))[:photo_count]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pb.full_w, pb.full_h))

    seed_base = _stable_seed(name)

    # --- PRECOMPUTE STORY PROGRESSION ---
    hours, missions, zones, chapter_idx = [], [], [], []
    chap = 1
    prev_zone_id = None
    for i in range(photo_count):
        h_val = (start_hour + i) % 24
        hours.append(h_val)
        seed = int(seed_base ^ (i << 1) ^ h_val) & 0xFFFFFFFF
        m = qd.pick_mission_for_time(h_val, diff, seed)
        missions.append(m)
        z = qd.get_zone_for_hour(h_val)
        zones.append(z)
        if prev_zone_id is not None and z.id != prev_zone_id:
            chap += 1
        chapter_idx.append(chap)
        prev_zone_id = z.id

    total_chapters = chapter_idx[-1] if chapter_idx else 1
    current_page_idx = 0

    if intro:
        sl, sr, stb = safe_margins_for_page(total_pages, kdp, current_page_idx, pb)
        c.setFillColor(colors.white); c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)
        c.setFillColor(INK_BLACK)
        _set_font(c, True, 34); c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 0.65 * inch, "Willkommen bei Eddies")
        _set_font(c, False, 22); c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 1.25 * inch, f"& {name}")
        _draw_eddie(c, pb.full_w / 2, pb.full_h / 2, 1.3 * inch)
        _set_font(c, False, 14); c.setFillColor(INK_GRAY_70)
        c.drawCentredString(pb.full_w / 2, stb + 0.75 * inch, "24 Stunden • 24 Missionen • Haken setzen")
        if debug_guides: _draw_kdp_debug_guides(c, pb, sl, sr, stb)
        c.showPage(); current_page_idx += 1

    target_w = int(pb.full_w * DPI / inch)
    target_h = int(pb.full_h * DPI / inch)

    pw, ph = pb.full_w, pb.full_h

    for i, up in enumerate(final):
        # --- chapter break page (separate) ---
        if i > 0 and chapter_idx[i] > chapter_idx[i-1]:
            sl, sr, stb = safe_margins_for_page(total_pages, kdp, current_page_idx, pb)
            zone = zones[i]
            c.saveState()
            c.setFillColorRGB(0.05, 0.07, 0.10)
            c.rect(0, 0, pw, ph, fill=1, stroke=0)
            c.setFillColorRGB(1, 1, 1)
            _set_font(c, True, 26)
            c.drawCentredString(pw / 2.0, ph / 2.0 + 0.8 * inch, f"KAPITEL {chapter_idx[i]}")
            _set_font(c, False, 14)
            c.drawCentredString(pw / 2.0, ph / 2.0 - 0.4 * inch, f"Willkommen in: {zone.name}")
            c.restoreState()
            if debug_guides: _draw_kdp_debug_guides(c, pb, sl, sr, stb)
            c.showPage(); current_page_idx += 1

        sl, sr, stb = safe_margins_for_page(total_pages, kdp, current_page_idx, pb)

        raw = up.getvalue()
        washed = iw.wash_image_bytes(raw).bytes
        png_bytes = _get_sketch_cached(washed, target_w, target_h)
        c.drawImage(ImageReader(io.BytesIO(png_bytes)), 0, 0, pb.full_w, pb.full_h)

        h_val = hours[i]
        mission = missions[i]
        zone = zones[i]
                
                try:
                    cum_xp += int(mission.xp)
                    mission.chapter = chapter_idx[i]
                    mission.total_chapters = total_chapters
                except Exception:
                    pass
                
                # --- BOSS-FIGHT / KAPITEL-TRENNSEITE ---
                if i > 0 and chapter_idx[i] > chapter_idx[i-1]:
                    c.saveState()
                    c.setFillColorRGB(0.05, 0.07, 0.1) # Dunkler KDP-safe Hintergrund
                    c.rect(0, 0, pw, ph, fill=1, stroke=0)
                    c.setFillColorRGB(1, 1, 1) # Weißer Text
                    
                    try:
                        _set_font(c, True, 26)
                    except:
                        c.setFont("Helvetica-Bold", 26)
                    c.drawCentredString(pw / 2.0, ph / 2.0 + 0.8 * 72.0, f"KAPITEL {mission.chapter}")
                    
                    try:
                        _set_font(c, False, 14)
                    except:
                        c.setFont("Helvetica", 14)
                    c.drawCentredString(pw / 2.0, ph / 2.0 - 0.4 * 72.0, f"Willkommen in: {zone.name}")
                    
                    c.restoreState()
                    c.showPage()
                    current_page_idx += 1

        _draw_quest_overlay(c, pb, sl, sr, stb, h_val, mission, debug=debug_guides)
        c.showPage()
        current_page_idx += 1

        del raw, washed, png_bytes
        gc.collect()

    if outro:
        sl, sr, stb = safe_margins_for_page(total_pages, kdp, current_page_idx, pb)
        c.setFillColor(colors.white); c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)
        _draw_eddie(c, pb.full_w / 2, pb.full_h / 2 + 0.6 * inch, 1.5 * inch)
        c.setFillColor(INK_BLACK); _set_font(c, True, 30)
        c.drawCentredString(pb.full_w / 2, stb + 1.75 * inch, "Quest abgeschlossen!")
        if debug_guides: _draw_kdp_debug_guides(c, pb, sl, sr, stb)
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()

def build_cover(name: str, pages: int, paper: str, uploads=None) -> bytes:
    sw = float(pages) * PAPER_FACTORS.get(paper, 0.002252) * inch
    sw = max(sw, 0.001 * inch)
    sw = round(sw / (0.001 * inch)) * (0.001 * inch)
    cw, ch = (2 * TRIM) + sw + (2 * BLEED), TRIM + (2 * BLEED)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(cw, ch))
    c.setFillColor(colors.white); c.rect(0, 0, cw, ch, fill=1, stroke=0)

    # spine
    c.setFillColor(INK_BLACK); c.rect(BLEED + TRIM, BLEED, sw, TRIM, fill=1, stroke=0)

    if pages >= SPINE_TEXT_MIN_PAGES:
        c.saveState()
        c.setFillColor(colors.white); _set_font(c, True, 10)
        c.translate(BLEED + TRIM + sw / 2, BLEED + TRIM / 2); c.rotate(90)
        c.drawCentredString(0, -4, f"EDDIES & {name}".upper())
        c.restoreState()

    # back (left) minimal
    bx = BLEED
    c.setFillColor(colors.white)
    c.rect(bx, BLEED, TRIM, TRIM, fill=1, stroke=0)
    _draw_eddie(c, bx + TRIM*0.18, BLEED + TRIM*0.82, TRIM*0.08)
    c.setFillColor(INK_GRAY_70); _set_font(c, False, 12)
    c.drawString(bx + TRIM*0.12, BLEED + TRIM*0.12, "24 Missionen • 24 Stunden • KDP-ready")

    # front (right)
    fx = BLEED + TRIM + sw
    c.setFillColor(colors.white); c.rect(fx, BLEED, TRIM, TRIM, fill=1, stroke=0)

    # collage zone (behind)
    collage_px = int((TRIM * DPI / inch) * 0.72)
    collage = _cover_collage_png(uploads, collage_px, _stable_seed(name + "|cover"))
    if collage:
        # place collage centered
        collage_w = TRIM * 0.72
        collage_h = collage_w
        cx = fx + (TRIM - collage_w) / 2
        cy = BLEED + TRIM*0.16
        c.drawImage(ImageReader(io.BytesIO(collage)), cx, cy, collage_w, collage_h, mask='auto')

        # white plate for title readability
        c.setFillColor(colors.white)
        c.setStrokeColor(INK_BLACK)
        c.setLineWidth(1)
        c.roundRect(fx + TRIM*0.10, BLEED + TRIM*0.74, TRIM*0.80, TRIM*0.20, TRIM*0.04, fill=1, stroke=1)

    # title
    c.setFillColor(INK_BLACK); _set_font(c, True, 44)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.86, "EDDIES")
    _set_font(c, False, 18)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.79, f"& {name}")

    # mascot on top
    _draw_eddie(c, fx + TRIM / 2, BLEED + TRIM * 0.62, TRIM * 0.14)

    c.save()
    buf.seek(0)
    return buf.getvalue()

def build_listing_text(child_name: str) -> str:
    cn = (child_name or "").strip()
    title = "Eddies" if cn.lower() in {"eddie", "eddies"} else f"Eddies & {cn}"
    keywords = [
        "personalisiertes malbuch kinder",
        "malbuch mit eigenen fotos",
        "geschenk kinder personalisiert",
        "kinder malbuch ab 4 jahre",
        "abenteuer buch kinder",
        "24 missionen kinder",
        "ausmalbilder aus fotos",
    ]
    html = f"""<h3>24 Stunden. 24 Missionen. Dein Kind als Held.</h3>
<p>Aus deinen Fotos entstehen Ausmalbilder – und jede Seite enthält eine Mini-Quest:
<b>Bewegung</b> + <b>Denkaufgabe</b> + <b>XP</b> zum Abhaken.</p>
<ul>
  <li><b>Personalisiert:</b> Seiten basieren auf deinen hochgeladenen Bildern.</li>
  <li><b>24h-Quest-System:</b> Zeit → Zone → Mission (spielerisch, ohne Druck).</li>
  <li><b>Druckoptimiert:</b> 300 DPI Render-Target + harte Schwarzwerte.</li>
</ul>
<p><i>Eddies bleibt schwarz-weiß als Guide – dein Kind macht die Welt bunt.</i></p>
"""
    return "\n".join(
        [
            "READY-TO-PUBLISH LISTING BUNDLE",
            f"TITEL: {title}",
            "",
            "KEYWORDS (7 Felder):",
            "\n".join([f"{i+1}. {k}" for i, k in enumerate(keywords)]),
            "",
            "BESCHREIBUNG (HTML):",
            html,
        ]
    )

# =========================================================
# UI
# =========================================================
st.set_page_config(page_title=APP_TITLE, layout="centered", page_icon=APP_ICON)

# ---- Streamlit warning killer (no value/key conflict)
st.session_state.setdefault("pages", KDP_MIN_PAGES)
st.session_state.setdefault("paper", list(PAPER_FACTORS.keys())[0])

if "assets" not in st.session_state:
    st.session_state.assets = None
if "upload_sig" not in st.session_state:
    st.session_state.upload_sig = ""
if "sketch_cache" not in st.session_state:
    st.session_state.sketch_cache = OrderedDict()

def _uploads_signature(uploads_list) -> str:
    h = hashlib.sha256()
    for up in uploads_list or []:
        try:
            buf = up.getbuffer()
            ln = len(buf)
            h.update(up.name.encode("utf-8", errors="ignore"))
            h.update(ln.to_bytes(8, "little", signed=False))
            if ln > 4096:
                sample = bytes(buf[:2048]) + bytes(buf[-2048:])
            else:
                sample = bytes(buf)
            h.update(hashlib.sha256(sample).digest())
        except Exception:
            b = up.getvalue()
            h.update(up.name.encode("utf-8", errors="ignore"))
            h.update(len(b).to_bytes(8, "little", signed=False))
            h.update(hashlib.sha256(b[:2048]).digest())
    return h.hexdigest()

st.markdown(f"<h1 style='text-align:center;'>{APP_TITLE}</h1>", unsafe_allow_html=True)

if qd is None:
    st.error("quest_data.py konnte nicht geladen werden. Fix das zuerst, sonst gibt’s keine Missionen.")
    st.code(_QD_IMPORT_ERROR or "Unbekannter Import-Fehler", language="text")
    st.stop()

with st.container(border=True):
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Name", value="Eddie")
        age = st.number_input("Alter", 3, 99, 5)
    with col2:
        pages = st.number_input("Seiten", min_value=KDP_MIN_PAGES, max_value=300, step=2, key="pages")
        paper = st.selectbox("Papier", list(PAPER_FACTORS.keys()), key="paper")

    kdp = st.toggle("KDP-Mode (Bleed)", True)
    debug_guides = st.toggle("🧪 KDP Preflight Debug (Bleed/Safe)", False)
    uploads = st.file_uploader("Fotos", accept_multiple_files=True, type=["jpg", "png", "jpeg"])

    n_uploads = len(uploads) if uploads else 0
    st.markdown(f"**📸 Hochgeladen:** `{n_uploads}` Bild(er)")
    st.caption("Hinweis: Streamlit zeigt nur die Datei-Liste (Pagination) – nicht deine Buchseiten.")

can_build = bool(uploads and name)

if uploads and name:
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

if st.button("🚀 Buch generieren", disabled=not can_build):
    upload_sig = _uploads_signature(uploads)
    if st.session_state.upload_sig != upload_sig:
        st.session_state.upload_sig = upload_sig
        st.session_state.sketch_cache.clear()

    with st.spinner("AUTO-SCALE & PDF Build..."):
        diff = 1 if age <= 4 else 2 if age <= 6 else 3 if age <= 9 else 4

        int_pdf = build_interior(
            name=name,
            uploads=uploads,
            total_pages=int(pages),
            kdp=bool(kdp),
            intro=True,
            outro=True,
            start_hour=6,
            diff=diff,
            debug_guides=bool(debug_guides),
        )

        cov_pdf = build_cover(name=name, pages=int(pages), paper=paper, uploads=uploads)
        listing_txt = build_listing_text(name)

        if st.session_state.assets:
            for f in st.session_state.assets.values():
                if isinstance(f, str) and os.path.exists(f):
                    try: os.remove(f)
                    except Exception: pass

        st.session_state.assets = {
            "int": _tmp("int_", ".pdf", int_pdf),
            "cov": _tmp("cov_", ".pdf", cov_pdf),
            "listing": _tmp("list_", ".txt", listing_txt.encode("utf-8")),
            "name": name,
        }

        st.success("KDP-Assets bereit!")

if st.session_state.assets:
    a = st.session_state.assets
    col1, col2, col3 = st.columns(3)
    with col1:
        with open(a["int"], "rb") as f:
            st.download_button("📘 Interior", f, file_name=f"Int_{a['name']}.pdf")
    with col2:
        with open(a["cov"], "rb") as f:
            st.download_button("🎨 Cover", f, file_name=f"Cov_{a['name']}.pdf")
    with col3:
        with open(a["listing"], "rb") as f:
            st.download_button("📝 Listing (SEO)", f, file_name=f"Listing_{a['name']}.txt")

st.markdown("<div style='text-align:center; color:grey;'>Eddies Welt © 2026</div>", unsafe_allow_html=True)
