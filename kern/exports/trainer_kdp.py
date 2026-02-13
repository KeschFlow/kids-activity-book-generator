# kern/exports/trainer_kdp.py
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
    draw_writing_area,
    draw_icon,
)
from kern.kdp_preflight import ensure_min_pages, PageFn

# -----------------------------
# Policy (KDP Square)
# -----------------------------
KDP_POLICY: Dict[str, Any] = {
    "watermark_opacity": 0.06,
    "content_pad_mm": 10,
    "icon_size_mm": 28,
    "gap_mm": 6,

    # Schreiblinien via spacing
    "writing_line_spacing_min_pt": 10.0,
    "writing_line_spacing_max_pt": 22.0,
}

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
    return []

def _get_images_bytes(data: Dict[str, Any]) -> List[bytes]:
    assets = data.get("assets") or {}
    imgs = assets.get("images") or []
    out: List[bytes] = []
    for b in imgs:
        if isinstance(b, (bytes, bytearray)) and len(b) > 0:
            out.append(bytes(b))
    return out

def _draw_image_fit(c: canvas.Canvas, img_bytes: bytes, *, x: float, y: float, w: float, h: float, pad: float) -> bool:
    try:
        reader = ImageReader(io.BytesIO(img_bytes))
        iw, ih = reader.getSize()
        if iw <= 0 or ih <= 0:
            return False
        max_w = max(1.0, w - 2*pad)
        max_h = max(1.0, h - 2*pad)
        scale = min(max_w/iw, max_h/ih)
        nw, nh = iw*scale, ih*scale
        dx = x + (w - nw)/2
        dy = y + (h - nh)/2
        c.drawImage(reader, dx, dy, width=nw, height=nh, preserveAspectRatio=True, mask="auto")
        return True
    except Exception:
        return False

def _make_reflection_page(*, title: str, prompts: List[str], watermark: bool, pol: Dict[str, Any]) -> PageFn:
    def _page(c: canvas.Canvas, ctx: Dict[str, Any]) -> None:
        page_w, page_h = ctx["page_w"], ctx["page_h"]
        m = ctx["margin"]

        if watermark:
            draw_brand_mark(c, page_w, page_h, mode="watermark", opacity=float(pol["watermark_opacity"]))

        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 22)
        c.drawString(m, page_h - m - 20, title)

        c.setFont("Helvetica", 12)
        y = page_h - m - 52
        for p in prompts[:5]:
            c.drawString(m, y, f"• {p}")
            y -= 18

        # große Schreibfläche
        write_top = y - 10
        write_h = max(1.0, write_top - m)
        write_y = m
        write_x = m
        write_w = page_w - 2*m

        # Linienabstand "hochwertig": eher mittig, nicht zu eng
        spacing = 14.0
        draw_writing_area(
            c,
            write_x, write_y,
            write_w, write_h,
            line_spacing=spacing,
            lines=True,
            border=True
        )

        c.setFont("Helvetica", 9)
        c.setFillColor(colors.Color(0, 0, 0, alpha=0.55))
        c.drawRightString(page_w - m, m - 8, "Reflexion • Offline-First • Eddie")
        c.setFillColor(colors.black)
    return _page

