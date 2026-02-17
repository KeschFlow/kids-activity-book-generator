# =========================================================
# app.py (Eddies Questbook Edition) — PLATINUM (v4.3)
# Production hardened + Preflight Gatekeeper + GOD MODE Visualizer + KDP Helper
# =========================================================
from __future__ import annotations

import io# =========================================================
# app.py (Eddies Questbook Edition) — PLATINUM (v4.3.1)
# Production hardened + Preflight Gatekeeper + GOD MODE Visualizer + KDP Helper
# + Upload Counter (requested)
# =========================================================
from __future__ import annotations

import io
import os
import time
import tempfile
import hashlib
import functools
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from collections import OrderedDict

import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth


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
# 1) CONFIG & COLORS
# =========================================================
APP_TITLE = "Eddies"
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
DEBUG_LINE_W = 0.4

PAPER_FACTORS = {
    "Schwarzweiß – Weiß": 0.002252,
    "Schwarzweiß – Creme": 0.0025,
    "Farbe – Weiß (Standard)": 0.002252,
    "Farbe – Weiß (Premium)": 0.002347,
}
SPINE_TEXT_MIN_PAGES = 79
KDP_MIN_PAGES = 24


# =========================================================
# 2) PAGE GEOMETRY (PageBox Pattern)
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
    # KDP gutter chart (inside margin depends on page count)
    if pages <= 150:
        return 0.375
    if pages <= 300:
        return 0.500
    if pages <= 500:
        return 0.625
    if pages <= 700:
        return 0.750
    return 0.875  # 701–828


def safe_margins_for_page(
    pages: int,
    kdp: bool,
    page_index_0: int,
    pb: PageBox,
) -> tuple[float, float, float]:
    """
    returns (safe_left, safe_right, safe_tb) in points
    - safe_tb applies to both top and bottom
    - safe_left/right are mirrored for facing pages when kdp=True
    """
    if not kdp:
        s = SAFE_INTERIOR
        return s, s, s

    outside = pb.bleed + (0.375 * inch)
    safe_tb = pb.bleed + (0.375 * inch)
    gutter = pb.bleed + (_kdp_inside_gutter_in(pages) * inch)

    # odd pages are right-hand pages -> gutter on left
    is_odd = ((page_index_0 + 1) % 2 == 1)
    safe_left = gutter if is_odd else outside
    safe_right = outside if is_odd else gutter
    return safe_left, safe_right, safe_tb


# =========================================================
# 3) FONT & TEXT HELPERS
# =========================================================
def _try_register_fonts() -> Dict[str, str]:
    normal_p = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_p = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    if os.path.exists(normal_p):
        try:
            pdfmetrics.registerFont(TTFont("EDDIES_FONT", normal_p))
        except Exception:
            pass
    if os.path.exists(bold_p):
        try:
            pdfmetrics.registerFont(TTFont("EDDIES_FONT_BOLD", bold_p))
        except Exception:
            pass

    f_n = "EDDIES_FONT" if "EDDIES_FONT" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    f_b = "EDDIES_FONT_BOLD" if "EDDIES_FONT_BOLD" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    return {"normal": f_n, "bold": f_b}


FONTS = _try_register_fonts()


def _set_font(c: canvas.Canvas, bold: bool, size: int, leading: Optional[float] = None) -> float:
    font_name = FONTS["bold"] if bold else FONTS["normal"]
    c.setFont(font_name, size)
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

        needed = (
            base_top
            + tl
            + gap_title
            + (ll * 2)
            + ((len(ml) + len(tl_lines)) * bl)
            + gap_sections
            + base_bottom
        )
        return {"ts": ts, "bs": bs, "ls": ls, "tl": tl, "bl": bl, "ll": ll, "ml": ml, "tl_lines": tl_lines, "needed": needed}

    ts, bs, ls = 13, 10, 10
    sc = compute(ts, bs, ls)

    while sc["needed"] > max_card_h and (ts > 11 or bs > 8 or ls > 8):
        if ts > 11:
            ts -= 1
        if bs > 8:
            bs -= 1
        if ls > 8:
            ls -= 1
        sc = compute(ts, bs, ls)

    if sc["needed"] > max_card_h:
        rem = max_card_h - (base_top + sc["tl"] + gap_title + (sc["ll"] * 2) + gap_sections + base_bottom)
        max_b = max(2, int(rem // sc["bl"]))
        move_allow = max(1, max_b // 2)
        think_allow = max(1, max_b - move_allow)

        sc["ml"] = _fit_lines(sc["ml"], move_allow)
        sc["tl_lines"] = _fit_lines(sc["tl_lines"], think_allow)

        sc["needed"] = (
            base_top
            + sc["tl"]
            + gap_title
            + (sc["ll"] * 2)
            + ((len(sc["ml"]) + len(sc["tl_lines"])) * sc["bl"])
            + gap_sections
            + base_bottom
        )

    return sc


def _stable_seed(s: str) -> int:
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:8], "big")


# =========================================================
# 4) SKETCH ENGINE (TRUE HASH-KEY CACHE + 1-BIT)
# =========================================================
_IMG_STORE_MAX = 256
_IMG_STORE: "OrderedDict[str, bytes]" = OrderedDict()

def _img_store_put(img_hash: str, img_bytes: bytes) -> None:
    if img_hash in _IMG_STORE:
        _IMG_STORE.move_to_end(img_hash)
        return
    _IMG_STORE[img_hash] = img_bytes
    _IMG_STORE.move_to_end(img_hash)
    while len(_IMG_STORE) > _IMG_STORE_MAX:
        _IMG_STORE.popitem(last=False)

def _img_store_get(img_hash: str) -> bytes:
    b = _IMG_STORE.get(img_hash)
    if b is None:
        raise KeyError("img_hash not in store")
    _IMG_STORE.move_to_end(img_hash)
    return b


@functools.lru_cache(maxsize=256)
def _sketch_cached_by_hash(img_hash: str, target_w: int, target_h: int) -> bytes:
    img_bytes = _img_store_get(img_hash)

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
    return out.getvalue()


def _get_sketch(img_bytes: bytes, target_w: int, target_h: int) -> bytes:
    h = hashlib.sha256(img_bytes).hexdigest()
    _img_store_put(h, img_bytes)
    return _sketch_cached_by_hash(h, target_w, target_h)


# =========================================================
# 5) PDF DEBUG GUIDES
# =========================================================
def _draw_kdp_debug_guides(c: canvas.Canvas, pb: PageBox, safe_l: float, safe_r: float, safe_tb: float):
    c.saveState()
    c.setLineWidth(DEBUG_LINE_W)
    c.setDash(3, 3)

    if pb.bleed > 0:
        c.setStrokeColor(DEBUG_BLEED_COLOR)
        c.rect(pb.bleed, pb.bleed, pb.full_w - 2 * pb.bleed, pb.full_h - 2 * pb.bleed, stroke=1, fill=0)

    c.setStrokeColor(DEBUG_SAFE_COLOR)
    c.rect(safe_l, safe_tb, pb.full_w - safe_l - safe_r, pb.full_h - 2 * safe_tb, stroke=1, fill=0)

    c.setDash()
    c.restoreState()


# =========================================================
# 6) DYNAMIC OVERLAY (MIRROR MARGINS)
# =========================================================
def _draw_quest_overlay(
    c: canvas.Canvas,
    pb: PageBox,
    safe_left: float,
    safe_right: float,
    safe_tb: float,
    hour: int,
    mission,
    debug: bool,
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

    # Header
    c.setFillColor(fill)
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(1)
    c.rect(x0, y_header_bottom, w, header_h, fill=1, stroke=1)

    c.setFillColor(tc)
    _set_font(c, True, 14)
    c.drawString(x0 + 0.18 * inch, y_header_bottom + header_h - 0.50 * inch, f"{qd.fmt_hour(hour)}  {zone.icon}  {zone.name}")
    _set_font(c, False, 10)
    c.drawString(x0 + 0.18 * inch, y_header_bottom + 0.18 * inch, f"{zone.quest_type} • {zone.atmosphere}")

    # Card
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
# 7) PDF BUILDERS
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


def build_interior(
    name: str,
    uploads,
    total_pages: int,
    eddie_mark: bool,
    kdp: bool,
    intro: bool,
    outro: bool,
    start_hour: int,
    diff: int,
    debug_guides: bool,
) -> bytes:
    pb = page_box(TRIM, TRIM, kdp_bleed=kdp)

    files = list(uploads or [])
    if not files:
        raise RuntimeError("Keine Bilder hochgeladen.")

    photo_count = max(1, total_pages - (int(intro) + int(outro)))
    final = (files * (photo_count // len(files) + 1))[:photo_count]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pb.full_w, pb.full_h))

    seed_base = _stable_seed(name)
    current_page_idx = 0  # 0-based for safe mirroring

    # INTRO
    if intro:
        sl, sr, stb = safe_margins_for_page(total_pages, kdp, current_page_idx, pb)

        c.setFillColor(colors.white)
        c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)

        c.setFillColor(INK_BLACK)
        _set_font(c, True, 34)
        c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 0.65 * inch, "Willkommen bei Eddies")
        _set_font(c, False, 22)
        c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 1.25 * inch, f"& {name}")
        _draw_eddie(c, pb.full_w / 2, pb.full_h / 2, 1.3 * inch)

        _set_font(c, False, 14)
        c.setFillColor(INK_GRAY_70)
        c.drawCentredString(pb.full_w / 2, stb + 0.75 * inch, "24 Stunden • 24 Missionen • Haken setzen")

        if debug_guides:
            _draw_kdp_debug_guides(c, pb, sl, sr, stb)

        c.showPage()
        current_page_idx += 1

    # CONTENT
    target_w = int(pb.full_w * DPI / inch)
    target_h = int(pb.full_h * DPI / inch)

    for i, up in enumerate(final):
        sl, sr, stb = safe_margins_for_page(total_pages, kdp, current_page_idx, pb)

        img_data = up.getvalue()
        png_bytes = _get_sketch(img_data, target_w, target_h)
        c.drawImage(ImageReader(io.BytesIO(png_bytes)), 0, 0, pb.full_w, pb.full_h)

        h_val = (start_hour + i) % 24
        seed = int(seed_base ^ (i << 1) ^ h_val) & 0x7FFFFFFF
        mission = qd.pick_mission_for_time(h_val, diff, seed)

        _draw_quest_overlay(c, pb, sl, sr, stb, h_val, mission, debug=debug_guides)

        if eddie_mark:
            # safe-center placement (never crosses safe)
            r = 0.18 * inch
            cx = (pb.full_w - sr) - r
            cy = (stb + 2.25 * inch) + r
            _draw_eddie(c, cx, cy, r)

        c.showPage()
        current_page_idx += 1

    # OUTRO
    if outro:
        sl, sr, stb = safe_margins_for_page(total_pages, kdp, current_page_idx, pb)

        c.setFillColor(colors.white)
        c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)

        _draw_eddie(c, pb.full_w / 2, pb.full_h / 2 + 0.6 * inch, 1.5 * inch)
        c.setFillColor(INK_BLACK)
        _set_font(c, True, 30)
        c.drawCentredString(pb.full_w / 2, stb + 1.75 * inch, "Quest abgeschlossen!")

        if debug_guides:
            _draw_kdp_debug_guides(c, pb, sl, sr, stb)

        c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()


