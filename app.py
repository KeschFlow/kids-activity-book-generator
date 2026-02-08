"""
Eddie's Welt – Quest Edition (v2.3, production)
- 24 Seiten (00:00–23:00) mit Quest-HUD (Zone + Mission)
- Foto -> Skizze (OpenCV) + Suchspiel
- Optional: KDP 8.5"x8.5" mit Bleed
- WICHTIG: PDF-Größe wird massiv reduziert durch JPEG-Quality-Controls
"""

import os
import re
import random
import tempfile
from pathlib import Path

import streamlit as st
import cv2
import qrcode
import numpy as np
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch

# SAFE IMPORTS (Quest System)
try:
    from quest_data import get_zone_for_hour, pick_mission_for_time, fmt_hour
except Exception:
    st.error("FEHLER: 'quest_data.py' fehlt oder ist fehlerhaft. Bitte im selben Ordner wie app.py ablegen.")
    st.stop()

# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="Eddie's Welt – Quest Edition", layout="centered")


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def _draw_debug_overlay(c, w, h, kdp_mode, margin, bleed=0.0):
    c.saveState()
    c.setLineWidth(0.7)
    if kdp_mode and bleed > 0:
        c.setStrokeColor(colors.blue)
        c.rect(0, 0, w, h)
        c.setStrokeColor(colors.red)
        c.rect(bleed, bleed, w - 2 * bleed, h - 2 * bleed)
    c.setStrokeColor(colors.green)
    c.rect(margin, margin, w - 2 * margin, h - 2 * margin)
    c.restoreState()


def foto_zu_skizze(input_path: str, output_path: str, jpeg_quality: int) -> bool:
    """
    Convert photo to sketch and save as JPEG with controlled quality.
    This is the single biggest lever for PDF file size.
    """
    try:
        img = cv2.imread(input_path)
        if img is None:
            return False
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        inverted = 255 - gray
        blurred = cv2.GaussianBlur(inverted, (21, 21), 0)
        sketch = cv2.divide(gray, 255 - blurred, scale=256.0)
        sketch = cv2.normalize(sketch, None, 0, 255, cv2.NORM_MINMAX)

        q = int(max(30, min(95, int(jpeg_quality))))
        ok = cv2.imwrite(output_path, sketch, [int(cv2.IMWRITE_JPEG_QUALITY), q])
        return bool(ok)
    except Exception:
        return False


def _cover_fit_to_page(src_path: str, out_path: str, page_w_px: int, page_h_px: int, quality: int = 55) -> bool:
    """
    Resize/crop to exact pixel size and write JPEG with controlled quality.
    Used in KDP mode when we want full-bleed images.
    """
    try:
        q = int(max(30, min(95, int(quality))))
        im = Image.open(src_path).convert("L")
        iw, ih = im.size
        scale = max(page_w_px / iw, page_h_px / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        im = im.resize((nw, nh), Image.LANCZOS)
        left, top = (nw - page_w_px) // 2, (nh - page_h_px) // 2
        im = im.crop((left, top, left + page_w_px, top + page_h_px))
        im.save(out_path, "JPEG", quality=q, optimize=True, progressive=True, subsampling=2)
        return True
    except Exception:
        return False


def zeichne_suchspiel(c, width: float, y_start: float, img_height: float, anzahl: int) -> None:
    form = random.choice(["kreis", "viereck", "dreieck"])
    c.setLineWidth(2)
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.white)

    y_min, y_max = int(y_start), int(y_start + img_height - 30)
    for _ in range(int(anzahl)):
        x = random.randint(50, int(width) - 50)
        y = random.randint(y_min, y_max)
        s = random.randint(15, 25)
        if form == "kreis":
            c.circle(x, y, s / 2, fill=1, stroke=1)
        elif form == "viereck":
            c.rect(x - s / 2, y - s / 2, s, s, fill=1, stroke=1)
        else:
            p = c.beginPath()
            p.moveTo(x, y + s / 2)
            p.lineTo(x - s / 2, y - s / 2)
            p.lineTo(x + s / 2, y - s / 2)
            p.close()
            c.drawPath(p, fill=1, stroke=1)

    # Legende
    leg_y = max(50, y_start - 35)
    c.setFillColor(colors.white)
    if form == "kreis":
        c.circle(80, leg_y + 5, 8, fill=0, stroke=1)
    elif form == "viereck":
        c.rect(72, leg_y - 3, 16, 16, fill=0, stroke=1)
    else:
        p = c.beginPath()
        p.moveTo(80, leg_y + 13)
        p.lineTo(72, leg_y - 3)
        p.lineTo(88, leg_y - 3)
        p.close()
        c.drawPath(p, fill=0, stroke=1)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(100, leg_y, f"x {anzahl}")


