# =========================================================
# app.py (Eddies Questbook Edition 2026 — ACTIVE / WASH + KDP)
# - Eddie as GUIDE: Black/White + Purple Tongue on every page
# - KDP-READY: No page numbers, no author names, 300 DPI
# - IMAGE WASH: sanitize uploads (fix broken EXIF/JPEG/PNG quirks)
# - SKETCH: line-art (max white, clean outlines for coloring)
# - HARD RULE: Interior pages >= 24 (enforced)
# - METADATA: scrubbed
# - UI: Image counter, preview slider, clean Streamlit
# =========================================================
from __future__ import annotations

import io
import os
import gc
import hashlib
from typing import Dict, List, Optional, Tuple

import streamlit as st
import cv2
import numpy as np
from PIL import Image

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth

# --- IMAGE WASH IMPORT ---
try:
    import image_wash as iw
except Exception:
    iw = None

# --- QUEST SYSTEM IMPORT ---
try:
    import quest_data as qd
except Exception as e:
    qd = None
    _QD_IMPORT_ERROR = str(e)
else:
    _QD_IMPORT_ERROR = ""

# =========================================================
# 1) CONFIG
# =========================================================
APP_TITLE = "Eddies"
APP_ICON = "🐶"
EDDIE_PURPLE = "#7c3aed"

DPI = 300
TRIM_IN = 8.5
TRIM = TRIM_IN * inch
BLEED = 0.125 * inch
SAFE_INTERIOR = 0.375 * inch
KDP_MIN_PAGES = 24

INK_BLACK = colors.Color(0, 0, 0)
INK_GRAY_70 = colors.Color(0.30, 0.30, 0.30)

PAPER_FACTORS = {
    "Schwarzweiß – Weiß": 0.002252,
    "Schwarzweiß – Creme": 0.0025,
    "Farbe – Weiß": 0.002347,
}

GUIDE_MARGIN = 0.22 * inch
GUIDE_R = 0.24 * inch
PROG_DOT_R = 0.045 * inch
PROG_GAP = 0.075 * inch

ZONE_STORY = {
    "wachturm": "Startklar werden: Körper an, Kopf auf, Struktur rein.",
    "wilder_pfad": "Draußen entdecken: Muster finden, Spuren lesen.",
    "taverne": "Energie tanken: bewusst essen, Körper wahrnehmen.",
    "werkstatt": "Bauen & tüfteln: aus Ideen werden Dinge.",
    "arena": "Action-Modus: Mut testen, Tempo fühlen.",
    "ratssaal": "Team-Moment: helfen, Verbindung schaffen.",
    "quellen": "Reset: sauber werden, runterfahren.",
    "trauminsel": "Leise Phase: atmen, Frieden sammeln.",
}

# =========================================================
# 2) FONT & TEXT HELPERS
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
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _stable_seed(s: str) -> int:
    h = hashlib.sha256((s or "").encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big", signed=False)


# =========================================================
# 3) GEOMETRY + METADATA
# =========================================================
def _page_geometry(kdp: bool) -> Tuple[float, float, float, float]:
    pw = ph = (TRIM + 2 * BLEED) if kdp else TRIM
    bleed = BLEED if kdp else 0.0
    safe = bleed + SAFE_INTERIOR
    return float(pw), float(ph), float(bleed), float(safe)


def _scrub_pdf_metadata(c: canvas.Canvas) -> None:
    try:
        c.setAuthor("")
        c.setTitle("")
        c.setSubject("")
        c.setCreator("")
        c.setKeywords("")
    except Exception:
        pass
    try:
        if hasattr(c, "_doc") and hasattr(c._doc, "info") and c._doc.info:
            c._doc.info.producer = ""
            c._doc.info.author = ""
            c._doc.info.title = ""
            c._doc.info.subject = ""
            c._doc.info.creator = ""
            c._doc.info.keywords = ""
    except Exception:
        pass


# =========================================================
# 4) IMAGE WASH (UPLOAD SANITIZE)
# =========================================================
def _wash_bytes(b: bytes) -> bytes:
    if iw is None:
        # fallback: return original bytes
        return b
    try:
        return iw.wash_image_bytes(b)
    except Exception:
        return b


# =========================================================
# 5) SKETCH ENGINE (LINE ART / MAX WHITE)
# =========================================================
def _cv_sketch_from_bytes(img_bytes: bytes) -> np.ndarray:
    arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise RuntimeError("Bild-Dekodierung fehlgeschlagen.")

    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, d=9, sigmaColor=80, sigmaSpace=80)

    edges = cv2.Canny(gray, threshold1=40, threshold2=120)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)

    line_art = 255 - edges
    line_art = cv2.medianBlur(line_art, 3)
    return line_art.astype(np.uint8)