def build_cover(name: str, pages: int, paper: str) -> bytes:
    sw = float(pages) * PAPER_FACTORS.get(paper, 0.002252) * inch
    sw = max(sw, 0.001 * inch)
    sw = round(sw / (0.001 * inch)) * (0.001 * inch)

    cw = (2 * TRIM) + sw + (2 * BLEED)
    ch = TRIM + (2 * BLEED)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(cw, ch))

    c.setFillColor(colors.white)
    c.rect(0, 0, cw, ch, fill=1, stroke=0)

    # Spine block
    c.setFillColor(INK_BLACK)
    c.rect(BLEED + TRIM, BLEED, sw, TRIM, fill=1, stroke=0)

    # Spine text
    if pages >= SPINE_TEXT_MIN_PAGES:
        c.saveState()
        c.setFillColor(colors.white)
        _set_font(c, True, 10)
        c.translate(BLEED + TRIM + sw / 2, BLEED + TRIM / 2)
        c.rotate(90)
        c.drawCentredString(0, -4, f"EDDIES & {name}".upper())
        c.restoreState()

    # Front cover start x
    fx = BLEED + TRIM + sw

    _draw_eddie(c, fx + TRIM / 2, BLEED + TRIM * 0.58, TRIM * 0.18)

    c.setFillColor(INK_BLACK)
    _set_font(c, True, 44)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.80, "EDDIES")
    _set_font(c, False, 18)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.73, f"& {name}")

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
  <li><b>Druckoptimiert:</b> 300 DPI Layout, klare Schwarzwerte, saubere Ränder.</li>
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
# 8) KDP PREFLIGHT GATEKEEPER
# =========================================================
@dataclass(frozen=True)
class PreflightIssue:
    level: str  # "ERROR"|"WARN"|"INFO"
    code: str
    message: str

@dataclass(frozen=True)
class PreflightResult:
    ok_to_build: bool
    issues: List[PreflightIssue]
    report_text: str

def _gutter_bucket(pages: int) -> str:
    if pages <= 150:
        return "≤150"
    if pages <= 300:
        return "151–300"
    if pages <= 500:
        return "301–500"
    if pages <= 700:
        return "501–700"
    return "701–828"

def _within(a0: float, a1: float, b0: float, b1: float, eps: float = 0.5) -> bool:
    return (a0 + eps) >= b0 and (a1 - eps) <= b1

def _rect_inside_safe(rect: Tuple[float, float, float, float], safe: Tuple[float, float, float, float], eps: float = 0.5) -> bool:
    x0, y0, x1, y1 = rect
    sx0, sy0, sx1, sy1 = safe
    return _within(x0, x1, sx0, sx1, eps=eps) and _within(y0, y1, sy0, sy1, eps=eps)

def _overlay_boxes_for_page(pb: PageBox, safe_left: float, safe_right: float, safe_tb: float, mission=None) -> Dict[str, Tuple[float, float, float, float]]:
    x0 = safe_left
    x1 = pb.full_w - safe_right
    y0 = safe_tb
    y1 = pb.full_h - safe_tb

    header_h = 0.75 * inch
    header = (x0, y1 - header_h, x1, y1)

    max_ch = (y1 - header_h - y0) - (0.15 * inch)

    if mission is None or max_ch <= 1:
        card_h = min(max_ch, 1.85 * inch) if max_ch > 0 else 0
    else:
        pad_x = 0.18 * inch
        w = max(1.0, x1 - x0)
        sc = _autoscale_mission_text(mission, w, x0, pad_x, max_ch)
        card_h = min(max_ch, max(1.85 * inch, sc["needed"]))

    card = (x0, y0, x1, y0 + max(0.0, card_h))
    safe = (x0, y0, x1, y1)
    return {"safe": safe, "header": header, "card": card}

