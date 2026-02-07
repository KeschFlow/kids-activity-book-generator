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

# =========================================================
# 0) STREAMLIT CONFIG (MUSS ALS ERSTES KOMMEN)
# =========================================================
st.set_page_config(page_title="Eddie's Welt", layout="centered")

# =========================================================
# 1) CORE HELPERS
# =========================================================

def _in_to_mm(x_in: float) -> float:
    return float(x_in) * 25.4

def _draw_debug_overlay(c, w, h, kdp_mode, margin, bleed=0.0):
    c.saveState()
    c.setLineWidth(0.7)

    if kdp_mode and bleed > 0:
        c.setStrokeColor(colors.blue)   # PDF edge
        c.rect(0, 0, w, h)
        c.setStrokeColor(colors.red)    # Trim
        c.rect(bleed, bleed, w - 2*bleed, h - 2*bleed)

    c.setStrokeColor(colors.green)      # Safe Area
    c.rect(margin, margin, w - 2*margin, h - 2*margin)

    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8)
    label = "DEBUG: BLUE=EDGE, RED=TRIM, GRN=SAFE" if kdp_mode else "DEBUG: GRN=SAFE"
    c.drawString(margin + 2, h - margin - 10, label)
    c.restoreState()

def _cover_fit_to_page(src_path, out_path, page_w, page_h, quality=85):
    """
    src_path: grayscale sketch jpg
    out_path: resized/cropped jpg in target pixel dims (page_w,page_h)
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
    except:
        return False

def foto_zu_skizze(input_path, output_path):
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
    except:
        return False

def zeichne_suchspiel(c, width, y_start, img_height, anzahl):
    form = random.choice(["kreis", "viereck", "dreieck"])
    c.setLineWidth(2)
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.white)

    y_min, y_max = int(y_start), int(y_start + img_height - 30)
    for _ in range(anzahl):
        x = random.randint(50, int(width) - 50)
        y = random.randint(y_min, y_max) if y_max > y_min else y_min
        s = random.randint(15, 25)

        if form == "kreis":
            c.circle(x, y, s / 2, fill=1, stroke=1)
        elif form == "viereck":
            c.rect(x - s / 2, y - s / 2, s, s, fill=1, stroke=1)
        else:
            p = c.beginPath()
            p.moveTo(x, y + s/2)
            p.lineTo(x - s/2, y - s/2)
            p.lineTo(x + s/2, y - s/2)
            p.close()
            c.drawPath(p, fill=1, stroke=1)

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
    Sort by EXIF datetime if available (needs >=2 images with dt), else keep upload order.
    """
    if not uploaded_list:
        return []
    items = []
    for idx, f in enumerate(uploaded_list):
        dt_str = ""
        try:
            f.seek(0)
            img = Image.open(f)
            exif = img.getexif()
            dt = exif.get(36867) or exif.get(306)
            f.seek(0)
            dt_str = str(dt).strip() if dt else ""
        except:
            dt_str = ""
        items.append((dt_str, idx, f))

    if sum(1 for d, _, _ in items if d) >= 2:
        items.sort(key=lambda x: (x[0] == "", x[0], x[1]))
    else:
        items.sort(key=lambda x: x[1])

    return [f for _, _, f in items]