def sort_uploads_smart(uploaded_list):
    """
    Sort by EXIF datetime when possible (>=2 timestamps found),
    else keep upload order.
    """
    if not uploaded_list:
        return []
    items = []
    for idx, f in enumerate(uploaded_list):
        try:
            f.seek(0)
            img = Image.open(f)
            exif = img.getexif()
            dt = exif.get(36867) or exif.get(306)
            f.seek(0)
            dt_str = str(dt).strip() if dt else ""
        except Exception:
            dt_str = ""
        items.append((dt_str, idx, f))

    if sum(1 for d, _, _ in items if d) >= 2:
        items.sort(key=lambda x: (x[0] == "", x[0], x[1]))
    else:
        items.sort(key=lambda x: x[1])

    return [f for _, _, f in items]


def draw_quest_hud(c, w, h, margin, hour, zone, mission):
    """
    Header (Zone) + Footer (Mission box)
    """
    # Header
    c.saveState()
    header_h = 1.0 * inch
    c.setFillColorRGB(*zone.color)
    c.rect(0, h - header_h, w, header_h, fill=1, stroke=0)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, h - 0.62 * inch, f"{zone.icon} {zone.name.upper()}")
    c.setFont("Helvetica", 10)
    c.drawString(margin, h - 0.85 * inch, f"{zone.quest_type} • {zone.atmosphere}")
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(w - margin, h - 0.62 * inch, fmt_hour(hour))
    c.restoreState()

    # Footer
    footer_y = margin
    footer_h = 1.85 * inch
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.5)
    c.roundRect(margin, footer_y, w - 2 * margin, footer_h, 8, fill=1, stroke=1)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin + 0.2 * inch, footer_y + 1.42 * inch, f"MISSION: {mission.title}")
    c.drawRightString(w - margin - 0.2 * inch, footer_y + 1.42 * inch, f"+{mission.xp} XP")

    c.setFont("Helvetica", 11)
    c.drawString(margin + 0.2 * inch, footer_y + 1.02 * inch, f"⚡ {mission.movement}")
    c.drawString(margin + 0.2 * inch, footer_y + 0.72 * inch, f"🧠 {mission.thinking}")

    c.setFont("Helvetica-Oblique", 10)
    c.setFillColor(colors.darkblue)
    c.drawString(margin + 0.2 * inch, footer_y + 0.30 * inch, f"Checkpoint: {mission.proof}")


