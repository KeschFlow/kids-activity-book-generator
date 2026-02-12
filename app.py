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

# =========================================================
# 1) BUSINESS & KDP CONFIG (NO APIs REQUIRED)
# =========================================================
APP_TITLE = "Eddies"
APP_ICON = "🐶"

EDDIE_PURPLE = "#7c3aed"  # Markenfarbe (Zunge)

DPI = 300
TRIM_IN = 8.5
TRIM = TRIM_IN * inch
BLEED = 0.125 * inch
SAFE_INTERIOR = 0.375 * inch

DEFAULT_PAGES = 24
KDP_MIN_PAGES = 24

# Cover / Spine
PAPER_FACTORS = {
    "Schwarzweiß – Weiß": 0.002252,
    "Schwarzweiß – Creme": 0.0025,
    "Farbe – Weiß": 0.002347,
}
SPINE_TEXT_MIN_PAGES = 79
COVER_SAFE = 0.25 * inch

HUB_URL = "https://eddieswelt.de"

# =========================================================
# 2) STREAMLIT CONFIG + STYLING (SAFE)
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
st.markdown(
    "<div class='subtitle'>Dein 1-Klick KDP-Publishing-Set: Interior + CoverWrap + Listing-Texte</div>",
    unsafe_allow_html=True,
)

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


def _draw_eddie_brand_pdf(c: canvas.Canvas, cx: float, cy: float, r: float):
    """Minimal Eddie: B/W + purple tongue."""
    c.saveState()
    c.setLineWidth(max(2, r * 0.06))
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.white)
    c.circle(cx, cy, r, stroke=1, fill=1)

    c.setFillColor(colors.black)
    c.circle(cx - r * 0.28, cy + r * 0.15, r * 0.10, stroke=0, fill=1)
    c.circle(cx + r * 0.28, cy + r * 0.15, r * 0.10, stroke=0, fill=1)

    c.setLineWidth(max(2, r * 0.05))
    c.arc(cx - r * 0.35, cy - r * 0.10, cx + r * 0.35, cy + r * 0.20, 200, 140)

    c.setFillColor(colors.HexColor(EDDIE_PURPLE))
    c.roundRect(cx - r * 0.10, cy - r * 0.35, r * 0.20, r * 0.22, r * 0.08, stroke=0, fill=1)
    c.restoreState()


def build_front_cover_preview_png(child_name: str, size_px: int = 900) -> bytes:
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

    d.text((size_px * 0.5, size_px * 0.84), "EDDIE", fill="black", anchor="mm")
    d.text((size_px * 0.5, size_px * 0.90), f"& {child_name}", fill=(90, 90, 90), anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _cv_sketch_from_bytes(img_bytes: bytes) -> np.ndarray:
    arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise RuntimeError("Bild konnte nicht dekodiert werden.")
    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    inverted = 255 - gray
    blurred = cv2.GaussianBlur(inverted, (21, 21), 0)
    sketch = cv2.divide(gray, 255 - blurred, scale=256.0)
    sketch = cv2.normalize(sketch, None, 0, 255, cv2.NORM_MINMAX)
    return sketch


def _center_crop_resize_square(pil_img: Image.Image, side_px: int) -> Image.Image:
    w, h = pil_img.size
    s = min(w, h)
    left = (w - s) // 2
    top = (h - s) // 2
    pil_img = pil_img.crop((left, top, left + s, top + s))
    pil_img = pil_img.resize((side_px, side_px), Image.LANCZOS)
    return pil_img


def preflight_uploads_for_300dpi(uploads, kdp_print_mode: bool) -> tuple[int, int, int]:
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
    title = f"Eddie & {child_name}"
    subtitle = (
        "Mein ganz persönliches Malbuch aus echten Momenten – "
        "Ein kreatives Abenteuer für Kinder ab 4 Jahren (Personalisiertes Geschenk)"
    )
    keywords = [
        "Personalisiertes Malbuch Kinder",
        "Malbuch mit eigenen Fotos",
        "Geschenk Schulanfang Junge Mädchen",
        "Kreativbuch personalisiert",
        "Fotogeschenk Kinder kreativ",
        "Eddie Malbuch Terrier",
        "Malen nach Fotos Abenteuer",
    ]
    html = f"""<h3>Lasse deine schönsten Momente lebendig werden!</h3>
<p>Was passiert, wenn deine eigenen Fotos zu magischen Ausmalbildern werden?
<b>Eddie</b> begleitet dich auf einer ganz besonderen Reise – und <b>{child_name}</b> steht im Mittelpunkt dieses Abenteuers.</p>

<p>In diesem Buch ist nichts gewöhnlich:</p>
<ul>
  <li><b>Vollständig personalisiert:</b> Jede Seite basiert auf deinen hochgeladenen Bildern.</li>
  <li><b>Eddie ist immer dabei:</b> Der treue schwarz-weiße Terrier führt dich durch das Buch.</li>
  <li><b>Viel Platz für Fantasie:</b> Große Flächen laden zum Ausmalen ein.</li>
  <li><b>Professionell druckfertig:</b> Optimiert für 300 DPI Druckqualität.</li>
</ul>
<p><i>Hinweis: Eddie bleibt in seinem klassischen Look (schwarz-weiß mit purpurfarbener Zunge) – du gestaltest die Welt um ihn herum bunt!</i></p>
"""
    aplus = (
        "A+ Content Blueprint (3 Banner):\n"
        "1) Header: Foto vs. Ausmalseite (Transformation)\n"
        "2) Eddie Brand: Eddie Close-up (B/W + purpur Zunge)\n"
        "3) Qualität: 300 DPI Linien-Detail (Profi-Druck)\n"
    )
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
            "",
            aplus,
        ]
    )


