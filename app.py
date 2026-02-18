# =========================================================
# app.py (Eddies Questbook Edition) — ENTERPRISE (v5.0)
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

# Change this string when you want a visible build marker:
BUILD_TAG = "v5.0-enterprise"


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
    if pages <= 150:
        return 0.375
    if pages <= 300:
        return 0.500
    if pages <= 500:
        return 0.625
    if pages <= 700:
        return 0.750
    return 0.875  # 701-828


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


def safe_margins_for_page(pages: int, kdp: bool, page_index_0: int, pb: PageBox) -> tuple[float, float, float]:
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

    is_odd = ((page_index_0 + 1) % 2 == 1)  # odd page number

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

    def compute(ts, bs, ls):
        tl, bl, ll = ts * 1.22, bs * 1.28, ls * 1.22
        ml = _wrap_text_hard(mission.movement, FONTS["normal"], bs, body_max_w_move)
        tl_lines = _wrap_text_hard(mission.thinking, FONTS["normal"], bs, body_max_w_think)
        needed = base_top + tl + gap_title + (ll * 2) + ((len(ml) + len(tl_lines)) * bl) + gap_sections + base_bottom
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
        sc["needed"] = base_top + sc["tl"] + gap_title + (sc["ll"] * 2) + ((len(sc["ml"]) + len(sc["tl_lines"])) * sc["bl"]) + gap_sections + base_bottom

    return sc


def _stable_seed(s: str) -> int:
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:8], "big")


