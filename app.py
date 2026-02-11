import streamlit as st
import cv2
import os
import random
import tempfile
import re
from pathlib import Path
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from datetime import datetime

# =========================================================
# BUSINESS CONFIG (KDP PAPERBACK)
# =========================================================
TRIM_IN = 8.5
TRIM_SIZE = TRIM_IN * inch

BLEED = 0.125 * inch  # KDP bleed guidance: extend 0.125" beyond trim :contentReference[oaicite:1]{index=1}
INTERIOR_SAFE = 0.375 * inch  # for 24–150 pages with bleed: outside margin >= 0.375" :contentReference[oaicite:2]{index=2}

DPI = 300  # hard enforced for print assets
PAGES_DEFAULT = 24

# Paperback spine factors (KDP paperback cover calculator uses paper/ink based factors; we use B&W white) :contentReference[oaicite:3]{index=3}
PAPER_FACTORS = {
    "B&W – White": 0.002252,
    "B&W – Cream": 0.0025,
    "Color – White": 0.002347,
}

SPINE_TEXT_MIN_PAGES = 79  # KDP: only prints spine text on books with more than 79 pages :contentReference[oaicite:4]{index=4}

# Cover safety (practical): keep important content away from edges + barcode area
COVER_SAFE = 0.25 * inch

# Links & Monetization (soft gate – payment provider can be plugged in later)
HUB_URL = "https://eddieswelt.de"
PWYW_SUGGESTION = 9

# =========================================================
# STREAMLIT CONFIG
# =========================================================
st.set_page_config(page_title="Eddie’s Welt – Asset Generator", layout="centered", page_icon="🖤")

st.markdown(
    """
<style>
:root{
  --ink:#0b0b0f; --muted:#6b7280; --panel:#fafafa; --line:#e5e7eb; --accent:#7c3aed;
}
.main-title{font-size:2.2rem;font-weight:800;text-align:center;letter-spacing:-0.02em;color:var(--ink);}
.subtitle{text-align:center;font-size:1rem;color:var(--muted);margin-bottom:1.2rem;}
.card{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px;}
.small{font-size:.9rem;color:var(--muted);}
.hr{height:1px;background:var(--line);margin:18px 0;}
.footer{text-align:center;font-size:.85rem;color:var(--muted);margin-top:28px;}
.kpi{display:inline-block;padding:4px 10px;border-radius:999px;border:1px solid var(--line);font-size:.8rem;color:var(--muted);background:#fff;}
</style>
""",
    unsafe_allow_html=True,
)

