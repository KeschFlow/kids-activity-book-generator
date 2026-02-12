# =========================
# app.py  (Questbook Edition)
# =========================
import streamlit as st
import cv2
import io
import random
import zipfile
import re
import numpy as np
from datetime import datetime

from PIL import Image, ImageDraw
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader

import quest_data as qd  # <-- QUEST SYSTEM (NamedTuple version compatible)

# =========================================================
# 1) BUSINESS & KDP CONFIG
# =========================================================
APP_TITLE = "Eddies"
APP_ICON = "🐶"

EDDIE_PURPLE = "#7c3aed"

DPI = 300
TRIM_IN = 8.5
TRIM = TRIM_IN * inch
BLEED = 0.125 * inch
SAFE_INTERIOR = 0.375 * inch

DEFAULT_PAGES = 24
KDP_MIN_PAGES = 24

PAPER_FACTORS = {
    "Schwarzweiß – Weiß": 0.002252,
    "Schwarzweiß – Creme": 0.0025,
    "Farbe – Weiß": 0.002347,
}
SPINE_TEXT_MIN_PAGES = 79
COVER_SAFE = 0.25 * inch

HUB_URL = "https://eddieswelt.de"

# =========================================================
# 2) STREAMLIT CONFIG + STYLING
# =========================================================
st.set_page_config(page_title=APP_TITLE, layout="centered", page_icon=APP_ICON)

st.markdown(
    """
<style>
.main-title { font-size: 2.5rem; font-weight: 900; text-align: center; letter-spacing: -0.03em; margin: 0; color:#0b0b0f; }
.subtitle { text-align: center; font-size: 1.05rem; color: #6b7280; margin: 0.2rem 0 1.2rem 0; }
.kpi-container { display: flex; justify-content: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap; }
.kpi { padding: 6px 14px; border-radius: 999px; border: 1px solid #e5e7eb; font-size: .8rem; font-weight: 700; color: #6b7280; background: #fff; }
.stButton>button { width: 100%; border-radius: 12px; font-weight: 800; padding: 0.65rem; border: 2px solid #000; }
small { color: #6b7280; }
</style>
""",
    unsafe_allow_html=True,
)

st.markdown(f"<div class='main-title'>{APP_TITLE}</div>", unsafe_allow_html=True)
st.markdown("<div class='subtitle'>24h Quest-Malbuch: Foto-Skizzen + Missionen + XP</div>", unsafe_allow_html=True)

# Quest DB sanity
issues = qd.validate_quest_db()
if issues:
    st.error("Quest-Datenbank hat Probleme:\n- " + "\n- ".join(issues))

# =========================================================
# 3) HELPERS
# =========================================================
def _sanitize_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "file"


def _page_geometry(kdp_print_mode: bool):
    """
    KDP Printmode:
      - Page = TRIM + 2*BLEED (8.75")
      - Safe = BLEED + SAFE_INTERIOR
    Preview mode:
      - Page = TRIM only (8.5")
      - Safe = SAFE_INTERIOR
    Returns (page_w, page_h, bleed, safe)
    """
    if kdp_print_mode:
        page_w = TRIM + 2 * BLEED
        page_h = TRIM + 2 * BLEED
        bleed = BLEED
        safe = BLEED + SAFE_INTERIOR
    else:
        page_w = TRIM
        page_h = TRIM
        bleed = 0.0
        safe = SAFE_INTERIOR
    return float(page_w), float(page_h), float(bleed), float(safe)


def _normalize_page_count(user_pages: int, include_intro: bool, include_outro: bool) -> int:
    """
    Forced KDP compliance:
      - min 24
      - even page count
      - must have room for fixed pages + at least 1 photo page
    """
    pages = int(user_pages)
    fixed = int(include_intro) + int(include_outro)

    pages = max(KDP_MIN_PAGES, fixed + 1, pages)
    if pages % 2 != 0:
        pages += 1

    if pages < fixed + 1:
        pages = fixed + 1
        if pages % 2 != 0:
            pages += 1
        pages = max(KDP_MIN_PAGES, pages)

    return pages


def _difficulty_from_age(age: int) -> int:
    """
    Alters-Mapping → Quest-Schwierigkeitsstufe (1–5)
    3–4   = 1
    5–6   = 2
    7–9   = 3
    10–13 = 4
    14+   = 5
    """
    age = int(age)
    if age <= 4:
        return 1
    elif age <= 6:
        return 2
    elif age <= 9:
        return 3
    elif age <= 13:
        return 4
    else:
        return 5


