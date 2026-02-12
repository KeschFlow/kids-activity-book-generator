# app_trainer.py  — Eddie Trainer V2 (Platinum)
# Features:
# - Fach auswählen (SUBJECTS) ODER eigene Vokabeln tippen
# - Optional: Bilder hochladen (zyklisch verteilt)
# - Wenn KEINE Bilder: automatisch Piktogramm/Icon (Registry) pro Fach
# - Schreiblinien (Schönschrift) pro Seite
# - Multiple-Choice Quiz-Seiten (A/B/C/D) am Ende (optional)
# - KDP-Mode via get_page_spec (Safe-Zone sauber)

from __future__ import annotations

import io
import random
from typing import List, Tuple, Optional, Dict, Any

import streamlit as st
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch

from kern.pdf_engine import get_page_spec, draw_box, embed_image

# Optional: subject_data (falls vorhanden)
try:
    from kern.subject_data import SUBJECTS, AUTO_ICON
except Exception:
    SUBJECTS = {}
    AUTO_ICON = {}

# Optional: Icon-Registry (falls du draw_icon() schon hast)
try:
    from kern.pdf_engine import draw_icon  # erwartet: draw_icon(c, key=..., x=..., y=..., size=...) -> bool
except Exception:
    draw_icon = None


# -----------------------------
# Parsing / Datenaufbereitung
# -----------------------------
def parse_vocab_lines(raw: str) -> List[Tuple[str, str]]:
    """
    Pro Zeile:
      deutsch;übersetzung
    oder nur:
      deutsch
    """
    items: List[Tuple[str, str]] = []
    for line in (raw or "").splitlines():
        s = line.strip()
        if not s:
            continue
        parts = [p.strip() for p in s.split(";")]
        if len(parts) == 1:
            items.append((parts[0], ""))
        else:
            items.append((parts[0], ";".join(parts[1:]).strip()))
    return items


def _auto_icon_for_subject(subject_name: str) -> str:
    """
    Sehr robuste Icon-Wahl:
    - nutzt AUTO_ICON mapping (keyword->slug), default "briefcase"
    """
    s = (subject_name or "").strip().lower()
    if not s:
        return "briefcase"
    # Direkter Treffer (z.B. "pflege" -> "medical_cross")
    if s in AUTO_ICON:
        return AUTO_ICON[s]
    # Keyword-Suche
    for k, slug in AUTO_ICON.items():
        if k in s:
            return slug
    return "briefcase"


def _make_distractors(vocab: List[Tuple[str, str]], correct_idx: int) -> List[str]:
    """
    Distraktoren aus den Übersetzungen (oder Wörtern, falls Übersetzung fehlt)
    -> gibt 3 Distraktoren zurück (wenn möglich)
    """
    correct_word, correct_trans = vocab[correct_idx]
    correct = (correct_trans or correct_word).strip()

    pool: List[str] = []
    for j, (w, t) in enumerate(vocab):
        if j == correct_idx:
            continue
        candidate = (t or w).strip()
        if candidate and candidate != correct and candidate not in pool:
            pool.append(candidate)

    random.shuffle(pool)
    # Falls zu wenig: auffüllen mit generischen Platzhaltern
    while len(pool) < 3:
        pool.append("—")
    return pool[:3]


# -----------------------------
# PDF Zeichnen: Schreiblinien
# -----------------------------
def draw_writing_lines(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    line_count: int = 4,
    dash: bool = False,
):
    """
    Zeichnet Schreiblinien in einem Bereich (x,y links-unten).
    """
    c.saveState()
    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    if dash:
        c.setDash(2, 3)
    else:
        c.setDash()

    if line_count <= 0:
        c.restoreState()
        return

    gap = h / (line_count + 1)
    for i in range(1, line_count + 1):
        yy = y + i * gap
        c.line(x + 8, yy, x + w - 8, yy)

    c.setDash()
    c.restoreState()