def _kdp_traffic_light(*, kdp_mode, bleed_in, safe_mm, pdf_mb, budget_mb, dpi, debug):
    checks = []
    if not kdp_mode:
        return "red", [("red", "KDP-Modus AUS.")]

    if abs(float(bleed_in) - 0.125) < 1e-6:
        checks.append(("green", 'Bleed: 0.125" ok.'))
    else:
        checks.append(("red", f'Bleed: {float(bleed_in):.3f}".'))

    if safe_mm >= 10.0:
        checks.append(("green", f"Safe-Area Offset: {safe_mm:.1f} mm."))
    elif safe_mm >= 8.0:
        checks.append(("yellow", f"Safe-Area Offset: {safe_mm:.1f} mm (knapp)."))
    else:
        checks.append(("red", f"Safe-Area Offset: {safe_mm:.1f} mm (zu klein)."))

    # Budget-Ampel: Gelb bis +25% tolerieren
    if pdf_mb <= budget_mb:
        checks.append(("green", f"PDF-Größe: {pdf_mb:.1f} MB."))
    elif pdf_mb <= budget_mb * 1.25:
        checks.append(("yellow", f"PDF-Größe: {pdf_mb:.1f} MB (über Budget)."))
    else:
        checks.append(("red", f"PDF-Größe: {pdf_mb:.1f} MB (Upload-Risiko)."))

    if int(dpi) >= 240:
        checks.append(("green", f"DPI: {int(dpi)} (ok)."))
    else:
        checks.append(("yellow", f"DPI: {int(dpi)} (niedrig)."))

    if bool(debug):
        checks.append(("green", "Röntgen-Overlay: AN."))
    else:
        checks.append(("yellow", "Röntgen-Overlay: AUS (für Testlauf: AN empfohlen)."))

    worst = "green"
    for lvl, _ in checks:
        if lvl == "red":
            worst = "red"
            break
        if lvl == "yellow":
            worst = "yellow"
    return worst, checks

# =========================================================
# 2) BUILD LOGIC
# =========================================================

