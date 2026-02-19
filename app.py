# =========================================================
# app.py — Eddies Questbook Edition — BRAND & PRE-READER (v4.7.2)
#
# Changelog v4.7.2:
# - UI: Sicherheits-Warnung bei aktivem Debug-Modus
# - UI: Tooltips für alle kritischen Einstellungen
# =========================================================

from __future__ import annotations

import io
import os
import gc
import tempfile
import hashlib
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
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

# Importiere den Sanitizer
try:
    import image_wash as iw
except ImportError:
    class iw:
        @staticmethod
        def wash_image(f):
            i = Image.open(f)
            return i.convert("RGB")

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
MAX_SKETCH_CACHE = 256
BUILD_TAG = "v4.7.2-safe-ui"

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
        except: pass
    if os.path.exists(bold_p):
        try: pdfmetrics.registerFont(TTFont("EDDIES_FONT_BOLD", bold_p))
        except: pass
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
    def fits(s: str) -> bool: return stringWidth(s, font, size) <= max_w
    for w in words:
        trial = (cur + " " + w).strip()
        if cur and fits(trial): cur = trial
        elif not cur and fits(w): cur = w
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
            else: cur = w
    if cur: lines.append(cur)
    return lines

def _fit_lines(lines: List[str], max_lines: int) -> List[str]:
    if len(lines) <= max_lines: return lines
    out = lines[:max_lines]
    last = out[-1].rstrip()
    out[-1] = (last[:-3].rstrip() if len(last) > 3 else last) + "…" if len(last) > 3 else last + "…"
    return out

def _kid_short(s: str, max_words: int = 4) -> str:
    """Kürzt Text radikal für Pre-Reader (nur Kernwörter)"""
    s = (s or "").strip()
    if not s: return ""
    # Filter junk
    s = s.replace("•", " ").replace("→", " ").replace("-", " ")
    words = [w for w in s.split() if w and len(w) > 1]
    return " ".join(words[:max_words])

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
    while sc["needed"] > max_card_h and (ts > 9):
        ts -= 1
        bs = max(8, bs - 0.5)
        ls = max(8, ls - 0.5)
        sc = compute(int(ts), int(bs), int(ls))
    return sc

def _stable_seed(s: str) -> int:
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:8], "big")

# =========================================================
# ICONS & BRANDING
# =========================================================
def _draw_eddie(c: canvas.Canvas, cx: float, cy: float, r: float, style: str = "tongue"):
    """
    style:
      - "tongue": minimal brand mark (lila Zunge)
      - "dog": mini dog-head outline (simple)
    """
    c.saveState()

    if style == "tongue":
        # minimal tongue mark
        t_w = r * 0.55
        t_h = r * 0.70

        c.setFillColor(colors.HexColor(EDDIE_PURPLE))
        c.setStrokeColor(INK_BLACK)
        c.setLineWidth(max(1.2, r * 0.06))

        x0 = cx - t_w / 2
        y0 = cy - t_h / 2

        # rounded tongue
        c.roundRect(x0, y0, t_w, t_h, r * 0.18, stroke=1, fill=1)
        # little notch line (tongue split)
        c.setLineWidth(max(0.8, r * 0.03))
        c.line(cx, y0 + t_h * 0.15, cx, y0 + t_h * 0.45)

        c.restoreState()
        return

    # "dog" (simple head + tongue)
    c.setStrokeColor(INK_BLACK)
    c.setFillColor(colors.white)
    c.setLineWidth(max(1.2, r * 0.06))
    c.circle(cx, cy, r, stroke=1, fill=1)

    # ears (triangles)
    ear = r * 0.55
    c.setFillColor(colors.white)
    c.setStrokeColor(INK_BLACK)
    c.line(cx - r*0.55, cy + r*0.55, cx - r*0.15, cy + r*0.95)
    c.line(cx - r*0.15, cy + r*0.95, cx - r*0.05, cy + r*0.45)

    c.line(cx + r*0.55, cy + r*0.55, cx + r*0.15, cy + r*0.95)
    c.line(cx + r*0.15, cy + r*0.95, cx + r*0.05, cy + r*0.45)

    # tongue
    c.setFillColor(colors.HexColor(EDDIE_PURPLE))
    c.roundRect(cx - r*0.12, cy - r*0.45, r*0.24, r*0.28, r*0.10, stroke=0, fill=1)

    c.restoreState()

