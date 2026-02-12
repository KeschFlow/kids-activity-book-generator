# kern/pdf_engine.py
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Optional

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader


@dataclass(frozen=True)
class PageSpec:
    page_w: float
    page_h: float
    bleed: float
    safe: float  # Abstand vom Trim-Rand (inkl. Bleed)


def get_page_spec(*, kdp_mode: bool) -> PageSpec:
    """
    KDP Print:
      - Trim: 8.5" x 8.5"
      - Bleed: 0.125" rundum
      - Safe Zone: mind. 0.375" vom Trim-Rand (also bleed + 0.375")
    Dev:
      - A4 ohne Bleed
      - safe = 0.5"
    """
    if kdp_mode:
        bleed = 0.125 * inch
        page_w = 8.5 * inch + 2 * bleed
        page_h = 8.5 * inch + 2 * bleed
        safe = bleed + 0.375 * inch
    else:
        bleed = 0.0
        page_w = 8.27 * inch   # ~A4
        page_h = 11.69 * inch  # ~A4
        safe = 0.5 * inch

    return PageSpec(page_w=page_w, page_h=page_h, bleed=bleed, safe=safe)


def draw_box(
    c: canvas.Canvas,
    x: float,
    y: float,
    w: float,
    h: float,
    *,
    title: Optional[str] = None,
    stroke=colors.black,
    fill=None,
    title_font: str = "Helvetica-Bold",
    title_size: int = 12,
    padding: float = 8,
):
    """
    Zeichnet eine Box (x,y links-unten).
    """
    c.saveState()
    c.setLineWidth(1)
    c.setStrokeColor(stroke)

    if fill is not None:
        c.setFillColor(fill)
        c.rect(x, y, w, h, fill=1, stroke=1)
    else:
        c.rect(x, y, w, h, fill=0, stroke=1)

    if title:
        c.setFont(title_font, title_size)
        c.setFillColor(colors.black)
        c.drawString(x + padding, y + h - title_size - padding / 2, title)

    c.restoreState()


def embed_image(
    c: canvas.Canvas,
    *,
    img_data: io.BytesIO,
    x: float,
    y: float,
    max_w: float,
    max_h: float,
    preserve_aspect: bool = True,
    scale_to: float = 0.5,
    debug_on_error: bool = False,
):
    """
    Bettet ein Bild (BytesIO) in eine Box ein:
      - RAM-only
      - Auto-Rotation via EXIF (Handyfotos)
      - RGB normalisieren
      - Skalierung: standardmäßig max 50% der Box (scale_to=0.5)
      - Zentriert in der Box

    Hinweis: (x,y) ist links-unten der Box.
    """
    try:
        from PIL import Image, ImageOps

        img_data.seek(0)
        im = Image.open(img_data)
        im = ImageOps.exif_transpose(im)

        if im.mode != "RGB":
            im = im.convert("RGB")

        img_w, img_h = im.size
        if img_w <= 0 or img_h <= 0:
            raise ValueError("Ungültige Bilddimensionen.")

        target_w = max_w * float(scale_to)
        target_h = max_h * float(scale_to)

        if preserve_aspect:
            scale = min(target_w / img_w, target_h / img_h)
            draw_w = img_w * scale
            draw_h = img_h * scale
        else:
            draw_w = target_w
            draw_h = target_h

        dx = (max_w - draw_w) / 2.0
        dy = (max_h - draw_h) / 2.0

        c.drawImage(ImageReader(im), x + dx, y + dy, width=draw_w, height=draw_h, mask="auto")

    except Exception as e:
        if debug_on_error:
            c.saveState()
            c.setFont("Helvetica", 9)
            c.setFillColor(colors.red)
            c.drawString(x + 8, y + 8, f"Bild-Fehler: {str(e)[:90]}")
            c.restoreState()
        # Silent fallback
        return
# ==========================
# PRO ICON PACK – JOB SET
# ==========================