def build_pdf(*, sorted_files, kind_name, kdp_mode, dpi, size_budget_mb, auto_compress, debug_overlay, app_url):
    with tempfile.TemporaryDirectory() as temp_dir:
        raw_paths, seed_parts = [], []

        for idx, up in enumerate(sorted_files):
            safe_name = Path(up.name).name
            safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", safe_name) or "upload.jpg"
            p = os.path.join(temp_dir, f"{idx:03d}_{safe_name}")
            with open(p, "wb") as f:
                f.write(up.getbuffer())
            raw_paths.append(p)
            seed_parts.append(f"{safe_name}:{up.size}")

        # Reproduzierbarer Shuffle pro Kind + Uploadset
        random.seed((kind_name.strip() + "|" + "|".join(seed_parts)).encode("utf-8", errors="ignore"))

        final_paths = list(raw_paths)
        pool = list(final_paths)

        if not pool:
            raise RuntimeError("Keine gültigen Bilder erhalten (Upload- oder Dekodier-Fehler).")

        while len(final_paths) < 24:
            tmp_p = list(pool)
            random.shuffle(tmp_p)
            final_paths.extend(tmp_p)
        final_paths = final_paths[:24]

        BLEED = 0.125 * inch if kdp_mode else 0.0
        if kdp_mode:
            TRIM = 8.5 * inch
            w, h = TRIM + 2 * BLEED, TRIM + 2 * BLEED
            margin = BLEED + 0.375 * inch
        else:
            w, h = A4
            margin = 50

        pdf_path = os.path.join(temp_dir, "output.pdf")
        c = canvas.Canvas(pdf_path, pagesize=(w, h))

        jpeg_quality = 85
        est_mb = 0.0
        done = 0
        target_pages = 28 if kdp_mode else 27

        # COVER
        c.setFont("Helvetica-Bold", 36)
        c.drawCentredString(w / 2, h / 2 + 20, f"{kind_name.upper()}S REISE")
        if debug_overlay:
            _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)
        c.showPage()

        # MANIFEST
        c.setFont("Helvetica-Bold", 20)
        c.drawCentredString(w / 2, h - 100, f"Hallo {kind_name}.")
        y_txt = h - 160
        for l in ["Das ist deine Welt.", "Hier gibt es kein Falsch.", "Nimm deinen Stift.", "Leg los."]:
            c.drawCentredString(w / 2, y_txt, l)
            y_txt -= 25
        if debug_overlay:
            _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)
        c.showPage()

        # CONTENT
        prog = st.progress(0)
        for i, p_path in enumerate(final_paths):
            prog.progress((i + 1) / 24.0)

            c.setFont("Helvetica-Bold", 24)
            c.drawCentredString(w / 2, h - 60, f"{i:02d}:00 Uhr")

            out_sk = os.path.join(temp_dir, f"sk_{i:02d}.jpg")
            ok_sketch = foto_zu_skizze(p_path, out_sk)

            file_mb = 0.0
            draw_done = False

            if ok_sketch:
                if kdp_mode:
                    px_w, px_h = int((w / inch) * int(dpi)), int((h / inch) * int(dpi))
                    out_bl = os.path.join(temp_dir, f"bl_{i:02d}.jpg")

                    ok_bleed = _cover_fit_to_page(out_sk, out_bl, px_w, px_h, quality=jpeg_quality)

                    if ok_bleed and os.path.exists(out_bl):
                        c.drawImage(out_bl, 0, 0, width=w, height=h)
                        draw_done = True
                        try:
                            file_mb = os.path.getsize(out_bl) / (1024 * 1024)
                        except:
                            pass
                    else:
                        # Fallback: draw sketch within safe content area
                        c.drawImage(
                            out_sk,
                            margin,
                            margin + 80,
                            width=w - 2 * margin,
                            height=h - 2 * margin - 140,
                            preserveAspectRatio=True,
                        )
                        draw_done = True
                        try:
                            file_mb = os.path.getsize(out_sk) / (1024 * 1024)
                        except:
                            pass

                    # Budget-Bremse: zählt auch Fallback (out_sk)
                    done += 1
                    est_mb += file_mb
                    est_full = (est_mb / max(1, done)) * target_pages
                    if auto_compress and est_full > float(size_budget_mb) and jpeg_quality > 60:
                        jpeg_quality = max(60, jpeg_quality - 5)
                        st.info(f"🧯 Auto-Kompression: {jpeg_quality}%")

                else:
                    c.drawImage(
                        out_sk,
                        margin,
                        margin + 80,
                        width=w - 2 * margin,
                        height=h - 2 * margin - 140,
                        preserveAspectRatio=True,
                    )
                    draw_done = True

                # Suchspiel nur wenn Bild gesetzt wurde
                if draw_done:
                    zeichne_suchspiel(c, w, margin + 80, h - 2 * margin - 140, random.randint(3, 6))

            # Timeline
            line_y = margin + 30
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

        # QR PAGE (KDP) – mit Kontext
        if kdp_mode:
            c.setFont("Helvetica-Bold", 16)
            c.drawCentredString(w / 2, h / 2 + 90, "Teile die Magie!")
            c.setFont("Helvetica", 11)
            c.drawCentredString(w / 2, h / 2 + 65, "Scanne den QR-Code für die App:")

            qr = qrcode.make(app_url)
            qr_p = os.path.join(temp_dir, "qr.png")
            qr.save(qr_p)

            c.drawImage(qr_p, (w - 140) / 2, h / 2 - 70, 140, 140)
            c.setFont("Helvetica", 10)
            c.drawCentredString(w / 2, h / 2 - 85, app_url)

            if debug_overlay:
                _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)
            c.showPage()

        # URKUNDE
        c.rect(margin, margin, w - 2 * margin, h - 2 * margin)
        c.setFont("Helvetica-Bold", 30)
        c.drawCentredString(w / 2, h / 2 + 40, "URKUNDE")
        c.setFont("Helvetica", 14)
        c.drawCentredString(w / 2, h / 2, f"für {kind_name.upper()}")
        c.setFont("Helvetica", 10)
        c.drawCentredString(w / 2, margin + 20, "Du hast den Tag gemeistert.")

        if debug_overlay:
            _draw_debug_overlay(c, w, h, kdp_mode, margin, BLEED)

        c.showPage()
        c.save()

        pdf_bytes = open(pdf_path, "rb").read()
        size_mb = len(pdf_bytes) / (1024 * 1024)
        return pdf_bytes, size_mb, jpeg_quality, margin, BLEED

# =========================================================
# 3) APP UI
# =========================================================

st.title("✏️ Eddie's Welt")