def _draw_eddie_brand_pdf(c: canvas.Canvas, cx: float, cy: float, r: float):
    """Minimal Eddie: B/W + purple tongue."""
    c.saveState()
    c.setLineWidth(max(2, r * 0.06))
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.white)
    c.circle(cx, cy, r, stroke=1, fill=1)

    # Eyes
    c.setFillColor(colors.black)
    c.circle(cx - r * 0.28, cy + r * 0.15, r * 0.10, stroke=0, fill=1)
    c.circle(cx + r * 0.28, cy + r * 0.15, r * 0.10, stroke=0, fill=1)

    # Smile arc
    c.setLineWidth(max(2, r * 0.05))
    c.arc(cx - r * 0.35, cy - r * 0.10, cx + r * 0.35, cy + r * 0.20, 200, 140)

    # Tongue (purple)
    c.setFillColor(colors.HexColor(EDDIE_PURPLE))
    c.roundRect(cx - r * 0.10, cy - r * 0.35, r * 0.20, r * 0.22, r * 0.08, stroke=0, fill=1)
    c.restoreState()


def build_front_cover_preview_png(child_name: str, size_px: int = 900) -> bytes:
    """Fast, reliable front-cover preview as PNG for UI."""
    img = Image.new("RGB", (size_px, size_px), "white")
    d = ImageDraw.Draw(img)

    cx, cy = size_px // 2, int(size_px * 0.47)
    r = int(size_px * 0.20)

    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline="black", width=max(4, r // 12), fill="white")
    d.rounded_rectangle(
        (cx - int(r * 0.12), cy + int(r * 0.30), cx + int(r * 0.12), cy + int(r * 0.55)),
        radius=10,
        fill=EDDIE_PURPLE,
    )

    d.text((size_px * 0.5, size_px * 0.84), "EDDIES", fill="black", anchor="mm")
    d.text((size_px * 0.5, size_px * 0.90), f"& {child_name}", fill=(90, 90, 90), anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _cv_sketch_from_bytes(img_bytes: bytes) -> np.ndarray:
    """Bytes -> sketch array (grayscale)."""
    arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise RuntimeError("Bild konnte nicht dekodiert werden.")
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    inverted = 255 - gray
    blurred = cv2.GaussianBlur(inverted, (21, 21), 0)
    sketch = cv2.divide(gray, 255 - blurred, scale=256.0)
    return cv2.normalize(sketch, None, 0, 255, cv2.NORM_MINMAX)


def _center_crop_resize_square(pil_img: Image.Image, side_px: int) -> Image.Image:
    """Center crop to square and resize to exact px."""
    w, h = pil_img.size
    s = min(w, h)
    left = (w - s) // 2
    top = (h - s) // 2
    pil_img = pil_img.crop((left, top, left + s, top + s))
    return pil_img.resize((side_px, side_px), Image.LANCZOS)


def preflight_uploads_for_300dpi(uploads, kdp_print_mode: bool) -> tuple[int, int, int]:
    """
    Check if uploads likely meet 300 DPI needs for the selected mode.
    Returns (ok_count, warn_count, target_px_short_side).
    """
    page_w, page_h, _, _ = _page_geometry(kdp_print_mode)
    target_inch = min(page_w, page_h) / inch
    target_px = int(round(target_inch * DPI))
    ok, warn = 0, 0

    for up in uploads:
        try:
            up.seek(0)
            with Image.open(up) as img:
                w, h = img.size
            if min(w, h) >= target_px:
                ok += 1
            else:
                warn += 1
        except Exception:
            warn += 1

    return ok, warn, target_px


def _calc_spine_width_inch(page_count: int, paper_type: str) -> float:
    factor = PAPER_FACTORS.get(paper_type, PAPER_FACTORS["Schwarzweiß – Weiß"])
    return float(page_count) * float(factor)


def build_listing_text(child_name: str) -> str:
    title = f"Eddies & {child_name}"
    subtitle = (
        "24h Quest-Malbuch aus echten Momenten – "
        "Bewegung + Denken + Ausmalen (Personalisiertes Geschenk)"
    )
    keywords = [
        "Personalisiertes Malbuch Kinder",
        "Quest Buch Kinder",
        "24 Stunden Abenteuer Buch",
        "Bewegung und Denken Kinder",
        "Geschenk Kinder personalisiert",
        "Malbuch mit Fotos",
        "Eddies Quest",
    ]
    html = f"""<h3>24 Stunden. 24 Missionen. Dein Kind als Held.</h3>
<p>Aus deinen Fotos entstehen Ausmalbilder – und jede Seite enthält eine echte Mission:
<b>Bewegung</b> + <b>Denkaufgabe</b> + <b>XP</b> zum Abhaken.</p>
<ul>
  <li><b>Personalisiert:</b> Jede Seite basiert auf deinen hochgeladenen Bildern.</li>
  <li><b>Quest-System:</b> Zeit → Zone → Mission (Gamification ohne Wettbewerb).</li>
  <li><b>Profi-Druck:</b> Optimiert für 300 DPI, KDP-kompatibel.</li>
</ul>
<p><i>Eddies bleibt als schwarz-weißer Referenzpunkt mit purpurfarbener Zunge – dein Kind macht die Welt bunt.</i></p>
"""
    return "\n".join(
        [
            "READY-TO-PUBLISH LISTING BUNDLE (KDP)",
            f"TITEL: {title}",
            f"UNTERTITEL: {subtitle}",
            "",
            "KEYWORDS (7 Felder):",
            "\n".join([f"{i+1}. {k}" for i, k in enumerate(keywords)]),
            "",
            "BESCHREIBUNG (HTML):",
            html,
        ]
    )

# =========================================================
# 4) QUEST RENDERING (ON EACH PHOTO PAGE)
# =========================================================
def _text_color_for_rgb(rgb01):
    r, g, b = rgb01
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return colors.white if lum < 0.45 else colors.black


def _draw_quest_overlay(
    c: canvas.Canvas,
    page_w: float,
    page_h: float,
    safe: float,
    hour: int,
    mission: qd.Mission,
):
    # Header band
    header_h = 0.75 * inch
    x0 = safe
    y0 = page_h - safe - header_h
    w = page_w - 2 * safe

    zone = qd.get_zone_for_hour(hour)
    zone_rgb = qd.get_hour_color(hour)
    fill = colors.Color(zone_rgb[0], zone_rgb[1], zone_rgb[2])
    tc = _text_color_for_rgb(zone_rgb)

    c.saveState()
    c.setFillColor(fill)
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    c.rect(x0, y0, w, header_h, fill=1, stroke=1)

    c.setFillColor(tc)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(
        x0 + 0.18 * inch,
        y0 + header_h - 0.50 * inch,
        f"{qd.fmt_hour(hour)}  {zone.icon}  {zone.name}",
    )

    c.setFont("Helvetica", 10)
    c.drawString(x0 + 0.18 * inch, y0 + 0.18 * inch, f"{zone.quest_type} • {zone.atmosphere}")

    # Mission card bottom
    card_h = 2.05 * inch
    cy = safe
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.black)
    c.rect(x0, cy, w, card_h, fill=1, stroke=1)

    # Mission title + XP
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(x0 + 0.18 * inch, cy + card_h - 0.45 * inch, f"MISSION: {mission.title}")
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(x0 + w - 0.18 * inch, cy + card_h - 0.45 * inch, f"+{mission.xp} XP")

    # Movement / Thinking
    c.setFont("Helvetica-Bold", 10)
    c.drawString(x0 + 0.18 * inch, cy + card_h - 0.85 * inch, "BEWEGUNG:")
    c.setFont("Helvetica", 10)
    c.drawString(x0 + 1.05 * inch, cy + card_h - 0.85 * inch, mission.movement)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(x0 + 0.18 * inch, cy + card_h - 1.20 * inch, "DENKEN:")
    c.setFont("Helvetica", 10)
    c.drawString(x0 + 0.90 * inch, cy + card_h - 1.20 * inch, mission.thinking)

    # Proof checkbox line
    box = 0.20 * inch
    bx = x0 + 0.18 * inch
    by = cy + 0.35 * inch
    c.setStrokeColor(colors.black)
    c.rect(bx, by, box, box, fill=0, stroke=1)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(bx + box + 0.15 * inch, by + 0.02 * inch, f"PROOF: {mission.proof}")

    c.restoreState()


# =========================================================
# 5) INTERIOR PAGES (INTRO/OUTRO + DPI GUARD + QUEST)
# =========================================================
def _draw_intro_page(c: canvas.Canvas, child_name: str, page_w: float, page_h: float, safe: float):
    c.setFillColor(colors.white)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)
    top = page_h - safe
    bottom = safe

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(page_w / 2, top - 0.65 * inch, "Willkommen bei Eddies")

    c.setFont("Helvetica", 22)
    c.drawCentredString(page_w / 2, top - 1.25 * inch, f"& {child_name}")

    r = min(1.35 * inch, (page_w - 2 * safe) * 0.18)
    _draw_eddie_brand_pdf(c, page_w / 2, (bottom + top) / 2 + 0.1 * inch, r)

    c.setFont("Helvetica-Oblique", 14)
    c.setFillColor(colors.grey)
    c.drawCentredString(page_w / 2, bottom + 0.75 * inch, "24 Stunden • 24 Missionen • Haken setzen • XP sammeln")


