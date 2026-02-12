from __future__ import annotations

import io
import random
import re
from typing import Dict, List, Optional

from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader


# -----------------------------
# PRINT GEOMETRY (keep stable)
# -----------------------------
TRIM = 8.5 * inch
BLEED = 0.125 * inch
SAFE = 0.375 * inch


def get_geometry(kdp_mode: bool = True):
    """
    Returns (page_w, page_h, safe_margin)
    kdp_mode True: includes bleed
    """
    if kdp_mode:
        return TRIM + 2 * BLEED, TRIM + 2 * BLEED, BLEED + SAFE
    return TRIM, TRIM, SAFE


# -----------------------------
# BRAND BADGE (simple + stable)
# -----------------------------
EDDIE_PURPLE = colors.HexColor("#7c3aed")


def draw_brand_badge(c: canvas.Canvas, cx: float, cy: float, r: float):
    """
    Simple Eddie badge:
      - black/white paw + small purple dot accent
    """
    c.saveState()

    c.setLineWidth(max(2, r * 0.07))
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.white)
    c.circle(cx, cy, r, stroke=1, fill=1)

    # paw pads
    c.setFillColor(colors.black)
    c.circle(cx - r * 0.30, cy + r * 0.18, r * 0.12, stroke=0, fill=1)
    c.circle(cx,           cy + r * 0.28, r * 0.12, stroke=0, fill=1)
    c.circle(cx + r * 0.30, cy + r * 0.18, r * 0.12, stroke=0, fill=1)
    c.roundRect(cx - r * 0.26, cy - r * 0.20, r * 0.52, r * 0.34, r * 0.12, stroke=0, fill=1)

    # purple accent
    c.setFillColor(EDDIE_PURPLE)
    c.circle(cx, cy - r * 0.42, r * 0.08, stroke=0, fill=1)

    c.restoreState()


# -----------------------------
# TEXT HELPERS
# -----------------------------
def _wrap_text(c: canvas.Canvas, text: str, x: float, y: float, max_width: float, leading: float = 14):
    """
    Simple word-wrapping for ReportLab.
    Draws downward from (x,y). Returns final y after drawing.
    """
    words = (text or "").split()
    line = ""
    for w in words:
        test = (line + " " + w).strip()
        if c.stringWidth(test, c._fontname, c._fontsize) <= max_width:
            line = test
        else:
            c.drawString(x, y, line)
            y -= leading
            line = w
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def _blank_sentence(sentence: str, target_word: str) -> str:
    """
    Replace (first) occurrence of target_word in sentence with "____".
    Case-insensitive, word boundary aware (best-effort).
    """
    if not sentence or not target_word:
        return sentence or ""

    # Escape for regex
    tw = re.escape(target_word.strip())
    pattern = re.compile(rf"\b{tw}\b", flags=re.IGNORECASE)
    return pattern.sub("____", sentence, count=1)


def _make_mcq_options(rng: random.Random, correct: str, pool: List[str], k: int = 3) -> List[str]:
    """
    Build A/B/C options: correct + 2 distractors from pool (unique).
    Returns shuffled list of length k (default 3).
    """
    distractors = [w for w in pool if w.strip() and w.strip().lower() != correct.strip().lower()]
    rng.shuffle(distractors)
    opts = [correct] + distractors[: max(0, k - 1)]
    # Ensure uniqueness
    seen = set()
    unique = []
    for o in opts:
        key = o.strip().lower()
        if key not in seen:
            unique.append(o)
            seen.add(key)
    while len(unique) < k and distractors:
        cand = distractors.pop()
        key = cand.strip().lower()
        if key not in seen:
            unique.append(cand)
            seen.add(key)

    rng.shuffle(unique)
    return unique[:k]


# -----------------------------
# PAGE DRAWING
# -----------------------------
def _draw_header(c: canvas.Canvas, page_w: float, page_h: float, safe: float, title_left: str, title_right: str = ""):
    c.saveState()
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.white)
    c.rect(safe, page_h - safe - 0.6 * inch, page_w - 2 * safe, 0.6 * inch, stroke=1, fill=1)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(safe + 0.18 * inch, page_h - safe - 0.40 * inch, title_left)

    if title_right:
        c.setFont("Helvetica", 10)
        c.drawRightString(page_w - safe - 0.18 * inch, page_h - safe - 0.38 * inch, title_right)

    draw_brand_badge(c, page_w - safe - 0.35 * inch, safe + 0.35 * inch, 0.28 * inch)
    c.restoreState()


