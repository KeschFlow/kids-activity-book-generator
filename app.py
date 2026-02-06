import streamlit as st
import cv2
import numpy as np
import os
import random
import tempfile
import re
from pathlib import Path
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.lib import colors
from reportlab.lib.units import inch

# --- HILFSFUNKTIONEN ---

def _safe_filename(name: str) -> str:
    base = Path(name).name
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base if base else "upload.jpg"

def foto_zu_skizze(input_path, output_path):
    try:
        img = cv2.imread(input_path)
        if img is None: return False
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        inverted = 255 - gray
        blurred = cv2.GaussianBlur(inverted, (21, 21), 0)
        inverted_blurred = 255 - blurred
        sketch = cv2.divide(gray, inverted_blurred, scale=256.0)
        sketch = cv2.normalize(sketch, None, 0, 255, cv2.NORM_MINMAX)
        cv2.imwrite(output_path, sketch)
        return True
    except: return False

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
        if form == "kreis": c.circle(x, y, s / 2, fill=1, stroke=1)
        elif form == "viereck": c.rect(x - s / 2, y - s / 2, s, s, fill=1, stroke=1)
        else:
            p = c.beginPath()
            p.moveTo(x, y + s / 2); p.lineTo(x - s / 2, y - s / 2); p.lineTo(x + s / 2, y - s / 2); p.close()
            c.drawPath(p, fill=1, stroke=1)
    legend_y = max(50, y_start - 30)
    c.setFillColor(colors.white)
    if form == "kreis": c.circle(80, legend_y + 5, 8, fill=0, stroke=1)
    elif form == "viereck": c.rect(72, legend_y - 3, 16, 16, fill=0, stroke=1)
    else: 
        p = c.beginPath()
        p.moveTo(80, legend_y + 13); p.lineTo(72, legend_y - 3); p.lineTo(88, legend_y - 3); p.close()
        c.drawPath(p, fill=0, stroke=1)
    c.setFillColor(colors.black); c.setFont("Helvetica-Bold", 16)
    c.drawString(100, legend_y, f"x {anzahl}")

def zeichne_fortschritt(c, width, stunde, y=40, margin=50):
    step = (width - 2 * margin) / 23
    c.setLineWidth(2); c.setStrokeColor(colors.gray); c.line(margin, y, width - margin, y)
    for i in range(24):
        cx = margin + i * step
        if i < stunde:
            c.setFillColor(colors.black); c.circle(cx, y, 4, fill=1, stroke=0)
        elif i == stunde:
            c.setFillColor(colors.white); c.setStrokeColor(colors.black); c.setLineWidth(3); c.circle(cx, y, 8, fill=1, stroke=1)
        else:
            c.setFillColor(colors.white); c.setStrokeColor(colors.lightgrey); c.setLineWidth(1); c.circle(cx, y, 3, fill=1, stroke=1)

def _draw_qr(c, url, x, y, size):
    qr = qrcode.QRCode(box_size=10, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    img_qr = qr.make_image(fill_color="black", back_color="white")
    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        img_qr.save(tmp.name)
        c.drawImage(tmp.name, x, y, width=size, height=size)
    os.unlink(tmp.name)

# --- UI ---
st.set_page_config(page_title="Eddie's Welt", layout="centered")
st.title("✏️ Eddie's Welt")

with st.sidebar:
    st.header("Einstellungen")
    kdp_mode = st.toggle('📦 KDP-Druckversion (8.5"x8.5")', value=False)
    app_url = st.text_input("App-Link für QR-Code", "https://eddie-welt.streamlit.app")

kind_name = st.text_input("Wie heißt das Kind?", "Eddie").strip()
uploaded_files = st.file_uploader("24 Bilder hochladen:", accept_multiple_files=True, type=["jpg", "jpeg", "png"])

if st.button("Buch binden", use_container_width=True):
    if not uploaded_files:
        st.error("Bilder fehlen!")
    else:
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_paths = []
            for idx, up in enumerate(uploaded_files[:24]):
                fname = f"{idx:03d}_{_safe_filename(up.name)}"
                p = os.path.join(temp_dir, fname)
                with open(p, "wb") as f: f.write(up.getbuffer())
                raw_paths.append(p)

            # Seed für Reproduzierbarkeit
            seed_parts = [f"{os.path.basename(p)}:{os.path.getsize(p)}" for p in raw_paths]
            random.seed((kind_name + "".join(seed_parts)).encode())

            # PDF Setup
            if kdp_mode:
                w, h = 8.5 * inch, 8.5 * inch
                margin = 0.375 * inch
            else:
                w, h = A4
                margin = 50
            
            pdf_path = os.path.join(temp_dir, "buch.pdf")
            c = canvas.Canvas(pdf_path, pagesize=(w, h))

            # Cover
            c.setFont("Helvetica-Bold", 40); c.drawCentredString(w/2, h/2+20, f"{kind_name.upper()}S REISE"); c.showPage()

            # Manifest
            c.setFont("Helvetica-Bold", 24); c.drawCentredString(w/2, h-120, f"Hallo {kind_name}.")
            lines = ["Das ist deine Welt.", "Hier gibt es kein Falsch.", "Nimm deinen Stift.", "Leg los."]
            y_txt = h-200
            for l in lines: c.drawCentredString(w/2, y_txt, l); y_txt -= 30
            c.showPage()

            # Seiten
            for i, p_path in enumerate(raw_paths):
                c.setFont("Helvetica-Bold", 30); c.drawCentredString(w/2, h-60, f"{i:02d}:00 Uhr")
                out_skizze = os.path.join(temp_dir, f"sk_{i}.jpg")
                if foto_zu_skizze(p_path, out_skizze):
                    c.drawImage(out_skizze, margin, margin+100, width=w-2*margin, height=h-2*margin-160, preserveAspectRatio=True)
                    zeichne_suchspiel(c, w, margin+100, h-2*margin-160, random.randint(3,6))
                zeichne_fortschritt(c, w, i, y=margin+30, margin=margin)
                c.showPage()

            # Solidarity QR (Nur KDP)
            if kdp_mode:
                c.setFont("Helvetica-Bold", 18); c.drawCentredString(w/2, h-100, "Teile die Magie!")
                _draw_qr(c, app_url, (w-120)/2, h/2-60, 120)
                c.showPage()

            # Urkunde
            c.rect(margin, margin, w-2*margin, h-2*margin)
            c.setFont("Helvetica-Bold", 30); c.drawCentredString(w/2, h/2, "URKUNDE"); c.showPage()
            c.save()

            with open(pdf_path, "rb") as f:
                st.download_button("📥 Buch herunterladen", f.read(), file_name=f"{kind_name}_Welt.pdf")