def _draw_outro_page(c: canvas.Canvas, child_name: str, page_w: float, page_h: float, safe: float):
    c.setFillColor(colors.white)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)
    top = page_h - safe
    bottom = safe

    r = min(1.55 * inch, (page_w - 2 * safe) * 0.20)
    _draw_eddie_brand_pdf(c, page_w / 2, (bottom + top) / 2 + 0.6 * inch, r)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 30)
    c.drawCentredString(page_w / 2, bottom + 1.75 * inch, "Quest abgeschlossen!")

    c.setFont("Helvetica", 16)
    c.setFillColor(colors.grey)
    c.drawCentredString(page_w / 2, bottom + 1.25 * inch, f"Gut gemacht, {child_name}!")


def _draw_dpi_guard_page(
    c: canvas.Canvas,
    page_w: float,
    page_h: float,
    safe: float,
    ok_ct: int,
    warn_ct: int,
    target_px: int,
    total_uploads: int,
):
    c.setFillColor(colors.white)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    left = safe
    top = page_h - safe
    bottom = safe

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(left, top - 0.35 * inch, "QUALITÄTS-CHECK (Preview)")

    c.setFont("Helvetica", 12)
    c.setFillColor(colors.grey)
    c.drawString(left, top - 0.70 * inch, "Nur Preview. Für KDP bitte Print Mode aktivieren.")

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 12)
    c.drawString(left, top - 1.15 * inch, f"Uploads: {total_uploads}")
    c.drawString(left, top - 1.45 * inch, f"Ziel: ≥ {target_px}px (kürzere Seite) @ {DPI} DPI")
    c.drawString(left, top - 1.75 * inch, f"OK: {ok_ct}  |  Warnung: {warn_ct}")

    if warn_ct > 0:
        c.setFillColor(colors.red)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(left, bottom + 1.35 * inch, "WARNUNG: Einige Fotos sind wahrscheinlich zu klein.")
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 12)
        c.drawString(left, bottom + 0.95 * inch, "Empfehlung: größere Fotos nutzen oder weniger Crop.")
    else:
        c.setFillColor(colors.green)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(left, bottom + 1.35 * inch, "OK: Fotos erfüllen voraussichtlich die 300-DPI-Anforderung.")