# =========================================================
# 4) SKETCH ENGINE (HASH CACHED 1-BIT + RAM Safety)
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

    # 1-bit look (KDP-friendly)
    pil_1bit = pil.point(lambda p: 255 if p > 200 else 0).convert("1")

    out = io.BytesIO()
    pil_1bit.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _get_sketch(img_bytes: bytes, target_w: int, target_h: int) -> bytes:
    h = hashlib.sha256(img_bytes).hexdigest()
    _img_store_put(h, img_bytes)
    return _sketch_cached_by_hash(h, target_w, target_h)


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
# 5) DYNAMIC OVERLAY (MIRROR MARGINS)
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
# 6) BUILDERS
# =========================================================
def build_interior(
    *,
    name: str,
    uploads,
    pages: int,
    kdp: bool,
    intro: bool,
    outro: bool,
    start_hour: int,
    diff: int,
    debug_guides: bool,
    eddie_guide: bool,
) -> bytes:
    if qd is None:
        raise RuntimeError("quest_data.py fehlt oder lädt nicht.")

    if pages < KDP_MIN_PAGES:
        raise RuntimeError(f"Min {KDP_MIN_PAGES} Seiten.")

    if pages % 2 != 0:
        pages += 1

    pb = page_box(TRIM, TRIM, kdp_bleed=bool(kdp))
    target_w = int(round(pb.full_w * DPI / 72.0))
    target_h = int(round(pb.full_h * DPI / 72.0))

    files = list(uploads or [])
    if not files:
        raise RuntimeError("Keine Bilder hochgeladen.")

    photo_count = max(1, pages - (int(intro) + int(outro)))
    final = (files * (photo_count // len(files) + 1))[:photo_count]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pb.full_w, pb.full_h))

    seed_base = _stable_seed(name)

    # Intro
    if intro:
        sl, sr, stb = safe_margins_for_page(pages, bool(kdp), 0, pb)
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

    # Pages
    for i, up in enumerate(final):
        page_idx_0 = i + (1 if intro else 0)  # in-book index for margin mirroring

        sl, sr, stb = safe_margins_for_page(pages, bool(kdp), page_idx_0, pb)

        data = up.getvalue()
        sk_png = _get_sketch(data, target_w, target_h)
        ib = io.BytesIO(sk_png)
        c.drawImage(ImageReader(ib), 0, 0, pb.full_w, pb.full_h)

        h_val = (start_hour + i) % 24
        seed = int(seed_base ^ (i << 1) ^ h_val) & 0xFFFFFFFF
        mission = qd.pick_mission_for_time(h_val, diff, seed)

        _draw_quest_overlay(c, pb, sl, sr, stb, h_val, mission, debug=bool(debug_guides))

        if eddie_guide:
            # bottom-right inside safe zone
            r = 0.18 * inch
            cx = (pb.full_w - sr) - r
            cy = stb + r
            _draw_eddie(c, cx, cy, r)

        c.showPage()

    # Outro
    if outro:
        sl, sr, stb = safe_margins_for_page(pages, bool(kdp), pages - 1, pb)
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

    cw, ch = (2 * TRIM) + sw + (2 * BLEED), TRIM + (2 * BLEED)

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(cw, ch))

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
    html = """<h3>24 Stunden. 24 Missionen. Dein Kind als Held.</h3>
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
# 7) UI
# =========================================================
st.set_page_config(page_title=APP_TITLE, layout="centered", page_icon=APP_ICON)

if qd is None:
    st.error("quest_data.py konnte nicht geladen werden. Fix das zuerst, sonst gibt’s keine Missionen.")
    st.code(_QD_IMPORT_ERROR or "Unbekannter Import-Fehler", language="text")
    st.stop()

st.markdown(f"<h1 style='text-align:center;'>{APP_TITLE} • Enterprise</h1>", unsafe_allow_html=True)
st.caption(f"Build: {BUILD_TAG}")

if "assets" not in st.session_state:
    st.session_state.assets = None
if "preview_idx" not in st.session_state:
    st.session_state.preview_idx = 0


def _tmp(prefix: str, suffix: str, data: bytes) -> str:
    with tempfile.NamedTemporaryFile(prefix=prefix, suffix=suffix, delete=False) as tf:
        tf.write(data)
        return tf.name


with st.container(border=True):
    col1, col2 = st.columns(2)
    with col1:
        name = st.text_input("Name", value="Eddie")
        age = st.number_input("Alter", 3, 99, 5)
    with col2:
        pages = st.number_input("Seiten", min_value=KDP_MIN_PAGES, max_value=300, value=KDP_MIN_PAGES, step=2)
        if int(pages) % 2 != 0:
            pages = int(pages) + 1
            st.info("ℹ️ Seitenzahl wurde auf die nächste gerade Zahl angehoben (Print-Safety).")

        paper = st.selectbox("Papier (Cover-Spine)", list(PAPER_FACTORS.keys()), index=0)

    kdp = st.toggle("KDP-Mode (Bleed)", True)
    debug_guides = st.toggle("🧪 Preflight Debug (Bleed/Safe anzeigen)", False)
    eddie_guide = st.toggle("🐶 Eddie als Guide auf jeder Seite", True)
    uploads = st.file_uploader("Fotos", accept_multiple_files=True, type=["jpg", "png", "jpeg"])

# ---- Own image counter + preview (THIS is what you want) ----
if uploads:
    n = len(uploads)
    st.session_state.preview_idx = max(0, min(st.session_state.preview_idx, n - 1))

    st.markdown("### Vorschau")
    st.write(f"**Bild {st.session_state.preview_idx + 1} von {n}**")

    st.session_state.preview_idx = st.slider(
        "Bild auswählen",
        min_value=1,
        max_value=n,
        value=st.session_state.preview_idx + 1,
        step=1,
        key="preview_slider",
    ) - 1

    try:
        b = uploads[st.session_state.preview_idx].getvalue()
        img = Image.open(io.BytesIO(b)).convert("RGB")
        st.image(img, caption=uploads[st.session_state.preview_idx].name, use_container_width=True)
    except Exception as e:
        st.warning(f"Preview konnte nicht geladen werden: {e}")

# ---- Res check gate ----
can_build = False
override_res = False

if uploads and name:
    pb = page_box(TRIM, TRIM, kdp_bleed=bool(kdp))
    target_px = int(round(min(pb.full_w, pb.full_h) * DPI / 72.0))

    small_files = []
    for up in uploads:
        try:
            with Image.open(io.BytesIO(up.getvalue())) as img:
                w, h = img.size
                if min(w, h) < target_px:
                    small_files.append((up.name, w, h))
        except Exception:
            pass

    if small_files:
        st.warning(
            f"⚠️ {len(small_files)} Foto(s) sind kleiner als die empfohlene Zielauflösung ({target_px}px). "
            "Das kann zu unscharfem Druck führen."
        )
        with st.expander("Details ansehen"):
            for sf, fw, fh in small_files:
                st.write(f"- {sf} ({fw}x{fh} px)")
        override_res = st.toggle("🚨 Warnung ignorieren und trotzdem generieren", False)
        can_build = override_res
    else:
        st.success(f"✅ Alle {len(uploads)} Fotos erfüllen die 300-DPI-Anforderung (≥ {target_px}px).")
        can_build = True

# ---- Generate ----
if st.button("🚀 Buch generieren", disabled=not can_build):
    with st.spinner("Rendering PDFs..."):
        diff = 1 if age <= 4 else 2 if age <= 6 else 3 if age <= 9 else 4

        int_pdf = build_interior(
            name=name,
            uploads=uploads,
            pages=int(pages),
            kdp=bool(kdp),
            intro=True,
            outro=True,
            start_hour=6,
            diff=diff,
            debug_guides=bool(debug_guides),
            eddie_guide=bool(eddie_guide),
        )

        cov_pdf = build_cover(name=name, pages=int(pages), paper=paper)
        listing_txt = build_listing_text(name)

        # cleanup previous
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
        st.success("✅ Assets bereit!")

# ---- Downloads ----
if st.session_state.assets:
    a = st.session_state.assets
    c1, c2, c3 = st.columns(3)
    with c1:
        with open(a["int"], "rb") as f:
            st.download_button("📘 Interior", f, file_name=f"Int_{a['name']}.pdf")
    with c2:
        with open(a["cov"], "rb") as f:
            st.download_button("🎨 Cover", f, file_name=f"Cov_{a['name']}.pdf")
    with c3:
        with open(a["listing"], "rb") as f:
            st.download_button("📝 Listing", f, file_name=f"Listing_{a['name']}.txt")

st.markdown("<div style='text-align:center; color:grey;'>Eddies Welt © 2026</div>", unsafe_allow_html=True)