# ---------------------------------------------------------
# BUILD ENGINE
# ---------------------------------------------------------
def build_pdf_quest(
    *,
    sorted_files,
    kind_name: str,
    kdp_mode: bool,
    dpi: int,
    difficulty: int,
    xray_overlay: bool,
    app_url: str,
    jpeg_quality: int,
    full_bleed_in_kdp: bool,
) -> bytes:
    with tempfile.TemporaryDirectory() as temp_dir:
        raw_paths = []
        seed_parts = []

        for idx, up in enumerate(sorted_files):
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(up.name).name) or "upload.jpg"
            p = os.path.join(temp_dir, f"{idx:03d}_{safe_name}")
            with open(p, "wb") as f:
                f.write(up.getbuffer())
            raw_paths.append(p)
            seed_parts.append(f"{safe_name}:{up.size}")

        # deterministic shuffle/repeat to exactly 24 pages
        random.seed((kind_name.strip() + "|" + "|".join(seed_parts)).encode("utf-8", errors="ignore"))
        final_paths = list(raw_paths)
        if not final_paths:
            raise RuntimeError("Keine gültigen Bilder erhalten.")

        while len(final_paths) < 24:
            pool = list(raw_paths)
            random.shuffle(pool)
            final_paths.extend(pool)
        final_paths = final_paths[:24]

        BLEED = 0.125 * inch if kdp_mode else 0.0
        w, h = ((8.5 * inch + 2 * BLEED), (8.5 * inch + 2 * BLEED)) if kdp_mode else A4
        margin = (BLEED + 0.375 * inch) if kdp_mode else 50

        pdf_path = os.path.join(temp_dir, "Quest_Buch.pdf")
        c = canvas.Canvas(pdf_path, pagesize=(w, h))

        # Cover
        c.setFont("Helvetica-Bold", 36)
        c.drawCentredString(w / 2, h / 2 + 30, f"{kind_name.upper()}S QUESTBUCH")
        c.setFont("Helvetica", 14)
        c.drawCentredString(w / 2, h / 2 - 10, "Eddie's Welt – Quest Edition")
        if xray_overlay:
            _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)
        c.showPage()

        # Manifest
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(w / 2, h - 110, f"Hallo {kind_name}.")
        y_txt = h - 170
        for line in ["Das ist deine Quest-Welt.", "Hier gibt es kein Falsch.", "Leg los."]:
            c.drawCentredString(w / 2, y_txt, line)
            y_txt -= 26
        if xray_overlay:
            _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)
        c.showPage()

        # Quest Pages
        unique_seed = random.randint(0, 999999)
        prog = st.progress(0)

        for hour, p_path in enumerate(final_paths):
            prog.progress((hour + 1) / 24)

            zone = get_zone_for_hour(hour)
            mission = pick_mission_for_time(hour, difficulty, seed=unique_seed + hour)

            # make sketch
            out_sk = os.path.join(temp_dir, f"sk_{hour:02d}.jpg")
            has_sketch = foto_zu_skizze(p_path, out_sk, jpeg_quality=jpeg_quality)

            # draw image area
            header_h = 1.0 * inch
            footer_h = 1.85 * inch
            img_y = margin + footer_h + 0.25 * inch
            img_h = h - (img_y + header_h + 0.25 * inch)
            img_w = w - 2 * margin

            if has_sketch:
                if kdp_mode and full_bleed_in_kdp:
                    # Fit to full page pixels (incl bleed) -> draw full page
                    px_w = int((w / inch) * int(dpi))
                    px_h = int((h / inch) * int(dpi))
                    out_bl = os.path.join(temp_dir, f"bl_{hour:02d}.jpg")
                    if _cover_fit_to_page(out_sk, out_bl, px_w, px_h, quality=jpeg_quality) and os.path.exists(out_bl):
                        c.drawImage(out_bl, 0, 0, width=w, height=h)
                    else:
                        c.drawImage(out_sk, margin, img_y, width=img_w, height=img_h, preserveAspectRatio=True)
                else:
                    c.drawImage(out_sk, margin, img_y, width=img_w, height=img_h, preserveAspectRatio=True)

                # hidden-object overlay
                zeichne_suchspiel(c, w, img_y, img_h, random.randint(3, 6))
            else:
                c.setFillColor(colors.lightgrey)
                c.rect(margin, img_y, img_w, img_h, fill=1, stroke=0)
                c.setFillColor(colors.darkgrey)
                c.setFont("Helvetica", 14)
                c.drawCentredString(w / 2, img_y + img_h / 2, "Bild konnte nicht verarbeitet werden")

            # HUD (on top)
            draw_quest_hud(c, w, h, margin, hour, zone, mission)

            # Timeline
            line_y = margin + 0.35 * inch
            c.setLineWidth(1)
            c.setStrokeColor(colors.gray)
            c.line(margin, line_y, w - margin, line_y)
            for dot in range(24):
                dot_x = margin + dot * ((w - 2 * margin) / 23)
                c.setFillColor(colors.black if dot <= hour else colors.lightgrey)
                c.circle(dot_x, line_y, 3 if dot != hour else 6, fill=1, stroke=0)

            if xray_overlay:
                _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)

            c.showPage()

        # QR (optional, mostly for KDP)
        if app_url and app_url.strip():
            try:
                qr = qrcode.make(app_url.strip())
                qr_p = os.path.join(temp_dir, "qr.png")
                qr.save(qr_p)

                c.setFont("Helvetica-Bold", 26)
                c.drawCentredString(w / 2, h - 140, "QR – Zur App")
                c.drawImage(qr_p, (w - 160) / 2, h / 2 - 120, 160, 160)
                c.setFont("Helvetica", 12)
                c.drawCentredString(w / 2, h / 2 - 140, app_url.strip())
                if xray_overlay:
                    _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)
                c.showPage()
            except Exception:
                pass

        # Certificate
        c.rect(margin, margin, w - 2 * margin, h - 2 * margin)
        c.setFont("Helvetica-Bold", 30)
        c.drawCentredString(w / 2, h / 2 + 50, "URKUNDE")
        c.setFont("Helvetica", 16)
        c.drawCentredString(w / 2, h / 2 + 10, f"{kind_name} hat 24 Missionen geschafft.")
        c.setFont("Helvetica-Oblique", 12)
        c.drawCentredString(w / 2, h / 2 - 30, "Eddie's Welt – Quest Edition")
        c.showPage()

        c.save()

        with open(pdf_path, "rb") as f:
            return f.read()