def _render_page_png_from_upload(upload_bytes: bytes, pw: float, ph: float) -> bytes:
    """
    - WASH -> decode -> line-art -> center-crop -> resize to page pixels @300DPI -> PNG bytes
    - returns PNG bytes ready for ReportLab ImageReader
    """
    washed = _wash_bytes(upload_bytes)
    sk = _cv_sketch_from_bytes(washed)

    pil = Image.fromarray(sk).convert("L")
    sw, sh = pil.size
    s = min(sw, sh)

    target_w = int(pw * DPI / inch)
    target_h = int(ph * DPI / inch)

    pil = pil.crop(((sw - s) // 2, (sh - s) // 2, (sw + s) // 2, (sh + s) // 2)).resize(
        (target_w, target_h), Image.LANCZOS
    )

    out = io.BytesIO()
    pil.save(out, "PNG", optimize=True)
    out.seek(0)

    # free mem
    del pil
    gc.collect()

    return out.getvalue()


# =========================================================
# 6) EDDIE VISUALS
# =========================================================
def _draw_eddie(c: canvas.Canvas, cx: float, cy: float, r: float):
    c.saveState()
    c.setLineWidth(max(1.5, r * 0.06))
    c.setStrokeColor(INK_BLACK)
    c.setFillColor(colors.white)

    c.circle(cx, cy, r, stroke=1, fill=1)

    c.setFillColor(INK_BLACK)
    c.circle(cx - r * 0.28, cy + r * 0.15, r * 0.10, stroke=0, fill=1)
    c.circle(cx + r * 0.28, cy + r * 0.15, r * 0.10, stroke=0, fill=1)

    c.setLineWidth(max(1.5, r * 0.05))
    c.arc(cx - r * 0.35, cy - r * 0.10, cx + r * 0.35, cy + r * 0.20, 200, 140)

    c.setFillColor(colors.HexColor(EDDIE_PURPLE))
    c.roundRect(cx - r * 0.10, cy - r * 0.35, r * 0.20, r * 0.22, r * 0.08, stroke=0, fill=1)
    c.restoreState()


def _draw_eddie_guide_stamp(c: canvas.Canvas, pw: float, ph: float, safe: float, cum_xp: int, total_xp: int):
    ed_x = pw - safe - GUIDE_MARGIN
    ed_y = safe + GUIDE_MARGIN + 0.10 * inch
    _draw_eddie(c, ed_x, ed_y, GUIDE_R)

    bar_w = 1.35 * inch
    bar_h = 0.10 * inch
    bar_x = pw - safe - bar_w - 0.05 * inch
    bar_y = safe + 0.12 * inch
    progress = float(cum_xp) / float(max(1, total_xp))

    c.saveState()
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(0.8)
    c.rect(bar_x, bar_y, bar_w, bar_h, stroke=1, fill=0)
    if progress > 0:
        c.setFillColor(INK_BLACK)
        c.rect(bar_x, bar_y, bar_w * min(1.0, progress), bar_h, stroke=0, fill=1)
    c.restoreState()


def _draw_progress_dots(c: canvas.Canvas, x_right: float, y: float, current_idx: int, total: int = 24):
    c.saveState()
    for i in range(total - 1, -1, -1):
        x = x_right - (total - 1 - i) * (2 * PROG_DOT_R + PROG_GAP)
        c.setLineWidth(0.8)
        c.setStrokeColor(colors.white)
        if i <= current_idx:
            c.setFillColor(colors.white)
            c.circle(x, y, PROG_DOT_R, stroke=1, fill=1)
        else:
            c.circle(x, y, PROG_DOT_R, stroke=1, fill=0)
    c.restoreState()


# =========================================================
# 7) QUEST OVERLAY
# =========================================================
def _draw_quest_overlay(c, pw, ph, safe, hour, mission, m_idx, m_total, xp_total):
    if qd is None:
        raise RuntimeError(f"quest_data.py nicht verfügbar: {_QD_IMPORT_ERROR}")

    header_h = 0.75 * inch
    x0, y0, w = safe, ph - safe - header_h, pw - 2 * safe

    zone = qd.get_zone_for_hour(hour)
    z_rgb = qd.get_hour_color(hour)  # 0..1
    fill = colors.Color(z_rgb[0], z_rgb[1], z_rgb[2])
    lum = (0.21 * z_rgb[0] + 0.71 * z_rgb[1] + 0.07 * z_rgb[2])
    tc = colors.white if lum < 0.45 else INK_BLACK

    c.saveState()
    c.setFillColor(fill)
    c.setLineWidth(1)
    c.rect(x0, y0, w, header_h, fill=1, stroke=1)

    c.setFillColor(tc)
    _set_font(c, True, 14)
    c.drawString(x0 + 0.18 * inch, y0 + header_h - 0.50 * inch, f"{qd.fmt_hour(hour)}  {zone.icon}  {zone.name}")

    _set_font(c, False, 8)
    c.setFillColor(INK_GRAY_70)
    c.drawString(x0 + 0.18 * inch, y0 + 0.18 * inch, f"{zone.name} — {ZONE_STORY.get(zone.id, '')}")

    c.setFillColor(tc)
    _set_font(c, True, 10)
    c.drawRightString(x0 + w - 0.18 * inch, y0 + header_h - 0.28 * inch, f"MISSION {m_idx+1:02d}/{m_total:02d}")
    _draw_progress_dots(c, x0 + w - 0.18 * inch, y0 + header_h - 0.55 * inch, m_idx, m_total)

    # Mission Card
    card_h = 1.85 * inch
    c.setFillColor(colors.white)
    c.rect(x0, safe, w, card_h, fill=1, stroke=1)

    c.setFillColor(INK_BLACK)
    _set_font(c, True, 12)
    c.drawString(x0 + 0.15 * inch, safe + card_h - 0.35 * inch, f"MISSION: {mission.title}")
    c.drawRightString(x0 + w - 0.15 * inch, safe + card_h - 0.35 * inch, f"+{int(mission.xp)} XP")

    _set_font(c, True, 9)
    c.drawString(x0 + 0.15 * inch, safe + 1.1 * inch, "BEWEGUNG:")
    c.drawString(x0 + 0.15 * inch, safe + 0.6 * inch, "DENKEN:")
    _set_font(c, False, 9)
    c.drawString(x0 + 1.1 * inch, safe + 1.1 * inch, (mission.movement or "")[:70])
    c.drawString(x0 + 1.1 * inch, safe + 0.6 * inch, (mission.thinking or "")[:70])

    c.restoreState()


# =========================================================
# 8) PDF BUILDERS (KDP)
# =========================================================
def build_interior(name, uploads, pages, kdp, start_hour, diff) -> bytes:
    if qd is None:
        raise RuntimeError(f"quest_data.py nicht verfügbar: {_QD_IMPORT_ERROR}")

    pw, ph, _, safe = _page_geometry(bool(kdp))

    pages_i = int(pages)
    if pages_i < KDP_MIN_PAGES:
        raise RuntimeError(f"KDP-Standard: Innen-PDF muss mindestens {KDP_MIN_PAGES} Seiten haben.")

    files = list(uploads or [])
    if not files:
        raise RuntimeError("Keine Bilder hochgeladen.")

    intro_pages = 1
    outro_pages = 1
    photo_count = pages_i - (intro_pages + outro_pages)
    if photo_count <= 0:
        raise RuntimeError("Seitenzahl zu klein für Intro/Outro.")

    final = (files * (photo_count // len(files) + 1))[:photo_count]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pw, ph))
    _scrub_pdf_metadata(c)

    seed_base = _stable_seed(name)
    missions = []
    for i in range(photo_count):
        h = (int(start_hour) + i) % 24
        missions.append(qd.pick_mission_for_time(h, int(diff), int(seed_base ^ i)))

    total_xp = sum(int(getattr(m, "xp", 0) or 0) for m in missions) or 1
    cum_xp = 0

    # Intro
    c.setFillColor(colors.white)
    c.rect(0, 0, pw, ph, fill=1, stroke=0)
    _draw_eddie(c, pw / 2, ph / 2 + 0.5 * inch, 1.3 * inch)
    c.setFillColor(INK_BLACK)
    _set_font(c, True, 28)
    c.drawCentredString(pw / 2, safe + 1.5 * inch, f"Eddies & {name}")
    c.showPage()

    # Mission pages
    for i, up in enumerate(final):
        h = (int(start_hour) + i) % 24

        png_bytes = _render_page_png_from_upload(up.getvalue(), pw, ph)
        ib = io.BytesIO(png_bytes)
        ib.seek(0)
        c.drawImage(ImageReader(ib), 0, 0, pw, ph)

        cum_xp += int(getattr(missions[i], "xp", 0) or 0)
        _draw_quest_overlay(c, pw, ph, safe, h, missions[i], i, len(final), cum_xp)
        _draw_eddie_guide_stamp(c, pw, ph, safe, cum_xp, total_xp)
        c.showPage()

        # memory
        del png_bytes, ib
        gc.collect()

    # Outro
    c.setFillColor(colors.white)
    c.rect(0, 0, pw, ph, fill=1, stroke=0)
    _draw_eddie(c, pw / 2, ph / 2, 1.2 * inch)
    _set_font(c, True, 24)
    c.setFillColor(INK_BLACK)
    c.drawCentredString(pw / 2, safe + 1.0 * inch, "Quest abgeschlossen!")
    c.showPage()

    c.save()
    return buf.getvalue()


def build_cover(name, pages, paper) -> bytes:
    sw = round(float(pages) * PAPER_FACTORS.get(paper, 0.00225) * 1000) / 1000 * inch
    cw, ch = (2 * TRIM) + sw + (2 * BLEED), TRIM + (2 * BLEED)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(cw, ch))
    _scrub_pdf_metadata(c)

    c.setFillColor(colors.white)
    c.rect(0, 0, cw, ch, fill=1, stroke=0)

    # Spine
    c.setFillColor(INK_BLACK)
    c.rect(BLEED + TRIM, BLEED, sw, TRIM, fill=1, stroke=0)

    # Front cover
    fx = BLEED + TRIM + sw
    _draw_eddie(c, fx + TRIM / 2, BLEED + TRIM * 0.58, TRIM * 0.18)
    c.setFillColor(INK_BLACK)
    _set_font(c, True, 44)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.80, "EDDIES")
    _set_font(c, False, 18)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.73, f"& {name}")

    c.save()
    return buf.getvalue()


