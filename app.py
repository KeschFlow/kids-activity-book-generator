"""
Quest Edition of Eddie's World
===============================

This Streamlit application generates a personalised activity book
incorporating both custom child photos and a fully fledged quest system.
Each hour of the day is mapped to one of eight themed zones defined in
``quest_data.py``.  Within each zone the application selects an age‑
appropriate mission based on a requested difficulty level.  The
resulting PDF includes a cover, a manifesto page and 24 pages with
sketches of the uploaded images, hidden‑object games and mission
instructions displayed inside a colourful header (HUD) aligned to the
current zone.  An optional KDP mode adjusts page size and adds bleed
for printing via Amazon KDP.

Usage
-----

Run this script with ``streamlit run app.py`` in an environment with
the dependencies listed in ``requirements.txt``.  Upload up to 24
images, choose the child's name, select a mission difficulty and
generate the PDF.  The application will repeat images to fill 24
pages if fewer photos are provided.  It also supports toggles for
KDP page size, a debug overlay and custom DPI settings.
"""

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
# HELPERS
# ---------------------------------------------------------

def _draw_debug_overlay(c, w, h, kdp_mode, margin, bleed=0.0):
    """Draw coloured frames for bleed and safe margin debugging."""
    c.saveState()
    c.setLineWidth(0.7)
    if kdp_mode and bleed > 0:
        c.setStrokeColor(colors.blue); c.rect(0, 0, w, h)
        c.setStrokeColor(colors.red); c.rect(bleed, bleed, w - 2*bleed, h - 2*bleed)
    # always draw green safe zone
    c.setStrokeColor(colors.green); c.rect(margin, margin, w - 2*margin, h - 2*margin)
    c.restoreState()


def foto_zu_skizze(input_path: str, output_path: str) -> bool:
    """Convert a colour photograph into a sketch and save as JPEG.

    Returns True on success and False otherwise.
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
        cv2.imwrite(output_path, sketch)
        return True
    except Exception:
        return False


def _cover_fit_to_page(src_path: str, out_path: str, page_w: int, page_h: int, quality: int = 85) -> bool:
    """Resize and crop an image to exactly fill the target page dimensions.

    This helper is used in KDP mode to ensure sketches fill the full
    square page when printing.  It returns True if the output file
    could be created successfully and False otherwise.

    :param src_path: Path to the input image to resize.
    :param out_path: Path where the output JPEG will be written.
    :param page_w: Target width in pixels.
    :param page_h: Target height in pixels.
    :param quality: JPEG quality between 35 and 95.
    :return: True on success, False on failure.
    """
    try:
        q = int(max(35, min(95, int(quality))))
        im = Image.open(src_path).convert("L")
        iw, ih = im.size
        scale = max(page_w / iw, page_h / ih)
        nw, nh = int(iw * scale), int(ih * scale)
        im = im.resize((nw, nh), Image.LANCZOS)
        left, top = (nw - page_w) // 2, (nh - page_h) // 2
        im = im.crop((left, top, left + page_w, top + page_h))
        im.save(out_path, "JPEG", quality=q, optimize=True, progressive=True, subsampling=2)
        return True
    except Exception:
        return False


def zeichne_suchspiel(c, width: float, y_start: float, img_height: float, anzahl: int) -> None:
    """Render a simple hidden object game on the PDF page.

    Randomly draws a set of shapes (circles, squares or triangles) on
    the image area and a legend indicating how many to find.  This
    mechanic complements the sketch by providing an interactive
    challenge that promotes visual scanning and fine motor skills.
    """
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
            c.rect(x - s/2, y - s/2, s, s, fill=1, stroke=1)
        else:
            p = c.beginPath()
            p.moveTo(x, y + s/2)
            p.lineTo(x - s/2, y - s/2)
            p.lineTo(x + s/2, y - s/2)
            p.close()
            c.drawPath(p, fill=1, stroke=1)
    # legend
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
    """Return a list of uploaded images sorted by EXIF datetime if available.

    This helper ensures that photos are processed in chronological order
    when multiple images are provided.  If timestamps are missing or
    inconsistent, the original upload order is preserved.
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
        # sort by date/time when at least two images have EXIF timestamps
        items.sort(key=lambda x: (x[0] == "", x[0], x[1]))
    else:
        items.sort(key=lambda x: x[1])
    return [f for _, _, f in items]


