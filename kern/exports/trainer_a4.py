# kern/exports/trainer_a4.py
from __future__ import annotations

import io
from typing import Dict, Any, List, Tuple, Optional

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

from kern.pdf_engine import (
    get_page_spec,
    draw_box,
    draw_writing_area,
    draw_brand_mark,
    draw_icon,
)

# -----------------------------
# Policy (stabil, skalierbar)
# -----------------------------
A4_POLICY: Dict[str, Any] = {
    "max_examples": 3,
    "min_write_area_ratio": 0.55,   # mindestens 55% der nutzbaren Höhe für Schreiben
    "icon_size_mm": 22,
    "header_h_mm": 18,              # Titel/Meta-Block
    "word_block_h_mm": 30,          # Wort + Icon Block
    "examples_block_min_h_mm": 22,  # Beispiele sollen nicht zu klein werden
    "gap_mm": 5,
    "watermark_opacity": 0.06,
    "writing_line_spacing_pt": 14,  # in Punkten (ReportLab)
}


def _coerce_vocab(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Erwartet data["vocab"] = [{"word":..., "translation":...}, ...]
    Fallback: wenn data["items"] im alten Format kommt.
    """
    vocab = data.get("vocab")
    if isinstance(vocab, list) and vocab:
        out = []
        for it in vocab:
            if isinstance(it, dict):
                out.append(
                    {
                        "word": str(it.get("word", "")).strip(),
                        "translation": str(it.get("translation", "")).strip(),
                    }
                )
        return [v for v in out if v["word"] or v["translation"]]

    # Fallback: items-Format
    items = data.get("items")
    if isinstance(items, list) and items:
        out = []
        for it in items:
            if isinstance(it, dict):
                out.append(
                    {
                        "word": str(it.get("term", "")).strip(),
                        "translation": "",  # legacy
                    }
                )
        return [v for v in out if v["word"]]
    return []


def _get_images_bytes(data: Dict[str, Any]) -> List[bytes]:
    assets = data.get("assets") or {}
    imgs = assets.get("images") or []
    out: List[bytes] = []
    for b in imgs:
        if isinstance(b, (bytes, bytearray)) and len(b) > 0:
            out.append(bytes(b))
    return out


def _choose_icon_slug(subject: str, word: str) -> str:
    """
    Simple offline heuristic (später: subject_data + Icon Registry Mapping).
    """
    s = (subject or "").strip().lower()
    w = (word or "").strip().lower()

    # grobe Heuristiken
    if any(k in s for k in ["pflege", "medizin", "arzt", "kranken", "hospital"]):
        return "medical_cross"
    if any(k in s for k in ["gastro", "küche", "restaurant", "service", "hotel"]):
        return "fork_knife"
    if any(k in s for k in ["bau", "handwerk", "werk", "metall", "schweiß", "schrein"]):
        return "tools"
    if "hammer" in w or "hammer" in s:
        return "hammer"
    return "briefcase"


def _draw_image_in_box(
    c: canvas.Canvas,
    img_bytes: bytes,
    *,
    x: float,
    y: float,
    w: float,
    h: float,
    pad: float = 6 * mm,
) -> bool:
    """
    Robust: rendert ein Bild aus bytes proportional in eine Box.
    """
    try:
        bio = io.BytesIO(img_bytes)
        reader = ImageReader(bio)
        iw, ih = reader.getSize()
        if iw <= 0 or ih <= 0:
            return False

        # Fit (contain)
        max_w = max(1.0, w - 2 * pad)
        max_h = max(1.0, h - 2 * pad)
        scale = min(max_w / iw, max_h / ih)

        nw = iw * scale
        nh = ih * scale
        dx = x + (w - nw) / 2
        dy = y + (h - nh) / 2

        c.drawImage(reader, dx, dy, width=nw, height=nh, preserveAspectRatio=True, mask="auto")
        return True
    except Exception:
        return False


def export_trainer_a4(
    data: Dict[str, Any],
    *,
    title: str = "Eddie Trainer V2",
    subtitle: Optional[str] = None,
    watermark: bool = True,
    lines: bool = True,
    policy: Dict[str, Any] = None,
) -> bytes:
    """
    A4 Arbeitsblatt Export (Trainer):
    - pro Vokabel 1 Seite
    - oben Wort + Icon, darunter Bild/Beispiele, unten große Schreibfläche
    - Bilder zyklisch, sonst Icon-Fallback
    """
    pol = dict(A4_POLICY)
    if policy:
        pol.update(policy)

    spec = get_page_spec("A4 Arbeitsblatt")
    page_w, page_h = spec["pagesize"]
    m = float(spec["margin"])

    subject = str((data.get("subject") or "")).strip()
    vocab = _coerce_vocab(data)
    images = _get_images_bytes(data)

    # Optionen (vom UI übergeben)
    opts = data.get("options") or {}
    writing_lines_per_page = int(opts.get("writing_lines_per_page", 5))
    # examples: Trainer liefert nicht zwingend Sätze -> wir lassen Platz
    # (später: subject_data kann Beispiele liefern)

    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(page_w, page_h))

    usable_w = page_w - 2 * m
    usable_h = page_h - 2 * m

    # Layout (mm → points)
    header_h = pol["header_h_mm"] * mm
    word_block_h = pol["word_block_h_mm"] * mm
    gap = pol["gap_mm"] * mm
    icon_size = pol["icon_size_mm"] * mm

    # Dynamische Höhe: wir garantieren min_write_area_ratio
    # Wir reservieren: Header + Wortblock + Beispiele+Bildblock (flex) + Schreibblock (>= ratio)
    min_write_h = usable_h * float(pol["min_write_area_ratio"])

    # Resthöhe für "Content oben" (Header+Wort+Gap+ContentBlock+Gap)
    # Wir nehmen einen Content-Block, der Bild+Beispiele enthält.
    fixed_top = header_h + gap + word_block_h + gap
    remaining = usable_h - fixed_top - gap  # minus gap vor Schreibblock
    content_block_h = max(pol["examples_block_min_h_mm"] * mm, remaining - min_write_h)
    write_block_h = remaining - content_block_h

    # Safety: falls Inhalt sehr klein / negativ wird -> clamp
    if write_block_h < min_write_h:
        write_block_h = min_write_h
        content_block_h = max(pol["examples_block_min_h_mm"] * mm, remaining - write_block_h)

    # Innerhalb Content-Block: Bild-Teil + Beispiele-Teil
    # Bild größer gewichten, Beispiele kompakt
    examples_h = max(pol["examples_block_min_h_mm"] * mm, content_block_h * 0.32)
    image_h = max(40 * mm, content_block_h - examples_h - gap)

    img_idx = 0

    if not vocab:
        vocab = [{"word": "", "translation": ""}]

    for i, it in enumerate(vocab, 1):
        word = (it.get("word") or "").strip()
        translation = (it.get("translation") or "").strip()

        # --- Branding Watermark ---
        if watermark:
            draw_brand_mark(
                c, page_w, page_h,
                mode="watermark",
                opacity=float(pol["watermark_opacity"]),
            )

        # --- Header ---
        top = page_h - m
        c.setFillColor(colors.black)

        c.setFont("Helvetica-Bold", 18)
        c.drawString(m, top - 18, title)

        meta = subtitle or (f"Fach: {subject}" if subject else "Arbeitsblatt")
        c.setFont("Helvetica", 11)
        c.setFillColor(colors.grey)
        c.drawString(m, top - 34, f"{meta}  •  Karte {i}/{len(vocab)}")
        c.setFillColor(colors.black)

        # --- Wortblock (Icon + Wort + Übersetzung) ---
        y_word_top = top - header_h - gap
        y_word = y_word_top - word_block_h
        draw_box(c, m, y_word, usable_w, word_block_h, line_width=1)

        # Icon links
        ix = m + 8 * mm
        iy = y_word + (word_block_h - icon_size) / 2
        slug = _choose_icon_slug(subject, word)
        draw_icon(c, slug, ix, iy, icon_size)

        # Wort/Übersetzung
        tx = ix + icon_size + 10 * mm
        c.setFont("Helvetica-Bold", 20)
        c.drawString(tx, y_word + word_block_h - 18 * mm, word if word else "________________________")

        if translation:
            c.setFont("Helvetica", 13)
            c.setFillColor(colors.black)
            c.drawString(tx, y_word + 9 * mm, translation[:90])
        else:
            c.setFont("Helvetica", 10)
            c.setFillColor(colors.grey)
            c.drawString(tx, y_word + 9 * mm, "Übersetzung: __________________________")
            c.setFillColor(colors.black)

        # --- Content-Block (Bild + Beispiele) ---
        y_content_top = y_word - gap
        y_content = y_content_top - content_block_h
        draw_box(c, m, y_content, usable_w, content_block_h, line_width=1)

        # Bildbereich oben im Content-Block
        img_y_top = y_content_top - 6 * mm
        img_y = img_y_top - image_h
        img_x = m + 6 * mm
        img_w = usable_w - 12 * mm

        # Bild zeichnen (zyklisch) oder Icon-Fallback groß
        drew = False
        if images:
            b = images[img_idx % len(images)]
            img_idx += 1
            drew = _draw_image_in_box(c, b, x=img_x, y=img_y, w=img_w, h=image_h, pad=4 * mm)

        if not drew:
            # großes Icon als Ersatz
            size = min(image_h * 0.6, img_w * 0.35)
            cx = m + usable_w / 2
            cy = img_y + image_h / 2
            draw_icon(c, slug, cx - size / 2, cy - size / 2, size)

            c.setFont("Helvetica-Oblique", 10)
            c.setFillColor(colors.grey)
            c.drawCentredString(cx, img_y + 6 * mm, "Optional: Bild hochladen (sonst Icon)")
            c.setFillColor(colors.black)

        # Beispiele unten im Content-Block
        ex_y_top = img_y - gap
        c.setFont("Helvetica-Bold", 12)
        c.drawString(m + 8 * mm, ex_y_top - 10, "Beispiele:")

        c.setFont("Helvetica", 11)
        c.setFillColor(colors.black)

        # Wenn du später Beispiele aus subject_data generierst: hier einsetzen
        examples: List[str] = []
        # Fallback-Linien (statt KI)
        if not examples:
            examples = [
                "______________________________________________",
                "______________________________________________",
                "______________________________________________",
            ]

        y = ex_y_top - 26
        for s in examples[: int(pol["max_examples"])]:
            c.drawString(m + 12 * mm, y, f"• {s}")
            y -= 14

        # --- Schreibblock (große Schreibfläche) ---
        y_write_top = y_content - gap
        y_write = y_write_top - write_block_h
        # Titel der Schreibfläche
        c.setFont("Helvetica-Bold", 12)
        c.drawString(m, y_write_top - 14, "Schreibe 3 eigene Sätze:")

        # Schreibfläche darunter
        write_area_y = y_write + 0
        write_area_h = write_block_h - 18  # Platz für Label
        draw_writing_area(
            c,
            m,
            write_area_y,
            usable_w,
            write_area_h,
            line_spacing=float(pol["writing_line_spacing_pt"]),
            lines=bool(lines),
            border=True,
        )

        # Footer (minimal)
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.Color(0, 0, 0, alpha=0.55))
        c.drawRightString(page_w - m, m - 6, "Offline-First • Eddie")
        c.setFillColor(colors.black)

        c.showPage()

    c.save()
    out.seek(0)
    return out.getvalue()