# =========================================================
# 9) STREAMLIT UI
# =========================================================
st.set_page_config(page_title=APP_TITLE, layout="centered", page_icon=APP_ICON)

st.markdown(
    "<style>div[data-testid='stFileUploader'] small { display: none !important; }</style>",
    unsafe_allow_html=True,
)
st.markdown(f"<h1 style='text-align:center;'>{APP_TITLE} ULTIMATE 2026</h1>", unsafe_allow_html=True)

if qd is None:
    st.warning(f"quest_data.py fehlt/fehlerhaft: {_QD_IMPORT_ERROR}")

if iw is None:
    st.info("image_wash.py nicht geladen (Upload-Wash aus). Für maximale Stabilität: image_wash.py ins Repo legen.")

with st.container(border=True):
    c1, c2 = st.columns(2)
    with c1:
        name = st.text_input("Name", value="Eddie")
        age = st.number_input("Alter", 3, 12, 5)
    with c2:
        pages = st.number_input("Seiten", KDP_MIN_PAGES, 100, 24, step=2)
        paper = st.selectbox("Papier", list(PAPER_FACTORS.keys()))

    uploads = st.file_uploader("Fotos hochladen", accept_multiple_files=True, type=["jpg", "png", "jpeg"])

if uploads:
    st.markdown(f"**📷 Bilder: {len(uploads)}**")
    idx = st.slider("Vorschau", 1, len(uploads), 1) if len(uploads) > 1 else 1
    prev_bytes = _wash_bytes(uploads[idx - 1].getvalue())
    st.image(Image.open(io.BytesIO(prev_bytes)), use_container_width=True)

if st.button("🚀 KDP-Buch generieren", disabled=not (uploads and name)):
    if qd is None:
        st.error(f"quest_data.py konnte nicht geladen werden: {_QD_IMPORT_ERROR}")
    else:
        with st.spinner("Erstelle druckfertige PDFs..."):
            diff = 1 if age <= 4 else 2 if age <= 6 else 3
            int_pdf = build_interior(name, uploads, int(pages), True, 6, diff)
            cov_pdf = build_cover(name, int(pages), paper)

            st.session_state.pdfs = {"int": int_pdf, "cov": cov_pdf, "name": name}
            st.success("Assets bereit!")

if "pdfs" in st.session_state:
    p = st.session_state.pdfs
    st.download_button("📘 Interior (KDP)", p["int"], f"Int_{p['name']}.pdf")
    st.download_button("🎨 Cover (KDP)", p["cov"], f"Cov_{p['name']}.pdf")

st.markdown(
    "<div style='text-align:center; color:grey; margin-top:2rem;'>Eddies Welt © 2026 | Druckfertig für Amazon KDP</div>",
    unsafe_allow_html=True,
)