def run_kdp_preflight(
    *,
    name: str,
    total_pages: int,
    kdp: bool,
    intro: bool,
    outro: bool,
    pb: PageBox,
    uploads: Optional[list],
    start_hour: int,
    diff: int,
    eddie_mark: bool,
    sample_pages: int = 12,
) -> PreflightResult:
    t0 = time.time()
    issues: List[PreflightIssue] = []

    # Hard gates
    if kdp:
        if total_pages < KDP_MIN_PAGES:
            issues.append(PreflightIssue("ERROR", "KDP_MIN_PAGES", f"KDP min {KDP_MIN_PAGES} Seiten. Aktuell: {total_pages}."))
        if total_pages % 2 != 0:
            issues.append(PreflightIssue("ERROR", "EVEN_PAGES", f"KDP braucht gerade Seitenzahl. Aktuell: {total_pages}."))

    # Fair trim-based res check
    if uploads:
        target_px = int(TRIM_IN * DPI)
        low = []
        for up in uploads:
            try:
                data = up.getvalue()
                with Image.open(io.BytesIO(data)) as img:
                    w, h = img.size
                if min(w, h) < target_px:
                    low.append((up.name, w, h))
            except Exception:
                issues.append(PreflightIssue("WARN", "IMAGE_READ_FAIL", f"Konnte Bild nicht prüfen: {getattr(up,'name','(unknown)')}"))
        if low:
            issues.append(PreflightIssue("WARN", "LOW_RES_UPLOADS", f"{len(low)} Foto(s) < {target_px}px (Trim @300DPI)."))

    # Sample pages
    if total_pages > 0:
        picks = {0, 1, total_pages // 2, max(0, total_pages // 2 - 1), total_pages - 1, max(0, total_pages - 2)}
        if total_pages > 8:
            step = max(1, total_pages // max(1, (sample_pages - len(picks))))
            for idx in range(0, total_pages, step):
                picks.add(idx)
                if len(picks) >= sample_pages:
                    break
        sample_idxs = sorted(picks)[:sample_pages]
    else:
        sample_idxs = []

    def mission_for_sample(page_idx_0: int):
        if qd is None:
            return None
        h_val = (start_hour + page_idx_0) % 24
        seed_base = _stable_seed(name)
        seed = int(seed_base ^ (page_idx_0 << 1) ^ h_val) & 0x7FFFFFFF
        try:
            return qd.pick_mission_for_time(h_val, diff, seed)
        except Exception:
            return None

    eps = 0.5
    for pidx in sample_idxs:
        sl, sr, stb = safe_margins_for_page(total_pages, kdp, pidx, pb)
        boxes = _overlay_boxes_for_page(pb, sl, sr, stb, mission=mission_for_sample(pidx))
        safe_box = boxes["safe"]

        if not _rect_inside_safe(boxes["header"], safe_box, eps=eps):
            issues.append(PreflightIssue("ERROR", "OVERLAY_HEADER_UNSAFE", f"Header verlässt Safe auf Seite {pidx+1}."))
        if not _rect_inside_safe(boxes["card"], safe_box, eps=eps):
            issues.append(PreflightIssue("ERROR", "OVERLAY_CARD_UNSAFE", f"Card verlässt Safe auf Seite {pidx+1}."))

        if eddie_mark:
            r = 0.18 * inch
            cx = (pb.full_w - sr) - r
            cy = (stb + 2.25 * inch) + r
            eddie_rect = (cx - r, cy - r, cx + r, cy + r)
            if not _rect_inside_safe(eddie_rect, safe_box, eps=eps):
                issues.append(PreflightIssue("ERROR", "EDDIE_MARK_UNSAFE", f"Eddie-Mark verlässt Safe auf Seite {pidx+1}."))

        sx0, sy0, sx1, sy1 = safe_box
        if (sx1 - sx0) <= (1.0 * inch) or (sy1 - sy0) <= (1.0 * inch):
            issues.append(PreflightIssue("ERROR", "SAFE_BOX_TOO_SMALL", f"Safe-Box wirkt zu klein (Seite {pidx+1})."))

    has_error = any(i.level == "ERROR" for i in issues)
    ok = not has_error

    gutter_in = _kdp_inside_gutter_in(total_pages) if kdp else (SAFE_INTERIOR / inch)
    outside_in = 0.375 if kdp else (SAFE_INTERIOR / inch)
    bucket = _gutter_bucket(total_pages) if kdp else "N/A"
    dt_ms = int((time.time() - t0) * 1000)

    lines = []
    lines.append("KDP PREFLIGHT REPORT — EDDIES QUESTBOOK")
    lines.append(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Name: {name!r}")
    lines.append(f"Pages: {total_pages} | KDP: {kdp} | Intro: {intro} | Outro: {outro}")
    lines.append("")
    lines.append("GEOMETRY")
    lines.append(f"- Trim: {TRIM_IN:.3f}in × {TRIM_IN:.3f}in")
    lines.append(f"- Bleed: {(pb.bleed / inch):.3f}in")
    lines.append(f"- Outside safe (from trim): {outside_in:.3f}in")
    lines.append(f"- Inside/gutter class: {bucket} → {gutter_in:.3f}in")
    lines.append("")
    lines.append("GATES")
    lines.append(f"- Min pages: {KDP_MIN_PAGES} → {'OK' if total_pages >= KDP_MIN_PAGES else 'FAIL'}")
    lines.append(f"- Even pages: {'OK' if total_pages % 2 == 0 else 'FAIL'}")
    lines.append(f"- Sample pages checked: {', '.join(str(i+1) for i in sample_idxs) if sample_idxs else 'N/A'}")
    lines.append("")
    lines.append("ISSUES")
    if issues:
        for it in issues:
            lines.append(f"[{it.level}] {it.code}: {it.message}")
    else:
        lines.append("None ✅")
    lines.append("")
    lines.append(f"Decision: {'PASS ✅' if ok else 'FAIL ❌'}")
    lines.append(f"Runtime: {dt_ms}ms")

    return PreflightResult(ok_to_build=ok, issues=issues, report_text="\n".join(lines))


# =========================================================
# 9) GOD MODE: VISUALIZER & KDP HELPER
# =========================================================
def _pt_to_px(pt: float, preview_dpi: int) -> int:
    return int(round((pt / 72.0) * preview_dpi))

def render_page_preview(
    *,
    page_num_1: int,
    total_pages: int,
    kdp: bool,
    pb: PageBox,
    img_bytes: bytes,
    start_hour: int,
    diff: int,
    name: str,
    preview_dpi: int = 120,
    mission_override=None,
) -> Image.Image:
    w_px = _pt_to_px(pb.full_w, preview_dpi)
    h_px = _pt_to_px(pb.full_h, preview_dpi)

    img = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img, "RGBA")

    sk_png = _get_sketch(img_bytes, w_px, h_px)
    sketch = Image.open(io.BytesIO(sk_png)).convert("RGB")
    img.paste(sketch, (0, 0))

    page_index_0 = page_num_1 - 1
    sl, sr, stb = safe_margins_for_page(total_pages, kdp, page_index_0, pb)

    def px(v_pt: float) -> int:
        return _pt_to_px(v_pt, preview_dpi)

    if pb.bleed > 0:
        b = px(pb.bleed)
        draw.rectangle([b, b, w_px - b, h_px - b], outline=(255, 0, 0, 180), width=3)

    safe_rect = [px(sl), px(stb), w_px - px(sr), h_px - px(stb)]
    draw.rectangle(safe_rect, outline=(0, 255, 0, 200), width=3)

    if mission_override is not None:
        mission = mission_override
    else:
        h_val = (start_hour + page_index_0) % 24
        seed = int(_stable_seed(name) ^ (page_index_0 << 1) ^ h_val) & 0x7FFFFFFF
        mission = qd.pick_mission_for_time(h_val, diff, seed)

    header_h = 0.75 * inch
    x0 = sl
    x1 = pb.full_w - sr
    y0 = stb
    y1 = pb.full_h - stb

    # Header box (top safe)
    hx0, hx1 = px(x0), px(x1)
    hy0 = px(stb)
    hy1 = hy0 + px(header_h)
    draw.rectangle([hx0, hy0, hx1, hy1], fill=(0, 80, 255, 50), outline=(0, 80, 255, 220), width=2)

    # Card box (bottom safe)
    max_ch = (y1 - header_h - y0) - (0.15 * inch)
    pad_x = 0.18 * inch
    w_pt = max(1.0, x1 - x0)

    sc = _autoscale_mission_text(mission, w_pt, x0, pad_x, max_ch)
    card_h = min(max_ch, max(1.85 * inch, sc["needed"]))

    cx0, cx1 = px(x0), px(x1)
    cy1 = h_px - px(stb)
    cy0 = cy1 - px(card_h)
    draw.rectangle([cx0, cy0, cx1, cy1], fill=(255, 165, 0, 50), outline=(255, 165, 0, 230), width=2)

    gutter_side = "Gutter links" if (page_num_1 % 2 == 1) else "Gutter rechts"
    draw.text((10, 10), f"Seite {page_num_1}/{total_pages} • {'Odd' if page_num_1%2 else 'Even'} • {gutter_side}", fill=(0, 0, 0, 180))
    return img


def render_kdp_helper(*, pages: int, paper_key: str):
    factor = PAPER_FACTORS.get(paper_key, 0.002252)
    spine_in = max(pages * factor, 0.001)
    spine_mm = spine_in * 25.4

    cover_w_in = (2 * TRIM_IN) + spine_in + (2 * (BLEED / inch))
    cover_h_in = TRIM_IN + (2 * (BLEED / inch))

    is_color = paper_key.startswith("Farbe")
    is_cream = "Creme" in paper_key
    quality = "Premium" if "Premium" in paper_key else ("Standard" if is_color else "B/W")

    st.markdown("#### 📏 KDP Cover Helper")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info(f"**Spine**\n\n`{spine_in:.4f} in`\n\n`{spine_mm:.2f} mm`")
    with c2:
        st.info(f"**Full Cover Size**\n\n`{cover_w_in:.4f} × {cover_h_in:.4f} in`")
    with c3:
        st.info(f"**Paper**\n\n{paper_key}\n\nQuality: `{quality}`")

    interior_type = "Color" if is_color else ("B&W (Cream)" if is_cream else "B&W (White)")
    st.write("**KDP Cover Calculator Inputs (copy/paste):**")
    st.code(
        f"""Binding: Paperback
Interior: {interior_type}
Paper: {"Cream" if is_cream else "White"}
Print: {quality}
Trim: {TRIM_IN:.2f} x {TRIM_IN:.2f} in
Bleed: Bleed
Pages: {pages}
Spine: {spine_in:.4f} in
Full Cover: {cover_w_in:.4f} x {cover_h_in:.4f} in"""
    )
    st.markdown("[👉 Zum KDP Cover Calculator](https://kdp.amazon.com/cover-calculator)")


# =========================================================
# 10) UI & SESSION HANDLING
# =========================================================
st.set_page_config(page_title=APP_TITLE, layout="centered", page_icon=APP_ICON)

if "assets" not in st.session_state:
    st.session_state.assets = None

def _tmp(prefix: str, suffix: str, data: bytes) -> str:
    with tempfile.NamedTemporaryFile(prefix=prefix, suffix=suffix, delete=False) as tf:
        tf.write(data)
        return tf.name

st.markdown(f"<h1 style='text-align:center;'>{APP_TITLE} PLATINUM</h1>", unsafe_allow_html=True)

if qd is None:
    st.error("quest_data.py konnte nicht geladen werden. Fix das zuerst, sonst gibt’s keine Missionen.")
    st.code(_QD_IMPORT_ERROR or "Unbekannter Import-Fehler", language="text")
    st.stop()

with st.container(border=True):
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Name", value="Eddie")
        age = st.number_input("Alter", 3, 99, 5)
        eddie_mark = st.toggle("Eddie-Mark im Interior", False)

    with col2:
        st.session_state.setdefault("pages", KDP_MIN_PAGES)
        pages = st.number_input(
            "Seiten",
            min_value=KDP_MIN_PAGES,
            max_value=300,
            value=int(st.session_state.pages),
            step=2,
            key="pages",
        )
        paper = st.selectbox("Papier", list(PAPER_FACTORS.keys()), key="paper")

    kdp = st.toggle("KDP-Mode (Bleed)", True)
    debug_guides = st.toggle("🧪 PDF Debug Guides (Bleed/Safe)", False)

    uploads = st.file_uploader("Fotos", accept_multiple_files=True, type=["jpg", "png", "jpeg"])

    # ✅ UPLOAD COUNTER (always visible)
    uploads_count = len(uploads) if uploads else 0
    # In deinem Build sind intro/outro fest auf True -> Content-Seiten = pages - 2
    content_pages = max(1, int(pages) - 2)

    if uploads_count > 0:
        st.caption(f"📸 **{uploads_count}** Foto(s) hochgeladen — werden zyklisch auf **{content_pages}** Content-Seiten verteilt.")
    else:
        st.caption("📸 **0** Foto(s) hochgeladen.")

can_build = False

# Difficulty mapping
diff = 1 if age <= 4 else 2 if age <= 6 else 3 if age <= 9 else 4

pf: Optional[PreflightResult] = None

if uploads and name:
    # Smart Cache invalidation (if uploads changed)
    upload_sig = hashlib.sha256(b"".join(up.getvalue()[:2048] for up in uploads)).hexdigest()
    if st.session_state.get("upload_sig") != upload_sig:
        _sketch_cached_by_hash.cache_clear()
        _IMG_STORE.clear()
        st.session_state["upload_sig"] = upload_sig

    pb = page_box(TRIM, TRIM, kdp_bleed=bool(kdp))

    # Run Gatekeeper
    pf = run_kdp_preflight(
        name=name,
        total_pages=int(pages),
        kdp=bool(kdp),
        intro=True,
        outro=True,
        pb=pb,
        uploads=uploads,
        start_hour=6,
        diff=diff,
        eddie_mark=bool(eddie_mark),
        sample_pages=12,
    )

    with st.expander("🛡️ KDP Preflight Gatekeeper", expanded=True):
        st.write(f"**Status:** {'✅ PASS' if pf.ok_to_build else '❌ FAIL'}")
        if bool(kdp):
            st.caption(f"Gutter: {_gutter_bucket(int(pages))} → {_kdp_inside_gutter_in(int(pages)):.3f}\" | Outside safe: 0.375\" (strict)")
        else:
            st.caption("KDP aus: symmetrische SAFE_INTERIOR-Margins.")

        if pf.issues:
            for it in pf.issues:
                if it.level == "ERROR":
                    st.error(f"{it.code}: {it.message}")
                elif it.level == "WARN":
                    st.warning(f"{it.code}: {it.message}")
                else:
                    st.info(f"{it.code}: {it.message}")
        else:
            st.success("Keine Findings.")

        st.download_button(
            "⬇️ Preflight Report (txt)",
            data=pf.report_text.encode("utf-8"),
            file_name=f"Preflight_{name}_{int(pages)}p.txt",
            mime="text/plain",
        )

    can_build = pf.ok_to_build

    # GOD MODE Visualizer
    with st.expander("👁️ Layout-Röntgenblick (Visualizer)", expanded=False):
        st.caption("Grün = Safe • Rot = Trim • Blau = Header • Orange = Mission-Card")
        preview_dpi = st.slider("Preview-DPI", 80, 200, 120, 10)
        v_page = st.slider("Seite prüfen", 1, int(pages), min(2, int(pages)))

        intro_pages = 1
        outro_pages = 1
        content_start = 1 + intro_pages
        content_end = int(pages) - outro_pages

        if content_start <= v_page <= content_end:
            content_idx_0 = v_page - content_start
            up_idx = content_idx_0 % len(uploads)
            b_data = uploads[up_idx].getvalue()

            prev_img = render_page_preview(
                page_num_1=int(v_page),
                total_pages=int(pages),
                kdp=bool(kdp),
                pb=pb,
                img_bytes=b_data,
                start_hour=6,
                diff=diff,
                name=name,
                preview_dpi=int(preview_dpi),
            )
            st.image(
                prev_img,
                caption=f"Seite {v_page} ({'Rechts/Ungerade' if v_page % 2 else 'Links/Gerade'})",
                use_container_width=True,
            )
        else:
            st.info("Intro/Outro werden hier nicht gerendert (Visualizer zeigt nur Content-Layout).")

    # KDP Helper
    with st.expander("📏 KDP Template Daten", expanded=False):
        render_kdp_helper(pages=int(pages), paper_key=paper)

# Build Button
if st.button("🚀 Buch generieren", disabled=not can_build):
    with st.spinner("AUTO-SCALE & PDF-Hardening (Cached)..."):
        int_pdf = build_interior(
            name=name,
            uploads=uploads,
            total_pages=int(pages),
            eddie_mark=bool(eddie_mark),
            kdp=bool(kdp),
            intro=True,
            outro=True,
            start_hour=6,
            diff=diff,
            debug_guides=bool(debug_guides),
        )

        cov_pdf = build_cover(
            name=name,
            pages=int(pages),
            paper=paper,
        )

        listing_txt = build_listing_text(name)

        # Cleanup old temp assets
        if st.session_state.assets:
            for f in st.session_state.assets.values():
                if isinstance(f, str) and os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

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

import os
import time
import tempfile
import hashlib
import functools
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from collections import OrderedDict

import streamlit as st
import cv2
import numpy as np
from PIL import Image, ImageDraw

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth


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
# 1) CONFIG & COLORS
# =========================================================
APP_TITLE = "Eddies"
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
DEBUG_LINE_W = 0.4

PAPER_FACTORS = {
    "Schwarzweiß – Weiß": 0.002252,
    "Schwarzweiß – Creme": 0.0025,
    "Farbe – Weiß (Standard)": 0.002252,
    "Farbe – Weiß (Premium)": 0.002347,
}
SPINE_TEXT_MIN_PAGES = 79
KDP_MIN_PAGES = 24


# =========================================================
# 2) PAGE GEOMETRY (PageBox Pattern)
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
    # KDP gutter chart (inside margin depends on page count)
    if pages <= 150:
        return 0.375
    if pages <= 300:
        return 0.500
    if pages <= 500:
        return 0.625
    if pages <= 700:
        return 0.750
    return 0.875  # 701–828


def safe_margins_for_page(
    pages: int,
    kdp: bool,
    page_index_0: int,
    pb: PageBox,
) -> tuple[float, float, float]:
    """
    returns (safe_left, safe_right, safe_tb) in points
    - safe_tb applies to both top and bottom
    - safe_left/right are mirrored for facing pages when kdp=True
    """
    if not kdp:
        s = SAFE_INTERIOR
        return s, s, s

    outside = pb.bleed + (0.375 * inch)
    safe_tb = pb.bleed + (0.375 * inch)
    gutter = pb.bleed + (_kdp_inside_gutter_in(pages) * inch)

    # odd pages are right-hand pages -> gutter on left
    is_odd = ((page_index_0 + 1) % 2 == 1)
    safe_left = gutter if is_odd else outside
    safe_right = outside if is_odd else gutter
    return safe_left, safe_right, safe_tb


# =========================================================
# 3) FONT & TEXT HELPERS
# =========================================================
def _try_register_fonts() -> Dict[str, str]:
    normal_p = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    bold_p = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    if os.path.exists(normal_p):
        try:
            pdfmetrics.registerFont(TTFont("EDDIES_FONT", normal_p))
        except Exception:
            pass
    if os.path.exists(bold_p):
        try:
            pdfmetrics.registerFont(TTFont("EDDIES_FONT_BOLD", bold_p))
        except Exception:
            pass

    f_n = "EDDIES_FONT" if "EDDIES_FONT" in pdfmetrics.getRegisteredFontNames() else "Helvetica"
    f_b = "EDDIES_FONT_BOLD" if "EDDIES_FONT_BOLD" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold"
    return {"normal": f_n, "bold": f_b}


FONTS = _try_register_fonts()


def _set_font(c: canvas.Canvas, bold: bool, size: int, leading: Optional[float] = None) -> float:
    font_name = FONTS["bold"] if bold else FONTS["normal"]
    c.setFont(font_name, size)
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

        needed = (
            base_top
            + tl
            + gap_title
            + (ll * 2)
            + ((len(ml) + len(tl_lines)) * bl)
            + gap_sections
            + base_bottom
        )
        return {"ts": ts, "bs": bs, "ls": ls, "tl": tl, "bl": bl, "ll": ll, "ml": ml, "tl_lines": tl_lines, "needed": needed}

    ts, bs, ls = 13, 10, 10
    sc = compute(ts, bs, ls)

    while sc["needed"] > max_card_h and (ts > 11 or bs > 8 or ls > 8):
        if ts > 11:
            ts -= 1
        if bs > 8:
            bs -= 1
        if ls > 8:
            ls -= 1
        sc = compute(ts, bs, ls)

    if sc["needed"] > max_card_h:
        rem = max_card_h - (base_top + sc["tl"] + gap_title + (sc["ll"] * 2) + gap_sections + base_bottom)
        max_b = max(2, int(rem // sc["bl"]))
        move_allow = max(1, max_b // 2)
        think_allow = max(1, max_b - move_allow)

        sc["ml"] = _fit_lines(sc["ml"], move_allow)
        sc["tl_lines"] = _fit_lines(sc["tl_lines"], think_allow)

        sc["needed"] = (
            base_top
            + sc["tl"]
            + gap_title
            + (sc["ll"] * 2)
            + ((len(sc["ml"]) + len(sc["tl_lines"])) * sc["bl"])
            + gap_sections
            + base_bottom
        )

    return sc


def _stable_seed(s: str) -> int:
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:8], "big")


# =========================================================
# 4) SKETCH ENGINE (TRUE HASH-KEY CACHE + 1-BIT)
# =========================================================
_IMG_STORE_MAX = 256
_IMG_STORE: "OrderedDict[str, bytes]" = OrderedDict()

def _img_store_put(img_hash: str, img_bytes: bytes) -> None:
    # LRU store for original bytes (hash->bytes)
    if img_hash in _IMG_STORE:
        _IMG_STORE.move_to_end(img_hash)
        return
    _IMG_STORE[img_hash] = img_bytes
    _IMG_STORE.move_to_end(img_hash)
    while len(_IMG_STORE) > _IMG_STORE_MAX:
        _IMG_STORE.popitem(last=False)

def _img_store_get(img_hash: str) -> bytes:
    b = _IMG_STORE.get(img_hash)
    if b is None:
        raise KeyError("img_hash not in store")
    _IMG_STORE.move_to_end(img_hash)
    return b


@functools.lru_cache(maxsize=256)
def _sketch_cached_by_hash(img_hash: str, target_w: int, target_h: int) -> bytes:
    img_bytes = _img_store_get(img_hash)

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
    return out.getvalue()


def _get_sketch(img_bytes: bytes, target_w: int, target_h: int) -> bytes:
    h = hashlib.sha256(img_bytes).hexdigest()
    _img_store_put(h, img_bytes)
    return _sketch_cached_by_hash(h, target_w, target_h)


# =========================================================
# 5) PDF DEBUG GUIDES
# =========================================================
def _draw_kdp_debug_guides(c: canvas.Canvas, pb: PageBox, safe_l: float, safe_r: float, safe_tb: float):
    c.saveState()
    c.setLineWidth(DEBUG_LINE_W)
    c.setDash(3, 3)

    if pb.bleed > 0:
        c.setStrokeColor(DEBUG_BLEED_COLOR)
        c.rect(pb.bleed, pb.bleed, pb.full_w - 2 * pb.bleed, pb.full_h - 2 * pb.bleed, stroke=1, fill=0)

    c.setStrokeColor(DEBUG_SAFE_COLOR)
    c.rect(safe_l, safe_tb, pb.full_w - safe_l - safe_r, pb.full_h - 2 * safe_tb, stroke=1, fill=0)

    c.setDash()
    c.restoreState()


# =========================================================
# 6) DYNAMIC OVERLAY (MIRROR MARGINS)
# =========================================================
def _draw_quest_overlay(
    c: canvas.Canvas,
    pb: PageBox,
    safe_left: float,
    safe_right: float,
    safe_tb: float,
    hour: int,
    mission,
    debug: bool,
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

    # Header
    c.setFillColor(fill)
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(1)
    c.rect(x0, y_header_bottom, w, header_h, fill=1, stroke=1)

    c.setFillColor(tc)
    _set_font(c, True, 14)
    c.drawString(x0 + 0.18 * inch, y_header_bottom + header_h - 0.50 * inch, f"{qd.fmt_hour(hour)}  {zone.icon}  {zone.name}")
    _set_font(c, False, 10)
    c.drawString(x0 + 0.18 * inch, y_header_bottom + 0.18 * inch, f"{zone.quest_type} • {zone.atmosphere}")

    # Card
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
# 7) PDF BUILDERS
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


def build_interior(
    name: str,
    uploads,
    total_pages: int,
    eddie_mark: bool,
    kdp: bool,
    intro: bool,
    outro: bool,
    start_hour: int,
    diff: int,
    debug_guides: bool,
) -> bytes:
    pb = page_box(TRIM, TRIM, kdp_bleed=kdp)

    files = list(uploads or [])
    if not files:
        raise RuntimeError("Keine Bilder hochgeladen.")

    photo_count = max(1, total_pages - (int(intro) + int(outro)))
    final = (files * (photo_count // len(files) + 1))[:photo_count]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pb.full_w, pb.full_h))

    seed_base = _stable_seed(name)
    current_page_idx = 0  # 0-based for safe mirroring

    # INTRO
    if intro:
        sl, sr, stb = safe_margins_for_page(total_pages, kdp, current_page_idx, pb)

        c.setFillColor(colors.white)
        c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)

        c.setFillColor(INK_BLACK)
        _set_font(c, True, 34)
        c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 0.65 * inch, "Willkommen bei Eddies")
        _set_font(c, False, 22)
        c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 1.25 * inch, f"& {name}")
        _draw_eddie(c, pb.full_w / 2, pb.full_h / 2, 1.3 * inch)

        _set_font(c, False, 14)
        c.setFillColor(INK_GRAY_70)
        c.drawCentredString(pb.full_w / 2, stb + 0.75 * inch, "24 Stunden • 24 Missionen • Haken setzen")

        if debug_guides:
            _draw_kdp_debug_guides(c, pb, sl, sr, stb)

        c.showPage()
        current_page_idx += 1

    # CONTENT
    target_w = int(pb.full_w * DPI / inch)
    target_h = int(pb.full_h * DPI / inch)

    for i, up in enumerate(final):
        sl, sr, stb = safe_margins_for_page(total_pages, kdp, current_page_idx, pb)

        img_data = up.getvalue()
        png_bytes = _get_sketch(img_data, target_w, target_h)
        c.drawImage(ImageReader(io.BytesIO(png_bytes)), 0, 0, pb.full_w, pb.full_h)

        h_val = (start_hour + i) % 24
        seed = int(seed_base ^ (i << 1) ^ h_val) & 0x7FFFFFFF
        mission = qd.pick_mission_for_time(h_val, diff, seed)

        _draw_quest_overlay(c, pb, sl, sr, stb, h_val, mission, debug=debug_guides)

        if eddie_mark:
            # safe-center placement (never crosses safe)
            r = 0.18 * inch
            cx = (pb.full_w - sr) - r
            cy = (stb + 2.25 * inch) + r
            _draw_eddie(c, cx, cy, r)

        c.showPage()
        current_page_idx += 1

    # OUTRO
    if outro:
        sl, sr, stb = safe_margins_for_page(total_pages, kdp, current_page_idx, pb)

        c.setFillColor(colors.white)
        c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)

        _draw_eddie(c, pb.full_w / 2, pb.full_h / 2 + 0.6 * inch, 1.5 * inch)
        c.setFillColor(INK_BLACK)
        _set_font(c, True, 30)
        c.drawCentredString(pb.full_w / 2, stb + 1.75 * inch, "Quest abgeschlossen!")

        if debug_guides:
            _draw_kdp_debug_guides(c, pb, sl, sr, stb)

        c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()


def build_cover(name: str, pages: int, paper: str) -> bytes:
    sw = float(pages) * PAPER_FACTORS.get(paper, 0.002252) * inch
    sw = max(sw, 0.001 * inch)
    sw = round(sw / (0.001 * inch)) * (0.001 * inch)

    cw = (2 * TRIM) + sw + (2 * BLEED)
    ch = TRIM + (2 * BLEED)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(cw, ch))

    c.setFillColor(colors.white)
    c.rect(0, 0, cw, ch, fill=1, stroke=0)

    # Spine block
    c.setFillColor(INK_BLACK)
    c.rect(BLEED + TRIM, BLEED, sw, TRIM, fill=1, stroke=0)

    # Spine text
    if pages >= SPINE_TEXT_MIN_PAGES:
        c.saveState()
        c.setFillColor(colors.white)
        _set_font(c, True, 10)
        c.translate(BLEED + TRIM + sw / 2, BLEED + TRIM / 2)
        c.rotate(90)
        c.drawCentredString(0, -4, f"EDDIES & {name}".upper())
        c.restoreState()

    # Front cover start x
    fx = BLEED + TRIM + sw

    _draw_eddie(c, fx + TRIM / 2, BLEED + TRIM * 0.58, TRIM * 0.18)

    c.setFillColor(INK_BLACK)
    _set_font(c, True, 44)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.80, "EDDIES")
    _set_font(c, False, 18)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.73, f"& {name}")

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
  <li><b>Druckoptimiert:</b> 300 DPI Layout, klare Schwarzwerte, saubere Ränder.</li>
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
# 8) KDP PREFLIGHT GATEKEEPER
# =========================================================
@dataclass(frozen=True)
class PreflightIssue:
    level: str  # "ERROR"|"WARN"|"INFO"
    code: str
    message: str

