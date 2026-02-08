import streamlit as st
import cv2
import os
import random
import tempfile
import re
from pathlib import Path

import qrcode
from PIL import Image
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch

from quest_data import get_zone_for_hour, pick_mission_for_time, fmt_hour


# ---------------------------------------------------------
# CONFIG
# ---------------------------------------------------------
st.set_page_config(page_title="Eddie's Welt – Quest Edition", layout="centered")


# ---------------------------------------------------------
# SIZE / COMPRESSION SETTINGS  (HIER PASSIERT DIE MAGIE)
# ---------------------------------------------------------
# Ziel: PDF klein genug für Upload/KDP.
# Diese Werte sind bewusst "aggressiv", aber Linien bleiben druckbar.
JPEG_QUALITY = 35          # 35–45 ist sweet spot für s/w Skizzen
MAX_SKETCH_WIDTH_PX = 1400 # 1200–1700 → kleiner = kleinere PDFs


# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def _draw_debug_overlay(c, w, h, kdp_mode, margin, bleed=0.0):
    c.saveState()
    c.setLineWidth(0.7)
    if kdp_mode and bleed > 0:
        c.setStrokeColor(colors.blue); c.rect(0, 0, w, h)
        c.setStrokeColor(colors.red); c.rect(bleed, bleed, w - 2*bleed, h - 2*bleed)
    c.setStrokeColor(colors.green); c.rect(margin, margin, w - 2*margin, h - 2*margin)
    c.restoreState()


def _resize_gray_to_max_width(gray_img, max_w=MAX_SKETCH_WIDTH_PX):
    """Downscale grayscale image to max width (reduces PDF size massively)."""
    h, w = gray_img.shape[:2]
    if w <= max_w:
        return gray_img
    scale = max_w / float(w)
    new_w = int(w * scale)
    new_h = int(h * scale)
    return cv2.resize(gray_img, (new_w, new_h), interpolation=cv2.INTER_AREA)