# =========================================================
# HELPERS
# =========================================================
def _sanitize_filename(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("_") or "file"

def sort_uploads_smart(uploaded_list):
    # Keep simple + stable. (EXIF sorting can be added back if desired.)
    return list(uploaded_list or [])

def foto_zu_skizze(input_path, output_path) -> bool:
    try:
        img = cv2.imread(input_path)
        if img is None:
            return False
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        inverted = 255 - gray
        blurred = cv2.GaussianBlur(inverted, (21, 21), 0)
        sketch = cv2.divide(gray, 255 - blurred, scale=256.0)
        sketch = cv2.normalize(sketch, None, 0, 255, cv2.NORM_MINMAX)
        cv2.imwrite(output_path, sketch)
        return True
    except Exception:
        return False

def _img_force_square(src_path: str, out_path: str, side_px: int, quality: int = 95) -> bool:
    """Crop/resize to exact square pixels (print stable)."""
    try:
        im = Image.open(src_path).convert("L")
        iw, ih = im.size
        scale = max(side_px / iw, side_px / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        im = im.resize((nw, nh), Image.LANCZOS)
        left, top = (nw - side_px) // 2, (nh - side_px) // 2
        im = im.crop((left, top, left + side_px, top + side_px))
        im.save(out_path, "JPEG", quality=quality, optimize=True, progressive=True, subsampling=2)
        return True
    except Exception:
        return False

def _draw_eddie_mark(c: canvas.Canvas, cx: float, cy: float, r: float):
    """Minimal Eddie (B/W) + purple tongue as brand anchor."""
    c.saveState()
    c.setLineWidth(max(2, r * 0.06))
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.white)
    c.circle(cx, cy, r, stroke=1, fill=1)

    eye_r = r * 0.10
    c.setFillColor(colors.black)
    c.circle(cx - r * 0.28, cy + r * 0.15, eye_r, stroke=0, fill=1)
    c.circle(cx + r * 0.28, cy + r * 0.15, eye_r, stroke=0, fill=1)

    c.setLineWidth(max(2, r * 0.05))
    c.arc(cx - r * 0.35, cy - r * 0.10, cx + r * 0.35, cy + r * 0.20, 200, 140)

    c.setFillColor(colors.HexColor("#7c3aed"))
    c.roundRect(cx - r * 0.10, cy - r * 0.35, r * 0.20, r * 0.22, r * 0.08, stroke=0, fill=1)
    c.restoreState()

# =========================================================
# BUILD: INTERIOR PDF (KDP FULL BLEED SQUARE)
# =========================================================
def build_interior(sorted_files, child_name: str, pages: int = PAGES_DEFAULT) -> bytes:
    page_w = TRIM_SIZE + 2 * BLEED
    page_h = TRIM_SIZE + 2 * BLEED
    side_px = int(round((page_w / inch) * DPI))

    with tempfile.TemporaryDirectory() as temp_dir:
        raw_paths = []
        seed_parts = []

        for idx, up in enumerate(sorted_files):
            safe_name = _sanitize_filename(Path(up.name).name)
            p = os.path.join(temp_dir, f"{idx:03d}_{safe_name}")
            with open(p, "wb") as f:
                f.write(up.getbuffer())
            raw_paths.append(p)
            seed_parts.append(f"{safe_name}:{up.size}")

        if not raw_paths:
            raise RuntimeError("Keine gültigen Bilder erhalten.")

        # deterministic randomness = reproducible books
        random.seed((child_name.strip() + "|" + "|".join(seed_parts)).encode("utf-8", errors="ignore"))

        # Ensure pages count
        final_paths = list(raw_paths)
        while len(final_paths) < pages:
            tmp = list(raw_paths)
            random.shuffle(tmp)
            final_paths.extend(tmp)
        final_paths = final_paths[:pages]

        pdf_path = os.path.join(temp_dir, "interior.pdf")
        c = canvas.Canvas(pdf_path, pagesize=(page_w, page_h))

        for i, src in enumerate(final_paths):
            sk = os.path.join(temp_dir, f"sk_{i:03d}.jpg")
            fit = os.path.join(temp_dir, f"fit_{i:03d}.jpg")

            if foto_zu_skizze(src, sk) and _img_force_square(sk, fit, side_px, quality=95):
                c.drawImage(fit, 0, 0, width=page_w, height=page_h)
            else:
                # fallback: empty page (still valid)
                c.setFillColor(colors.white)
                c.rect(0, 0, page_w, page_h, fill=1, stroke=0)

            # Timeline (kept inside safe zone)
            m = BLEED + INTERIOR_SAFE
            line_y = m + 18
            c.setLineWidth(1)
            c.setStrokeColor(colors.gray)
            c.line(m, line_y, page_w - m, line_y)
            for dot in range(24):
                x = m + dot * ((page_w - 2 * m) / 23)
                c.setFillColor(colors.black if dot <= i else colors.lightgrey)
                c.circle(x, line_y, 4 if dot != i else 8, fill=1, stroke=0)

            c.showPage()

        c.save()
        with open(pdf_path, "rb") as f:
            return f.read()

# =========================================================
# BUILD: COVER WRAP PDF (BACK + SPINE + FRONT IN ONE PDF)
# =========================================================
def _calc_spine_width_inch(page_count: int, paper: str) -> float:
    factor = PAPER_FACTORS.get(paper, PAPER_FACTORS["B&W – White"])
    return float(page_count) * factor

def build_cover_wrap(child_name: str, page_count: int = PAGES_DEFAULT, paper: str = "B&W – White") -> bytes:
    # Spine width in inches (KDP formula guidance) :contentReference[oaicite:5]{index=5}
    spine_w = _calc_spine_width_inch(page_count, paper) * inch

    # Stability minimum (practical rendering) — still tiny at 24 pages
    if spine_w < 0.06 * inch:
        spine_w = 0.06 * inch

    cover_w = (2 * TRIM_SIZE) + spine_w + (2 * BLEED)
    cover_h = TRIM_SIZE + (2 * BLEED)

    # Coordinate map (left->right):
    # [BLEED][BACK TRIM][SPINE][FRONT TRIM][BLEED]
    back_x0 = BLEED
    spine_x0 = BLEED + TRIM_SIZE
    front_x0 = BLEED + TRIM_SIZE + spine_w

    with tempfile.TemporaryDirectory() as temp_dir:
        pdf_path = os.path.join(temp_dir, "cover_wrap.pdf")
        c = canvas.Canvas(pdf_path, pagesize=(cover_w, cover_h))

        # Background (full bleed white)
        c.setFillColor(colors.white)
        c.rect(0, 0, cover_w, cover_h, fill=1, stroke=0)

        # --- BACK COVER (left) ---
        c.saveState()
        # keep text inside safe area and away from barcode zone
        safe_x = back_x0 + COVER_SAFE
        safe_y = BLEED + COVER_SAFE
        safe_w = TRIM_SIZE - 2 * COVER_SAFE
        safe_h = TRIM_SIZE - 2 * COVER_SAFE

        # Minimal brand line
        c.setFillColor(colors.black)
        c.setFont("Helvetica", 12)
        c.drawString(safe_x, safe_y + safe_h - 14, "Eddie’s Welt")

        c.setFont("Helvetica", 10)
        c.setFillColor(colors.grey)
        c.drawString(safe_x, safe_y + safe_h - 30, "Erstellt mit dem kostenlosen Asset-Generator")

        # Barcode keep-out box (KDP may place barcode if not provided) :contentReference[oaicite:6]{index=6}
        box_w, box_h = 2.0 * inch, 1.2 * inch
        box_x = back_x0 + TRIM_SIZE - COVER_SAFE - box_w
        box_y = BLEED + COVER_SAFE
        c.setStrokeColor(colors.lightgrey)
        c.setLineWidth(1)
        c.rect(box_x, box_y, box_w, box_h, fill=0, stroke=1)
        c.setFont("Helvetica", 7)
        c.setFillColor(colors.lightgrey)
        c.drawCentredString(box_x + box_w / 2, box_y + box_h / 2 - 3, "Barcode area (KDP)")
        c.restoreState()

        # --- SPINE (center) ---
        c.saveState()
        c.setFillColor(colors.black)
        c.rect(spine_x0, BLEED, spine_w, TRIM_SIZE, fill=1, stroke=0)

        # No spine text for <79 pages (avoid KDP rejection) :contentReference[oaicite:7]{index=7}
        if page_count >= SPINE_TEXT_MIN_PAGES:
            c.setFillColor(colors.white)
            c.setFont("Helvetica-Bold", 10)
            # rotate text to run along spine
            c.translate(spine_x0 + spine_w / 2, BLEED + TRIM_SIZE / 2)
            c.rotate(90)
            c.drawCentredString(0, -4, f"Eddie & {child_name}".upper())
        else:
            # tiny Eddie mark instead (safe, brand-consistent)
            _draw_eddie_mark(c, spine_x0 + spine_w / 2, BLEED + TRIM_SIZE / 2, r=min(0.18 * inch, spine_w * 0.35))
        c.restoreState()

        # --- FRONT COVER (right) ---
        c.saveState()
        # Title block within safe zone
        front_safe_x = front_x0 + COVER_SAFE
        front_safe_y = BLEED + COVER_SAFE
        front_safe_w = TRIM_SIZE - 2 * COVER_SAFE
        front_safe_h = TRIM_SIZE - 2 * COVER_SAFE

        # Eddie icon (hero)
        _draw_eddie_mark(
            c,
            cx=front_x0 + TRIM_SIZE / 2,
            cy=BLEED + TRIM_SIZE * 0.58,
            r=TRIM_SIZE * 0.18,
        )

        # Title
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 44)
        c.drawCentredString(front_x0 + TRIM_SIZE / 2, BLEED + TRIM_SIZE * 0.80, "EDDIE")

        # Personalization
        c.setFont("Helvetica", 18)
        c.drawCentredString(front_x0 + TRIM_SIZE / 2, BLEED + TRIM_SIZE * 0.73, f"& {child_name}")

        # Subtitle
        c.setFont("Helvetica", 12)
        c.setFillColor(colors.grey)
        c.drawCentredString(front_x0 + TRIM_SIZE / 2, BLEED + TRIM_SIZE * 0.18, "Dein persönliches Malbuch aus echten Momenten")
        c.restoreState()

        c.save()
        with open(pdf_path, "rb") as f:
            return f.read()

