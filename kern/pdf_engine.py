# kern/pdf_engine.py  (Platinum Pro)
from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Callable, Dict, Optional

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader

# Branding-Farbe (zentral)
EDDIE_PURPLE = colors.HexColor("#7c3aed")


# =========================================================
# PAGE SPEC
# =========================================================
@dataclass(frozen=True)
class PageSpec:
    page_w: float
    page_h: float
    bleed: float
    safe: float  # Abstand vom Trim-Rand (inkl. Bleed)


def get_page_spec(*, kdp_mode: bool, square: bool = True) -> PageSpec:
    """
    KDP Print:
      - Trim: 8.5" x 8.5" (square=True) oder A4 (square=False)
      - Bleed: 0.125" rundum
      - Safe Zone: bleed + 0.375"
    Dev/Preview:
      - Kein Bleed, safe = 0.5"
    """
    if kdp_mode:
        bleed = 0.125 * inch
        if square:
            trim_w = 8.5 * inch
            trim_h = 8.5 * inch
        else:
            trim_w = 8.27 * inch   # A4
            trim_h = 11.69 * inch  # A4
        page_w = trim_w + 2 * bleed
        page_h = trim_h + 2 * bleed
        safe = bleed + 0.375 * inch
    else:
        bleed = 0.0
        if square:
            page_w = 8.5 * inch
            page_h = 8.5 * inch
        else:
            page_w = 8.27 * inch
            page_h = 11.69 * inch
        safe = 0.5 * inch

    return PageSpec(page_w=float(page_w), page_h=float(page_h), bleed=float(bleed), safe=float(safe))