def draw_icon_hammer(c, x, y, size):
    c.saveState()
    _icon_style(c, size)
    c.line(x + size*0.2, y + size*0.8, x + size*0.8, y + size*0.2)
    c.rect(x + size*0.55, y + size*0.6, size*0.35, size*0.15, stroke=1, fill=0)
    c.setFillColor(EDDIE_PURPLE)
    c.circle(x + size*0.2, y + size*0.8, size*0.06, fill=1, stroke=0)
    c.restoreState()


def draw_icon_wrench(c, x, y, size):
    c.saveState()
    _icon_style(c, size)
    c.line(x + size*0.25, y + size*0.25, x + size*0.75, y + size*0.75)
    c.arc(x + size*0.6, y + size*0.6, x + size*0.9, y + size*0.9, 30, 300)
    c.setFillColor(EDDIE_PURPLE)
    c.circle(x + size*0.75, y + size*0.75, size*0.05, fill=1, stroke=0)
    c.restoreState()


def draw_icon_gear(c, x, y, size):
    c.saveState()
    _icon_style(c, size)
    c.circle(x + size*0.5, y + size*0.5, size*0.3, stroke=1, fill=0)
    c.circle(x + size*0.5, y + size*0.5, size*0.1, stroke=1, fill=0)
    c.setFillColor(EDDIE_PURPLE)
    c.circle(x + size*0.5, y + size*0.8, size*0.05, fill=1, stroke=0)
    c.restoreState()


def draw_icon_medical_cross(c, x, y, size):
    c.saveState()
    _icon_style(c, size)
    c.rect(x + size*0.4, y + size*0.2, size*0.2, size*0.6, stroke=1, fill=0)
    c.rect(x + size*0.2, y + size*0.4, size*0.6, size*0.2, stroke=1, fill=0)
    c.setFillColor(EDDIE_PURPLE)
    c.circle(x + size*0.5, y + size*0.9, size*0.05, fill=1, stroke=0)
    c.restoreState()


def draw_icon_briefcase(c, x, y, size):
    c.saveState()
    _icon_style(c, size)
    c.rect(x + size*0.2, y + size*0.3, size*0.6, size*0.45, stroke=1, fill=0)
    c.rect(x + size*0.4, y + size*0.75, size*0.2, size*0.1, stroke=1, fill=0)
    c.setFillColor(EDDIE_PURPLE)
    c.circle(x + size*0.8, y + size*0.5, size*0.05, fill=1, stroke=0)
    c.restoreState()


def draw_icon_book_open(c, x, y, size):
    c.saveState()
    _icon_style(c, size)
    c.rect(x + size*0.2, y + size*0.3, size*0.3, size*0.5, stroke=1, fill=0)
    c.rect(x + size*0.5, y + size*0.3, size*0.3, size*0.5, stroke=1, fill=0)
    c.line(x + size*0.5, y + size*0.3, x + size*0.5, y + size*0.8)
    c.setFillColor(EDDIE_PURPLE)
    c.circle(x + size*0.5, y + size*0.85, size*0.05, fill=1, stroke=0)
    c.restoreState()


def draw_icon_fork_knife(c, x, y, size):
    c.saveState()
    _icon_style(c, size)
    c.line(x + size*0.3, y + size*0.2, x + size*0.3, y + size*0.85)
    c.line(x + size*0.6, y + size*0.2, x + size*0.6, y + size*0.85)
    c.setFillColor(EDDIE_PURPLE)
    c.circle(x + size*0.6, y + size*0.85, size*0.05, fill=1, stroke=0)
    c.restoreState()


def draw_icon_computer(c, x, y, size):
    c.saveState()
    _icon_style(c, size)
    c.rect(x + size*0.2, y + size*0.4, size*0.6, size*0.4, stroke=1, fill=0)
    c.line(x + size*0.4, y + size*0.3, x + size*0.6, y + size*0.3)
    c.setFillColor(EDDIE_PURPLE)
    c.circle(x + size*0.8, y + size*0.6, size*0.05, fill=1, stroke=0)
    c.restoreState()