# =========================================================
# UI (BUSINESS FLOW)
# =========================================================
st.markdown('<div class="main-title">Eddie’s Welt</div>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Erstelle dein komplettes KDP-Upload-Set: <b>Interior PDF</b> + <b>Cover-Wrap PDF</b> (Full Bleed)</div>', unsafe_allow_html=True)

st.markdown(
    '<div style="text-align:center;margin-bottom:10px;">'
    f'<span class="kpi">KDP: 8.5" × 8.5"</span> '
    f'<span class="kpi">Bleed: 0.125"</span> '
    f'<span class="kpi">DPI: {DPI}</span>'
    "</div>",
    unsafe_allow_html=True,
)

with st.container():
    st.markdown('<div class="card">', unsafe_allow_html=True)
    child_name = st.text_input("Name des Kindes", placeholder="z.B. Eddie", value="")
    paper = st.selectbox("Papier / Ink (für Spine-Berechnung)", options=list(PAPER_FACTORS.keys()), index=0)
    page_count = st.number_input("Seitenanzahl (Interior)", min_value=24, max_value=300, value=PAGES_DEFAULT, step=1)

    uploads = st.file_uploader("Fotos hochladen", accept_multiple_files=True, type=["jpg", "png"])
    st.caption("Tipp: 24 Bilder reichen. Wenn du weniger hochlädst, wird automatisch wiederholt (deterministisch).")
    st.markdown("</div>", unsafe_allow_html=True)