# =========================================================
# BASIC DRAW HELPERS
# =========================================================
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
    """Zeichnet eine Box (x,y ist links-unten)."""
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
    scale_to: float = 0.75,
    debug_on_error: bool = False,
):
    """
    Bettet ein Bild (BytesIO) zentriert und skaliert ein.
    RAM-only, EXIF-Rotation, RGB-Konvertierung, Error-Fallback.
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
            raise ValueError("Ungültige Bilddimensionen")

        target_w = max_w * float(scale_to)
        target_h = max_h * float(scale_to)

        if preserve_aspect:
            scale = min(target_w / img_w, target_h / img_h)
            draw_w = img_w * scale
            draw_h = img_h * scale
        else:
            draw_w, draw_h = target_w, target_h

        dx = (max_w - draw_w) / 2.0
        dy = (max_h - draw_h) / 2.0

        c.drawImage(ImageReader(im), x + dx, y + dy, width=draw_w, height=draw_h, mask="auto")

    except Exception as e:
        if debug_on_error:
            c.saveState()
            c.setFont("Helvetica", 10)
            c.setFillColor(colors.red)
            c.drawString(x + 12, y + 12, f"Bild-Fehler: {str(e)[:80]}")
            c.restoreState()
        return


# =========================================================
# ICONS – STYLE HELPERS
# Konvention: x,y = links-unten der Icon-Box; size = Kantenlänge
# =========================================================
def _icon_style(c: canvas.Canvas, size: float):
    """Grundstil: schwarze Linien, rund, skalierbar."""
    c.setStrokeColor(colors.black)
    c.setFillColor(colors.white)
    c.setLineWidth(max(1.0, float(size) * 0.06))
    try:
        c.setLineCap(1)   # round
        c.setLineJoin(1)  # round
    except Exception:
        pass


def _purple_dot(c: canvas.Canvas, x: float, y: float, r: float):
    c.setFillColor(EDDIE_PURPLE)
    c.circle(x, y, r, fill=1, stroke=0)


# =========================================================
# PRO-ICONS (Job-Set) – Piktogramme (druck-sicher)
# =========================================================
def draw_icon_hammer(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    _icon_style(c, size)
    c.line(x + size * 0.20, y + size * 0.80, x + size * 0.80, y + size * 0.20)
    c.rect(x + size * 0.55, y + size * 0.60, size * 0.35, size * 0.15, stroke=1, fill=0)
    _purple_dot(c, x + size * 0.22, y + size * 0.78, size * 0.06)
    c.restoreState()


def draw_icon_wrench(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    _icon_style(c, size)
    c.line(x + size * 0.25, y + size * 0.25, x + size * 0.75, y + size * 0.75)
    x1, y1 = x + size * 0.62, y + size * 0.62
    x2, y2 = x + size * 0.92, y + size * 0.92
    c.arc(x1, y1, x2, y2, 30, 300)
    _purple_dot(c, x + size * 0.74, y + size * 0.76, size * 0.05)
    c.restoreState()


def draw_icon_gear(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    _icon_style(c, size)
    cx, cy = x + size * 0.50, y + size * 0.50
    c.circle(cx, cy, size * 0.30, stroke=1, fill=0)
    c.circle(cx, cy, size * 0.10, stroke=1, fill=0)

    for deg in range(0, 360, 45):
        a = math.radians(deg)
        x1 = cx + (size * 0.30) * math.cos(a)
        y1 = cy + (size * 0.30) * math.sin(a)
        x2 = cx + (size * 0.44) * math.cos(a)
        y2 = cy + (size * 0.44) * math.sin(a)
        c.line(x1, y1, x2, y2)

    _purple_dot(c, cx, y + size * 0.82, size * 0.05)
    c.restoreState()


def draw_icon_medical_cross(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    _icon_style(c, size)
    c.rect(x + size * 0.40, y + size * 0.20, size * 0.20, size * 0.60, stroke=1, fill=0)
    c.rect(x + size * 0.20, y + size * 0.40, size * 0.60, size * 0.20, stroke=1, fill=0)
    _purple_dot(c, x + size * 0.50, y + size * 0.86, size * 0.05)
    c.restoreState()


def draw_icon_briefcase(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    _icon_style(c, size)
    c.rect(x + size * 0.20, y + size * 0.30, size * 0.60, size * 0.45, stroke=1, fill=0)
    c.rect(x + size * 0.40, y + size * 0.75, size * 0.20, size * 0.10, stroke=1, fill=0)
    _purple_dot(c, x + size * 0.78, y + size * 0.52, size * 0.05)
    c.restoreState()


def draw_icon_book_open(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    _icon_style(c, size)
    c.rect(x + size * 0.20, y + size * 0.30, size * 0.30, size * 0.50, stroke=1, fill=0)
    c.rect(x + size * 0.50, y + size * 0.30, size * 0.30, size * 0.50, stroke=1, fill=0)
    c.line(x + size * 0.50, y + size * 0.30, x + size * 0.50, y + size * 0.80)
    _purple_dot(c, x + size * 0.50, y + size * 0.86, size * 0.05)
    c.restoreState()


def draw_icon_fork_knife(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    _icon_style(c, size)
    c.line(x + size * 0.32, y + size * 0.20, x + size * 0.32, y + size * 0.85)
    c.line(x + size * 0.60, y + size * 0.20, x + size * 0.60, y + size * 0.85)
    _purple_dot(c, x + size * 0.60, y + size * 0.86, size * 0.05)
    c.restoreState()


def draw_icon_computer(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    _icon_style(c, size)
    c.rect(x + size * 0.20, y + size * 0.40, size * 0.60, size * 0.40, stroke=1, fill=0)
    c.line(x + size * 0.40, y + size * 0.30, x + size * 0.60, y + size * 0.30)
    _purple_dot(c, x + size * 0.78, y + size * 0.60, size * 0.05)
    c.restoreState()


# =========================================================
# NEUE ICONS (zusätzliche Slugs)
# =========================================================
def draw_icon_scissors(c: canvas.Canvas, x: float, y: float, size: float):
    """Schere (Schneidern)"""
    c.saveState()
    _icon_style(c, size)

    c.line(x + size * 0.20, y + size * 0.25, x + size * 0.80, y + size * 0.75)
    c.line(x + size * 0.20, y + size * 0.75, x + size * 0.80, y + size * 0.25)

    c.circle(x + size * 0.38, y + size * 0.22, size * 0.10, stroke=1, fill=0)
    c.circle(x + size * 0.62, y + size * 0.22, size * 0.10, stroke=1, fill=0)

    _purple_dot(c, x + size * 0.50, y + size * 0.52, size * 0.06)
    c.restoreState()


def draw_icon_syringe(c: canvas.Canvas, x: float, y: float, size: float):
    """Spritze (Pflege/Medizin)"""
    c.saveState()
    _icon_style(c, size)

    c.rect(x + size * 0.28, y + size * 0.38, size * 0.44, size * 0.18, stroke=1, fill=0)
    c.line(x + size * 0.18, y + size * 0.47, x + size * 0.28, y + size * 0.47)
    c.line(x + size * 0.16, y + size * 0.52, x + size * 0.16, y + size * 0.42)
    c.line(x + size * 0.72, y + size * 0.47, x + size * 0.90, y + size * 0.47)

    _purple_dot(c, x + size * 0.50, y + size * 0.66, size * 0.05)
    c.restoreState()


def draw_icon_envelope(c: canvas.Canvas, x: float, y: float, size: float):
    """Briefumschlag (Kommunikation)"""
    c.saveState()
    _icon_style(c, size)

    c.rect(x + size * 0.18, y + size * 0.30, size * 0.64, size * 0.44, stroke=1, fill=0)
    c.line(x + size * 0.18, y + size * 0.74, x + size * 0.50, y + size * 0.52)
    c.line(x + size * 0.82, y + size * 0.74, x + size * 0.50, y + size * 0.52)
    c.line(x + size * 0.18, y + size * 0.30, x + size * 0.50, y + size * 0.52)
    c.line(x + size * 0.82, y + size * 0.30, x + size * 0.50, y + size * 0.52)

    _purple_dot(c, x + size * 0.80, y + size * 0.32, size * 0.05)
    c.restoreState()


def draw_icon_calendar(c: canvas.Canvas, x: float, y: float, size: float):
    """Kalender (Termine)"""
    c.saveState()
    _icon_style(c, size)

    c.rect(x + size * 0.18, y + size * 0.22, size * 0.64, size * 0.62, stroke=1, fill=0)
    c.rect(x + size * 0.18, y + size * 0.72, size * 0.64, size * 0.12, stroke=1, fill=0)
    c.circle(x + size * 0.32, y + size * 0.86, size * 0.04, stroke=1, fill=0)
    c.circle(x + size * 0.68, y + size * 0.86, size * 0.04, stroke=1, fill=0)

    _purple_dot(c, x + size * 0.50, y + size * 0.46, size * 0.06)
    c.restoreState()


def draw_icon_wheelchair(c: canvas.Canvas, x: float, y: float, size: float):
    """Rollstuhl (Pflege/Barrierefreiheit)"""
    c.saveState()
    _icon_style(c, size)

    c.circle(x + size * 0.40, y + size * 0.34, size * 0.22, stroke=1, fill=0)
    c.circle(x + size * 0.72, y + size * 0.28, size * 0.08, stroke=1, fill=0)
    c.line(x + size * 0.40, y + size * 0.56, x + size * 0.62, y + size * 0.56)
    c.line(x + size * 0.62, y + size * 0.56, x + size * 0.70, y + size * 0.44)
    c.line(x + size * 0.50, y + size * 0.56, x + size * 0.50, y + size * 0.78)

    _purple_dot(c, x + size * 0.50, y + size * 0.80, size * 0.05)
    c.restoreState()


def draw_icon_tray(c: canvas.Canvas, x: float, y: float, size: float):
    """Tablett (Gastro/Service)"""
    c.saveState()
    _icon_style(c, size)

    c.roundRect(x + size * 0.18, y + size * 0.42, size * 0.64, size * 0.20, radius=size * 0.08, stroke=1, fill=0)
    c.line(x + size * 0.50, y + size * 0.42, x + size * 0.50, y + size * 0.28)
    c.circle(x + size * 0.50, y + size * 0.26, size * 0.05, stroke=1, fill=0)

    _purple_dot(c, x + size * 0.78, y + size * 0.54, size * 0.05)
    c.restoreState()


# =========================================================
# ICON REGISTRY
# =========================================================
IconDrawer = Callable[[canvas.Canvas, float, float, float], None]

ICON_DRAWERS: Dict[str, IconDrawer] = {}
ICON_DRAWERS.update(
    {
        # existing slugs
        "hammer": draw_icon_hammer,
        "wrench": draw_icon_wrench,
        "gear": draw_icon_gear,
        "medical": draw_icon_medical_cross,
        "briefcase": draw_icon_briefcase,
        "teacher": draw_icon_book_open,
        "gastro": draw_icon_fork_knife,
        "computer": draw_icon_computer,
        # new slugs
        "scissors": draw_icon_scissors,
        "syringe": draw_icon_syringe,
        "envelope": draw_icon_envelope,
        "calendar": draw_icon_calendar,
        "wheelchair": draw_icon_wheelchair,
        "tray": draw_icon_tray,
    }
)


# Optional: friendly aliases (wenn subject_data andere Namen nutzt)
# Beispiel: subject_data nutzt "medical_cross" statt "medical"
ICON_ALIASES: Dict[str, str] = {
    "medical_cross": "medical",
    "fork_knife": "gastro",
    "book_open": "teacher",
}


def draw_icon(c: canvas.Canvas, *, key: str, x: float, y: float, size: float) -> bool:
    """
    Zeichnet ein Icon aus dem Registry.
    - key wird normalisiert
    - Aliases werden aufgelöst
    Returns True wenn gezeichnet, sonst False.
    """
    k = str(key).strip().lower()
    k = ICON_ALIASES.get(k, k)
    fn = ICON_DRAWERS.get(k)
    if not fn:
        return False
    fn(c, x, y, float(size))
    return True