def build_pdf_quest(*, sorted_files, kind_name: str, kdp_mode: bool, dpi: int,
                    difficulty: int, xray_overlay: bool, app_url: str) -> bytes:
    """Construct the quest edition PDF and return it as raw bytes.

    :param sorted_files: A list of uploaded files in order.
    :param kind_name: Child's name used on the cover and manifesto.
    :param kdp_mode: Enable KDP layout (8.5" square with bleed).
    :param dpi: Dots per inch for image resizing when KDP mode is active.
    :param difficulty: Maximum mission difficulty.
    :param xray_overlay: Draw bleed/margin guides when True.
    :param app_url: Link embedded as a QR code on the certificate page.
    :return: Binary PDF data.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Write uploads to temporary files and build a seed string
        raw_paths = []
        seed_parts = []
        for idx, up in enumerate(sorted_files):
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(up.name).name) or "upload.jpg"
            p = os.path.join(temp_dir, f"{idx:03d}_{safe_name}")
            with open(p, "wb") as f:
                f.write(up.getbuffer())
            raw_paths.append(p)
            seed_parts.append(f"{safe_name}:{up.size}")

        # build deterministic sequence by repeating images to 24 items
        random.seed((kind_name.strip() + "|" + "|".join(seed_parts)).encode("utf-8", errors="ignore"))
        final_paths = list(raw_paths)
        pool = list(final_paths)
        if not pool:
            raise RuntimeError("Keine gültigen Bilder erhalten.")
        while len(final_paths) < 24:
            tmp_p = list(pool)
            random.shuffle(tmp_p)
            final_paths.extend(tmp_p)
        final_paths = final_paths[:24]

        # Determine page geometry
        BLEED = 0.125 * inch if kdp_mode else 0.0
        w, h = ((8.5 * inch + 2 * BLEED), (8.5 * inch + 2 * BLEED)) if kdp_mode else A4
        margin = (BLEED + 0.375 * inch) if kdp_mode else 50

        # Create PDF
        pdf_path = os.path.join(temp_dir, "output.pdf")
        c = canvas.Canvas(pdf_path, pagesize=(w, h))
        jpeg_quality = 85

        # cover page
        c.setFont("Helvetica-Bold", 36)
        c.drawCentredString(w / 2, h / 2 + 20, f"{kind_name.upper()}S REISE")
        if xray_overlay:
            _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)
        c.showPage()

        # manifesto / intro page
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(w / 2, h - 100, f"Hallo {kind_name}.")
        y_txt = h - 160
        for line in [
            "Das ist deine Quest-Welt.",
            "Hier gibt es kein Falsch.",
            "Leg los und entdecke deine Missionen!",
        ]:
            c.drawCentredString(w / 2, y_txt, line)
            y_txt -= 25
        if xray_overlay:
            _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)
        c.showPage()

        # Build 24 quest pages
        unique_seed = random.randint(0, 999999)
        for i, p_path in enumerate(final_paths):
            # Determine zone and mission for this hour
            zone = get_zone_for_hour(i)
            mission = pick_mission_for_time(i, difficulty, seed=unique_seed + i)

            # Header / HUD region
            header_height = 90
            c.setFillColorRGB(*zone.color)
            c.rect(0, h - header_height, w, header_height, fill=1, stroke=0)
            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 24)
            c.drawString(margin, h - header_height + 50, f"{fmt_hour(i)}  {zone.icon}")
            c.setFont("Helvetica-Bold", 18)
            c.drawString(margin, h - header_height + 25, mission.title)
            c.setFont("Helvetica", 12)
            details_y = h - header_height + 5
            # movement and thinking details on separate lines
            c.drawString(margin, details_y, mission.movement)
            c.drawRightString(w - margin, details_y, mission.proof)
            details_y -= 14
            c.drawString(margin, details_y, mission.thinking)
            c.drawRightString(w - margin, details_y, f"{mission.xp} XP")

            # Convert current photo to sketch
            out_sk = os.path.join(temp_dir, f"sk_{i:02d}.jpg")
            has_sketch = foto_zu_skizze(p_path, out_sk)

            # Draw sketch or placeholder area
            sketch_top = h - header_height - 20
            sketch_height = h - header_height - 160  # reserve space for timeline
            if has_sketch:
                if kdp_mode:
                    # compute pixel dimensions for KDP printing
                    px_w = int((w / inch) * int(dpi))
                    px_h = int((h / inch) * int(dpi))
                    out_bl = os.path.join(temp_dir, f"bl_{i:02d}.jpg")
                    # Fit the sketch to page size including bleed
                    if _cover_fit_to_page(out_sk, out_bl, px_w, px_h, quality=jpeg_quality) and os.path.exists(out_bl):
                        c.drawImage(out_bl, 0, 0, width=w, height=h)
                    else:
                        c.drawImage(
                            out_sk,
                            margin,
                            margin + 60,
                            width=w - 2 * margin,
                            height=sketch_height,
                            preserveAspectRatio=True,
                        )
                else:
                    c.drawImage(
                        out_sk,
                        margin,
                        margin + 60,
                        width=w - 2 * margin,
                        height=sketch_height,
                        preserveAspectRatio=True,
                    )
                # Draw hidden objects on top of the sketch area
                zeichne_suchspiel(c, w, margin + 60, sketch_height, random.randint(3, 6))
            else:
                # draw placeholder rectangle if sketch failed
                c.setFillColor(colors.lightgrey)
                c.rect(margin, margin + 60, w - 2 * margin, sketch_height, fill=1, stroke=0)
                c.setFillColor(colors.darkgrey)
                c.setFont("Helvetica", 14)
                c.drawCentredString(w / 2, margin + 60 + sketch_height / 2, "Bild konnte nicht verarbeitet werden")

            # Timeline across bottom of page
            line_y = margin + 30
            c.setLineWidth(1)
            c.setStrokeColor(colors.gray)
            c.line(margin, line_y, w - margin, line_y)
            for dot in range(24):
                dot_x = margin + dot * ((w - 2 * margin) / 23)
                c.setFillColor(colors.black if dot <= i else colors.lightgrey)
                c.circle(dot_x, line_y, 3 if dot != i else 6, fill=1, stroke=0)

            # Optional overlay for debugging
            if xray_overlay:
                _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)

            c.showPage()

        # Final certificate / QR page for KDP
        if kdp_mode:
            qr = qrcode.make(app_url)
            qr_p = os.path.join(temp_dir, "qr.png")
            qr.save(qr_p)
            c.drawImage(qr_p, (w - 120) / 2, h / 2 - 60, 120, 120)
            c.showPage()

        # Urkunde / certificate page for all modes
        c.rect(margin, margin, w - 2 * margin, h - 2 * margin)
        c.setFont("Helvetica-Bold", 30)
        c.drawCentredString(w / 2, h / 2 + 40, "URKUNDE")
        c.setFont("Helvetica", 18)
        c.drawCentredString(w / 2, h / 2, f"{kind_name} hat seine Missionen gemeistert!")
        c.showPage()

        c.save()

        with open(pdf_path, "rb") as f:
            return f.read()


# ---------------------------------------------------------
# UI START
# ---------------------------------------------------------

st.title("✏️ Eddie's Welt – Quest Edition")

with st.sidebar:
    kdp_mode = st.toggle('📦 KDP (8.5"x8.5")', False)
    dpi = st.select_slider("DPI", options=[180, 240, 300], value=240, disabled=not kdp_mode)
    xray = st.toggle("🩻 Röntgen-Overlay", False)
    difficulty = st.slider("Schwierigkeitsgrad", min_value=1, max_value=5, value=3)
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
                dpi=dpi,
                difficulty=difficulty,
                xray_overlay=xray,
                app_url=app_url,
            )
            st.success("Fertig!")
            st.download_button("Download", pdf_bytes, file_name="Quest_Buch.pdf")
        except Exception as e:
            st.error(f"Fehler: {e}")