# Session state
if "interior_pdf" not in st.session_state:
    st.session_state.interior_pdf = None
if "cover_pdf" not in st.session_state:
    st.session_state.cover_pdf = None

can_build = bool(child_name.strip()) and bool(uploads)

st.markdown('<div class="hr"></div>', unsafe_allow_html=True)

if st.button("📦 Komplettes KDP-Set erstellen", disabled=not can_build):
    if not can_build:
        st.warning("Bitte Name eingeben und mindestens 1 Foto hochladen.")
    else:
        with st.spinner("Generiere Interior & Cover-Wrap…"):
            files_sorted = sort_uploads_smart(uploads)
            st.session_state.interior_pdf = build_interior(files_sorted, child_name.strip(), pages=int(page_count))
            st.session_state.cover_pdf = build_cover_wrap(child_name.strip(), page_count=int(page_count), paper=paper)
        st.success("Fertig. Dein KDP-Upload-Set ist bereit.")

# =========================================================
# PWYW GATE + DOWNLOADS
# =========================================================
if st.session_state.interior_pdf and st.session_state.cover_pdf:
    st.markdown('<div class="card">', unsafe_allow_html=True)
    st.markdown("### 💜 Unterstütze Eddie’s Welt (Pay what you want)")
    amount = st.number_input("Betrag (€)", min_value=0, value=PWYW_SUGGESTION, step=1)
    st.caption("Empfehlung: 9€ – finanziert Entwicklung, Hosting und neue Premium-Cover.")

    st.markdown('<div class="hr"></div>', unsafe_allow_html=True)
    col1, col2 = st.columns(2)

    fname_base = _sanitize_filename(child_name.strip())
    today = datetime.now().date().isoformat()

    with col1:
        st.download_button(
            "📄 Download: Interior PDF",
            data=st.session_state.interior_pdf,
            file_name=f"Interior_{fname_base}_{today}.pdf",
            mime="application/pdf",
        )
        st.caption("Upload als „Manuskript / Inhalt“ in KDP.")

    with col2:
        st.download_button(
            "🎨 Download: Cover-Wrap PDF",
            data=st.session_state.cover_pdf,
            file_name=f"CoverWrap_{fname_base}_{today}.pdf",
            mime="application/pdf",
        )
        st.caption("Upload als „Cover“ (Back+Spine+Front in einer Datei).")

    st.markdown("</div>", unsafe_allow_html=True)

st.markdown(
    f'<div class="footer">Eddie’s Welt • <a href="{HUB_URL}" target="_blank">Zum Hub (Bonus, Community, Updates)</a></div>',
    unsafe_allow_html=True,
)