# =========================================================
# 4) INTERIOR PAGES (INTRO/OUTRO + DPI GUARD PAGE)
# =========================================================
def _draw_intro_page(c: canvas.Canvas, child_name: str, page_w: float, page_h: float, safe: float):
    c.setFillColor(colors.white)
    c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

    top = page_h - safe
    bottom = safe

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 34)
    c.drawCentredString(page_w / 2, top - 0.65 * inch, "Willkommen bei Eddie")

    c.setFont("Helvetica", 22)
    c.drawCentredString(page_w / 2, top - 1.25 * inch, f"& {child_name}")

    r = min(1.35 * inch, (page_w - 2 * safe) * 0.18)
    _draw_eddie_brand_pdf(c, page_w / 2, (bottom + top) / 2 + 0.1 * inch, r)

    c.setFont("Helvetica-Oblique", 14)
    c.setFillColor(colors.grey)
    c.drawCentredString(page_w / 2, bottom + 0.55 * inch, "Male dieses Abenteuer in deinen Farben aus!")


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
    right = page_w - safe
    top = page_h - safe
    bottom = safe

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 26)
    c.drawString(left, top - 0.35 * inch, "QUALITÄTS-CHECK (Preview)")

    c.setFont("Helvetica", 12)
    c.setFillColor(colors.grey)
    c.drawString(left, top - 0.70 * inch, "Diese Seite wird nur im Preview-Modus eingefügt und ist NICHT für KDP-Upload gedacht.")

    box_h = 2.15 * inch
    box_y = top - 0.95 * inch - box_h
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(1)
    c.rect(left, box_y, (right - left), box_h, fill=0, stroke=1)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(left + 0.25 * inch, box_y + box_h - 0.45 * inch, "DPI Preflight Ergebnis")

    c.setFont("Helvetica", 12)
    c.drawString(left + 0.25 * inch, box_y + box_h - 0.85 * inch, f"Uploads: {total_uploads}")
    c.drawString(left + 0.25 * inch, box_y + box_h - 1.15 * inch, f"Ziel (kürzere Seite): ≥ {target_px}px (@ {DPI} DPI)")
    c.drawString(left + 0.25 * inch, box_y + box_h - 1.45 * inch, f"OK: {ok_ct}  |  Warnung: {warn_ct}")

    if warn_ct > 0:
        c.setFillColor(colors.red)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(left, bottom + 1.35 * inch, "WARNUNG: Einige Fotos sind wahrscheinlich zu klein für vollen Druck-Anschnitt.")
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 12)
        c.drawString(left, bottom + 0.95 * inch, "Empfehlung: Nutze größere Fotos oder weniger Crop (Original höher auflösen).")
    else:
        c.setFillColor(colors.green)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(left, bottom + 1.35 * inch, "OK: Deine Fotos erfüllen voraussichtlich die 300-DPI-Anforderung.")
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 12)
        c.drawString(left, bottom + 0.95 * inch, "Du kannst jetzt in den KDP-Druckmodus wechseln und final exportieren.")