def build_interior_pdf(
    child_name: str,
    uploads,
    page_count_kdp: int,
    eddie_inside: bool,
    kdp_print_mode: bool,
    include_intro: bool,
    include_outro: bool,
    preflight_ok: int,
    preflight_warn: int,
    preflight_target_px: int,
    quest_start_hour: int,
    quest_difficulty: int,
) -> bytes:
    page_w, page_h, _, safe = _page_geometry(kdp_print_mode)
    side_px = int(round((min(page_w, page_h) / inch) * DPI))

    files = list(uploads)
    if not files:
        raise RuntimeError("Bitte mindestens 1 Foto hochladen.")

    fixed = int(include_intro) + int(include_outro)
    photo_pages_count = max(1, page_count_kdp - fixed)

    # Deterministic base seed (depends on name + file signatures)
    signature = [f"{_sanitize_filename(getattr(u, 'name', 'img'))}:{getattr(u, 'size', 0)}" for u in files]
    base_seed_bytes = (child_name.strip() + "|" + "|".join(signature)).encode("utf-8", errors="ignore")
    random.seed(base_seed_bytes)

    # Deterministic repetition/shuffle to fill pages
    final = list(files)
    while len(final) < photo_pages_count:
        tmp = list(files)
        random.shuffle(tmp)
        final.extend(tmp)
    final = final[:photo_pages_count]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))

    # Preview-only QA page
    if (not kdp_print_mode) and (preflight_warn > 0):
        _draw_dpi_guard_page(c, page_w, page_h, safe, preflight_ok, preflight_warn, preflight_target_px, len(files))
        c.showPage()

    if include_intro:
        _side = _normalize_page_count(24, True, True)  # no-op, keeps structure stable
        _draw_intro_page(c, child_name, page_w, page_h, safe)
        c.showPage()

    # Photo pages + Quest overlay
    for i, up in enumerate(final):
        try:
            up.seek(0)
            img_bytes = up.read()
            sketch_arr = _cv_sketch_from_bytes(img_bytes)
            pil = Image.fromarray(sketch_arr).convert("L")
            pil = _center_crop_resize_square(pil, side_px)
            c.drawImage(ImageReader(pil), 0, 0, width=page_w, height=page_h)
        except Exception:
            c.setFillColor(colors.white)
            c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

        hour = (int(quest_start_hour) + i) % 24

        # Deterministic mission selection per page
        seed_int = (
            int.from_bytes(base_seed_bytes[:8].ljust(8, b"\0"), "big", signed=False)
            ^ (hour * 1_000_003)
            ^ (i * 97)
            ^ (int(quest_difficulty) * 10_000_019)
        )
        mission = qd.pick_mission_for_time(hour=hour, difficulty=int(quest_difficulty), seed=int(seed_int))

        _draw_quest_overlay(c, page_w, page_h, safe, hour, mission)

        if eddie_inside:
            _draw_eddie_brand_pdf(c, page_w - safe, safe + 2.25 * inch, 0.18 * inch)

        c.showPage()

    if include_outro:
        _draw_outro_page(c, child_name, page_w, page_h, safe)
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()