def _draw_footer_note(c: canvas.Canvas, page_w: float, safe: float, note: str):
    c.saveState()
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.grey)
    c.drawCentredString(page_w / 2, safe * 0.55, note)
    c.restoreState()


# -----------------------------
# PUBLIC API: VOCAB WORKBOOK
# -----------------------------
def build_trainer_pdf(
    subject_name: str,
    level: str,
    entries: List[Dict[str, str]],
    uploaded_images: Optional[List] = None,
    include_vocab_pages: bool = True,
    include_cloze_pages: bool = True,
    include_quiz_pages: bool = True,
    quiz_questions: Optional[int] = None,
    seed: int = 42,
    kdp_mode: bool = False,
) -> bytes:
    """
    Build a printable trainer workbook:
      - Vocab pages (word + sentence + optional image)
      - Cloze pages (fill-in-the-blank)
      - Multiple choice quiz pages (A/B/C)
      - Answer key

    entries: list of {"wort": "...", "satz": "..."} (additional keys ignored)
    uploaded_images: list of file-like objects for the first N vocab pages (optional)
    """
    page_w, page_h, safe = get_geometry(kdp_mode=kdp_mode)
    rng = random.Random(int(seed))

    clean_entries = []
    for e in entries:
        w = (e.get("wort") or "").strip()
        s = (e.get("satz") or "").strip()
        if w:
            clean_entries.append({"wort": w, "satz": s})
    if not clean_entries:
        raise ValueError("Keine Vokabel-Einträge vorhanden.")

    all_words = [e["wort"] for e in clean_entries]

    if quiz_questions is None:
        quiz_questions = min(10, len(clean_entries))
    quiz_questions = max(1, min(int(quiz_questions), len(clean_entries)))

    # Prepare quiz selection deterministically
    quiz_pool = clean_entries[:]
    rng.shuffle(quiz_pool)
    quiz_sel = quiz_pool[:quiz_questions]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))

    # ---- Cover / Title page
    _draw_header(c, page_w, page_h, safe, "Sprachtrainer", f"{subject_name} • {level}")
    c.setFont("Helvetica-Bold", 28)
    c.setFillColor(colors.black)
    c.drawCentredString(page_w / 2, page_h * 0.62, subject_name)

    c.setFont("Helvetica", 16)
    c.setFillColor(colors.grey)
    c.drawCentredString(page_w / 2, page_h * 0.56, f"Niveau: {level}")

    c.setFont("Helvetica", 12)
    c.setFillColor(colors.black)
    c.drawCentredString(page_w / 2, page_h * 0.48, "Druckfertiges Arbeitsheft")
    _draw_footer_note(c, page_w, safe, "Eddies Welt • Trainer-Modul")
    c.showPage()

    # ---- VOCAB PAGES
    if include_vocab_pages:
        for i, e in enumerate(clean_entries):
            _draw_header(c, page_w, page_h, safe, "Vokabelkarte", f"{subject_name} • {level}")

            # Word
            c.setFont("Helvetica-Bold", 30)
            c.setFillColor(colors.black)
            c.drawCentredString(page_w / 2, page_h - safe - 1.35 * inch, e["wort"])

            # Sentence
            c.setFont("Helvetica", 14)
            c.setFillColor(colors.black)
            max_w = page_w - 2 * safe - 0.4 * inch
            y = page_h - safe - 1.85 * inch
            y = _wrap_text(c, e["satz"] or "", safe + 0.2 * inch, y, max_w, leading=16)

            # Optional image
            if uploaded_images and i < len(uploaded_images):
                try:
                    img_file = uploaded_images[i]
                    img_file.seek(0)
                    img = ImageReader(img_file)
                    # fixed square image box
                    box = 3.2 * inch
                    c.setStrokeColor(colors.black)
                    c.rect(page_w/2 - box/2, page_h/2 - box/2, box, box, stroke=1, fill=0)
                    c.drawImage(img, page_w/2 - box/2, page_h/2 - box/2, width=box, height=box, preserveAspectRatio=True, anchor='c')
                except Exception:
                    pass

            # Writing lines
            c.setStrokeColor(colors.lightgrey)
            x0 = safe + 0.2 * inch
            x1 = page_w - safe - 0.2 * inch
            base_y = safe + 2.4 * inch
            for k in range(6):
                yy = base_y + k * 0.35 * inch
                c.line(x0, yy, x1, yy)

            c.setFont("Helvetica-Oblique", 10)
            c.setFillColor(colors.grey)
            c.drawString(safe + 0.2 * inch, safe + 0.55 * inch, "Schreibe das Wort / den Satz nach:")

            c.showPage()

    # ---- CLOZE PAGES
    if include_cloze_pages:
        for e in clean_entries:
            _draw_header(c, page_w, page_h, safe, "Lückentext", f"{subject_name} • {level}")

            c.setFont("Helvetica-Bold", 18)
            c.setFillColor(colors.black)
            c.drawString(safe + 0.2 * inch, page_h - safe - 1.25 * inch, "Setze das richtige Wort ein:")

            cloze = _blank_sentence(e.get("satz", ""), e.get("wort", ""))
            c.setFont("Helvetica", 16)
            y = page_h - safe - 1.75 * inch
            y = _wrap_text(c, cloze, safe + 0.2 * inch, y, page_w - 2 * safe - 0.4 * inch, leading=20)

            # big answer line
            c.setStrokeColor(colors.black)
            c.setLineWidth(1)
            c.line(safe + 0.2 * inch, safe + 3.0 * inch, page_w - safe - 0.2 * inch, safe + 3.0 * inch)
            c.setFont("Helvetica-Oblique", 12)
            c.setFillColor(colors.grey)
            c.drawString(safe + 0.2 * inch, safe + 3.15 * inch, "Antwort:")

            # hint (optional)
            c.setFont("Helvetica", 10)
            c.setFillColor(colors.grey)
            c.drawString(safe + 0.2 * inch, safe + 1.2 * inch, f"Hinweis: Wortlänge = {len(e['wort'])} Buchstaben")

            c.showPage()

    # ---- QUIZ PAGES (MCQ A/B/C)
    answers = []  # list of dict {q, correct, options, right_letter}
    if include_quiz_pages:
        for idx, e in enumerate(quiz_sel, start=1):
            _draw_header(c, page_w, page_h, safe, "Quiz (A/B/C)", f"{subject_name} • {level}")

            c.setFont("Helvetica-Bold", 16)
            c.setFillColor(colors.black)
            c.drawString(safe + 0.2 * inch, page_h - safe - 1.25 * inch, f"Frage {idx}:")

            # Question: cloze sentence
            question = _blank_sentence(e.get("satz", ""), e.get("wort", ""))
            c.setFont("Helvetica", 16)
            y = page_h - safe - 1.70 * inch
            y = _wrap_text(c, question, safe + 0.2 * inch, y, page_w - 2 * safe - 0.4 * inch, leading=20)

            # Options
            opts = _make_mcq_options(rng, e["wort"], all_words, k=3)
            letters = ["A", "B", "C"]
            correct_idx = opts.index(e["wort"]) if e["wort"] in opts else 0
            right_letter = letters[correct_idx]

            start_y = safe + 4.6 * inch
            c.setFont("Helvetica-Bold", 16)
            for i, opt in enumerate(opts):
                yy = start_y - i * 0.75 * inch
                # checkbox circle
                c.setStrokeColor(colors.black)
                c.circle(safe + 0.35 * inch, yy + 4, 10, stroke=1, fill=0)
                c.setFillColor(colors.black)
                c.drawString(safe + 0.65 * inch, yy, f"{letters[i]})  {opt}")

            answers.append(
                {
                    "q": idx,
                    "correct": e["wort"],
                    "options": opts,
                    "right_letter": right_letter,
                }
            )

            c.showPage()

    # ---- ANSWER KEY
    if include_quiz_pages and answers:
        _draw_header(c, page_w, page_h, safe, "Lösungen", f"{subject_name} • {level}")

        c.setFont("Helvetica-Bold", 18)
        c.setFillColor(colors.black)
        c.drawString(safe + 0.2 * inch, page_h - safe - 1.25 * inch, "Antwortschlüssel (Quiz):")

        c.setFont("Helvetica", 12)
        y = page_h - safe - 1.75 * inch
        for a in answers:
            line = f"Frage {a['q']}: {a['right_letter']}  ({a['correct']})"
            c.drawString(safe + 0.2 * inch, y, line)
            y -= 0.28 * inch
            if y < safe + 1.0 * inch:
                c.showPage()
                _draw_header(c, page_w, page_h, safe, "Lösungen", f"{subject_name} • {level}")
                c.setFont("Helvetica", 12)
                y = page_h - safe - 1.25 * inch

        c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()