# =========================================================
# 5) BUILD ENGINES
# =========================================================
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
) -> bytes:
    page_w, page_h, _, safe = _page_geometry(kdp_print_mode)
    side_px = int(round((min(page_w, page_h) / inch) * DPI))

    files = list(uploads)
    if not files:
        raise RuntimeError("Bitte mindestens 1 Foto hochladen.")

    fixed = int(include_intro) + int(include_outro)
    photo_pages_count = max(1, page_count_kdp - fixed)

    signature = []
    for u in files:
        signature.append(f"{_sanitize_filename(getattr(u, 'name', 'img'))}:{getattr(u, 'size', 0)}")
    random.seed((child_name.strip() + "|" + "|".join(signature)).encode("utf-8", errors="ignore"))

    final = list(files)
    while len(final) < photo_pages_count:
        tmp = list(files)
        random.shuffle(tmp)
        final.extend(tmp)
    final = final[:photo_pages_count]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))

    if (not kdp_print_mode) and (preflight_warn > 0):
        _draw_dpi_guard_page(
            c=c,
            page_w=page_w,
            page_h=page_h,
            safe=safe,
            ok_ct=preflight_ok,
            warn_ct=preflight_warn,
            target_px=preflight_target_px,
            total_uploads=len(files),
        )
        c.showPage()

    if include_intro:
        _draw_intro_page(c, child_name, page_w, page_h, safe)
        c.showPage()

    for up in final:
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

        if eddie_inside:
            _draw_eddie_brand_pdf(c, page_w - safe, safe, 0.20 * inch)

        c.showPage()

    if include_outro:
        _draw_outro_page(c, child_name, page_w, page_h, safe)
        c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()


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

    safe_x = back_x0 + COVER_SAFE
    safe_y = BLEED + COVER_SAFE
    safe_h = TRIM - 2 * COVER_SAFE

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 12)
    c.drawString(safe_x, safe_y + safe_h - 14, "Eddie’s Welt")

    c.setFont("Helvetica", 10)
    c.setFillColor(colors.grey)
    c.drawString(safe_x, safe_y + safe_h - 30, "Erstellt mit dem Eddie Publishing System")

    box_w, box_h = 2.0 * inch, 1.2 * inch
    box_x = back_x0 + TRIM - COVER_SAFE - box_w
    box_y = BLEED + COVER_SAFE
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(1)
    c.rect(box_x, box_y, box_w, box_h, fill=0, stroke=1)
    c.setFont("Helvetica", 7)
    c.setFillColor(colors.lightgrey)
    c.drawCentredString(box_x + box_w / 2, box_y + box_h / 2 - 3, "Barcode area (KDP)")

    c.setFillColor(colors.black)
    c.rect(spine_x0, BLEED, spine_w, TRIM, fill=1, stroke=0)

    if page_count >= SPINE_TEXT_MIN_PAGES and spine_w >= 0.08 * inch:
        c.saveState()
        c.setFillColor(colors.white)
        c.setFont("Helvetica-Bold", 10)
        c.translate(spine_x0 + spine_w / 2, BLEED + TRIM / 2)
        c.rotate(90)
        c.drawCentredString(0, -4, f"EDDIE & {child_name}".upper())
        c.restoreState()
    else:
        _draw_eddie_brand_pdf(
            c,
            spine_x0 + spine_w / 2,
            BLEED + TRIM / 2,
            r=min(0.18 * inch, max(spine_w, 0.06 * inch) * 0.35),
        )

    _draw_eddie_brand_pdf(c, front_x0 + TRIM / 2, BLEED + TRIM * 0.58, r=TRIM * 0.18)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 44)
    c.drawCentredString(front_x0 + TRIM / 2, BLEED + TRIM * 0.80, "EDDIE")

    c.setFont("Helvetica", 18)
    c.drawCentredString(front_x0 + TRIM / 2, BLEED + TRIM * 0.73, f"& {child_name}")

    c.setFont("Helvetica", 12)
    c.setFillColor(colors.grey)
    c.drawCentredString(front_x0 + TRIM / 2, BLEED + TRIM * 0.18, "Dein persönliches Malbuch aus echten Momenten")

    c.save()
    buf.seek(0)
    return buf.getvalue()


# =========================================================
# 6) SESSION STATE INIT
# =========================================================
if "assets" not in st.session_state:
    st.session_state.assets = None


# =========================================================
# 7) UI INPUTS
# =========================================================
st.markdown(
    f"""
<div class="kpi-container">
  <span class="kpi">8,5″ × 8,5″</span>
  <span class="kpi">Anschnitt 0,125″</span>
  <span class="kpi">{DPI} DPI druckfertig</span>
</div>
""",
    unsafe_allow_html=True,
)

