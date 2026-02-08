# ==========================================================
# app.py — Eddie's Welt QUEST EDITION (PRODUKTIONSREIF)
# ==========================================================

import streamlit as st
import cv2
import os
import random
import tempfile
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import inch
from quest_data import get_zone_for_hour, pick_mission_for_time, fmt_hour

st.set_page_config(page_title="Eddie's Welt – Quest Edition", layout="centered")

# ----------------------------------------------------------
# SKETCH (MIT HARTER KOMPRESSION → KLEINE PDFS!)
# ----------------------------------------------------------
def foto_zu_skizze(inp, out):
    img = cv2.imread(inp)
    if img is None:
        return False
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    inv = 255 - gray
    blur = cv2.GaussianBlur(inv, (21,21), 0)
    sketch = cv2.divide(gray, 255-blur, scale=256)
    cv2.imwrite(out, sketch, [int(cv2.IMWRITE_JPEG_QUALITY), 55])
    return True

# ----------------------------------------------------------
# PDF BUILDER
# ----------------------------------------------------------
def build_pdf(files, name, difficulty):
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for i,f in enumerate(files):
            p = os.path.join(tmp, f"{i}.jpg")
            with open(p,"wb") as o:
                o.write(f.getbuffer())
            paths.append(p)

        while len(paths) < 24:
            paths += paths
        paths = paths[:24]

        pdf_path = os.path.join(tmp, "Questbuch.pdf")
        c = canvas.Canvas(pdf_path, pagesize=A4)
        w,h = A4
        margin = 40

        # COVER
        c.setFont("Helvetica-Bold", 32)
        c.drawCentredString(w/2, h/2, f"{name.upper()}S QUESTBUCH")
        c.showPage()

        seed = random.randint(0,999999)

        for i,p in enumerate(paths):
            zone = get_zone_for_hour(i)
            mission = pick_mission_for_time(i, difficulty, seed+i)

            c.setFillColorRGB(*zone.color)
            c.rect(0, h-80, w, 80, fill=1)

            c.setFillColor(colors.black)
            c.setFont("Helvetica-Bold", 20)
            c.drawString(margin, h-40, f"{fmt_hour(i)} {zone.icon} {zone.name}")

            c.setFont("Helvetica", 12)
            c.drawString(margin, h-60, mission.title)

            sk = os.path.join(tmp, f"sk{i}.jpg")
            if foto_zu_skizze(p, sk):
                c.drawImage(sk, margin, margin+80, w-2*margin, h-200, preserveAspectRatio=True)

            c.setFont("Helvetica-Bold", 12)
            c.drawString(margin, margin+40, f"⚡ {mission.movement}")
            c.drawString(margin, margin+25, f"🧠 {mission.thinking}")
            c.drawRightString(w-margin, margin+25, f"+{mission.xp} XP")

            c.showPage()

        c.save()
        with open(pdf_path,"rb") as f:
            return f.read()

# ----------------------------------------------------------
# UI
# ----------------------------------------------------------
st.title("⚔️ Eddie's Welt – Quest Generator")

name = st.text_input("Name des Kindes", "Eddie")
difficulty = st.slider("Schwierigkeit", 1,5,2)
files = st.file_uploader("Bilder (bis 24)", accept_multiple_files=True)

if files and st.button("📘 QUESTBUCH ERSTELLEN"):
    pdf = build_pdf(files[:24], name, difficulty)
    st.download_button("📥 Download Questbuch", pdf, "Questbuch.pdf")
