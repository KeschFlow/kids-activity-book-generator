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
    "examples_block_min_h_mm": 26,  # Beispiele sollen nicht zu klein werden
    "gap_mm": 5,
    "watermark_opacity": 0.06,

    # Schreiblinien (wir berechnen spacing dynamisch aus lines_per_page,
    # clampen aber in sinnvollen Grenzen)
    "writing_line_spacing_min_pt": 10.0,
    "writing_line_spacing_max_pt": 22.0,

    # Content Box Innenpadding
    "content_pad_mm": 6,
}


# -----------------------------
# Helpers: Daten lesen
# -----------------------------
def _coerce_vocab(data: Dict[str, Any]) -> List[Dict[str, str]]:
    """
    Erwartet trainer_v2:
      data["vocab"] = [{"word":..., "translation":...}, ...]
    Fallback:
      data["items"] legacy -> word=term
    """
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
                out2.append({"word": str(it.get("term", "")).strip(), "translation": ""})
        return [v for v in out2 if v["word"]]
    return []


def _get_images_bytes(data: Dict[str, Any]) -> List[bytes]:
    assets = data.get("assets") or {}
    imgs = assets.get("images") or []
    out: List[bytes] = []
    for b in imgs:
        if isinstance(b, (bytes, bytearray)) and len(b) > 0:
            out.append(bytes(b))
    return out