# ---------------------------------------------------------
# UI
# ---------------------------------------------------------
st.title("✏️ Eddie's Welt – Quest Edition")

with st.sidebar:
    st.markdown("### Druck / Layout")
    kdp_mode = st.toggle('📦 KDP (8.5"x8.5")', False)
    dpi = st.select_slider("DPI", options=[180, 240, 300], value=180, disabled=not kdp_mode)
    full_bleed_in_kdp = st.toggle("🖨️ KDP Full-Bleed Bilder (größer!)", False)

    st.markdown("### Debug")
    xray = st.toggle("🩻 Röntgen-Overlay", False)

    st.markdown("### Quest")
    difficulty = st.slider("Schwierigkeitsgrad", min_value=1, max_value=5, value=3)

    st.markdown("### PDF Größe")
    jpeg_quality = st.slider("JPEG-Qualität (kleiner = weniger MB)", min_value=35, max_value=85, value=55, step=5)

    st.markdown("### QR-Link")
    app_url = st.text_input("QR-Link", "https://eddie-welt.streamlit.app")

kind = st.text_input("Name", "Eddie")
ups = st.file_uploader("Bis zu 24 Bilder", accept_multiple_files=True, type=["jpg", "png", "jpeg"])

if ups:
    if st.button("📚 Buch binden"):
        try:
            pdf_bytes = build_pdf_quest(
                sorted_files=sort_uploads_smart(ups[:24]),
                kind_name=kind,
                kdp_mode=kdp_mode,
                dpi=int(dpi),
                difficulty=int(difficulty),
                xray_overlay=xray,
                app_url=app_url,
                jpeg_quality=int(jpeg_quality),
                full_bleed_in_kdp=bool(full_bleed_in_kdp),
            )
            mb = len(pdf_bytes) / (1024 * 1024)
            st.success(f"Fertig! PDF-Größe: {mb:.1f} MB")
            st.download_button("Download", pdf_bytes, file_name="Quest_Buch.pdf")
        except Exception as e:
            st.error(f"Fehler: {e}")
