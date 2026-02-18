# kern/pdf_engine.py
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm, inch
from reportlab.pdfgen import canvas

def get_page_spec(mode: str):
    """
    Liefert Seitenformat & Margins pro Exportmodus.
    """
    if mode == "A4 Arbeitsblatt":
        w, h = A4
        margin = 18 * mm
        return {"pagesize": (w, h), "margin": margin, "bleed": 0.0}

    if mode == "KDP Buch":
        # KDP Square: 8.5" x 8.5" + 0.125" bleed auf allen Seiten
        bleed = 0.125 * inch
        w = 8.5 * inch + 2 * bleed
        h = 8.5 * inch + 2 * bleed
        # Safe-Zone: 0.375" innerhalb vom Trim; also ab Trim+0.375"
        # Margin ab äußerer Seite (inkl. Bleed) gerechnet:
        margin = bleed + 0.375 * inch
        return {"pagesize": (w, h), "margin": margin, "bleed": bleed}

    raise ValueError(f"Unknown mode: {mode}")

def draw_box(c: canvas.Canvas, x, y, w, h, *, stroke=1, fill=0, line_width=1):
    c.saveState()
    c.setLineWidth(line_width)
    c.rect(x, y, w, h, stroke=stroke, fill=fill)
    c.restoreState()

def draw_writing_area(
    c: canvas.Canvas,
    x, y, w, h,
    *,
    line_spacing=12,
    left_padding=8,
    top_padding=10,
    lines=True,
    border=True
):
    """
    Große Schreibfläche: optional Linien + optional Rahmen.
    Koordinaten: (x,y) = unten links, ReportLab-Standard.
    """
    c.saveState()

    if border:
        c.setLineWidth(1)
        c.setStrokeColor(colors.black)
        c.rect(x, y, w, h, stroke=1, fill=0)

    if lines:
        c.setLineWidth(0.6)
        c.setStrokeColor(colors.Color(0, 0, 0, alpha=0.25))
        y_top = y + h - top_padding
        cur = y_top
        y_min = y + 10
        while cur > y_min:
            c.line(x + left_padding, cur, x + w - left_padding, cur)
            cur -= line_spacing

    c.restoreState()

def draw_brand_mark(
    c: canvas.Canvas,
    page_w, page_h,
    *,
    mode="watermark",
    scale=1.0,
    opacity=0.08
):
    """
    Lila Zunge als vektorbasierte Marke.
    'mode=watermark' setzt sie groß, dezent im Hintergrund.
    """
    c.saveState()
    try:
        c.setFillAlpha(opacity)
        c.setStrokeAlpha(opacity)
    except Exception:
        pass

    tongue = colors.Color(0.45, 0.20, 0.65, alpha=opacity)

    cx = page_w * 0.72
    cy = page_h * 0.18
    base = min(page_w, page_h) * 0.45 * scale

    c.translate(cx, cy)
    c.setFillColor(tongue)
    c.setStrokeColor(tongue)
    c.setLineWidth(2)

    p = c.beginPath()
    p.moveTo(0, 0)
    p.curveTo(base*0.55, base*0.10, base*0.75, base*0.55, base*0.30, base*0.85)
    p.curveTo(base*0.05, base*1.05, -base*0.35, base*0.95, -base*0.55, base*0.65)
    p.curveTo(-base*0.80, base*0.30, -base*0.55, base*0.05, 0, 0)
    p.close()
    c.drawPath(p, stroke=0, fill=1)

    try:
        c.setFillAlpha(min(0.18, opacity*2))
    except Exception:
        pass
    c.setFillColor(colors.white)
    notch = c.beginPath()
    notch.moveTo(-base*0.05, base*0.62)
    notch.curveTo(base*0.02, base*0.58, base*0.05, base*0.52, 0, base*0.45)
    notch.curveTo(-base*0.05, base*0.52, -base*0.02, base*0.58, -base*0.05, base*0.62)
    notch.close()
    c.drawPath(notch, stroke=0, fill=1)

    c.restoreState()

def draw_icon(c: canvas.Canvas, icon_slug: str, x, y, size):
    """
    Platzhalter: Hier hängst du dein ICON_REGISTRY-Vektorzeichnen rein.
    Bis dahin: neutrale Box als Icon-Fallback.
    """
    c.saveState()
    c.setLineWidth(1)
    c.rect(x, y, size, size, stroke=1, fill=0)
    c.setFont("Helvetica", 7)
    c.drawCentredString(x + size/2, y + size/2 - 3, icon_slug[:10])
    c.restoreState()