# =========================================================
# 6) COVER
# =========================================================
def build_cover_wrap_pdf(child_name: str, page_count: int, paper_type: str) -> bytes:
    spine_w = _calc_spine_width_inch(page_count, paper_type) * inch
    cov_w = (2 * TRIM) + spine_w + (2 * BLEED)
    cov_h = TRIM + (2 * BLEED)

    back_x0 = BLEED
    spine_x0 = BLEED + TRIM
    front_x0 = BLEED + TRIM + spine_w

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(cov_w, cov_h))

    c.setFillColor(colors.white)
    c.rect(0, 0, cov_w, cov_h, fill=1, stroke=0)

    # BACK
    safe_x = back_x0 + COVER_SAFE
    safe_y = BLEED + COVER_SAFE
    safe_h = TRIM - 2 * COVER_SAFE

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 12)
    c.drawString(safe_x, safe_y + safe_h - 14, "Eddies")

    c.setFont("Helvetica", 10)
    c.setFillColor(colors.grey)
    c.drawString(safe_x, safe_y + safe_h - 30, "24h Quest-Malbuch")

    # Barcode keepout
    box_w, box_h = 2.0 * inch, 1.2 * inch
    box_x = back_x0 + TRIM - COVER_SAFE - box_w
    box_y = BLEED + COVER_SAFE
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(1)
    c.rect(box_x, box_y, box_w, box_h, fill=0, stroke=1)
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.lightgrey)
    c.drawCentredString(box_x + box_w / 2, box_y + box_h / 2 - 3, "Barcode area (KDP)")

    # SPINE
    c.setFillColor(colors.black)
    c.rect(spine_x0, BLEED, spine_w, TRIM, fill=1, stroke=0)

    if page_count >= SPINE_TEXT_MIN_PAGES and spine_w >= 0.08 * inch:
        c.saveState()
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.translate(spine_x0 + spine_w / 2, BLEED + TRIM / 2)
        c.rotate(90)
        c.drawCentredString(0, -4, f"EDDIES & {child_name}".upper())
        c.restoreState()
    else:
        _draw_eddie_brand_pdf(
            c,
            spine_x0 + spine_w / 2,
            BLEED + TRIM / 2,
            r=min(0.18 * inch, max(spine_w, 0.06 * inch) * 0.35),
        )

    # FRONT
    _draw_eddie_brand_pdf(c, front_x0 + TRIM / 2, BLEED + TRIM * 0.58, r=TRIM * 0.18)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 44)
    c.drawCentredString(front_x0 + TRIM / 2, BLEED + TRIM * 0.80, "EDDIES")
    c.setFont("Helvetica", 18)
    c.drawCentredString(front_x0 + TRIM / 2, BLEED + TRIM * 0.73, f"& {child_name}")

    c.setFont("Helvetica", 12)
    c.setFillColor(colors.grey)
    c.drawCentredString(front_x0 + TRIM / 2, BLEED + TRIM * 0.18, "24h Quest-Malbuch")

    c.save()
    buf.seek(0)
    return buf.getvalue()