with st.container(border=True):
    col1, col2 = st.columns(2)
    with col1:
        child_name = st.text_input("Vorname des Kindes", value="Eddie", placeholder="z.B. Lukas")
    with col2:
        user_page_count = st.number_input(
            "Seitenanzahl (User-Eingabe)",
            min_value=1,
            max_value=300,
            value=DEFAULT_PAGES,
            step=1,
        )

    paper_type = st.selectbox("Papier-Typ (Spine-Berechnung)", options=list(PAPER_FACTORS.keys()), index=0)

    kdp_print_mode = st.toggle("KDP-Druckmodus (Trim + Bleed)", value=True)
    include_intro = st.toggle("Intro-Seite (Willkommen)", value=True)
    include_outro = st.toggle("Outro-Seite (Quest abgeschlossen)", value=True)

    eddie_inside = st.toggle("Eddie-Marke auf Foto-Seiten (unten rechts)", value=False)
    uploads = st.file_uploader("Fotos hochladen (min. 1)", accept_multiple_files=True, type=["jpg", "png"])

    normalized_pages = _normalize_page_count(int(user_page_count), include_intro, include_outro)
    fixed = int(include_intro) + int(include_outro)
    photo_pages_hint = max(1, normalized_pages - fixed)

    page_w, page_h, _, _ = _page_geometry(kdp_print_mode)
    target_px_hint = int(round((min(page_w, page_h) / inch) * DPI))

    st.caption(
        f"Forced Compliance aktiv: **{normalized_pages} Seiten** (min. 24, gerade Zahl). "
        f"Aktuell: **{photo_pages_hint}** Foto-Seiten + **{fixed}** Sonderseiten. "
        f"Für volle {DPI}-DPI-Schärfe sollten Fotos mindestens **~{target_px_hint}px** an der kürzeren Seite haben."
    )

    if normalized_pages != int(user_page_count):
        st.info(f"Seitenzahl wird automatisch angepasst: {int(user_page_count)} → {normalized_pages}")

can_build = bool(child_name.strip()) and bool(uploads)

# =========================================================
# 8) BUILD
# =========================================================
if st.button("🚀 Publishing-Paket generieren", disabled=not can_build):
    if not can_build:
        st.warning("Bitte Name eingeben und mindestens 1 Foto hochladen.")
    else:
        progress = st.progress(0, text="Starte Build…")
        with st.spinner("Erstelle Preflight, Interior, CoverWrap, Listing & ZIP…"):
            page_count_kdp = _normalize_page_count(int(user_page_count), include_intro, include_outro)

            progress.progress(15, text="Preflight-Check…")
            ok_ct, warn_ct, target_px = preflight_uploads_for_300dpi(uploads, kdp_print_mode)

            progress.progress(40, text="Render: Interior PDF…")
            interior_pdf = build_interior_pdf(
                child_name.strip(),
                uploads,
                page_count_kdp,
                eddie_inside,
                kdp_print_mode,
                include_intro,
                include_outro,
                preflight_ok=ok_ct,
                preflight_warn=warn_ct,
                preflight_target_px=target_px,
            )

            progress.progress(65, text="Render: CoverWrap PDF…")
            cover_pdf = build_cover_wrap_pdf(child_name.strip(), page_count_kdp, paper_type)

            progress.progress(75, text="Erzeuge Cover-Vorschau…")
            preview_png = build_front_cover_preview_png(child_name.strip(), size_px=900)

            progress.progress(85, text="Erzeuge Listing-Bundle…")
            listing_txt = build_listing_text(child_name.strip())

            progress.progress(95, text="Packe ZIP…")
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
                "kdp_mode": kdp_print_mode,
                "intro": include_intro,
                "outro": include_outro,
                "pages_kdp": page_count_kdp,
                "pages_user": int(user_page_count),
            }

            progress.progress(100, text="Fertig ✅")

        st.success("Assets erfolgreich generiert!")

# =========================================================
# 9) OUTPUT
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
            st.write(f"KDP-Seiten (forced): **{a['pages_kdp']}**  |  User-Eingabe: **{a['pages_user']}**")
            st.write(f"Ziel-Auflösung (kürzere Seite): **≥ {a['target_px']}px** (für den gewählten Modus @ {DPI} DPI)")
            st.success(f"✅ {a['ok']} Foto(s) erfüllen das Ziel")
            if a["warn"] > 0:
                st.warning("⚠️ Einige Fotos sind wahrscheinlich zu klein – im Preview wird eine QA-Seite eingefügt (nur Preview).")
            st.info(
                f"Modus: **{'KDP-Druckmodus (mit Bleed)' if a['kdp_mode'] else 'Preview (ohne Bleed)'}** · "
                f"Intro: **{'an' if a['intro'] else 'aus'}** · Outro: **{'an' if a['outro'] else 'aus'}**"
            )

        st.divider()
        st.markdown("### 📥 Downloads")

        st.download_button(
            "📦 Download: Komplettpaket (ZIP)",
            data=a["zip"],
            file_name=f"Eddie_Publishing_Set_{_sanitize_filename(a['name'])}_{a['date']}.zip",
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

    with st.expander("📦 Ready-to-Publish: KDP Listing-Paket (Copy & Paste)", expanded=True):
        st.info("Kopiere diese Texte direkt in dein Amazon KDP Listing.")
        st.code(a["listing"], language="text")

st.markdown(
    f"<div style='text-align:center; margin-top:32px; color:#6b7280; font-size:0.85rem;'>"
    f"Eddie’s Welt • <a href='{HUB_URL}' target='_blank' style='color:#6b7280;'>Zum Strategie-Hub</a>"
    f"</div>",
    unsafe_allow_html=True,
)