def export_trainer_kdp(
    data: Dict[str, Any],
    *,
    title: str = "Eddie Trainer V2",
    subtitle: Optional[str] = None,
    watermark: bool = True,
    policy: Optional[Dict[str, Any]] = None,
    min_pages: int = 24,
) -> bytes:
    """
    KDP Export (Square + Bleed):
    - baut Seitenliste (Cover + Vokabelseiten + optional Quiz später)
    - Preflight: garantiert min_pages (default 24) durch Reflexionsseiten
    """
    if not isinstance(data, dict):
        raise ValueError("export_trainer_kdp: data must be a dict")

    pol = dict(KDP_POLICY)
    if policy:
        pol.update(policy)

    spec = get_page_spec("KDP Buch")
    page_w, page_h = spec["pagesize"]
    margin = float(spec["margin"])
    bleed = float(spec["bleed"])

    subject = str((data.get("subject") or "")).strip()
    vocab = _coerce_vocab(data)
    images = _get_images_bytes(data)

    opts = data.get("options") or {}
    writing_lines_per_page = int(opts.get("writing_lines_per_page", 5))

    if not vocab:
        vocab = [{"word": "", "translation": ""}]

    # ---- Seiten als Callables sammeln ----
    pages: List[PageFn] = []

    def cover_page(c: canvas.Canvas, ctx: Dict[str, Any]) -> None:
        if watermark:
            draw_brand_mark(c, page_w, page_h, mode="watermark", opacity=float(pol["watermark_opacity"]))
        # Trim-Box optional (kein Debug)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 32)
        c.drawCentredString(page_w/2, page_h/2 + 18, title)
        c.setFont("Helvetica", 14)
        sub = subtitle or (f"Fach: {subject}" if subject else "KDP Edition")
        c.setFillColor(colors.grey)
        c.drawCentredString(page_w/2, page_h/2 - 10, sub)
        c.setFillColor(colors.black)

    pages.append(cover_page)

    # Vokabelseiten
    pad = float(pol["content_pad_mm"]) * mm
    gap = float(pol["gap_mm"]) * mm
    icon_size = float(pol["icon_size_mm"]) * mm

    img_idx = 0

    for i, it in enumerate(vocab, 1):
        word = str(it.get("word", "")).strip()
        translation = str(it.get("translation", "")).strip()

        def make_vocab_page(word=word, translation=translation, idx=i) -> PageFn:
            def _page(c: canvas.Canvas, ctx: Dict[str, Any]) -> None:
                if watermark:
                    draw_brand_mark(c, page_w, page_h, mode="watermark", opacity=float(pol["watermark_opacity"]))

                m = ctx["margin"]
                usable_w = page_w - 2*m
                usable_h = page_h - 2*m

                # Header klein
                c.setFillColor(colors.black)
                c.setFont("Helvetica-Bold", 18)
                c.drawString(m, page_h - m - 16, title)
                c.setFont("Helvetica", 11)
                c.setFillColor(colors.grey)
                meta = subtitle or (f"Fach: {subject}" if subject else "KDP Edition")
                c.drawRightString(page_w - m, page_h - m - 16, f"{meta}  •  {idx}/{len(vocab)}")
                c.setFillColor(colors.black)

                # Wortbox
                word_box_h = 34 * mm
                y_word_top = page_h - m - 28*mm
                y_word = y_word_top - word_box_h
                draw_box(c, m, y_word, usable_w, word_box_h, line_width=1)

                # Icon links
                ix = m + pad
                iy = y_word + (word_box_h - icon_size)/2
                draw_icon(c, "briefcase", ix, iy, icon_size)

                tx = ix + icon_size + 10*mm
                c.setFont("Helvetica-Bold", 24)
                c.drawString(tx, y_word + word_box_h - 18*mm, word if word else "____________________")

                if translation:
                    c.setFont("Helvetica", 14)
                    c.drawString(tx, y_word + 8*mm, translation[:90])
                else:
                    c.setFont("Helvetica", 11)
                    c.setFillColor(colors.grey)
                    c.drawString(tx, y_word + 8*mm, "Übersetzung: ____________________")
                    c.setFillColor(colors.black)

                # Bildbox
                img_box_h = 74 * mm
                y_img_top = y_word - gap
                y_img = y_img_top - img_box_h
                draw_box(c, m, y_img, usable_w, img_box_h, line_width=1)

                nonlocal img_idx
                drew = False
                if images:
                    b = images[img_idx % len(images)]
                    img_idx += 1
                    drew = _draw_image_fit(c, b, x=m, y=y_img, w=usable_w, h=img_box_h, pad=pad)

                if not drew:
                    # großes Icon als fallback
                    size = min(img_box_h*0.6, usable_w*0.35)
                    cx = m + usable_w/2
                    cy = y_img + img_box_h/2
                    draw_icon(c, "briefcase", cx - size/2, cy - size/2, size)

                # Schreibbox
                y_write_top = y_img - gap
                write_h = max(1.0, (y_write_top - m))
                draw_box(c, m, m, usable_w, write_h, line_width=1)

                # Prompt
                c.setFont("Helvetica-Bold", 12)
                c.drawString(m + pad, y_write_top - 14, "Schreibe 3 eigene Sätze:")

                write_area_y = m + pad
                write_area_h = max(1.0, write_h - (pad + 18))
                write_area_x = m + pad
                write_area_w = usable_w - 2*pad

                # Dynamische Linien: Anzahl aus UI (via spacing)
                if writing_lines_per_page > 0:
                    dyn_spacing = write_area_h / float(writing_lines_per_page + 1)
                    dyn_spacing = max(
                        float(pol["writing_line_spacing_min_pt"]),
                        min(float(pol["writing_line_spacing_max_pt"]), dyn_spacing),
                    )
                else:
                    dyn_spacing = 14.0

                draw_writing_area(
                    c,
                    write_area_x, write_area_y,
                    write_area_w, write_area_h,
                    line_spacing=float(dyn_spacing),
                    lines=True,
                    border=False
                )

                # Footer
                c.setFont("Helvetica", 9)
                c.setFillColor(colors.Color(0, 0, 0, alpha=0.55))
                c.drawRightString(page_w - m, m - 10, "KDP • Bleed+Safe • Eddie")
                c.setFillColor(colors.black)
            return _page
        pages.append(make_vocab_page())

    # ---- Preflight: min pages ----
    reflection_templates = [
        ("Reflexion", ["Was habe ich heute gelernt?", "Welches Wort war neu?", "Wann brauche ich das im Alltag?"]),
        ("Wiederholung", ["Schreibe das Wort 5×.", "Bilde 2 neue Sätze.", "Erkläre das Wort in eigenen Worten."]),
        ("Transfer", ["Wo siehst du das in der Arbeit?", "Welche Situation passt dazu?", "Wie würdest du es jemandem erklären?"]),
    ]
    ref_idx = 0

    def make_reflection_page(n: int) -> PageFn:
        nonlocal ref_idx
        t, prompts = reflection_templates[ref_idx % len(reflection_templates)]
        ref_idx += 1
        return _make_reflection_page(
            title=f"{t} – Seite {n}",
            prompts=prompts,
            watermark=watermark,
            pol=pol
        )

    pages = ensure_min_pages(pages, min_pages=min_pages, make_reflection_page=make_reflection_page)

    # ---- Render ----
    ctx = {"page_w": page_w, "page_h": page_h, "margin": margin, "bleed": bleed}

    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(page_w, page_h))
    for fn in pages:
        fn(c, ctx)
        c.showPage()
    c.save()

    out.seek(0)
    return out.getvalue()