def foto_zu_skizze(input_path: str, output_path: str) -> bool:
    """
    Foto -> Skizze (JPEG stark komprimiert + vorher downscale)
    => Das ist der Haupthebel gegen zu große PDFs.
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

        # HARD DOWNSCALE
        sketch = _resize_gray_to_max_width(sketch, MAX_SKETCH_WIDTH_PX)

        # HARD JPEG COMPRESSION
        cv2.imwrite(
            output_path,
            sketch,
            [
                int(cv2.IMWRITE_JPEG_QUALITY), int(JPEG_QUALITY),
                int(cv2.IMWRITE_JPEG_OPTIMIZE), 1
            ]
        )
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
        x = random.randint(60, int(width) - 60)
        y = random.randint(y_min, y_max)
        s = random.randint(15, 25)

        if form == "kreis":
            c.circle(x, y, s / 2, fill=1, stroke=1)
        elif form == "viereck":
            c.rect(x - s/2, y - s/2, s, s, fill=1, stroke=1)
        else:
            p = c.beginPath()
            p.moveTo(x, y + s/2)
            p.lineTo(x - s/2, y - s/2)
            p.lineTo(x + s/2, y - s/2)
            p.close()
            c.drawPath(p, fill=1, stroke=1)

    # Legende
    leg_y = max(60, y_start - 35)
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
    header_h = 85

    # Header (Zone-Farbe)
    c.saveState()
    c.setFillColorRGB(*zone.color)
    c.rect(0, h - header_h, w, header_h, fill=1, stroke=0)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 18)
    c.drawString(margin, h - 30, f"{zone.icon} {zone.name}")
    c.setFont("Helvetica", 11)
    c.drawString(margin, h - 50, f"{zone.quest_type} • {zone.atmosphere}")
    c.setFont("Helvetica-Bold", 14)
    c.drawRightString(w - margin, h - 30, fmt_hour(hour))
    c.restoreState()

    # Footer (Mission Box)
    footer_h = 1.65 * inch
    footer_y = margin

    c.setFillColor(colors.white)
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.2)
    c.roundRect(margin, footer_y, w - 2*margin, footer_h, 8, fill=1, stroke=1)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin + 0.18*inch, footer_y + footer_h - 0.45*inch, f"MISSION: {mission.title}")
    c.drawRightString(w - margin - 0.18*inch, footer_y + footer_h - 0.45*inch, f"+{mission.xp} XP")

    c.setFont("Helvetica", 11)
    c.drawString(margin + 0.18*inch, footer_y + footer_h - 0.85*inch, f"⚡ {mission.movement}")
    c.drawString(margin + 0.18*inch, footer_y + footer_h - 1.15*inch, f"🧠 {mission.thinking}")

    c.setFont("Helvetica-Oblique", 10)
    c.setFillColor(colors.darkblue)
    c.drawString(margin + 0.18*inch, footer_y + 0.22*inch, f"Checkpoint: {mission.proof}")


# ---------------------------------------------------------
# BUILD ENGINE
# ---------------------------------------------------------
def build_pdf_quest(*, sorted_files, kind_name, kdp_mode, dpi, difficulty, xray_overlay, app_url):
    with tempfile.TemporaryDirectory() as temp_dir:
        raw_paths, seed_parts = [], []

        for idx, up in enumerate(sorted_files):
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(up.name).name) or "upload.jpg"
            p = os.path.join(temp_dir, f"{idx:03d}_{safe_name}")
            with open(p, "wb") as f:
                f.write(up.getbuffer())
            raw_paths.append(p)
            seed_parts.append(f"{safe_name}:{up.size}")

        # deterministisch seed
        random.seed((kind_name.strip() + "|" + str(difficulty) + "|" + "|".join(seed_parts)).encode("utf-8", errors="ignore"))

        final_paths = list(raw_paths)
        if not final_paths:
            raise RuntimeError("Keine gültigen Bilder erhalten.")

        while len(final_paths) < 24:
            pool = list(raw_paths)
            random.shuffle(pool)
            final_paths.extend(pool)
        final_paths = final_paths[:24]

        # Page geometry
        BLEED = 0.125 * inch if kdp_mode else 0.0
        w, h = ((8.5*inch + 2*BLEED), (8.5*inch + 2*BLEED)) if kdp_mode else A4
        margin = (BLEED + 0.375*inch) if kdp_mode else 45

        pdf_path = os.path.join(temp_dir, "Questbuch.pdf")
        c = canvas.Canvas(pdf_path, pagesize=(w, h))

        # COVER
        c.setFont("Helvetica-Bold", 34)
        c.drawCentredString(w/2, h/2 + 10, f"{kind_name.upper()}S QUEST-LOGBUCH")
        c.setFont("Helvetica", 14)
        c.drawCentredString(w/2, h/2 - 20, "24 Missionen • 8 Zonen • 1 Tag")
        if xray_overlay:
            _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)
        c.showPage()

        # MANIFEST
        c.setFont("Helvetica-Bold", 22)
        c.drawCentredString(w/2, h - 120, f"Hallo {kind_name}.")
        c.setFont("Helvetica", 14)
        lines = [
            "Das ist deine Quest-Welt.",
            "Hier gibt es kein Falsch.",
            "Du schaffst das. Schritt für Schritt.",
        ]
        y = h - 180
        for line in lines:
            c.drawCentredString(w/2, y, line)
            y -= 28
        if xray_overlay:
            _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)
        c.showPage()

        # CONTENT LOOP
        unique_seed = random.randint(0, 999999)
        prog = st.progress(0)

        for i, p_path in enumerate(final_paths):
            prog.progress((i + 1) / 24)

            zone = get_zone_for_hour(i)
            mission = pick_mission_for_time(i, difficulty, seed=unique_seed + i)

            # Convert photo to sketch (compressed)
            out_sk = os.path.join(temp_dir, f"sk_{i:02d}.jpg")
            ok = foto_zu_skizze(p_path, out_sk)

            # Draw image area
            header_h = 85
            footer_h = 1.65 * inch
            img_y = margin + footer_h + 20
            img_h = h - (header_h + img_y + 20)

            if ok and os.path.exists(out_sk):
                c.drawImage(out_sk, margin, img_y, width=w - 2*margin, height=img_h, preserveAspectRatio=True)
                zeichne_suchspiel(c, w, img_y, img_h, random.randint(3, 6))
            else:
                c.setFillColor(colors.lightgrey)
                c.rect(margin, img_y, w - 2*margin, img_h, fill=1, stroke=0)
                c.setFillColor(colors.darkgrey)
                c.setFont("Helvetica", 14)
                c.drawCentredString(w/2, img_y + img_h/2, "Bild konnte nicht verarbeitet werden")

            # HUD
            draw_quest_hud(c, w, h, margin, i, zone, mission)

            # Timeline
            line_y = margin + 12
            c.setLineWidth(1)
            c.setStrokeColor(colors.gray)
            c.line(margin, line_y, w - margin, line_y)
            for dot in range(24):
                dot_x = margin + dot * ((w - 2*margin) / 23)
                c.setFillColor(colors.black if dot <= i else colors.lightgrey)
                c.circle(dot_x, line_y, 3 if dot != i else 6, fill=1, stroke=0)

            if xray_overlay:
                _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)

            c.showPage()

        # QR PAGE (optional)
        if app_url and app_url.strip():
            try:
                qr = qrcode.make(app_url.strip())
                qr_p = os.path.join(temp_dir, "qr.png")
                qr.save(qr_p)
                c.setFont("Helvetica-Bold", 22)
                c.drawCentredString(w/2, h - 120, "QR-Portal")
                c.drawImage(qr_p, (w-160)/2, h/2 - 80, 160, 160)
                c.setFont("Helvetica", 12)
                c.drawCentredString(w/2, h/2 - 110, app_url.strip())
                c.showPage()
            except Exception:
                pass

        # CERTIFICATE
        c.rect(margin, margin, w - 2*margin, h - 2*margin)
        c.setFont("Helvetica-Bold", 30)
        c.drawCentredString(w/2, h/2 + 40, "URKUNDE")
        c.setFont("Helvetica", 16)
        c.drawCentredString(w/2, h/2, f"{kind_name} hat seine Missionen gemeistert!")
        c.showPage()

        c.save()

        with open(pdf_path, "rb") as f:
            return f.read()


# ---------------------------------------------------------
# UI
# ---------------------------------------------------------
st.title("⚔️ Eddie's Welt – Quest Edition")

with st.sidebar:
    kdp_mode = st.toggle('📦 KDP (8.5"x8.5")', False)
    dpi = st.select_slider("DPI", options=[180, 240, 300], value=240, disabled=not kdp_mode)
    xray = st.toggle("🩻 Röntgen-Overlay", False)
    difficulty = st.slider("Schwierigkeitsgrad", 1, 5, 3)
    app_url = st.text_input("QR-Link", "https://eddie-welt.streamlit.app")

kind = st.text_input("Name", "Eddie")
ups = st.file_uploader("Bis zu 24 Bilder", accept_multiple_files=True, type=["jpg", "png", "jpeg"])

if ups:
    if len(ups) > 24:
        st.error("Maximal 24 Bilder.")
        st.stop()

    if st.button("📚 Buch binden"):
        try:
            pdf_bytes = build_pdf_quest(
                sorted_files=sort_uploads_smart(ups),
                kind_name=kind,
                kdp_mode=kdp_mode,
                dpi=int(dpi),
                difficulty=int(difficulty),
                xray_overlay=xray,
                app_url=app_url,
            )
            st.success("Fertig!")
            st.download_button("Download", pdf_bytes, file_name="Quest_Buch.pdf")
        except Exception as e:
            st.error(f"Fehler: {e}")