with st.sidebar:
    st.header("Einstellungen")
    kdp_mode = st.toggle('📦 KDP-Druckversion (8.5"x8.5")', value=False)
    dpi = st.select_slider("🖨️ Druck-DPI", options=[180, 240, 300], value=240, disabled=not kdp_mode)
    st.divider()
    size_budget_mb = st.select_slider("📦 PDF-Budget (MB)", options=[40, 60, 80, 120, 150], value=80, disabled=not kdp_mode)
    auto_compress = st.toggle("🧯 Auto-Kompression", value=True, disabled=not kdp_mode)

    # UX: getrennt
    roentgen_overlay = st.toggle("🩻 Röntgen-Overlay (Trim/Safe)", value=False)
    debug_mode = st.toggle("🧰 Debug (Fehlerdetails)", value=False)

    app_url = st.text_input("QR-Link", "https://eddie-welt.streamlit.app")

kind_name = st.text_input("Name des Kindes", "Eddie").strip()
uploaded_raw = st.file_uploader("Wähle Bilder (max. 24):", accept_multiple_files=True, type=["jpg", "jpeg", "png"])

if uploaded_raw:
    oversize = next((f for f in uploaded_raw[:24] if f.size > 10 * 1024 * 1024), None)
    if oversize:
        st.error(f"⚠️ '{oversize.name}' zu groß (max. 10MB).")
    else:
        sorted_files = sort_uploads_smart(uploaded_raw[:24])

        with st.expander("👀 Vorschau Timeline"):
            for i, f in enumerate(sorted_files, start=1):
                st.text(f"{i:02d}. {f.name}")

        if st.button("📘 Buch jetzt binden", use_container_width=True):
            if not kind_name:
                st.error("Bitte Namen eingeben.")
            elif not sorted_files:
                st.error("Bitte Bilder hochladen.")
            else:
                status = st.empty()
                status.info("Bindevorgang läuft... 📖")

                try:
                    pdf_bytes, size_mb, q, m, bl = build_pdf(
                        sorted_files=sorted_files,
                        kind_name=kind_name,
                        kdp_mode=bool(kdp_mode),
                        dpi=int(dpi),
                        size_budget_mb=float(size_budget_mb),
                        auto_compress=bool(auto_compress),
                        debug_overlay=bool(roentgen_overlay),
                        app_url=str(app_url).strip() or "https://eddie-welt.streamlit.app",
                    )

                    status.empty()
                    st.caption(f"📦 PDF: {size_mb:.1f} MB | Qualität: {q}%")

                    if kdp_mode:
                        st.subheader("🚦 KDP-Preflight")
                        safe_mm = _in_to_mm(float(m / inch))
                        lvl, checks = _kdp_traffic_light(
                            kdp_mode=True,
                            bleed_in=0.125,
                            safe_mm=safe_mm,
                            pdf_mb=float(size_mb),
                            budget_mb=float(size_budget_mb),
                            dpi=int(dpi),
                            debug=bool(roentgen_overlay),
                        )
                        (st.success if lvl == "green" else st.warning if lvl == "yellow" else st.error)(
                            "KDP-Status: " + lvl.upper()
                        )
                        for l, msg in checks:
                            st.write(f"{'✅' if l=='green' else '⚠️' if l=='yellow' else '❌'} {msg}")

                    st.download_button(
                        "📥 PDF herunterladen",
                        data=pdf_bytes,
                        file_name=f"{kind_name}_Welt{'_KDP' if kdp_mode else '_A4'}.pdf",
                        use_container_width=True,
                    )

                except RuntimeError as e:
                    status.empty()
                    st.error("❌ Export fehlgeschlagen.")
                    st.info(str(e))
                    st.info("Tipp: Probiere andere Bilder oder reduziere im KDP-Modus die DPI auf 240.")
                    if debug_mode:
                        st.exception(e)

                except Exception as e:
                    status.empty()
                    st.error("❌ Export fehlgeschlagen.")
                    st.info("Bitte probiere andere Bilder aus oder reduziere im KDP-Modus die DPI auf 240.")
                    if debug_mode:
                        st.exception(e)

            status.success("Buch fertig!")
            with open(pdf_path, "rb") as f:
                st.download_button("📥 Buch herunterladen", f.read(), file_name=f"{kind_name}_Welt.pdf", use_container_width=True)
            with open(pdf_path, "rb") as f:
                st.download_button("📥 Buch herunterladen", f.read(), file_name=f"{kind_name}_Welt.pdf")