@dataclass(frozen=True)
class PreflightResult:
    ok_to_build: bool
    issues: List[PreflightIssue]
    report_text: str

def _gutter_bucket(pages: int) -> str:
    if pages <= 150:
        return "≤150"
    if pages <= 300:
        return "151–300"
    if pages <= 500:
        return "301–500"
    if pages <= 700:
        return "501–700"
    return "701–828"

def _within(a0: float, a1: float, b0: float, b1: float, eps: float = 0.5) -> bool:
    return (a0 + eps) >= b0 and (a1 - eps) <= b1

def _rect_inside_safe(rect: Tuple[float, float, float, float], safe: Tuple[float, float, float, float], eps: float = 0.5) -> bool:
    x0, y0, x1, y1 = rect
    sx0, sy0, sx1, sy1 = safe
    return _within(x0, x1, sx0, sx1, eps=eps) and _within(y0, y1, sy0, sy1, eps=eps)

def _overlay_boxes_for_page(pb: PageBox, safe_left: float, safe_right: float, safe_tb: float, mission=None) -> Dict[str, Tuple[float, float, float, float]]:
    x0 = safe_left
    x1 = pb.full_w - safe_right
    y0 = safe_tb
    y1 = pb.full_h - safe_tb

    header_h = 0.75 * inch
    header = (x0, y1 - header_h, x1, y1)

    max_ch = (y1 - header_h - y0) - (0.15 * inch)

    if mission is None or max_ch <= 1:
        card_h = min(max_ch, 1.85 * inch) if max_ch > 0 else 0
    else:
        pad_x = 0.18 * inch
        w = max(1.0, x1 - x0)
        sc = _autoscale_mission_text(mission, w, x0, pad_x, max_ch)
        card_h = min(max_ch, max(1.85 * inch, sc["needed"]))

    card = (x0, y0, x1, y0 + max(0.0, card_h))
    safe = (x0, y0, x1, y1)
    return {"safe": safe, "header": header, "card": card}