# =========================================================
# 7) SESSION STATE
# =========================================================
if "assets" not in st.session_state:
    st.session_state.assets = None

# =========================================================
# 8) UI
# =========================================================
st.markdown(
    f"""
<div class="kpi-container">
  <span class="kpi">Quest: 24h System</span>
  <span class="kpi">Anschnitt 0,125″</span>
  <span class="kpi">{DPI} DPI</span>
</div>
""",
    unsafe_allow_html=True,
)

with st.container(border=True):
    col1, col2 = st.columns(2)

    with col1:
        child_name = st.text_input("Vorname des Kindes", value="Eddie", placeholder="z.B. Lukas")
        child_age = st.number_input("Alter des Kindes", min_value=3, max_value=99, value=4, step=1)

    with col2:
        user_page_count = st.number_input("Seitenanzahl (Innen)", min_value=1, max_value=300, value=DEFAULT_PAGES, step=1)

    paper_type = st.selectbox("Papier-Typ (Spine)", options=list(PAPER_FACTORS.keys()), index=0)
    kdp_print_mode = st.toggle("KDP-Druckmodus (Trim + Bleed)", value=True)

    # Quest Controls
    c3, c4 = st.columns(2)
    with c3:
        quest_start_hour = st.number_input("Quest-Startzeit (Stunde)", min_value=0, max_value=23, value=6, step=1)
    with c4:
        quest_difficulty = _difficulty_from_age(int(child_age))
        st.markdown("**Quest-Schwierigkeit (auto)**")
        st.caption(f"Alter {int(child_age)} → Stufe **{quest_difficulty}** (1–5)")

    include_intro = st.toggle("Intro-Seite", value=True)
    include_outro = st.toggle("Outro-Seite", value=True)
    eddie_inside = st.toggle("Eddies-Marke extra einblenden", value=False)

    uploads = st.file_uploader("Fotos hochladen (min. 1)", accept_multiple_files=True, type=["jpg", "png"])

    normalized_pages = _normalize_page_count(int(user_page_count), include_intro, include_outro)
    fixed = int(include_intro) + int(include_outro)
    photo_pages_hint = max(1, normalized_pages - fixed)

    page_w, page_h, _, _ = _page_geometry(bool(kdp_print_mode))
    target_px_hint = int(round((min(page_w, page_h) / inch) * DPI))

    st.caption(
        f"Forced Compliance: **{normalized_pages} Seiten** (min. 24, gerade). "
        f"Davon **{photo_pages_hint}** Quest-Foto-Seiten + **{fixed}** Sonderseiten. "
        f"300DPI Ziel: **~{target_px_hint}px** (kürzere Seite)."
    )

    if normalized_pages != int(user_page_count):
        st.info(f"Seitenzahl wird automatisch angepasst: {int(user_page_count)} → {normalized_pages}")

can_build = bool(child_name.strip()) and bool(uploads)