def _icon_run(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    c.setStrokeColor(INK_BLACK); c.setLineWidth(max(1.2, size*0.10))
    # stick runner
    c.circle(x+size*0.30, y+size*0.72, size*0.12, stroke=1, fill=0) # head
    c.line(x+size*0.30, y+size*0.60, x+size*0.30, y+size*0.30) # body
    c.line(x+size*0.30, y+size*0.50, x+size*0.55, y+size*0.40) # arm R
    c.line(x+size*0.30, y+size*0.50, x+size*0.05, y+size*0.40) # arm L
    c.line(x+size*0.30, y+size*0.30, x+size*0.15, y+size*0.10) # leg L
    c.line(x+size*0.30, y+size*0.30, x+size*0.50, y+size*0.12) # leg R
    c.restoreState()

def _icon_brain(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    c.setStrokeColor(INK_BLACK); c.setLineWidth(max(1.2, size*0.08))
    c.roundRect(x+size*0.15, y+size*0.20, size*0.70, size*0.60, size*0.18, stroke=1, fill=0)
    c.line(x+size*0.50, y+size*0.20, x+size*0.50, y+size*0.80) # split
    c.circle(x+size*0.35, y+size*0.50, size*0.05, stroke=1, fill=1) # dot L
    c.circle(x+size*0.65, y+size*0.50, size*0.05, stroke=1, fill=1) # dot R
    c.restoreState()

def _icon_check(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    c.setStrokeColor(INK_BLACK); c.setLineWidth(max(1.2, size*0.08))
    c.rect(x+size*0.15, y+size*0.20, size*0.70, size*0.60, stroke=1, fill=0)
    # checkmark
    c.line(x+size*0.30, y+size*0.45, x+size*0.45, y+size*0.30)
    c.line(x+size*0.45, y+size*0.30, x+size*0.70, y+size*0.65)
    c.restoreState()

# =========================================================
# IMAGING
# =========================================================
_IMG_STORE = OrderedDict()

def _get_sketch(img_bytes: bytes, target_w: int, target_h: int) -> bytes:
    h = hashlib.sha256(img_bytes).hexdigest()
    if h in _IMG_STORE:
        _IMG_STORE.move_to_end(h)
        return _IMG_STORE[h]
    
    try:
        arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
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
        res = out.getvalue()
        
        _IMG_STORE[h] = res
        _IMG_STORE.move_to_end(h)
        if len(_IMG_STORE) > MAX_SKETCH_CACHE:
            _IMG_STORE.popitem(last=False)
        return res
    except Exception:
        return img_bytes

# =========================================================
# OVERLAYS
# =========================================================
def _draw_quest_overlay(c, pb, safe_left, safe_right, safe_tb, hour, mission, debug, pre_reader=False):
    header_h = 0.75 * inch
    x0, x1 = safe_left, pb.full_w - safe_right
    y1 = pb.full_h - safe_tb
    w = max(1.0, x1 - x0)
    y_header_bottom = y1 - header_h

    zone = qd.get_zone_for_hour(hour)
    zone_rgb = qd.get_hour_color(hour)
    fill = colors.Color(zone_rgb[0], zone_rgb[1], zone_rgb[2])
    
    # Header
    c.saveState()
    c.setFillColor(fill)
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(1)
    c.rect(x0, y_header_bottom, w, header_h, fill=1, stroke=1)
    
    c.setFillColor(colors.white if sum(zone_rgb[:3]) < 1.5 else INK_BLACK)
    _set_font(c, True, 14)
    c.drawString(x0 + 0.18 * inch, y_header_bottom + header_h - 0.50 * inch, f"{qd.fmt_hour(hour)}  {zone.icon}  {zone.name}")
    _set_font(c, False, 10)
    c.drawString(x0 + 0.18 * inch, y_header_bottom + 0.18 * inch, f"{zone.quest_type} • {zone.atmosphere}")

    # Content Card
    cy = safe_tb
    max_ch = (y_header_bottom - cy) - (0.15 * inch)
    pad_x = 0.18 * inch
    
    # Pre-calc height
    if pre_reader:
        # Fixed height for icons
        card_h = min(max_ch, 2.5 * inch)
    else:
        sc = _autoscale_mission_text(mission, w, x0, pad_x, max_ch)
        card_h = min(max_ch, max(1.85 * inch, sc["needed"]))
    
    c.setFillColor(colors.white)
    c.setStrokeColor(INK_BLACK)
    c.rect(x0, cy, w, card_h, fill=1, stroke=1)
    
    y_text_top = cy + card_h - 0.20 * inch
    
    if pre_reader:
        # --- PRE-READER LAYOUT (ICONS) ---
        c.setFillColor(INK_BLACK)
        _set_font(c, True, 14)
        title = _kid_short(getattr(mission, "title", "MISSION"), 3)
        c.drawString(x0 + pad_x, y_text_top - 10, title)
        _set_font(c, True, 11)
        c.drawRightString(x0 + w - pad_x, y_text_top - 10, f"+{getattr(mission, 'xp', 0)} XP")

        # 3 Rows
        row_h = 0.46 * inch
        icon = 0.34 * inch
        start_y = y_text_top - 0.50 * inch

        move = _kid_short(getattr(mission, "movement", ""), 3)
        think = _kid_short(getattr(mission, "thinking", ""), 3)
        proof = _kid_short(getattr(mission, "proof", ""), 2)

        # 1. Move
        _icon_run(c, x0 + pad_x, start_y - icon*0.2, icon)
        _set_font(c, False, 12)
        c.drawString(x0 + pad_x + icon + 0.2*inch, start_y, move or "Bewegen!")

        # 2. Think
        _icon_brain(c, x0 + pad_x, start_y - row_h - icon*0.2, icon)
        _set_font(c, False, 12)
        c.drawString(x0 + pad_x + icon + 0.2*inch, start_y - row_h, think or "Denken!")

        # 3. Check
        _icon_check(c, x0 + pad_x, start_y - 2*row_h - icon*0.2, icon)
        _set_font(c, False, 12)
        c.drawString(x0 + pad_x + icon + 0.2*inch, start_y - 2*row_h, proof or "Haken!")

        # Parent Hint
        _set_font(c, False, 8)
        c.setFillColor(INK_GRAY_70)
        c.drawString(x0 + pad_x, cy + 0.12*inch, "Eltern: Kurz vorlesen – Kind macht’s nach.")

    else:
        # --- CLASSIC TEXT LAYOUT ---
        c.setFillColor(INK_BLACK)
        _set_font(c, True, sc["ts"])
        c.drawString(x0 + pad_x, y_text_top - sc["tl"] + 2, f"MISSION: {mission.title}")
        _set_font(c, True, max(8, sc["ts"] - 2))
        c.drawRightString(x0 + w - pad_x, y_text_top - sc["tl"] + 2, f"+{mission.xp} XP")
        
        y_cur = y_text_top - sc["tl"] + 0.10 * inch
        y_cur -= sc["tl"] + 0.10 * inch
        
        _set_font(c, True, sc["ls"])
        c.drawString(x0 + pad_x, y_cur - sc["ll"] + 2, "BEWEGUNG:")
        _set_font(c, False, sc["bs"])
        yy = y_cur - sc["ll"] + 2
        for l in sc["ml"]: c.drawString(x0 + 1.05 * inch, yy, l); yy -= sc["bl"]
        
        y_cur = yy - 0.06 * inch
        _set_font(c, True, sc["ls"])
        c.drawString(x0 + pad_x, y_cur - sc["ll"] + 2, "DENKEN:")
        _set_font(c, False, sc["bs"])
        yy = y_cur - sc["ll"] + 2
        for l in sc["tl_lines"]: c.drawString(x0 + 0.90 * inch, yy, l); yy -= sc["bl"]
        
        bx, box = x0 + pad_x, 0.20 * inch
        c.rect(bx, cy + 0.18 * inch, box, box, fill=0, stroke=1)
        _set_font(c, True, sc["ls"])
        c.drawString(bx + box + 0.15 * inch, cy + 0.20 * inch, "PROOF:")
        _set_font(c, False, sc["bs"])
        if mission.proof:
            pr = _fit_lines(_wrap_text_hard(mission.proof, FONTS["normal"], sc["bs"], w - 1.5 * inch), 1)[0]
            c.drawString(bx + box + 0.75 * inch, cy + 0.20 * inch, pr)

    if debug:
        c.saveState()
        c.setLineWidth(0.5); c.setDash(3, 3); c.setStrokeColor(colors.red)
        c.rect(pb.bleed, pb.bleed, pb.full_w - 2*pb.bleed, pb.full_h - 2*pb.bleed)
        c.restoreState()

    c.restoreState()

# =========================================================
# BUILDERS
# =========================================================
def build_interior(name, uploads, pages, kdp, intro, outro, start_hour, diff, debug_guides, eddie_guide, eddie_style, pre_reader):
    if qd is None: return None
    pb = page_box(TRIM, TRIM, kdp_bleed=kdp)
    target_w = int(round(pb.full_w * DPI / 72.0))
    target_h = int(round(pb.full_h * DPI / 72.0))
    
    files = list(uploads)
    if not files: return None
    
    photo_count = max(1, pages - (int(intro) + int(outro)))
    final = (files * (photo_count // len(files) + 1))[:photo_count]
    
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pb.full_w, pb.full_h))
    seed_base = _stable_seed(name)
    
    # Intro
    if intro:
        sl, sr, stb = safe_margins_for_page(pages, kdp, 0, pb)
        c.setFillColor(colors.white); c.rect(0,0,pb.full_w, pb.full_h, fill=1, stroke=0)
        c.setFillColor(INK_BLACK)
        _set_font(c, True, 34)
        c.drawCentredString(pb.full_w/2, pb.full_h - stb - 2*inch, "Willkommen bei Eddies")
        _set_font(c, False, 22)
        c.drawCentredString(pb.full_w/2, pb.full_h - stb - 2.6*inch, f"& {name}")
        # Large Brand Mark on Intro
        _draw_eddie(c, pb.full_w/2, pb.full_h/2, 1.3*inch, style=eddie_style)
        c.showPage()
        
    # Content
    for i, up in enumerate(final):
        clean_img = iw.wash_image(up)
        b = io.BytesIO(); clean_img.save(b, format="PNG"); b_val = b.getvalue()
        sk_png = _get_sketch(b_val, target_w, target_h)
        
        c.drawImage(ImageReader(io.BytesIO(sk_png)), 0, 0, pb.full_w, pb.full_h)
        
        page_idx_0 = i + (1 if intro else 0)
        sl, sr, stb = safe_margins_for_page(pages, kdp, page_idx_0, pb)
        h_val = (start_hour + i) % 24
        seed = int(seed_base ^ (i << 1) ^ h_val) & 0xFFFFFFFF
        mission = qd.pick_mission_for_time(h_val, diff, seed)
        
        # Pass pre_reader state
        _draw_quest_overlay(c, pb, sl, sr, stb, h_val, mission, debug_guides, pre_reader=pre_reader)
        
        if eddie_guide:
            r = 0.18 * inch
            _draw_eddie(c, (pb.full_w - sr) - r, stb + r, r, style=eddie_style)
            
        c.showPage()
        
    # Outro
    if outro:
        c.setFillColor(colors.white); c.rect(0,0,pb.full_w, pb.full_h, fill=1, stroke=0)
        _draw_eddie(c, pb.full_w/2, pb.full_h/2 + 0.6*inch, 1.5*inch, style=eddie_style)
        c.setFillColor(INK_BLACK)
        _set_font(c, True, 30)
        c.drawCentredString(pb.full_w/2, pb.full_h/2 - 1.5*inch, "Quest abgeschlossen!")
        c.showPage()
        
    c.save()
    buf.seek(0)
    return buf.getvalue()

def build_cover(name, pages, paper, uploads, eddie_style):
    sw = float(pages) * PAPER_FACTORS.get(paper, 0.002252) * inch
    sw = max(sw, 0.001 * inch)
    sw = round(sw / (0.001 * inch)) * (0.001 * inch)
    cw, ch = (2 * TRIM) + sw + (2 * BLEED), TRIM + (2 * BLEED)
    
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(cw, ch))
    
    # White base
    c.setFillColor(colors.white)
    c.rect(0, 0, cw, ch, fill=1, stroke=0)
    
    front_x_start = BLEED + TRIM + sw
    
    # Collage
    if uploads:
        grid_imgs = [iw.wash_image(u) for u in uploads[:4]]
        coll = Image.new("RGB", (2000, 2000), "white")
        cell_w, cell_h = 1000, 1000
        for idx, img in enumerate(grid_imgs):
            iw_img, ih_img = img.size
            s = min(iw_img, ih_img)
            img = img.crop(((iw_img-s)//2, (ih_img-s)//2, (iw_img+s)//2, (ih_img+s)//2))
            img = img.resize((cell_w, cell_h))
            r, c_idx = divmod(idx, 2)
            coll.paste(img, (c_idx * cell_w, r * cell_h))
            
        c.drawImage(ImageReader(coll), front_x_start, 0, width=TRIM+BLEED, height=TRIM+2*BLEED)
        
        # Overlay for Text readability
        c.saveState()
        c.setFillColor(colors.white)
        c.setFillAlpha(0.8) # etwas stärker für besseren Kontrast
        c.rect(front_x_start, BLEED + TRIM*0.6, TRIM, TRIM*0.3, fill=1, stroke=0)
        c.restoreState()

    # Spine
    c.setFillColor(INK_BLACK)
    c.rect(BLEED + TRIM, BLEED, sw, TRIM, fill=1, stroke=0)
    
    # Back Cover Brand Mark (Small)
    bx = BLEED
    _draw_eddie(c, bx + TRIM*0.5, BLEED + TRIM*0.85, TRIM*0.06, style=eddie_style)

    # Front Cover Brand Mark (Large)
    fx = BLEED + TRIM + sw
    _draw_eddie(c, fx + TRIM / 2, BLEED + TRIM * 0.62, TRIM * 0.16, style=eddie_style)

    c.setFillColor(INK_BLACK)
    _set_font(c, True, 44)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.80, "EDDIES")
    _set_font(c, False, 18)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.73, f"& {name}")
    
    c.save()
    buf.seek(0)
    return buf.getvalue()

# =========================================================
# UI
# =========================================================
st.set_page_config(page_title=APP_TITLE, layout="centered", page_icon=APP_ICON)

if qd is None:
    st.error("quest_data.py fehlt!")
    st.stop()
    
st.markdown(f"<h1 style='text-align:center;'>{APP_TITLE}</h1>", unsafe_allow_html=True)
st.caption(f"Build: {BUILD_TAG}")

if "assets" not in st.session_state: st.session_state.assets = None

with st.container(border=True):
    c1, c2 = st.columns(2)
    name = c1.text_input("Name", "Eddie")
    age = c1.number_input("Alter", 3, 99, 5)
    
    pages = c2.number_input("Seiten", KDP_MIN_PAGES, 300, KDP_MIN_PAGES, 2)
    if int(pages) % 2 != 0: pages += 1
    paper = c2.selectbox("Papier", list(PAPER_FACTORS.keys()), 0)
    
    st.divider()
    
    c3, c4 = st.columns(2)
    eddie_style = c3.selectbox("Eddie-Icon", ["tongue", "dog"], index=0, help="'tongue' ist das neue Brand-Logo.")
    pre_reader_mode = c4.toggle("👶 Pre-Reader Mode", value=(age <= 6), help="Für Kinder, die noch nicht lesen: Icons statt Text.")
    
    kdp = st.toggle("KDP Mode (Bleed + Margins)", True)
    
    # Improved Debug Toggle with explanation and warning
    debug = st.toggle(
        "🛠️ Preflight Debug (Schnittkanten)", 
        value=False, 
        help="Zeigt rote Linien für Beschnitt (Bleed) und Sicherheitsabstand (Safe Zone). Nur zur Prüfung am Bildschirm – nicht drucken!"
    )
    
    if debug:
        st.warning("⚠️ ACHTUNG: Rote Linien werden mitgedruckt. Diese Version NICHT bei Amazon hochladen!", icon="🚫")
    
    uploads = st.file_uploader("Fotos (werden gewaschen & skizziert)", accept_multiple_files=True, type=["jpg","png","jpeg","webp"])

if st.button("🚀 GENRIEREN", disabled=not uploads):
    with st.spinner("Waschen... Skizzieren... Layouten..."):
        diff = 1 if age <= 4 else 2 if age <= 6 else 3 if age <= 9 else 4
        
        pdf_int = build_interior(name, uploads, pages, kdp, True, True, 6, diff, debug, True, eddie_style, pre_reader_mode)
        pdf_cov = build_cover(name, pages, paper, uploads, eddie_style)
        
        st.session_state.assets = {
            "int": pdf_int,
            "cov": pdf_cov,
            "name": name
        }
        st.success("Fertig!")

if st.session_state.assets:
    a = st.session_state.assets
    c1, c2 = st.columns(2)
    c1.download_button("📘 Interior PDF", a["int"], f"Int_{a['name']}.pdf")
    c2.download_button("🎨 Cover PDF", a["cov"], f"Cov_{a['name']}.pdf")
