# kern/export_orchestrator.py
import io
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import mm

from .pdf_engine import (
    get_page_spec,
    draw_box,
    draw_icon,
    draw_brand_mark,
    draw_writing_area,
)

# optional – wenn du es schon hast:
# from .subject_data import get_icon_slug

def run_export(mode, data, **kwargs):
    if mode == "A4 Arbeitsblatt":
        return _export_a4(data, **kwargs)
    elif mode == "KDP Buch":
        return _export_kdp(data, **kwargs)
    elif mode == "QR Lernkarten":
        return _export_cards(data, **kwargs)
    raise ValueError(f"Unknown export mode: {mode}")

def _export_kdp(data, **kwargs):
    raise NotImplementedError

def _export_cards(data, **kwargs):
    raise NotImplementedError

def _export_a4(
    data: dict,
    *,
    title="Eddie – Arbeitsblatt",
    subtitle=None,
    watermark=True,
    lines=True,
):
    """
    A4-Arbeitsblatt: 1-seitig (oder mehrseitig, falls data mehrere Einträge enthält).
    Erwartetes data-Format (minimal):
      data = {
        "items": [
          {
            "term": "der Hammer",
            "icon_slug": "hammer",
            "examples": ["Ich nehme den Hammer.", "Der Hammer ist schwer.", "Wo ist der Hammer?"],
            "note_prompt": "Schreibe 3 eigene Sätze:"
          },
          ...
        ]
      }
    Rückgabe: bytes (PDF)
    """
    mode = "A4 Arbeitsblatt"
    spec = get_page_spec(mode)
    page_w, page_h = spec["pagesize"]
    m = spec["margin"]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(page_w, page_h))

    items = (data or {}).get("items") or []
    if not items:
        items = [{"term": "", "icon_slug": "icon", "examples": [], "note_prompt": "Notizen:"}]

    for idx, item in enumerate(items):
        # ---- Hintergrund-Branding (Wasserzeichen) ----
        if watermark:
            draw_brand_mark(c, page_w, page_h, mode="watermark", opacity=0.06)

        # ---- Header ----
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 18)
        c.drawString(m, page_h - m - 8, title)

        c.setFont("Helvetica", 11)
        if subtitle:
            c.drawString(m, page_h - m - 28, subtitle)

        # ---- Wort + Icon Block ----
        icon_size = 22 * mm
        top_y = page_h - m - 62  # unter Header
        block_h = 30 * mm
        block_w = page_w - 2 * m
        block_x = m
        block_y = top_y - block_h

        draw_box(c, block_x, block_y, block_w, block_h, line_width=1)

        # Icon links
        ix = block_x + 8 * mm
        iy = block_y + (block_h - icon_size) / 2
        icon_slug = (item.get("icon_slug") or "icon").strip()
        draw_icon(c, icon_slug, ix, iy, icon_size)

        # Term rechts neben Icon
        term = (item.get("term") or "").strip()
        c.setFont("Helvetica-Bold", 16)
        c.drawString(ix + icon_size + 10*mm, block_y + block_h - 18*mm, term if term else "________________________")

        # Mini-Metadatenzeile
        c.setFont("Helvetica", 10)
        c.setFillColor(colors.Color(0, 0, 0, alpha=0.65))
        c.drawString(ix + icon_size + 10*mm, block_y + 8*mm, "Sprich. Schreib. Wiederhole.")
        c.setFillColor(colors.black)

        # ---- Beispielsätze ----
        examples = item.get("examples") or []
        ex_title_y = block_y - 16
        c.setFont("Helvetica-Bold", 12)
        c.drawString(m, ex_title_y, "Beispiele:")

        c.setFont("Helvetica", 11)
        y = ex_title_y - 16
        if not examples:
            examples = ["______________________________________________",
                        "______________________________________________",
                        "______________________________________________"]

        for s in examples[:3]:
            c.drawString(m + 6*mm, y, f"• {s}")
            y -= 14

        # ---- Große Schreibfläche / Notizen ----
        prompt = (item.get("note_prompt") or "Notizen:").strip()
        c.setFont("Helvetica-Bold", 12)
        c.drawString(m, y - 8, prompt)

        # Schreibbox groß: bewusst maximaler Freiraum
        write_y_top = y - 18
        write_h = (write_y_top - m)  # bis Seitenrand unten
        write_y = m
        write_w = page_w - 2*m
        write_x = m

        draw_writing_area(
            c,
            write_x, write_y,
            write_w, write_h,
            line_spacing=14,
            lines=lines,
            border=True
        )

        # ---- Footer minimal ----
        c.setFont("Helvetica", 9)
        c.setFillColor(colors.Color(0, 0, 0, alpha=0.55))
        c.drawRightString(page_w - m, m - 8, "Offline-First • DSGVO • Eddie")
        c.setFillColor(colors.black)

        c.showPage()

    c.save()
    return buf.getvalue()