# =========================================================
# 9) BUILD
# =========================================================
if st.button("🚀 Questbuch generieren", disabled=not can_build):
    if not can_build:
        st.warning("Bitte Name eingeben und mindestens 1 Foto hochladen.")
    else:
        progress = st.progress(0, text="Starte Build…")
        with st.spinner("Preflight, Interior, Cover, Listing, ZIP…"):
            page_count_kdp = _normalize_page_count(int(user_page_count), include_intro, include_outro)

            progress.progress(15, text="Preflight…")
            ok_ct, warn_ct, target_px = preflight_uploads_for_300dpi(uploads, bool(kdp_print_mode))

            progress.progress(45, text="Interior (Quest)…")
            interior_pdf = build_interior_pdf(
                child_name.strip(),
                uploads,
                page_count_kdp,
                bool(eddie_inside),
                bool(kdp_print_mode),
                bool(include_intro),
                bool(include_outro),
                preflight_ok=ok_ct,
                preflight_warn=warn_ct,
                preflight_target_px=target_px,
                quest_start_hour=int(quest_start_hour),
                quest_difficulty=int(quest_difficulty),
            )

            progress.progress(70, text="CoverWrap…")
            cover_pdf = build_cover_wrap_pdf(child_name.strip(), int(page_count_kdp), paper_type)

            progress.progress(82, text="Cover Preview…")
            preview_png = build_front_cover_preview_png(child_name.strip(), size_px=900)

            progress.progress(90, text="Listing…")
            listing_txt = build_listing_text(child_name.strip())

            progress.progress(96, text="ZIP…")
            today = datetime.now().date().isoformat()
            base = _sanitize_filename(child_name.strip())
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr(f"Interior_{base}_{today}.pdf", interior_pdf)
                z.writestr(f"CoverWrap_{base}_{today}.pdf", cover_pdf)
                z.writestr(f"Listing_{base}_{today}.txt", listing_txt)

            zip_buf.seek(0)

            st.session_state.assets = {
                "zip": zip_buf.getvalue(),
                "interior": interior_pdf,
                "cover": cover_pdf,
                "preview": preview_png,
                "listing": listing_txt,
                "ok": ok_ct,
                "warn": warn_ct,
                "target_px": target_px,
                "name": child_name.strip(),
                "date": today,
                "kdp_mode": bool(kdp_print_mode),
                "pages_kdp": int(page_count_kdp),
                "age": int(child_age),
                "difficulty": int(quest_difficulty),
            }

            progress.progress(100, text="Fertig ✅")

        st.success("Questbuch-Assets erfolgreich generiert!")

# =========================================================
# 10) OUTPUT
# =========================================================
if st.session_state.assets:
    a = st.session_state.assets

    with st.container(border=True):
        st.markdown("### 👀 Vorschau & Qualitätscheck")

        c1, c2 = st.columns([1, 1], gap="large")
        with c1:
            st.image(a["preview"], caption="Front-Cover Vorschau", use_container_width=True)

        with c2:
            st.markdown("**Preflight:**")
            st.write(f"KDP-Seiten (forced): **{a['pages_kdp']}**")
            st.write(f"Alter: **{a['age']}**  |  Quest-Stufe (auto): **{a['difficulty']}**")
            st.write(f"Ziel-Auflösung (kürzere Seite): **≥ {a['target_px']}px** (@ {DPI} DPI)")
            st.success(f"✅ {a['ok']} Foto(s) erfüllen das Ziel")

            if a["warn"] > 0:
                if a.get("kdp_mode", False):
                    st.warning("⚠️ Einige Fotos sind wahrscheinlich zu klein – KDP-Export wird trotzdem erzeugt, kann aber weicher wirken.")
                else:
                    st.warning("⚠️ Einige Fotos sind wahrscheinlich zu klein – im Preview wird eine QA-Seite eingefügt (nur Preview).")

        st.divider()
        st.markdown("### 📥 Downloads")

        st.download_button(
            "📦 Download: Komplettpaket (ZIP)",
            data=a["zip"],
            file_name=f"Eddies_Quest_Set_{_sanitize_filename(a['name'])}_{a['date']}.zip",
            mime="application/zip",
        )

        d1, d2 = st.columns(2)
        with d1:
            st.download_button(
                "📘 Interior PDF",
                data=a["interior"],
                file_name=f"Interior_{_sanitize_filename(a['name'])}_{a['date']}.pdf",
                mime="application/pdf",
            )
        with d2:
            st.download_button(
                "🎨 CoverWrap PDF",
                data=a["cover"],
                file_name=f"CoverWrap_{_sanitize_filename(a['name'])}_{a['date']}.pdf",
                mime="application/pdf",
            )

    with st.expander("📦 Listing.txt (Copy & Paste)", expanded=True):
        st.code(a["listing"], language="text")

st.markdown(
    f"<div style='text-align:center; margin-top:32px; color:#6b7280; font-size:0.85rem;'>"
    f"Eddies • <a href='{HUB_URL}' target='_blank' style='color:#6b7280;'>Hub</a>"
    f"</div>",
    unsafe_allow_html=True,
)
