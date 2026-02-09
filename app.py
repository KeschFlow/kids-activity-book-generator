"""
Eddie's Welt – Quest Edition (v2.3)
- 24 Seiten (00–23 Uhr)
- Quest-System (Zonen + Missionen) aus quest_data.py
- 24-Stunden-Farb-System via get_hour_color(hour)
- Auto-Textfarbe (Schwarz/Weiß) je nach Hintergrund-Luminanz
- Skizzen aus Fotos + Suchspiel (Kreis/Viereck/Dreieck)
- KDP-Modus: 8.5"x8.5" Trim + 0.125" Bleed (PDF: 8.75"x8.75")
- Safe Zone: 0.375" vom Trim-Rand => (Bleed + 0.375") vom PDF-Rand
- Preflight Ampel (Bleed/Safe/PDF-Size/DPI/Debug)
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

# QUEST IMPORTS (muss im selben Ordner liegen)
from quest_data import (
    get_zone_for_hour,
    pick_mission_for_time,
    fmt_hour,
    get_hour_color,
    validate_quest_db,
)


# =========================================================
# 1) HELPERS & GEOMETRIE
# =========================================================

def _in_to_mm(x_in: float) -> float:
    return float(x_in) * 25.4


def _best_text_color(rgb):
    """Entscheidet ob Schwarz oder Weiß besser lesbar ist (Luma-Check)."""
    r, g, b = rgb
    luminance = (0.299 * r + 0.587 * g + 0.114 * b)
    return colors.black if luminance > 0.55 else colors.white


def _draw_debug_overlay(c, w, h, kdp_mode, margin, bleed=0.0):
    c.saveState()
    c.setLineWidth(0.7)
    if kdp_mode and bleed > 0:
        c.setStrokeColor(colors.blue)
        c.rect(0, 0, w, h)  # full page (incl bleed)
        c.setStrokeColor(colors.red)
        c.rect(bleed, bleed, w - 2 * bleed, h - 2 * bleed)  # trim box
    c.setStrokeColor(colors.green)
    c.rect(margin, margin, w - 2 * margin, h - 2 * margin)  # safe area
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    label = "DEBUG: BLUE=EDGE, RED=TRIM, GRN=SAFE" if kdp_mode else "DEBUG: GRN=SAFE"
    c.drawString(margin + 2, h - margin - 10, label)
    c.restoreState()


def _cover_fit_to_page(src_path, out_path, page_w, page_h, quality=85):
    """Bild exakt auf Seite skalieren + zentriert crop (für KDP Full-Page Skizzen)."""
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


def _exif_datetime(file_obj):
    try:
        file_obj.seek(0)
        img = Image.open(file_obj)
        exif = img.getexif()
        dt = exif.get(36867) or exif.get(306)
        file_obj.seek(0)
        return str(dt).strip() if dt else ""
    except Exception:
        return ""


def sort_uploads_smart(uploaded_list):
    """Sortiert Uploads nach EXIF-Datum (falls vorhanden), sonst Upload-Reihenfolge."""
    if not uploaded_list:
        return []
    items = []
    for idx, f in enumerate(uploaded_list):
        dt = _exif_datetime(f)
        items.append((dt, idx, f))

    if sum(1 for dt, _, _ in items if dt) >= 2:
        items.sort(key=lambda x: (x[0] == "", x[0], x[1]))
    else:
        items.sort(key=lambda x: x[1])

    return [f for _, _, f in items]


def foto_zu_skizze(input_path, output_path):
    """Foto -> Skizze (Bleistift-Look)."""
    try:
        img = cv2.imread(input_path)
        if img is None:
            return False
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        inverted = 255 - gray
        blurred = cv2.GaussianBlur(inverted, (21, 21), 0)
        inverted_blurred = 255 - blurred
        sketch = cv2.divide(gray, inverted_blurred, scale=256.0)
        sketch = cv2.normalize(sketch, None, 0, 255, cv2.NORM_MINMAX)
        cv2.imwrite(output_path, sketch)
        return True
    except Exception:
        return False


def zeichne_suchspiel(c, width, y_start, img_height, anzahl):
    """Suchspiel: NUR 3 Grundformen (Kreis/Viereck/Dreieck)."""
    form = random.choice(["kreis", "viereck", "dreieck"])
    c.setLineWidth(2)
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.white)

    y_min, y_max = int(y_start), int(y_start + img_height - 30)
    for _ in range(int(anzahl)):
        x = random.randint(50, int(width) - 50)
        y = random.randint(y_min, y_max) if y_max > y_min else y_min
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


def _kdp_traffic_light(*, kdp_mode, bleed_in, safe_mm, pdf_mb, budget_mb, dpi, debug):
    checks = []
    if not kdp_mode:
        checks.append(("red", "KDP-Modus ist AUS (Interior nicht KDP-ready)."))
        return "red", checks

    if abs(bleed_in - 0.125) < 1e-6:
        checks.append(("green", 'Bleed: 0.125" korrekt.'))
    else:
        checks.append(("red", f'Bleed untypisch: {bleed_in:.3f}".'))

    if safe_mm >= 10.0:
        checks.append(("green", f"Safe-Area Offset: {safe_mm:.1f} mm."))
    elif safe_mm >= 8.0:
        checks.append(("yellow", f"Safe-Area Offset: {safe_mm:.1f} mm (knapp)."))
    else:
        checks.append(("red", f"Safe-Area Offset: {safe_mm:.1f} mm (zu klein)."))

    if pdf_mb <= budget_mb:
        checks.append(("green", f"PDF-Größe: {pdf_mb:.1f} MB."))
    elif pdf_mb <= budget_mb * 1.25:
        checks.append(("yellow", f"PDF-Größe: {pdf_mb:.1f} MB (riskant)."))
    else:
        checks.append(("red", f"PDF-Größe: {pdf_mb:.1f} MB (zu groß)."))

    if dpi >= 240:
        checks.append(("green", f"DPI: {dpi} (Druckqualität ok)."))
    else:
        checks.append(("yellow", f"DPI: {dpi} (etwas niedrig)."))

    if debug:
        checks.append(("green", "Debug-Overlay: AN."))
    else:
        checks.append(("yellow", "Debug-Overlay: AUS (Empfohlen)."))

    worst = "green"
    for lvl, _ in checks:
        if lvl == "red":
            worst = "red"
            break
        if lvl == "yellow":
            worst = "yellow"
    return worst, checks


# =========================================================
# 2) APP UI
# =========================================================

st.set_page_config(page_title="Eddie's Welt – Quest Edition", layout="centered")
st.title("⚔️ Eddie's Welt – Quest Edition")

# DB validation (zeigt sofort Probleme im Repo)
issues = validate_quest_db()
if issues:
    st.warning("Quest-DB hat Probleme:\n- " + "\n- ".join(issues))

with st.sidebar:
    st.header("Einstellungen")
    kdp_mode = st.toggle('📦 KDP-Druckversion (8.5"x8.5")', value=False)
    dpi = st.select_slider("🖨️ Druck-DPI", options=[180, 240, 300], value=240, disabled=not kdp_mode)

    st.divider()
    size_budget_mb = st.select_slider("📦 PDF-Budget (MB)", options=[40, 60, 80, 120, 150], value=80, disabled=not kdp_mode)
    auto_compress = st.toggle("🧯 Auto-Kompression", value=True, disabled=not kdp_mode)
    debug_overlay = st.toggle("🩻 Debug-Overlay", value=False)
    difficulty = st.slider("Schwierigkeitsgrad", 1, 5, 3)
    app_url = st.text_input("QR-Link", "https://eddie-welt.streamlit.app")

kind_name = st.text_input("Name des Kindes", "Eddie").strip()
uploaded_raw = st.file_uploader("Wähle Bilder (max. 24):", accept_multiple_files=True, type=["jpg", "jpeg", "png"])


# =========================================================
# 3) BUILD PDF
# =========================================================
if uploaded_raw:
    MAX_MB = 10
    for f in uploaded_raw[:24]:
        if getattr(f, "size", 0) > MAX_MB * 1024 * 1024:
            st.error(f"⚠️ '{f.name}' ist > {MAX_MB}MB und wird abgelehnt.")
            st.stop()

    sorted_files = sort_uploads_smart(uploaded_raw[:24])

    with st.expander("👀 Vorschau"):
        for i, f in enumerate(sorted_files, start=1):
            st.text(f"{i:02d}. {f.name}")

    if st.button("📘 Buch jetzt binden", use_container_width=True):
        if not kind_name:
            st.error("Bitte Namen eingeben.")
            st.stop()

        status = st.empty()
        status.info("Verarbeitung läuft... 📖")

        with tempfile.TemporaryDirectory() as temp_dir:
            # Uploads -> temp files + deterministic seed parts
            raw_paths, seed_parts = [], []
            for idx, up in enumerate(sorted_files):
                safe_name = Path(up.name).name
                safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", safe_name) or "upload.jpg"
                p = os.path.join(temp_dir, f"{idx:03d}_{safe_name}")
                with open(p, "wb") as f:
                    f.write(up.getbuffer())
                raw_paths.append(p)
                seed_parts.append(f"{safe_name}:{up.size}")

            if not raw_paths:
                st.error("Keine gültigen Bilder.")
                st.stop()

            seed_material = kind_name.strip() + "|" + "|".join(seed_parts)
            random.seed(seed_material.encode("utf-8", errors="ignore"))

            # Fill to 24 deterministically
            final_paths = list(raw_paths)
            pool = list(raw_paths)
            while len(final_paths) < 24:
                tmp = list(pool)
                random.shuffle(tmp)
                final_paths.extend(tmp)
            final_paths = final_paths[:24]

            # Page setup
            BLEED = 0.0
            if kdp_mode:
                TRIM = 8.5 * inch
                BLEED = 0.125 * inch
                w, h = TRIM + 2 * BLEED, TRIM + 2 * BLEED
                margin = BLEED + 0.375 * inch  # SAFE from PDF edge
            else:
                w, h = A4
                margin = 50

            pdf_path = os.path.join(temp_dir, "Quest_Buch.pdf")
            c = canvas.Canvas(pdf_path, pagesize=(w, h))

            jpeg_quality = 85
            estimated_total_mb, pages_done = 0.0, 0
            target_pages = 28 if kdp_mode else 27  # intro+24 + (qr?) + cert

            # -------------------
            # Cover
            c.setFont("Helvetica-Bold", 36)
            c.drawCentredString(w / 2, h / 2 + 20, f"{kind_name.upper()}S QUESTBUCH")
            c.setFont("Helvetica", 14)
            c.drawCentredString(w / 2, h / 2 - 10, "24 Stunden • 24 Missionen")
            if debug_overlay:
                _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)
            c.showPage()

            # -------------------
            # Intro
            c.setFont("Helvetica-Bold", 20)
            c.drawCentredString(w / 2, h - 100, f"Hallo {kind_name}.")
            c.setFont("Helvetica", 14)
            y_txt = h - 160
            for l in ["Das ist deine Quest-Welt.", "Hier gibt es kein Falsch.", "Nimm deinen Stift.", "Leg los."]:
                c.drawCentredString(w / 2, y_txt, l)
                y_txt -= 25
            if debug_overlay:
                _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)
            c.showPage()

            # -------------------
            # Quest pages
            unique_seed = random.randint(0, 999999)
            prog = st.progress(0)

            for i, p_path in enumerate(final_paths):
                prog.progress((i + 1) / 24)

                zone = get_zone_for_hour(i)
                mission = pick_mission_for_time(i, difficulty, seed=unique_seed + i)

                # Header
                header_h = 1.0 * inch
                bg_rgb = get_hour_color(i)
                txt_col = _best_text_color(bg_rgb)

                c.saveState()
                c.setFillColorRGB(*bg_rgb)
                c.rect(0, h - header_h, w, header_h, fill=1, stroke=0)

                c.setFillColor(txt_col)
                c.setFont("Helvetica-Bold", 18)
                c.drawString(margin, h - 0.62 * inch, f"{fmt_hour(i)}  {zone.icon}  {zone.name.upper()}")

                c.setFont("Helvetica", 10)
                c.drawString(margin, h - 0.86 * inch, f"{zone.quest_type} • {zone.atmosphere}")

                c.setFont("Helvetica-Bold", 14)
                c.drawRightString(w - margin, h - 0.62 * inch, f"+{mission.xp} XP")
                c.restoreState()

                # Footer box (Mission)
                footer_h = 1.85 * inch
                footer_y = margin
                c.setFillColor(colors.white)
                c.setStrokeColor(colors.black)
                c.setLineWidth(1.5)
                c.roundRect(margin, footer_y, w - 2 * margin, footer_h, 8, fill=1, stroke=1)

                c.setFillColor(colors.black)
                c.setFont("Helvetica-Bold", 14)
                c.drawString(margin + 0.2 * inch, footer_y + 1.35 * inch, f"MISSION: {mission.title}")

                c.setFont("Helvetica", 11)
                c.drawString(margin + 0.2 * inch, footer_y + 0.95 * inch, f"⚡ {mission.movement}")
                c.drawString(margin + 0.2 * inch, footer_y + 0.65 * inch, f"🧠 {mission.thinking}")

                c.setFont("Helvetica-Oblique", 10)
                c.setFillColor(colors.darkblue)
                c.drawString(margin + 0.2 * inch, footer_y + 0.28 * inch, f"Checkpoint: {mission.proof}")

                # Image area
                out_sk = os.path.join(temp_dir, f"sk_{i:02d}.jpg")
                has_sketch = foto_zu_skizze(p_path, out_sk)

                img_y = footer_y + footer_h + 0.25 * inch
                img_h = h - header_h - img_y - 0.35 * inch
                img_w = w - 2 * margin

                if has_sketch:
                    if kdp_mode:
                        px_w = int((w / inch) * int(dpi))
                        px_h = int((h / inch) * int(dpi))
                        out_bl = os.path.join(temp_dir, f"bl_{i:02d}.jpg")
                        ok = _cover_fit_to_page(out_sk, out_bl, px_w, px_h, quality=jpeg_quality)

                        if ok and os.path.exists(out_bl):
                            c.drawImage(out_bl, 0, 0, width=w, height=h)  # full page (with bleed)
                            try:
                                file_mb = os.path.getsize(out_bl) / (1024 * 1024)
                            except Exception:
                                file_mb = 0.0
                        else:
                            c.drawImage(out_sk, margin, img_y, width=img_w, height=img_h, preserveAspectRatio=True)
                            try:
                                file_mb = os.path.getsize(out_sk) / (1024 * 1024)
                            except Exception:
                                file_mb = 0.0

                        pages_done += 1
                        estimated_total_mb += file_mb
                        est_full = (estimated_total_mb / max(1, pages_done)) * target_pages

                        if auto_compress and est_full > float(size_budget_mb) and jpeg_quality > 60:
                            jpeg_quality = max(60, jpeg_quality - 5)
                            st.info(f"🧯 Auto-Kompression: {jpeg_quality}%")

                        # Suchspiel (auf Bildfläche)
                        zeichne_suchspiel(c, w, img_y, img_h, random.randint(3, 6))
                    else:
                        c.drawImage(out_sk, margin, img_y, width=img_w, height=img_h, preserveAspectRatio=True)
                        zeichne_suchspiel(c, w, img_y, img_h, random.randint(3, 6))
                else:
                    c.setFillColor(colors.lightgrey)
                    c.rect(margin, img_y, img_w, img_h, fill=1, stroke=0)
                    c.setFillColor(colors.darkgrey)
                    c.setFont("Helvetica", 14)
                    c.drawCentredString(w / 2, img_y + img_h / 2, "Bild konnte nicht verarbeitet werden")

                # Timeline
                line_y = footer_y - 0.15 * inch
                c.setLineWidth(1)
                c.setStrokeColor(colors.gray)
                c.line(margin, line_y, w - margin, line_y)
                for dot in range(24):
                    dot_x = margin + dot * ((w - 2 * margin) / 23)
                    c.setFillColor(colors.black if dot <= i else colors.lightgrey)
                    c.circle(dot_x, line_y, 3 if dot != i else 6, fill=1, stroke=0)

                if debug_overlay:
                    _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)

                c.showPage()

            # -------------------
            # QR page (nur KDP)
            if kdp_mode and app_url:
                c.setFont("Helvetica-Bold", 16)
                c.drawCentredString(w / 2, h / 2 + 80, "Scan & erneut erstellen")
                qr = qrcode.make(app_url)
                qr_p = os.path.join(temp_dir, "qr.png")
                qr.save(qr_p)
                c.drawImage(qr_p, (w - 120) / 2, h / 2 - 60, 120, 120)
                c.setFont("Helvetica", 10)
                c.drawCentredString(w / 2, h / 2 - 80, app_url)
                if debug_overlay:
                    _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)
                c.showPage()

            # -------------------
            # Urkunde
            c.setStrokeColor(colors.black)
            c.setLineWidth(2)
            c.rect(margin, margin, w - 2 * margin, h - 2 * margin)
            c.setFont("Helvetica-Bold", 30)
            c.drawCentredString(w / 2, h / 2 + 40, "URKUNDE")
            c.setFont("Helvetica", 14)
            c.drawCentredString(w / 2, h / 2, f"{kind_name} hat seine Missionen gemeistert!")
            c.setFont("Helvetica", 10)
            c.drawCentredString(w / 2, margin + 20, "Du hast den Tag gemeistert.")
            if debug_overlay:
                _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)
            c.showPage()

            c.save()

            # -------------------
            # DOWNLOAD + PREFLIGHT
            pdf_bytes = open(pdf_path, "rb").read()
            size_mb = len(pdf_bytes) / (1024 * 1024)

            st.caption(f"📦 PDF: {size_mb:.1f} MB | Qualität: {jpeg_quality}%")

            if kdp_mode:
                st.subheader("🚦 KDP-Preflight")
                safe_mm = _in_to_mm(float(margin / inch))  # (bleed+safe) in mm
                level, checks = _kdp_traffic_light(
                    kdp_mode=True,
                    bleed_in=0.125,
                    safe_mm=safe_mm,
                    pdf_mb=size_mb,
                    budget_mb=float(size_budget_mb),
                    dpi=int(dpi),
                    debug=bool(debug_overlay),
                )

                if level == "green":
                    st.success("🟢 GRÜN – Bereit.")
                elif level == "yellow":
                    st.warning("🟡 GELB – Optimierung möglich.")
                else:
                    st.error("🔴 ROT – Bitte beheben.")

                for lvl, msg in checks:
                    st.write(f"{'✅' if lvl=='green' else '⚠️' if lvl=='yellow' else '❌'} {msg}")

                if level != "green":
                    with st.expander("🛠️ Strategie"):
                        if size_mb > float(size_budget_mb):
                            st.write("- **Größe:** DPI auf 240 / Budget hoch / Auto-Kompression an.")
                        if not debug_overlay:
                            st.write("- **Check:** Debug-Overlay an, um Safe/Bleed zu sehen.")

            suffix = "_KDP" if kdp_mode else "_A4"
            st.download_button(
                "📥 PDF herunterladen",
                data=pdf_bytes,
                file_name=f"{kind_name}_Questbuch{suffix}.pdf",
                use_container_width=True,
            )

            status.success("Fertig! ✅")