def _build_legacy_lookup(data: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """
    Legacy items -> schneller Zugriff per term (word).
    items: [{term, icon_slug, examples, note_prompt}, ...]
    """
    lookup: Dict[str, Dict[str, Any]] = {}
    items = data.get("items")
    if not isinstance(items, list):
        return lookup
    for it in items:
        if not isinstance(it, dict):
            continue
        term = str(it.get("term", "")).strip()
        if term:
            lookup[term] = it
    return lookup


def _choose_icon_slug(subject: str, word: str, legacy_icon_slug: Optional[str] = None) -> str:
    """
    Priorität:
    1) legacy_icon_slug (falls vorhanden)
    2) Offline-Heuristik
    """
    if legacy_icon_slug:
        s = str(legacy_icon_slug).strip()
        if s:
            return s

    s = (subject or "").strip().lower()
    w = (word or "").strip().lower()

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
    pad: float,
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


def _fallback_examples() -> List[str]:
    return [
        "______________________________________________",
        "______________________________________________",
        "______________________________________________",
    ]


# -----------------------------
# Exporter
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
    A4 Arbeitsblatt Export (Trainer):
    - pro Vokabel 1 Seite
    - oben Wort + Icon
    - Content-Block: Bild (oben) + Beispiele (unten)
    - unten: große Schreibfläche
    - nutzt trainer_v2 schema, kann aber Legacy items (examples, note_prompt, icon_slug) einweben
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
    legacy_lookup = _build_legacy_lookup(data)

    # Optionen (vom UI übergeben)
    opts = data.get("options") or {}
    writing_lines_per_page = int(opts.get("writing_lines_per_page", 5))

    out = io.BytesIO()
    c = canvas.Canvas(out, pagesize=(page_w, page_h))

    usable_w = page_w - 2 * m
    usable_h = page_h - 2 * m

    # Layout
    header_h = float(pol["header_h_mm"]) * mm
    word_block_h = float(pol["word_block_h_mm"]) * mm
    gap = float(pol["gap_mm"]) * mm
    icon_size = float(pol["icon_size_mm"]) * mm
    content_pad = float(pol["content_pad_mm"]) * mm

    # Garantie: min_write_area_ratio
    min_write_h = usable_h * float(pol["min_write_area_ratio"])

    fixed_top = header_h + gap + word_block_h + gap
    remaining = usable_h - fixed_top - gap  # gap vor Schreibblock

    # Content (Bild+Beispiele)
    content_block_h = max(float(pol["examples_block_min_h_mm"]) * mm, remaining - min_write_h)
    write_block_h = remaining - content_block_h

    if write_block_h < min_write_h:
        write_block_h = min_write_h
        content_block_h = max(float(pol["examples_block_min_h_mm"]) * mm, remaining - write_block_h)

    # Zonierung im Content-Block
    examples_h = max(float(pol["examples_block_min_h_mm"]) * mm, content_block_h * 0.32)

    img_idx = 0

    if not vocab:
        vocab = [{"word": "", "translation": ""}]

    for i, it in enumerate(vocab, 1):
        word = (it.get("word") or "").strip()
        translation = (it.get("translation") or "").strip()

        legacy = legacy_lookup.get(word, {}) if word else {}
        legacy_examples = legacy.get("examples") if isinstance(legacy, dict) else None
        legacy_prompt = legacy.get("note_prompt") if isinstance(legacy, dict) else None
        legacy_icon = legacy.get("icon_slug") if isinstance(legacy, dict) else None

        # Examples aus trainer_v2 optional (falls später ergänzt)
        v2_examples = it.get("examples") if isinstance(it, dict) else None

        # ---- Branding Watermark ----
        if watermark:
            draw_brand_mark(
                c, page_w, page_h,
                mode="watermark",
                opacity=float(pol["watermark_opacity"]),
            )

        # ---- Header ----
        top = page_h - m
        c.setFillColor(colors.black)

        c.setFont("Helvetica-Bold", 18)
        c.drawString(m, top - 18, title)

        meta = subtitle or (f"Fach: {subject}" if subject else "Arbeitsblatt")
        c.setFont("Helvetica", 11)
        c.setFillColor(colors.grey)
        c.drawString(m, top - 34, f"{meta}  •  Karte {i}/{len(vocab)}")
        c.setFillColor(colors.black)

        # ---- Wortblock (Icon + Wort + Übersetzung) ----
        y_word_top = top - header_h - gap
        y_word = y_word_top - word_block_h
        draw_box(c, m, y_word, usable_w, word_block_h, line_width=1)

        slug = _choose_icon_slug(subject, word, legacy_icon_slug=legacy_icon)

        # Icon links
        ix = m + 8 * mm
        iy = y_word + (word_block_h - icon_size) / 2
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

        # ---- Content-Block (Bild oben + Beispiele unten) ----
        y_content_top = y_word - gap
        y_content = y_content_top - content_block_h
        draw_box(c, m, y_content, usable_w, content_block_h, line_width=1)

        inner_top = y_content_top - content_pad
        inner_bottom = y_content + content_pad
        inner_h = max(1.0, inner_top - inner_bottom)

        ex_h = examples_h
        img_h = max(40 * mm, inner_h - ex_h - gap)

        # Bildzone
        img_y_top = inner_top
        img_y = img_y_top - img_h
        img_x = m + content_pad
        img_w = usable_w - 2 * content_pad

        drew = False
        if images:
            b = images[img_idx % len(images)]
            img_idx += 1
            drew = _draw_image_in_box(
                c, b,
                x=img_x, y=img_y, w=img_w, h=img_h,
                pad=4 * mm,
            )

        if not drew:
            # großes Icon als Ersatz
            size = min(img_h * 0.60, img_w * 0.35)
            cx = m + usable_w / 2
            cy = img_y + img_h / 2
            draw_icon(c, slug, cx - size / 2, cy - size / 2, size)

            c.setFont("Helvetica-Oblique", 10)
            c.setFillColor(colors.grey)
            c.drawCentredString(cx, img_y + 6 * mm, "Optional: Bild hochladen (sonst Icon)")
            c.setFillColor(colors.black)

        # Beispiele-Zone
        ex_top = img_y - gap
        ex_bottom = inner_bottom

        # Quelle der Beispiele:
        # 1) trainer_v2 item["examples"] (falls später ergänzt)
        # 2) legacy item["examples"]
        # 3) Fallback-Linien
        examples: List[str] = []
        if isinstance(v2_examples, list) and v2_examples:
            examples = [str(x).strip() for x in v2_examples if str(x).strip()]
        elif isinstance(legacy_examples, list) and legacy_examples:
            examples = [str(x).strip() for x in legacy_examples if str(x).strip()]
        if not examples:
            examples = _fallback_examples()

        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.black)
        c.drawString(m + 8 * mm, ex_top - 10, "Beispiele:")

        c.setFont("Helvetica", 11)
        y = ex_top - 26
        min_y = ex_bottom + 10

        for s in examples[: int(pol["max_examples"])]:
            if y < min_y:
                break
            c.drawString(m + 12 * mm, y, f"• {s}")
            y -= 14

        # ---- Schreibblock (große Schreibfläche) ----
        y_write_top = y_content - gap
        y_write = y_write_top - write_block_h

        # Prompt Quelle:
        # 1) trainer_v2 item["note_prompt"] (falls später ergänzt)
        # 2) legacy item["note_prompt"]
        # 3) Default
        v2_prompt = it.get("note_prompt") if isinstance(it, dict) else None
        prompt = (
            str(v2_prompt).strip()
            if isinstance(v2_prompt, str) and str(v2_prompt).strip()
            else str(legacy_prompt).strip()
            if isinstance(legacy_prompt, str) and str(legacy_prompt).strip()
            else "Schreibe 3 eigene Sätze:"
        )

        c.setFont("Helvetica-Bold", 12)
        c.setFillColor(colors.black)
        c.drawString(m, y_write_top - 14, prompt)

        write_area_y = y_write
        write_area_h = max(1.0, write_block_h - 18)

        # Dynamische Linien: lines_per_page steuert Zeilenanzahl (über spacing)
        if lines and writing_lines_per_page > 0:
            dyn_spacing = write_area_h / float(writing_lines_per_page + 1)
            dyn_spacing = max(
                float(pol["writing_line_spacing_min_pt"]),
                min(float(pol["writing_line_spacing_max_pt"]), dyn_spacing),
            )
        else:
            dyn_spacing = 14.0  # fallback

        draw_writing_area(
            c,
            m,
            write_area_y,
            usable_w,
            write_area_h,
            line_spacing=float(dyn_spacing),
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
