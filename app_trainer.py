# app_trainer.py
from __future__ import annotations

import io
from typing import List, Tuple

import streamlit as st
from reportlab.pdfgen import canvas

from kern.pdf_engine import get_page_spec, draw_box, embed_image


def parse_vocab_lines(raw: str) -> List[Tuple[str, str]]:
    """
    Erwartet pro Zeile:
      wort;übersetzung
    oder nur:
      wort
    Trenner: ";" oder "," oder TAB
    """
    items: List[Tuple[str, str]] = []
    for line in (raw or "").splitlines():
        s = line.strip()
        if not s:
            continue
        for sep in (";", "\t", ","):
            if sep in s:
                a, b = s.split(sep, 1)
                items.append((a.strip(), b.strip()))
                break
        else:
            items.append((s, ""))
    return items


def build_trainer_pdf(
    *,
    vocab: List[Tuple[str, str]],
    uploads: List,
    kdp_mode: bool,
) -> bytes:
    spec = get_page_spec(kdp_mode=kdp_mode)
    w, h, safe = spec.page_w, spec.page_h, spec.safe

    # Uploads -> BytesIO (RAM only)
    img_buffers: List[io.BytesIO] = []
    for up in uploads or []:
        # up.getvalue() ist bereits bytes im RAM (Streamlit)
        img_buffers.append(io.BytesIO(up.getvalue()))

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(w, h))

    # Layout-Parameter (einfach, robust)
    header_h = 60
    word_box_h = 120
    img_box_h = 200
    notes_h = 120
    gap = 16

    usable_w = w - 2 * safe
    y = h - safe

    img_idx = 0

    for i, (word, tr) in enumerate(vocab, start=1):
        # Header
        c.setFont("Helvetica-Bold", 22)
        c.drawString(safe, y - 30, f"Vokabel {i}/{len(vocab)}")

        # Wort-Box
        y_word_top = y - header_h
        draw_box(c, safe, y_word_top - word_box_h, usable_w, word_box_h, title="WORT")
        c.setFont("Helvetica-Bold", 34)
        c.drawCentredString(w / 2, y_word_top - 78, word[:40])

        # Übersetzung (optional)
        if tr:
            c.setFont("Helvetica", 16)
            c.drawCentredString(w / 2, y_word_top - 105, tr[:60])

        # Bild-Box
        y_img_top = y_word_top - word_box_h - gap
        if img_buffers:
            draw_box(c, safe, y_img_top - img_box_h, usable_w, img_box_h, title="BILD")
            img_buf = img_buffers[img_idx % len(img_buffers)]
            img_buf.seek(0)
            embed_image(
                c,
                img_data=img_buf,
                x=safe,
                y=y_img_top - img_box_h,
                max_w=usable_w,
                max_h=img_box_h,
                preserve_aspect=True,
                scale_to=0.5,          # wie gewünscht: max 50% der Box
                debug_on_error=False,  # auf True, wenn du Fehlertexte willst
            )
            img_idx += 1
        else:
            draw_box(c, safe, y_img_top - img_box_h, usable_w, img_box_h, title="BILD (optional)")

        # Notizen/Beispielsatz
        y_notes_top = y_img_top - img_box_h - gap
        draw_box(c, safe, y_notes_top - notes_h, usable_w, notes_h, title="NOTIZEN / SATZ")
        c.setFont("Helvetica", 12)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(safe + 12, y_notes_top - 40, "Schreibe einen Satz mit dem Wort:")

        c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()


# ----------------------------
# UI
# ----------------------------
st.set_page_config(page_title="Eddie Trainer V2", layout="centered")
st.title("🧠 Eddie Trainer V2 – Vokabeln mit echten Bildern")

with st.sidebar:
    kdp_mode = st.toggle('📦 KDP Druckmodus (8.5"x8.5" + Bleed)', value=True)
    st.caption("Safe Zone: 0.375\" vom Rand (plus Bleed).")

raw = st.text_area(
    "Vokabeln (eine Zeile pro Eintrag) – Format: wort;übersetzung (Übersetzung optional)",
    value="Nadel;needle\nApfel;apple\nTür;door",
    height=180,
)

uploads = st.file_uploader(
    "Bilder hochladen (JPG/PNG) – werden zyklisch auf die Seiten verteilt",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

vocab = parse_vocab_lines(raw)
col1, col2 = st.columns(2)
with col1:
    st.metric("Vokabeln", len(vocab))
with col2:
    st.metric("Bilder", len(uploads) if uploads else 0)

if st.button("PDF generieren", type="primary", disabled=(len(vocab) == 0)):
    try:
        pdf_bytes = build_trainer_pdf(vocab=vocab, uploads=uploads or [], kdp_mode=kdp_mode)
        st.success("PDF fertig!")
        st.download_button("Download PDF", data=pdf_bytes, file_name="eddie_trainer_v2.pdf", mime="application/pdf")
    except Exception as e:
        st.error(f"Fehler: {e}")
