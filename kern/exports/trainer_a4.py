# kern/exports/trainer_a4.py
from __future__ import annotations

import io
from typing import Dict, Any, List, Optional

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

from kern.pdf_engine import (
    get_page_spec,
    draw_box,
    draw_brand_mark,
    draw_icon,
    draw_writing_area,
)

# -----------------------------
# Helpers
# -----------------------------
def _coerce_vocab(data: Dict[str, Any]) -> List[Dict[str, str]]:
    vocab = data.get("vocab")
    if isinstance(vocab, list) and vocab:
        out: List[Dict[str, str]] = []
        for it in vocab:
            if isinstance(it, dict):
                out.append(
                    {
                        "word": str(it.get("word", "")).strip(),
                        "translation": str(it.get("translation", "")).strip(),
                    }
                )
        return [v for v in out if v["word"] or v["translation"]]

    items = data.get("items")
    if isinstance(items, list) and items:
        out2: List[Dict[str, str]] = []
        for it in items:
            if isinstance(it, dict):
                w = str(it.get("term", "")).strip()
                if w:
                    out2.append({"word": w, "translation": ""})
        return out2

    return []


def _coerce_images(data: Dict[str, Any]) -> List[bytes]:
    assets = data.get("assets")
    if not isinstance(assets, dict):
        return []
    imgs = assets.get("images")
    if not isinstance(imgs, list):
        return []
    out: List[bytes] = []
    for b in imgs:
        if isinstance(b, (bytes, bytearray)) and len(b) > 0:
            out.append(bytes(b))
    return out


def _draw_image_safe(c: canvas.Canvas, img_bytes: bytes, x: float, y: float, w: float, h: float) -> None:
    """
    Zieht NIE den Export runter. Wenn Bild kaputt/zu groß/Format komisch → skip.
    """
    try:
        ir = ImageReader(io.BytesIO(img_bytes))
        # ReportLab skaliert, wir füllen die Box "contain"
        c.drawImage(ir, x, y, width=w, height=h, preserveAspectRatio=True, anchor="c", mask="auto")
    except Exception:
        # stiller Fallback (kein Crash)
        c.saveState()
        c.setStrokeColor(colors.Color(0, 0, 0, alpha=0.2))
        c.rect(x, y, w, h, stroke=1, fill=0)
        c.setFillColor(colors.Color(0, 0, 0, alpha=0.35))
        c.setFont("Helvetica", 8)
        c.drawCentredString(x + w / 2, y + h / 2, "Bild konnte nicht geladen werden")
        c.restoreState()


# -----------------------------
# Export
# -----------------------------
def export_trainer_a4(
    data: Dict[str, Any],
    *,
    title: str = "Eddie Trainer V2",
    subtitle: Optional[str] = None,
    watermark: bool = True,
    lines: bool = True,
    policy: Optional[Dict[str, Any]] = None,
) -> bytes:
    """
    A4 Arbeitsblatt:
    - Wortliste + optional Übersetzung
    - Schreiblinien (optional)
    - optional Bilder: zyklisch pro Zeile oder als Deko-Element
    """
    if not isinstance(data, dict):
        raise ValueError("export_trainer_a4: data must be a dict")

    spec = get_page_spec("A4 Arbeitsblatt")
    page_w, page_h = spec["pagesize"]
    margin = float(spec["margin"])

    subject = str(data.get("subject") or "").strip()
    vocab = _coerce_vocab(data)
    images = _coerce_images(data)

    # wenn leer: trotzdem ein Blatt generieren
    if not vocab:
        vocab = [{"word": "", "translation": ""}]

    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(page_w, page_h))

    # Layout
    header_h = 18 * mm
    row_h = 18 * mm if lines else 14 * mm
    gap = 4 * mm

    # Bereiche
    x0 = margin
    y_top = page_h - margin
    usable_w = page_w - 2 * margin
    usable_h = page_h - 2 * margin - header_h

    # Spalten: links Text, rechts Bild (optional)
    img_col_w = 42 * mm if images else 0
    text_col_w = usable_w - img_col_w - (gap if images else 0)

    # Header
    def draw_header() -> None:
        if watermark:
            draw_brand_mark(c, page_w, page_h, mode="watermark", opacity=0.05)

        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(x0, y_top - 10 * mm, title)

        c.setFont("Helvetica", 10)
        meta = subtitle or (f"Fach: {subject}" if subject else "Arbeitsblatt")
        c.setFillColor(colors.grey)
        c.drawRightString(x0 + usable_w, y_top - 10 * mm, meta)
        c.setFillColor(colors.black)

    draw_header()

    y = y_top - header_h
    img_i = 0

    for it in vocab:
        # neue Seite wenn kein Platz
        if y - row_h < margin:
            c.showPage()
            draw_header()
            y = y_top - header_h

        word = str(it.get("word", "")).strip()
        trans = str(it.get("translation", "")).strip()

        # Textbox
        box_x = x0
        box_y = y - row_h
        draw_box(c, box_x, box_y, text_col_w, row_h, line_width=1)

        # Icon fallback (nur wenn kein Bild)
        if not images:
            # kleines Icon links
            draw_icon(c, "briefcase", box_x + 4 * mm, box_y + row_h - 12 * mm, 8 * mm)

        # Text
        c.setFont("Helvetica-Bold", 13)
        c.setFillColor(colors.black)
        c.drawString(box_x + 14 * mm, box_y + row_h - 7.5 * mm, word if word else "__________")

        if trans:
            c.setFont("Helvetica", 11)
            c.setFillColor(colors.Color(0, 0, 0, alpha=0.75))
            c.drawString(box_x + 14 * mm, box_y + row_h - 13.5 * mm, trans)
            c.setFillColor(colors.black)

        # Schreiblinien
        if lines:
            draw_writing_area(
                c,
                x=box_x + 14 * mm,
                y=box_y + 3.2 * mm,
                w=text_col_w - 16 * mm,
                h=row_h - 18 * mm,
                lines=3,
                line_alpha=0.22,
            )

        # Bildspalte (optional)
        if images:
            ix = x0 + text_col_w + gap
            iy = box_y
            draw_box(c, ix, iy, img_col_w, row_h, line_width=1)

            img = images[img_i % len(images)]
            img_i += 1
            _draw_image_safe(c, img, ix + 2 * mm, iy + 2 * mm, img_col_w - 4 * mm, row_h - 4 * mm)

        y -= (row_h + 4 * mm)

    c.save()
    out.seek(0)
    return out.getvalue()