# -----------------------------
# PDF Builder
# -----------------------------
def build_trainer_pdf(
    *,
    subject: str,
    vocab: List[Tuple[str, str]],
    uploads: List,
    kdp_mode: bool,
    include_quiz: bool,
    quiz_questions: int,
    writing_lines_per_page: int,
) -> bytes:
    spec = get_page_spec(kdp_mode=kdp_mode)  # dein pdf_engine liefert .page_w .page_h .safe
    page_w, page_h, safe = float(spec.page_w), float(spec.page_h), float(spec.safe)

    img_buffers = [io.BytesIO(up.getvalue()) for up in (uploads or [])]

    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(page_w, page_h))

    usable_w = page_w - 2 * safe
    top = page_h - safe

    # Layout Höhen
    header_h = 70
    word_box_h = 140
    img_box_h = 240
    write_box_h = 170
    gap = 14

    img_idx = 0

    # -----------------
    # Vokabel-Seiten
    # -----------------
    for i, (word, translation) in enumerate(vocab, 1):
        # Header
        c.setFont("Helvetica-Bold", 20)
        c.drawString(safe, top - 28, "Eddie Trainer V2")
        c.setFont("Helvetica", 12)
        c.setFillColor(colors.grey)
        c.drawString(safe, top - 50, f"Fach: {subject}  •  Karte {i}/{len(vocab)}")
        c.setFillColor(colors.black)

        # Wortbox
        y_word_top = top - header_h
        draw_box(c, safe, y_word_top - word_box_h, usable_w, word_box_h, title="VOKABEL")
        c.setFont("Helvetica-Bold", 34)
        c.drawCentredString(page_w / 2, y_word_top - 78, (word or "")[:40])

        if translation:
            c.setFont("Helvetica", 16)
            c.setFillColor(colors.black)
            c.drawCentredString(page_w / 2, y_word_top - 112, translation[:80])

        # Bild / Icon
        y_img_top = y_word_top - word_box_h - gap
        draw_box(c, safe, y_img_top - img_box_h, usable_w, img_box_h, title="BILD / SYMBOL")

        if img_buffers:
            buf = img_buffers[img_idx % len(img_buffers)]
            buf.seek(0)
            embed_image(
                c,
                img_data=buf,
                x=safe,
                y=y_img_top - img_box_h,
                max_w=usable_w,
                max_h=img_box_h,
                preserve_aspect=True,
                scale_to=0.80,
                debug_on_error=False,
            )
            img_idx += 1
        else:
            # Icon fallback (wenn draw_icon existiert)
            if callable(draw_icon):
                slug = _auto_icon_for_subject(subject)
                size = min(120, img_box_h * 0.6)
                cx = safe + usable_w / 2
                cy = (y_img_top - img_box_h) + img_box_h / 2
                ok = draw_icon(c, key=slug, x=cx - size / 2, y=cy - size / 2, size=size)
                if not ok:
                    draw_icon(c, key="briefcase", x=cx - size / 2, y=cy - size / 2, size=size)
            else:
                c.setFont("Helvetica-Oblique", 12)
                c.setFillColor(colors.grey)
                c.drawCentredString(page_w / 2, (y_img_top - img_box_h) + img_box_h / 2, "Keine Bilder hochgeladen.")
                c.setFillColor(colors.black)

        # Schreibübung
        y_write_top = y_img_top - img_box_h - gap
        draw_box(c, safe, y_write_top - write_box_h, usable_w, write_box_h, title="SCHREIBÜBUNG")
        c.setFont("Helvetica", 11)
        c.drawString(safe + 12, y_write_top - 32, "Schreibe das Wort (und ggf. Übersetzung) sauber ab:")
        c.setFont("Helvetica-Bold", 12)
        c.drawString(safe + 12, y_write_top - 52, f"• {word}" + (f" — {translation}" if translation else ""))

        # Linien
        lines_area_y = (y_write_top - write_box_h) + 14
        lines_area_h = write_box_h - 78
        draw_writing_lines(
            c,
            x=safe,
            y=lines_area_y,
            w=usable_w,
            h=lines_area_h,
            line_count=max(2, int(writing_lines_per_page)),
            dash=False,
        )

        c.showPage()

    # -----------------
    # Quiz-Seiten (optional)
    # -----------------
    if include_quiz and vocab:
        qn = min(int(quiz_questions), len(vocab))
        idxs = list(range(len(vocab)))
        random.shuffle(idxs)
        idxs = idxs[:qn]

        # pro Seite 4 Fragen
        per_page = 4
        pages = (qn + per_page - 1) // per_page

        for p in range(pages):
            start = p * per_page
            batch = idxs[start : start + per_page]

            # Header
            c.setFont("Helvetica-Bold", 20)
            c.drawString(safe, top - 28, "QUIZ – Multiple Choice")
            c.setFont("Helvetica", 12)
            c.setFillColor(colors.grey)
            c.drawString(safe, top - 50, f"Fach: {subject}  •  Seite {p+1}/{pages}")
            c.setFillColor(colors.black)

            y = top - 85
            c.setFont("Helvetica", 12)

            for n, idx in enumerate(batch, 1):
                word, trans = vocab[idx]
                correct = (trans or word).strip()
                distractors = _make_distractors(vocab, idx)
                options = [correct] + distractors
                random.shuffle(options)

                # Frage
                c.setFont("Helvetica-Bold", 13)
                c.drawString(safe, y, f"{start + n}. Was bedeutet: „{word}“?")
                y -= 18

                # Optionen
                c.setFont("Helvetica", 12)
                letters = ["A", "B", "C", "D"]
                for j, opt in enumerate(options[:4]):
                    c.drawString(safe + 18, y, f"{letters[j]}) {opt}")
                    y -= 16

                y -= 12  # Abstand

                # Seitenumbruch-Schutz
                if y < safe + 90:
                    break

            # (Optional) Lösungen klein unten
            c.setFont("Helvetica-Oblique", 10)
            c.setFillColor(colors.grey)
            sol = []
            for idx in batch:
                word, trans = vocab[idx]
                correct = (trans or word).strip()
                distractors = _make_distractors(vocab, idx)
                options = [correct] + distractors
                random.shuffle(options)
                letters = ["A", "B", "C", "D"]
                correct_letter = letters[options.index(correct)] if correct in options else "A"
                sol.append(f"{word}:{correct_letter}")
            c.drawString(safe, safe + 18, "Lösungen (intern): " + "  •  ".join(sol))
            c.setFillColor(colors.black)

            c.showPage()

    c.save()
    out.seek(0)
    return out.getvalue()