def run_kdp_preflight(
    *,
    name: str,
    total_pages: int,
    kdp: bool,
    intro: bool,
    outro: bool,
    pb: PageBox,
    uploads: Optional[list],
    start_hour: int,
    diff: int,
    eddie_mark: bool,
    sample_pages: int = 12,
) -> PreflightResult:
    t0 = time.time()
    issues: List[PreflightIssue] = []

    # Hard gates
    if kdp:
        if total_pages < KDP_MIN_PAGES:
            issues.append(PreflightIssue("ERROR", "KDP_MIN_PAGES", f"KDP min {KDP_MIN_PAGES} Seiten. Aktuell: {total_pages}."))
        if total_pages % 2 != 0:
            issues.append(PreflightIssue("ERROR", "EVEN_PAGES", f"KDP braucht gerade Seitenzahl. Aktuell: {total_pages}."))

    # Fair trim-based res check
    if uploads:
        target_px = int(TRIM_IN * DPI)
        low = []
        for up in uploads:
            try:
                data = up.getvalue()
                with Image.open(io.BytesIO(data)) as img:
                    w, h = img.size
                if min(w, h) < target_px:
                    low.append((up.name, w, h))
            except Exception:
                issues.append(PreflightIssue("WARN", "IMAGE_READ_FAIL", f"Konnte Bild nicht prüfen: {getattr(up,'name','(unknown)')}"))
        if low:
            issues.append(PreflightIssue("WARN", "LOW_RES_UPLOADS", f"{len(low)} Foto(s) < {target_px}px (Trim @300DPI)."))

    # Sample pages
    if total_pages > 0:
        picks = {0, 1, total_pages // 2, max(0, total_pages // 2 - 1), total_pages - 1, max(0, total_pages - 2)}
        if total_pages > 8:
            step = max(1, total_pages // max(1, (sample_pages - len(picks))))
            for idx in range(0, total_pages, step):
                picks.add(idx)
                if len(picks) >= sample_pages:
                    break
        sample_idxs = sorted(picks)[:sample_pages]
    else:
        sample_idxs = []

    def mission_for_sample(page_idx_0: int):
        if qd is None:
            return None
        h_val = (start_hour + page_idx_0) % 24
        seed_base = _stable_seed(name)
        seed = int(seed_base ^ (page_idx_0 << 1) ^ h_val) & 0x7FFFFFFF
        try:
            return qd.pick_mission_for_time(h_val, diff, seed)
        except Exception:
            return None

    eps = 0.5
    for pidx in sample_idxs:
        sl, sr, stb = safe_margins_for_page(total_pages, kdp, pidx, pb)
        boxes = _overlay_boxes_for_page(pb, sl, sr, stb, mission=mission_for_sample(pidx))
        safe_box = boxes["safe"]

        if not _rect_inside_safe(boxes["header"], safe_box, eps=eps):
            issues.append(PreflightIssue("ERROR", "OVERLAY_HEADER_UNSAFE", f"Header verlässt Safe auf Seite {pidx+1}."))
        if not _rect_inside_safe(boxes["card"], safe_box, eps=eps):
            issues.append(PreflightIssue("ERROR", "OVERLAY_CARD_UNSAFE", f"Card verlässt Safe auf Seite {pidx+1}."))

        if eddie_mark:
            r = 0.18 * inch
            cx = (pb.full_w - sr) - r
            cy = (stb + 2.25 * inch) + r
            eddie_rect = (cx - r, cy - r, cx + r, cy + r)
            if not _rect_inside_safe(eddie_rect, safe_box, eps=eps):
                issues.append(PreflightIssue("ERROR", "EDDIE_MARK_UNSAFE", f"Eddie-Mark verlässt Safe auf Seite {pidx+1}."))

        sx0, sy0, sx1, sy1 = safe_box
        if (sx1 - sx0) <= (1.0 * inch) or (sy1 - sy0) <= (1.0 * inch):
            issues.append(PreflightIssue("ERROR", "SAFE_BOX_TOO_SMALL", f"Safe-Box wirkt zu klein (Seite {pidx+1})."))

    has_error = any(i.level == "ERROR" for i in issues)
    ok = not has_error

    gutter_in = _kdp_inside_gutter_in(total_pages) if kdp else (SAFE_INTERIOR / inch)
    outside_in = 0.375 if kdp else (SAFE_INTERIOR / inch)
    bucket = _gutter_bucket(total_pages) if kdp else "N/A"
    dt_ms = int((time.time() - t0) * 1000)

    lines = []
    lines.append("KDP PREFLIGHT REPORT — EDDIES QUESTBOOK")
    lines.append(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Name: {name!r}")
    lines.append(f"Pages: {total_pages} | KDP: {kdp} | Intro: {intro} | Outro: {outro}")
    lines.append("")
    lines.append("GEOMETRY")
    lines.append(f"- Trim: {TRIM_IN:.3f}in × {TRIM_IN:.3f}in")
    lines.append(f"- Bleed: {(pb.bleed / inch):.3f}in")
    lines.append(f"- Outside safe (from trim): {outside_in:.3f}in")
    lines.append(f"- Inside/gutter class: {bucket} → {gutter_in:.3f}in")
    lines.append("")
    lines.append("GATES")
    lines.append(f"- Min pages: {KDP_MIN_PAGES} → {'OK' if total_pages >= KDP_MIN_PAGES else 'FAIL'}")
    lines.append(f"- Even pages: {'OK' if total_pages % 2 == 0 else 'FAIL'}")
    lines.append(f"- Sample pages checked: {', '.join(str(i+1) for i in sample_idxs) if sample_idxs else 'N/A'}")
    lines.append("")
    lines.append("ISSUES")
    if issues:
        for it in issues:
            lines.append(f"[{it.level}] {it.code}: {it.message}")
    else:
        lines.append("None ✅")
    lines.append("")
    lines.append(f"Decision: {'PASS ✅' if ok else 'FAIL ❌'}")
    lines.append(f"Runtime: {dt_ms}ms")

    return PreflightResult(ok_to_build=ok, issues=issues, report_text="\n".join(lines))


# =========================================================
# 9) GOD MODE: VISUALIZER & KDP HELPER
# =========================================================
def _pt_to_px(pt: float, preview_dpi: int) -> int:
    return int(round((pt / 72.0) * preview_dpi))

def render_page_preview(
    *,
    page_num_1: int,
    total_pages: int,
    kdp: bool,
    pb: PageBox,
    img_bytes: bytes,
    start_hour: int,
    diff: int,
    name: str,
    preview_dpi: int = 120,
    mission_override=None,
) -> Image.Image:
    w_px = _pt_to_px(pb.full_w, preview_dpi)
    h_px = _pt_to_px(pb.full_h, preview_dpi)

    img = Image.new("RGB", (w_px, h_px), "white")
    draw = ImageDraw.Draw(img, "RGBA")

    sk_png = _get_sketch(img_bytes, w_px, h_px)
    sketch = Image.open(io.BytesIO(sk_png)).convert("RGB")
    img.paste(sketch, (0, 0))

    page_index_0 = page_num_1 - 1
    sl, sr, stb = safe_margins_for_page(total_pages, kdp, page_index_0, pb)

    def px(v_pt: float) -> int:
        return _pt_to_px(v_pt, preview_dpi)

    if pb.bleed > 0:
        b = px(pb.bleed)
        draw.rectangle([b, b, w_px - b, h_px - b], outline=(255, 0, 0, 180), width=3)

    safe_rect = [px(sl), px(stb), w_px - px(sr), h_px - px(stb)]
    draw.rectangle(safe_rect, outline=(0, 255, 0, 200), width=3)

    if mission_override is not None:
        mission = mission_override
    else:
        h_val = (start_hour + page_index_0) % 24
        seed = int(_stable_seed(name) ^ (page_index_0 << 1) ^ h_val) & 0x7FFFFFFF
        mission = qd.pick_mission_for_time(h_val, diff, seed)

    header_h = 0.75 * inch
    x0 = sl
    x1 = pb.full_w - sr
    y0 = stb
    y1 = pb.full_h - stb

    # Header box (top safe)
    hx0, hx1 = px(x0), px(x1)
    hy0 = px(stb)
    hy1 = hy0 + px(header_h)
    draw.rectangle([hx0, hy0, hx1, hy1], fill=(0, 80, 255, 50), outline=(0, 80, 255, 220), width=2)

    # Card box (bottom safe)
    max_ch = (y1 - header_h - y0) - (0.15 * inch)
    pad_x = 0.18 * inch
    w_pt = max(1.0, x1 - x0)

    sc = _autoscale_mission_text(mission, w_pt, x0, pad_x, max_ch)
    card_h = min(max_ch, max(1.85 * inch, sc["needed"]))

    cx0, cx1 = px(x0), px(x1)
    cy1 = h_px - px(stb)
    cy0 = cy1 - px(card_h)
    draw.rectangle([cx0, cy0, cx1, cy1], fill=(255, 165, 0, 50), outline=(255, 165, 0, 230), width=2)

    gutter_side = "Gutter links" if (page_num_1 % 2 == 1) else "Gutter rechts"
    draw.text((10, 10), f"Seite {page_num_1}/{total_pages} • {'Odd' if page_num_1%2 else 'Even'} • {gutter_side}", fill=(0, 0, 0, 180))
    return img


def render_kdp_helper(*, pages: int, paper_key: str):
    factor = PAPER_FACTORS.get(paper_key, 0.002252)
    spine_in = max(pages * factor, 0.001)
    spine_mm = spine_in * 25.4

    cover_w_in = (2 * TRIM_IN) + spine_in + (2 * (BLEED / inch))
    cover_h_in = TRIM_IN + (2 * (BLEED / inch))

    is_color = paper_key.startswith("Farbe")
    is_cream = "Creme" in paper_key
    quality = "Premium" if "Premium" in paper_key else ("Standard" if is_color else "B/W")

    st.markdown("#### 📏 KDP Cover Helper")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.info(f"**Spine**\n\n`{spine_in:.4f} in`\n\n`{spine_mm:.2f} mm`")
    with c2:
        st.info(f"**Full Cover Size**\n\n`{cover_w_in:.4f} × {cover_h_in:.4f} in`")
    with c3:
        st.info(f"**Paper**\n\n{paper_key}\n\nQuality: `{quality}`")

    interior_type = "Color" if is_color else ("B&W (Cream)" if is_cream else "B&W (White)")
    st.write("**KDP Cover Calculator Inputs (copy/paste):**")
    st.code(
        f"""Binding: Paperback
Interior: {interior_type}
Paper: {"Cream" if is_cream else "White"}
Print: {quality}
Trim: {TRIM_IN:.2f} x {TRIM_IN:.2f} in
Bleed: Bleed
Pages: {pages}
Spine: {spine_in:.4f} in
Full Cover: {cover_w_in:.4f} x {cover_h_in:.4f} in"""
    )
    st.markdown("[👉 Zum KDP Cover Calculator](https://kdp.amazon.com/cover-calculator)")


# =========================================================
# 10) UI & SESSION HANDLING
# =========================================================
st.set_page_config(page_title=APP_TITLE, layout="centered", page_icon=APP_ICON)

if "assets" not in st.session_state:
    st.session_state.assets = None

def _tmp(prefix: str, suffix: str, data: bytes) -> str:
    with tempfile.NamedTemporaryFile(prefix=prefix, suffix=suffix, delete=False) as tf:
        tf.write(data)
        return tf.name

st.markdown(f"<h1 style='text-align:center;'>{APP_TITLE} PLATINUM</h1>", unsafe_allow_html=True)

if qd is None:
    st.error("quest_data.py konnte nicht geladen werden. Fix das zuerst, sonst gibt’s keine Missionen.")
    st.code(_QD_IMPORT_ERROR or "Unbekannter Import-Fehler", language="text")
    st.stop()

with st.container(border=True):
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Name", value="Eddie")
        age = st.number_input("Alter", 3, 99, 5)
        eddie_mark = st.toggle("Eddie-Mark im Interior", False)

    with col2:
        st.session_state.setdefault("pages", KDP_MIN_PAGES)
        pages = st.number_input(
            "Seiten",
            min_value=KDP_MIN_PAGES,
            max_value=300,
            value=int(st.session_state.pages),
            step=2,
            key="pages",
        )
        paper = st.selectbox("Papier", list(PAPER_FACTORS.keys()), key="paper")

    kdp = st.toggle("KDP-Mode (Bleed)", True)
    debug_guides = st.toggle("🧪 PDF Debug Guides (Bleed/Safe)", False)
    uploads = st.file_uploader("Fotos", accept_multiple_files=True, type=["jpg", "png", "jpeg"])

can_build = False
override_res = False

# Difficulty mapping
diff = 1 if age <= 4 else 2 if age <= 6 else 3 if age <= 9 else 4

pf: Optional[PreflightResult] = None

if uploads and name:
    # Smart Cache invalidation (if uploads changed)
    upload_sig = hashlib.sha256(b"".join(up.getvalue()[:2048] for up in uploads)).hexdigest()
    if st.session_state.get("upload_sig") != upload_sig:
        _sketch_cached_by_hash.cache_clear()
        _IMG_STORE.clear()
        st.session_state["upload_sig"] = upload_sig

    pb = page_box(TRIM, TRIM, kdp_bleed=bool(kdp))

    # Run Gatekeeper
    pf = run_kdp_preflight(
        name=name,
        total_pages=int(pages),
        kdp=bool(kdp),
        intro=True,
        outro=True,
        pb=pb,
        uploads=uploads,
        start_hour=6,
        diff=diff,
        eddie_mark=bool(eddie_mark),
        sample_pages=12,
    )

    with st.expander("🛡️ KDP Preflight Gatekeeper", expanded=True):
        st.write(f"**Status:** {'✅ PASS' if pf.ok_to_build else '❌ FAIL'}")
        if bool(kdp):
            st.caption(f"Gutter: {_gutter_bucket(int(pages))} → {_kdp_inside_gutter_in(int(pages)):.3f}\" | Outside safe: 0.375\" (strict)")
        else:
            st.caption("KDP aus: symmetrische SAFE_INTERIOR-Margins.")

        if pf.issues:
            for it in pf.issues:
                if it.level == "ERROR":
                    st.error(f"{it.code}: {it.message}")
                elif it.level == "WARN":
                    st.warning(f"{it.code}: {it.message}")
                else:
                    st.info(f"{it.code}: {it.message}")
        else:
            st.success("Keine Findings.")

        st.download_button(
            "⬇️ Preflight Report (txt)",
            data=pf.report_text.encode("utf-8"),
            file_name=f"Preflight_{name}_{int(pages)}p.txt",
            mime="text/plain",
        )

    # Separate resolution override gate (warns are allowed; but user can still override low-res warnings)
    # pf.ok_to_build blocks only on ERROR, not on WARN.
    # If they want to override WARN -> build anyway, that's already allowed by ok_to_build.
    # If they want to build even with ERROR (not recommended), we keep it blocked.
    can_build = pf.ok_to_build

    # GOD MODE Visualizer
    with st.expander("👁️ Layout-Röntgenblick (Visualizer)", expanded=False):
        st.caption("Grün = Safe • Rot = Trim • Blau = Header • Orange = Mission-Card")
        preview_dpi = st.slider("Preview-DPI", 80, 200, 120, 10)
        v_page = st.slider("Seite prüfen", 1, int(pages), min(2, int(pages)))

        intro_pages = 1
        outro_pages = 1
        content_start = 1 + intro_pages
        content_end = int(pages) - outro_pages

        if content_start <= v_page <= content_end:
            content_idx_0 = v_page - content_start
            up_idx = content_idx_0 % len(uploads)
            b_data = uploads[up_idx].getvalue()

            prev_img = render_page_preview(
                page_num_1=int(v_page),
                total_pages=int(pages),
                kdp=bool(kdp),
                pb=pb,
                img_bytes=b_data,
                start_hour=6,
                diff=diff,
                name=name,
                preview_dpi=int(preview_dpi),
            )
            st.image(
                prev_img,
                caption=f"Seite {v_page} ({'Rechts/Ungerade' if v_page % 2 else 'Links/Gerade'})",
                use_container_width=True,
            )
        else:
            st.info("Intro/Outro werden hier nicht gerendert (Visualizer zeigt nur Content-Layout).")

    # KDP Helper
    with st.expander("📏 KDP Template Daten", expanded=False):
        render_kdp_helper(pages=int(pages), paper_key=paper)

# Build Button
if st.button("🚀 Buch generieren", disabled=not can_build):
    with st.spinner("AUTO-SCALE & PDF-Hardening (Cached)..."):
        int_pdf = build_interior(
            name=name,
            uploads=uploads,
            total_pages=int(pages),
            eddie_mark=bool(eddie_mark),
            kdp=bool(kdp),
            intro=True,
            outro=True,
            start_hour=6,
            diff=diff,
            debug_guides=bool(debug_guides),
        )

        cov_pdf = build_cover(
            name=name,
            pages=int(pages),
            paper=paper,
        )

        listing_txt = build_listing_text(name)

        # Cleanup old temp assets
        if st.session_state.assets:
            for f in st.session_state.assets.values():
                if isinstance(f, str) and os.path.exists(f):
                    try:
                        os.remove(f)
                    except Exception:
                        pass

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