# ---------------- UI ----------------
st.set_page_config(page_title="Eddie Trainer V2", layout="centered")
st.title("🗣️ Eddie Trainer V2 – Fachsprache mit Bildern / Icons")

with st.sidebar:
    st.header("Konfiguration")
    kdp = st.toggle("KDP-Modus (8.5×8.5 + Bleed)", value=True)
    include_quiz = st.toggle("Quiz-Seiten anhängen (A/B/C/D)", value=True)
    quiz_questions = st.slider("Quiz-Fragen (Anzahl)", 4, 30, 12, 1)
    writing_lines = st.slider("Schreiblinien pro Seite", 2, 10, 5, 1)

st.subheader("1) Fach wählen oder eigene Vokabeln nutzen")

mode = st.radio(
    "Quelle der Vokabeln",
    ["Fach-Modul (vorbelegt)", "Eigene Eingabe (Copy/Paste)"],
    horizontal=True,
)

subject = "Eigenes Fach"
default_text = "die Nadel;needle\nStoff;fabric\nSchere;scissors"

if mode == "Fach-Modul (vorbelegt)" and SUBJECTS:
    subject = st.selectbox("Fachgebiet", list(SUBJECTS.keys()), index=0)
    # SUBJECTS kann dicts mit {"wort","satz"} sein – wir bauen daraus ein (wort, "")
    # (Übersetzung bleibt optional – Lehrer kann später selbst ergänzen)
    preset = SUBJECTS.get(subject, [])
    # Wenn preset schon (wort,übersetzung) wäre, trotzdem robust bleiben
    lines: List[str] = []
    for it in preset:
        if isinstance(it, dict):
            lines.append(str(it.get("wort", "")).strip())
        elif isinstance(it, (list, tuple)) and len(it) >= 1:
            lines.append(str(it[0]).strip())
    default_text = "\n".join([ln for ln in lines if ln]) or default_text
else:
    subject = st.text_input("Fach / Thema (frei)", value="Schneidern")

raw_text = st.text_area(
    "Vokabeln (pro Zeile: deutsch;übersetzung ODER nur deutsch)",
    value=default_text,
    height=220,
)

st.subheader("2) Optional: Bilder hochladen (sonst Icon-Fallback)")
uploads = st.file_uploader(
    "Bilder (werden zyklisch verteilt)",
    type=["jpg", "jpeg", "png"],
    accept_multiple_files=True,
)

vocab = parse_vocab_lines(raw_text)

st.caption(
    "Hinweis: Wenn du keine Bilder hochlädst, versucht die App ein Fach-Icon aus der Icon-Registry zu zeichnen. "
    "Falls draw_icon() in deiner pdf_engine noch nicht existiert, bleibt das Feld einfach neutral."
)

if st.button("PDF erstellen", type="primary", disabled=not vocab):
    try:
        pdf_data = build_trainer_pdf(
            subject=subject,
            vocab=vocab,
            uploads=uploads or [],
            kdp_mode=kdp,
            include_quiz=include_quiz,
            quiz_questions=int(quiz_questions),
            writing_lines_per_page=int(writing_lines),
        )
        st.success("PDF erstellt ✅")
        st.download_button(
            "PDF herunterladen",
            pdf_data,
            file_name=f"eddie_trainer_v2_{subject.lower().replace(' ', '_')}.pdf",
            mime="application/pdf",
        )
    except Exception as e:
        st.error(f"Fehler beim Erstellen: {e}")