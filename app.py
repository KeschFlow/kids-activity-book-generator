# =========================================================
# app.py — E. P. E. Eddie's Print Engine — v5.10.2 FINAL
#
# Includes:
# - Streamlit Cloud / OpenCV fix via runtime.txt (Python 3.11)
# - 24-hour color system (quest_data.py:get_hour_color)
# - OUTRO CTA page with VECTOR QR (ReportLab) -> https://keschflow.github.io/eddies-print-engine/
# - KDP preflight + safe zones + barcode zone + cover facts strip
# - Upload hardening + SQLite fair-use rate limit
# =========================================================

from __future__ import annotations

import io
import os
import gc
import time
import math
import secrets
import hashlib
import sqlite3
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from collections import OrderedDict

import streamlit as st
import cv2
import numpy as np
import stripe
from PIL import Image, ImageDraw, ImageFile

from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import stringWidth

# --- VECTOR QR (print-perfect) ---
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

import image_wash as iw

# --- PIL Hardening ---
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = 25_000_000  # ~25MP

# =========================================================
# HELPERS
# =========================================================
def _qp(name: str) -> str:
    v = st.query_params.get(name, "")
    if isinstance(v, list):
        return v[0] if v else ""
    return v or ""

def _name_genitive(name: str) -> str:
    n = (name or "").strip()
    if not n:
        return "Deins"
    low = n.lower()
    if low.endswith(("s", "ß", "x", "z")):
        return f"{n}'"
    return f"{n}s"

# =========================================================
# RATE LIMITING (SQLite local - Self Healing)
# =========================================================
DB_PATH = "fair_use.db"

def _init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS builds (id INTEGER PRIMARY KEY AUTOINCREMENT, ip TEXT, timestamp REAL)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_builds_ip_ts ON builds(ip, timestamp)")
    cutoff = time.time() - (7 * 24 * 3600)
    c.execute("DELETE FROM builds WHERE timestamp < ?", (cutoff,))
    conn.commit()
    conn.close()

def _get_client_ip() -> str:
    try:
        from streamlit.web.server.websocket_headers import _get_websocket_headers
        headers = _get_websocket_headers()
        if headers:
            xff = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
            if xff:
                return xff.split(",")[0].strip()
    except Exception:
        pass
    try:
        from streamlit.runtime.scriptrunner.script_run_context import get_script_run_ctx
        ctx = get_script_run_ctx()
        if ctx and getattr(ctx, "session_id", None):
            return f"session:{ctx.session_id}"
    except Exception:
        pass
    return "unknown"

def _get_build_count(ip: str, hours: int = 24) -> int:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    cutoff = time.time() - (hours * 3600)
    c.execute("SELECT COUNT(*) FROM builds WHERE ip=? AND timestamp>?", (ip, cutoff))
    row = c.fetchone()
    conn.close()
    return int(row[0] if row else 0)

def _log_build(ip: str):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO builds (ip, timestamp) VALUES (?, ?)", (ip, time.time()))
    conn.commit()
    conn.close()

_init_db()

# =========================================================
# ACCESS & LIMIT LOGIC
# =========================================================
STRIPE_SECRET = st.secrets.get("STRIPE_SECRET_KEY", "")
PAYMENT_LINK = st.secrets.get("STRIPE_PAYMENT_LINK", "https://buy.stripe.com/...")

FREE_LIMIT = 3
COMMUNITY_TOKENS = {"KITA-2026": 50, "SCHULE-X": 50, "THERAPIE-EDDIE": 100}

client_ip = _get_client_ip()
builds_used = _get_build_count(client_ip)

user_limit = FREE_LIMIT
is_supporter = False
access_mode = "Free"

st.session_state.setdefault("community_pass", "")
community_pass = _qp("pass") or st.session_state["community_pass"]

if community_pass in COMMUNITY_TOKENS:
    user_limit = int(COMMUNITY_TOKENS[community_pass])
    access_mode = "Community"

session_id = _qp("session_id")
if session_id and STRIPE_SECRET:
    stripe.api_key = STRIPE_SECRET
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if getattr(session, "status", "") == "complete" and getattr(session, "payment_status", "") == "paid":
            is_supporter = True
            user_limit = 9999
            access_mode = "Supporter"
    except Exception:
        pass

if not STRIPE_SECRET and not community_pass and not session_id:
    access_mode = "Dev Mode"
    user_limit = 9999

builds_left = max(0, user_limit - builds_used)
can_build_limit = builds_left > 0 or is_supporter

# =========================================================
# QUEST SYSTEM ZONES (world-building; optional quest_data.py)
# =========================================================
try:
    import quest_data as qd
except Exception as e:
    qd = None
    _QD_IMPORT_ERROR = str(e)

@dataclass(frozen=True)
class ZoneStub:
    name: str
    icon: str
    quest_type: str
    atmosphere: str

def _zone_stub(hour: int) -> ZoneStub:
    if 6 <= hour <= 10:
        return ZoneStub("Morgen-Start", "🌤️", "Warm-up", "ruhig")
    if 11 <= hour <= 15:
        return ZoneStub("Mittags-Mission", "🌞", "Action", "wach")
    if 16 <= hour <= 20:
        return ZoneStub("Nachmittags-Boost", "🟣", "Abenteuer", "spielerisch")
    return ZoneStub("Abend-Ruhe", "🌙", "Runterfahren", "sanft")

def _get_zone_for_hour(hour: int) -> ZoneStub:
    if qd and hasattr(qd, "get_zone_for_hour"):
        try:
            z = qd.get_zone_for_hour(hour)
            return ZoneStub(
                getattr(z, "name", "Zone"),
                getattr(z, "icon", "🟣"),
                getattr(z, "quest_type", "Quest"),
                getattr(z, "atmosphere", ""),
            )
        except Exception:
            pass
    return _zone_stub(hour)

def _get_hour_color(hour: int) -> Tuple[float, float, float]:
    if qd and hasattr(qd, "get_hour_color"):
        try:
            rgb = qd.get_hour_color(hour)
            if isinstance(rgb, (tuple, list)) and len(rgb) >= 3:
                return float(rgb[0]), float(rgb[1]), float(rgb[2])
        except Exception:
            pass
    t = (hour % 24) / 24.0
    return (0.45 + 0.25 * (1 - t), 0.2 + 0.15 * t, 0.9 - 0.25 * t)

def _fmt_hour(hour: int) -> str:
    if qd and hasattr(qd, "fmt_hour"):
        try:
            return str(qd.fmt_hour(hour))
        except Exception:
            pass
    return f"{int(hour):02d}:00"

# =========================================================
# DYNAMIC QUEST BANK (240 unique quests + fallback)
# =========================================================
def _build_full_quest_bank():
    bank = {}

    m_titles = ["Start-Kraft", "Rüstung anlegen", "Morgen-Fokus", "Wachmacher", "Sonnen-Sucher", "Frühsport", "Augen auf", "Energie-Tank", "Tag-Blick", "Morgen-Scan"]
    m_moves = ["Mache 10 Kniebeugen.", "20 Sekunden Hampelmann.", "Streck dich so groß du kannst.", "Laufe 10 Sekunden auf der Stelle.", "Hüpfe 5x hoch in die Luft.", "Berühre 10x deine Zehenspitzen.", "Kreise deine Arme wie Windmühlen.", "Mache 5 Froschsprünge.", "Balanciere 10 Sekunden auf einem Bein.", "Mache 3 große Ausfallschritte."]

    d_titles = ["Musterjäger", "Adlerauge", "Action-Check", "Spürhund", "Fokus-Meister", "Abenteuer-Blick", "Such-Ninja", "Formen-Ritter", "Tempo-Scan", "Durchblick"]
    d_moves = ["Mache 10 Hampelmänner.", "Hüpfe 10x auf dem rechten Bein.", "Mache 5 Kniebeugen.", "Laufe im Zickzack.", "Dreh dich 5x im Kreis.", "Mache 5 Känguru-Sprünge.", "Balanciere wie ein Flamingo.", "Mache 10 schnelle Schritte auf der Stelle.", "Streck dich und berühre den Boden.", "Mache 3 Sternensprünge."]

    e_titles = ["Nacht-Wache", "Ruhe-Check", "Schatten-Jäger", "Leise Pfoten", "Dämmerungs-Blick", "Abend-Fokus", "Sternen-Scanner", "Fokus-Ninja", "Traum-Pfad", "Nacht-Auge"]
    e_moves = ["Stell dich auf die Zehenspitzen und zähle bis 10.", "Bewege dich 10 Sekunden in Zeitlupe.", "Atme 3x tief ein und aus.", "Setz dich in den Schneidersitz.", "Massiere sanft deine Ohren.", "Mache dich ganz klein wie ein Igel.", "Streck dich langsam nach oben.", "Kreise sanft deine Schultern.", "Schließe die Augen und zähle bis 5.", "Stell dich aufrecht hin wie ein Baum."]

    n_titles = ["Traum-Fänger", "Stille Wacht", "Nacht-Flug", "Schlaf-Ninja", "Mondlicht-Blick", "Traum-Scan", "Sternen-Staub", "Leise Suche", "Ruhe-Mission", "Nacht-Fokus"]
    n_moves = ["Atme tief in den Bauch.", "Lege dich 10 Sekunden ganz still hin.", "Bewege deine Finger wie Sterne.", "Schließe die Augen und atme.", "Sei so leise wie eine Maus.", "Strecke deine Arme sanft aus.", "Mache ein leises 'Schh'-Geräusch.", "Gähne einmal herzhaft.", "Lächle mit geschlossenen Augen.", "Entspanne deine Schultern."]

    proofs = ["Kreise alle Formen ein.", "Male die Sterne gelb aus.", "Setze einen Punkt in jede Form.", "Verbinde die Formen mit einer Linie.", "Zähle laut mit und hake ab.", "Male die Quadrate bunt an.", "Setze einen Haken neben die Dreiecke.", "Male kleine Gesichter in die Formen."]

    for h in range(24):
        hour_str = f"{h:02d}"
        bank[hour_str] = []

        if 6 <= h <= 11:
            t_list, m_list = m_titles, m_moves
        elif 12 <= h <= 17:
            t_list, m_list = d_titles, d_moves
        elif 18 <= h <= 21:
            t_list, m_list = e_titles, e_moves
        else:
            t_list, m_list = n_titles, n_moves

        for i in range(10):
            q_id = f"{hour_str}_{i:02d}"
            if i % 3 == 0:
                thinking = "Finde {tri} Dreiecke, {sq} Quadrate und {st_} Sterne."
            elif i % 3 == 1:
                thinking = "Spüre insgesamt {total} versteckte Formen auf (△, □, ★)."
            else:
                thinking = "Suche: {tri}x Dreieck, {sq}x Quadrat, {st_}x Stern."

            bank[hour_str].append({
                "id": q_id,
                "title": t_list[i % len(t_list)],
                "xp": 10 + i + (h % 5),
                "movement": m_list[i % len(m_list)],
                "thinking": thinking,
                "proof": proofs[(h + i) % len(proofs)]
            })

    reserve = []
    for i in range(24):
        reserve.append({
            "id": f"res_{i:02d}",
            "title": "Sonder-Mission",
            "xp": 20,
            "movement": "Mache 3x tief Ooommm.",
            "thinking": "Finde {total} versteckte Symbole.",
            "proof": "Setze einen dicken Haken!"
        })

    return bank, reserve

QUEST_BANK, QUEST_RESERVE = _build_full_quest_bank()

# =========================================================
# UNIQUE SCHEDULE GENERATOR
# =========================================================
def build_book_schedule(seed: int, start_hour: int, count: int) -> dict:
    rng = np.random.default_rng(seed)
    used_ids = set()
    schedule = {}

    for i in range(count):
        hour = (start_hour + i) % 24
        hour_str = f"{hour:02d}"
        candidates = [q for q in QUEST_BANK.get(hour_str, []) if q["id"] not in used_ids]

        if not candidates:
            candidates = [q for q in QUEST_RESERVE if q["id"] not in used_ids]

        if not candidates:
            candidates = QUEST_RESERVE

        idx = rng.integers(0, len(candidates))
        picked = candidates[idx]
        used_ids.add(picked["id"])
        schedule[hour] = picked

    return schedule

@dataclass
class Mission:
    title: str
    xp: int
    movement: str
    thinking: str
    proof: str

# =========================================================
# CONFIG
# =========================================================
APP_TITLE = "E. P. E. Eddie's Print Engine"
APP_ICON = "🐶"

EDDIE_PURPLE = "#7c3aed"
DPI = 300
TRIM_IN = 8.5
TRIM = TRIM_IN * inch
BLEED = 0.125 * inch
SAFE_INTERIOR = 0.375 * inch

INK_BLACK = colors.Color(0, 0, 0)
INK_GRAY_70 = colors.Color(0.30, 0.30, 0.30)
DEBUG_BLEED_COLOR = colors.Color(0.85, 0.20, 0.20)
DEBUG_SAFE_COLOR = colors.Color(0.15, 0.55, 0.15)

PAPER_FACTORS = {
    "Schwarzweiß – Weiß": 0.002252,
    "Schwarzweiß – Creme": 0.0025,
    "Farbe – Weiß (Standard)": 0.002252
}
KDP_PAGES_FIXED = 26
SPINE_TEXT_MIN_PAGES = 79

MAX_SKETCH_CACHE = 256
MAX_WASH_CACHE = 64

BUILD_TAG = "v5.10.2-final"

# QR target (printed)
QR_URL = "https://keschflow.github.io/eddies-print-engine/"
QR_TEXT = "keschflow.github.io/eddies-print-engine"

# =========================================================
# CORE & PAGE GEOMETRY
# =========================================================
def _new_build_nonce() -> str:
    return f"{time.time_ns():x}-{secrets.token_hex(16)}"

def _imprint_nonce(c: canvas.Canvas, build_nonce: str) -> None:
    try:
        c.saveState()
        c.setFillColor(colors.white)
        c.setFont("Helvetica", 1)
        c.drawString(-1000, -1000, f"nonce:{build_nonce}")
        c.restoreState()
    except Exception:
        pass

@dataclass(frozen=True)
class PageBox:
    trim_w: float
    trim_h: float
    bleed: float
    full_w: float
    full_h: float

def page_box(trim_w: float, trim_h: float, kdp_bleed: bool) -> PageBox:
    b = BLEED if kdp_bleed else 0.0
    return PageBox(trim_w, trim_h, b, trim_w + 2.0 * b, trim_h + 2.0 * b)

def _kdp_inside_gutter_in(pages: int) -> float:
    if pages <= 150: return 0.375
    if pages <= 300: return 0.500
    if pages <= 500: return 0.625
    if pages <= 700: return 0.750
    return 0.875

def safe_margins_for_page(pages: int, kdp: bool, page_index_0: int, pb: PageBox) -> Tuple[float, float, float]:
    if not kdp:
        return SAFE_INTERIOR, SAFE_INTERIOR, SAFE_INTERIOR
    out, stb = pb.bleed + (0.375 * inch), pb.bleed + (0.375 * inch)
    gut = pb.bleed + (_kdp_inside_gutter_in(pages) * inch)
    is_odd = ((page_index_0 + 1) % 2 == 1)
    return (gut if is_odd else out), (out if is_odd else gut), stb

def _draw_kdp_debug_guides(c: canvas.Canvas, pb: PageBox, safe_l: float, safe_r: float, safe_tb: float):
    c.saveState()
    c.setLineWidth(0.5)
    c.setDash(3, 3)
    if pb.bleed > 0:
        c.setStrokeColor(DEBUG_BLEED_COLOR)
        c.rect(pb.bleed, pb.bleed, pb.full_w - 2 * pb.bleed, pb.full_h - 2 * pb.bleed, stroke=1, fill=0)
    c.setStrokeColor(DEBUG_SAFE_COLOR)
    c.rect(safe_l, safe_tb, pb.full_w - safe_l - safe_r, pb.full_h - 2 * safe_tb, stroke=1, fill=0)
    c.setDash()
    c.restoreState()

# =========================================================
# FONTS & TEXT TOOLS
# =========================================================
def _try_register_fonts() -> Dict[str, str]:
    n = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    b = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if os.path.exists(n):
        try:
            pdfmetrics.registerFont(TTFont("EDDIES_FONT", n))
        except Exception:
            pass
    if os.path.exists(b):
        try:
            pdfmetrics.registerFont(TTFont("EDDIES_FONT_BOLD", b))
        except Exception:
            pass
    return {
        "normal": "EDDIES_FONT" if "EDDIES_FONT" in pdfmetrics.getRegisteredFontNames() else "Helvetica",
        "bold": "EDDIES_FONT_BOLD" if "EDDIES_FONT_BOLD" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold",
    }

FONTS = _try_register_fonts()

def _set_font(c: canvas.Canvas, bold: bool, size: int) -> float:
    c.setFont(FONTS["bold"] if bold else FONTS["normal"], size)
    return size * 1.22

def _wrap_text_hard(text: str, font: str, size: int, max_w: float) -> List[str]:
    text = (text or "").strip()
    if not text:
        return [""]
    lines, cur = [], ""

    def fits(s: str) -> bool:
        return stringWidth(s, font, size) <= max_w

    for w in text.split():
        trial = (cur + " " + w).strip()
        if cur and fits(trial):
            cur = trial
        elif not cur and fits(w):
            cur = w
        else:
            if cur:
                lines.append(cur)
            if not fits(w):
                chunk = ""
                for ch in w:
                    if fits(chunk + ch):
                        chunk += ch
                    else:
                        if chunk:
                            lines.append(chunk)
                        chunk = ch
                cur = chunk
            else:
                cur = w
    if cur:
        lines.append(cur)
    return lines

def _fit_lines(lines: List[str], max_lines: int) -> List[str]:
    if len(lines) <= max_lines:
        return lines
    out = lines[:max_lines]
    out[-1] = (out[-1].rstrip()[:-3].rstrip() if len(out[-1]) > 3 else out[-1]) + "…"
    return out

def _kid_short(s: str, max_words: int = 4) -> str:
    s = (s or "").strip().replace("•", " ").replace("→", " ").replace("-", " ")
    return " ".join([w for w in s.split() if w and len(w) > 1][:max_words])

def _autoscale_mission_text(mission, w: float, x0: float, pad_x: float, max_card_h: float) -> Dict[str, Any]:
    b_t, b_b, g_t, g_s = 0.36 * inch, 0.40 * inch, 0.10 * inch, 0.06 * inch
    mw_m, mw_t = (x0 + w - pad_x) - (x0 + 1.05 * inch), (x0 + w - pad_x) - (x0 + 0.90 * inch)

    def compute(ts, bs, ls):
        ml = _wrap_text_hard(getattr(mission, "movement", ""), FONTS["normal"], bs, mw_m)
        tl = _wrap_text_hard(getattr(mission, "thinking", ""), FONTS["normal"], bs, mw_t)
        need = b_t + (ts * 1.22) + g_t + (ls * 1.22 * 2) + ((len(ml) + len(tl)) * (bs * 1.28)) + g_s + b_b
        return {"ts": ts, "bs": bs, "ls": ls, "tl": ts * 1.22, "bl": bs * 1.28, "ll": ls * 1.22, "ml": ml, "tl_lines": tl, "needed": need}

    ts, bs, ls = 13, 10, 10
    sc = compute(ts, bs, ls)
    while sc["needed"] > max_card_h and (ts > 10 or bs > 8 or ls > 8):
        if ts > 10: ts -= 1
        if bs > 8: bs -= 1
        if ls > 8: ls -= 1
        sc = compute(ts, bs, ls)

    if sc["needed"] > max_card_h:
        rem = max_card_h - (b_t + sc["tl"] + g_t + (sc["ll"] * 2) + g_s + b_b)
        mb = max(2, int(rem // sc["bl"]))
        sc["ml"] = _fit_lines(sc["ml"], max(1, mb // 2))
        sc["tl_lines"] = _fit_lines(sc["tl_lines"], max(1, mb - max(1, mb // 2)))
    return sc

def _stable_seed(s: str) -> int:
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:8], "big")

def _fmt_in(x: float) -> str:
    return f"{x:.4f} in"

def _fmt_pt(x: float) -> str:
    return f"{x:.2f} pt"

def _fmt_xy_in(x_pt: float, y_pt: float) -> str:
    return f"({_fmt_in(x_pt / inch)}, {_fmt_in(y_pt / inch)})"

def _fmt_xy_pt(x_pt: float, y_pt: float) -> str:
    return f"({_fmt_pt(x_pt)}, {_fmt_pt(y_pt)})"

def _draw_cover_preflight_facts_strip(
    c: canvas.Canvas,
    *,
    cw: float,
    ch: float,
    trim: float,
    bleed: float,
    spine_w: float,
    build_nonce: str,
    paper: str,
    back_x: float,
    spine_x: float,
    front_x: float,
    trim_y: float,
    barcode_x: float,
    barcode_y: float,
    barcode_w: float,
    barcode_h: float,
):
    pad = 0.20 * inch
    x0 = back_x + pad
    strip_w = min(trim - 2 * pad, 3.55 * inch)
    strip_h = 1.55 * inch
    y_bottom = (trim_y + trim - strip_h - pad)

    c.saveState()
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.HexColor("#111111"))
    c.setLineWidth(0.8)
    c.roundRect(x0, y_bottom, strip_w, strip_h, 8, stroke=1, fill=1)

    c.setFillColor(colors.HexColor("#111111"))
    _set_font(c, True, 10)
    c.drawString(x0 + 0.12 * inch, y_bottom + strip_h - 0.22 * inch, "COVER PREFLIGHT FACTS")

    _set_font(c, False, 8)
    c.setFillColor(colors.HexColor("#444444"))
    c.drawString(
        x0 + 0.12 * inch,
        y_bottom + strip_h - 0.40 * inch,
        f"paper={paper} | nonce={str(build_nonce)[:16]}…"
    )

    _set_font(c, False, 7)
    c.setFillColor(colors.HexColor("#111111"))

    line = 0.14 * inch
    yy = y_bottom + strip_h - 0.60 * inch

    def row(label: str, v_in: str, v_pt: str):
        nonlocal yy
        c.setFillColor(colors.HexColor("#111111"))
        c.drawString(x0 + 0.12 * inch, yy, label)
        c.setFillColor(colors.HexColor("#333333"))
        c.drawRightString(x0 + strip_w - 0.12 * inch, yy, f"{v_in} | {v_pt}")
        yy -= line

    row("CANVAS (W×H)", f"{_fmt_in(cw / inch)}×{_fmt_in(ch / inch)}", f"{_fmt_pt(cw)}×{_fmt_pt(ch)}")
    row("TRIM (W×H)", f"{_fmt_in(trim / inch)}×{_fmt_in(trim / inch)}", f"{_fmt_pt(trim)}×{_fmt_pt(trim)}")
    row("BLEED", _fmt_in(bleed / inch), _fmt_pt(bleed))
    row("SPINE W", _fmt_in(spine_w / inch), _fmt_pt(spine_w))

    row("BACK X0", _fmt_in(back_x / inch), _fmt_pt(back_x))
    row("SPINE X0", _fmt_in(spine_x / inch), _fmt_pt(spine_x))
    row("FRONT X0", _fmt_in(front_x / inch), _fmt_pt(front_x))

    row("BARCODE XY", _fmt_xy_in(barcode_x, barcode_y), _fmt_xy_pt(barcode_x, barcode_y))
    row("BARCODE WH", f"{_fmt_in(barcode_w / inch)}×{_fmt_in(barcode_h / inch)}", f"{_fmt_pt(barcode_w)}×{_fmt_pt(barcode_h)}")

    c.setFillColor(colors.HexColor("#666666"))
    _set_font(c, False, 6)
    c.drawString(x0 + 0.12 * inch, y_bottom + 0.10 * inch, "All values are absolute PDF coords (origin bottom-left).")
    c.restoreState()

def _draw_preflight_facts_page(c: canvas.Canvas, pb: PageBox, total_pages: int, kdp: bool, paper: str, build_nonce: str) -> None:
    trim_w_in, trim_h_in = pb.trim_w / inch, pb.trim_h / inch
    bleed_in = (pb.bleed / inch)
    full_w_in, full_h_in = pb.full_w / inch, pb.full_h / inch

    safe_l_odd, safe_r_odd, safe_tb_odd = safe_margins_for_page(total_pages, kdp, 0, pb)
    safe_l_even, safe_r_even, safe_tb_even = safe_margins_for_page(total_pages, kdp, 1, pb)

    safe_w_odd = pb.full_w - (safe_l_odd + safe_r_odd)
    safe_h_odd = pb.full_h - (2 * safe_tb_odd)
    safe_w_even = pb.full_w - (safe_l_even + safe_r_even)
    safe_h_even = pb.full_h - (2 * safe_tb_even)

    def _as_in(x_pt: float) -> float:
        return x_pt / inch

    factor = float(PAPER_FACTORS.get(paper, 0.002252))
    spine_in = max(float(total_pages) * factor, 0.001)

    c.saveState()
    c.setFillColor(colors.white)
    c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)
    c.setFillColor(INK_BLACK)
    _set_font(c, True, 24)
    c.drawCentredString(pb.full_w / 2, pb.full_h - 1.0 * inch, "KDP PREFLIGHT — NO FEELINGS, JUST FACTS")
    _set_font(c, False, 11)
    c.setFillColor(INK_GRAY_70)
    c.drawCentredString(pb.full_w / 2, pb.full_h - 1.28 * inch, f"Pages fixed: {total_pages}  |  Paper: {paper}  |  nonce: {build_nonce[:16]}…")

    left, top, line = 0.75 * inch, pb.full_h - 1.75 * inch, 0.24 * inch
    c.setFillColor(INK_BLACK)
    _set_font(c, True, 12)
    c.drawString(left, top, "PAGE GEOMETRY")
    _set_font(c, False, 11)

    y = top - 0.35 * inch
    rows = [
        ("TRIM (W x H)", f"{_fmt_in(trim_w_in)} × {_fmt_in(trim_h_in)}", f"{_fmt_pt(pb.trim_w)} × {_fmt_pt(pb.trim_h)}"),
        ("BLEED", _fmt_in(bleed_in), _fmt_pt(pb.bleed)),
        ("FULL PAGE (W x H)", f"{_fmt_in(full_w_in)} × {_fmt_in(full_h_in)}", f"{_fmt_pt(pb.full_w)} × {_fmt_pt(pb.full_h)}"),
        ("SAFE W (odd/even)", f"{_fmt_in(_as_in(safe_w_odd))} / {_fmt_in(_as_in(safe_w_even))}", f"{_fmt_pt(safe_w_odd)} / {_fmt_pt(safe_w_even)}"),
        ("SAFE H (odd/even)", f"{_fmt_in(_as_in(safe_h_odd))} / {_fmt_in(_as_in(safe_h_even))}", f"{_fmt_pt(safe_h_odd)} / {_fmt_pt(safe_h_even)}"),
        ("SAFE TB (odd/even)", f"{_fmt_in(_as_in(safe_tb_odd))} / {_fmt_in(_as_in(safe_tb_even))}", f"{_fmt_pt(safe_tb_odd)} / {_fmt_pt(safe_tb_even)}"),
        ("SAFE L (odd/even)", f"{_fmt_in(_as_in(safe_l_odd))} / {_fmt_in(_as_in(safe_l_even))}", f"{_fmt_pt(safe_l_odd)} / {_fmt_pt(safe_l_even)}"),
        ("SAFE R (odd/even)", f"{_fmt_in(_as_in(safe_r_odd))} / {_fmt_in(_as_in(safe_r_even))}", f"{_fmt_pt(safe_r_odd)} / {_fmt_pt(safe_r_even)}"),
        ("GUTTER (inside margin)", _fmt_in(_kdp_inside_gutter_in(total_pages)), _fmt_pt(_kdp_inside_gutter_in(total_pages) * inch)),
        ("SPINE WIDTH (cover)", _fmt_in(spine_in), _fmt_pt(spine_in * inch)),
    ]

    col1, col2, col3 = left, left + 2.6 * inch, left + 5.3 * inch
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(1)
    c.roundRect(left - 0.2 * inch, y - (len(rows) * line) - 0.25 * inch,
                pb.full_w - 2 * left + 0.4 * inch, (len(rows) * line) + 0.55 * inch, 10, stroke=1, fill=0)

    _set_font(c, True, 10)
    c.drawString(col1, y + 0.10 * inch, "Metric")
    c.drawString(col2, y + 0.10 * inch, "Inches")
    c.drawString(col3, y + 0.10 * inch, "Points (pt)")
    c.line(left - 0.15 * inch, y + 0.06 * inch, pb.full_w - left + 0.15 * inch, y + 0.06 * inch)

    _set_font(c, False, 10)
    yy = y - 0.12 * inch
    for label, inches_val, pt_val in rows:
        c.drawString(col1, yy, str(label))
        c.drawString(col2, yy, str(inches_val))
        c.drawString(col3, yy, str(pt_val))
        yy -= line

    _set_font(c, False, 9)
    c.setFillColor(INK_GRAY_70)
    c.drawString(left, 0.85 * inch, "Tip: enable 'Preflight Debug' too — green box = safe, red = trim/bleed.")
    c.restoreState()

# =========================================================
# ICONS, SHAPES & BRANDING
# =========================================================
def _draw_eddie(c: canvas.Canvas, cx: float, cy: float, r: float, style: str = "tongue"):
    c.saveState()
    if style == "tongue":
        tw, th = r * 0.55, r * 0.70
        c.setFillColor(colors.HexColor(EDDIE_PURPLE))
        c.setStrokeColor(INK_BLACK)
        c.setLineWidth(max(1.2, r * 0.06))
        c.roundRect(cx - tw / 2, cy - th / 2, tw, th, r * 0.18, stroke=1, fill=1)
        c.setLineWidth(max(0.8, r * 0.03))
        c.line(cx, cy - th / 2 + th * 0.15, cx, cy - th / 2 + th * 0.45)
    else:
        c.setStrokeColor(INK_BLACK)
        c.setFillColor(colors.white)
        c.setLineWidth(max(1.2, r * 0.06))
        c.circle(cx, cy, r, stroke=1, fill=1)
        c.line(cx - r * 0.55, cy + r * 0.55, cx - r * 0.15, cy + r * 0.95)
        c.line(cx - r * 0.15, cy + r * 0.95, cx - r * 0.05, cy + r * 0.45)
        c.line(cx + r * 0.55, cy + r * 0.55, cx + r * 0.15, cy + r * 0.95)
        c.line(cx + r * 0.15, cy + r * 0.95, cx + r * 0.05, cy + r * 0.45)
        c.setFillColor(colors.HexColor(EDDIE_PURPLE))
        c.roundRect(cx - r * 0.12, cy - r * 0.45, r * 0.24, r * 0.28, r * 0.10, stroke=0, fill=1)
    c.restoreState()

def _icon_run(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(max(1.2, size * 0.10))
    c.circle(x + size * 0.30, y + size * 0.72, size * 0.12, stroke=1, fill=0)
    c.line(x + size * 0.30, y + size * 0.60, x + size * 0.30, y + size * 0.30)
    c.line(x + size * 0.30, y + size * 0.50, x + size * 0.55, y + size * 0.40)
    c.line(x + size * 0.30, y + size * 0.50, x + size * 0.05, y + size * 0.40)
    c.line(x + size * 0.30, y + size * 0.30, x + size * 0.15, y + size * 0.10)
    c.line(x + size * 0.30, y + size * 0.30, x + size * 0.50, y + size * 0.12)
    c.restoreState()

def _icon_brain(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(max(1.2, size * 0.08))
    c.roundRect(x + size * 0.15, y + size * 0.20, size * 0.70, size * 0.60, size * 0.18, stroke=1, fill=0)
    c.line(x + size * 0.50, y + size * 0.20, x + size * 0.50, y + size * 0.80)
    c.circle(x + size * 0.35, y + size * 0.50, size * 0.05, stroke=1, fill=1)
    c.circle(x + size * 0.65, y + size * 0.50, size * 0.05, stroke=1, fill=1)
    c.restoreState()

def _icon_check(c: canvas.Canvas, x: float, y: float, size: float):
    c.saveState()
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(max(1.2, size * 0.08))
    c.rect(x + size * 0.15, y + size * 0.20, size * 0.70, size * 0.60, stroke=1, fill=0)
    c.line(x + size * 0.30, y + size * 0.45, x + size * 0.45, y + size * 0.30)
    c.line(x + size * 0.45, y + size * 0.30, x + size * 0.70, y + size * 0.65)
    c.restoreState()

@dataclass
class ShapeSpec:
    kind: str
    cx: float
    cy: float
    size: float
    rot: float

def _generate_shapes(pb: PageBox, sl: float, sr: float, stb: float, pre_reader: bool, seed: int) -> List[ShapeSpec]:
    rng = np.random.default_rng(seed)
    header_h = 0.75 * inch
    card_h = (2.45 * inch) if pre_reader else (2.85 * inch)
    pad = 0.40 * inch
    min_x, max_x = sl + pad, pb.full_w - sr - pad
    min_y, max_y = stb + card_h + pad, pb.full_h - stb - header_h - pad
    if max_x <= min_x or max_y <= min_y:
        return []

    shapes = []
    for _ in range(int(rng.integers(3, 8))):
        shapes.append(ShapeSpec(
            kind=str(rng.choice(["triangle", "square", "star"])),
            cx=float(rng.uniform(min_x, max_x)),
            cy=float(rng.uniform(min_y, max_y)),
            size=float(rng.uniform(0.28, 0.58)) * inch,
            rot=float(rng.uniform(0, 360))
        ))
    return shapes

def _draw_shapes(c: canvas.Canvas, shapes: List[ShapeSpec]):
    if not shapes:
        return
    c.saveState()
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(2.2)
    c.setFillColor(colors.white)
    for s in shapes:
        c.saveState()
        c.translate(s.cx, s.cy)
        c.rotate(s.rot)
        if s.kind == "triangle":
            p = c.beginPath()
            p.moveTo(0, s.size / 2)
            p.lineTo(-s.size / 2, -s.size / 2)
            p.lineTo(s.size / 2, -s.size / 2)
            p.close()
            c.drawPath(p, fill=1, stroke=1)
        elif s.kind == "square":
            c.rect(-s.size / 2, -s.size / 2, s.size, s.size, fill=1, stroke=1)
        else:
            p = c.beginPath()
            r_out, r_in = s.size / 2, (s.size / 2) / 2.5
            for i in range(10):
                r = r_out if i % 2 == 0 else r_in
                theta = i * (math.pi / 5) - (math.pi / 2)
                x, y = r * math.cos(theta), r * math.sin(theta)
                if i == 0:
                    p.moveTo(x, y)
                else:
                    p.lineTo(x, y)
            p.close()
            c.drawPath(p, fill=1, stroke=1)
        c.restoreState()
    c.restoreState()

# =========================================================
# CACHES & WASHING
# =========================================================
MAX_UPLOAD_BYTES = 12 * 1024 * 1024  # 12MB pro Datei

def _get_lru(name: str, max_items: int) -> "OrderedDict":
    od = st.session_state.get(name)
    if not isinstance(od, OrderedDict):
        od = OrderedDict()
        st.session_state[name] = od
    st.session_state[f"{name}__max"] = max_items
    return od

def _lru_put(od: "OrderedDict", key, value, max_items: int):
    od[key] = value
    od.move_to_end(key)
    while len(od) > max_items:
        od.popitem(last=False)

def _read_upload_bytes(up) -> bytes:
    try:
        b = up.getvalue()
    except Exception:
        try:
            b = bytes(up.read())
        except Exception:
            b = b""
    if len(b) > MAX_UPLOAD_BYTES:
        raise ValueError(f"Upload zu groß (max 12MB pro Bild): {getattr(up, 'name', 'Unbekannt')}")
    return b

def _wash_bytes(raw: bytes) -> bytes:
    if not raw:
        raise ValueError("empty upload")
    if hasattr(iw, "wash_image_bytes"):
        return bytes(iw.wash_image_bytes(raw))
    if hasattr(iw, "wash_bytes"):
        return bytes(iw.wash_bytes(raw))
    raise RuntimeError("image_wash logic missing")

def _wash_upload_to_bytes(up) -> bytes:
    raw = _read_upload_bytes(up)
    h = hashlib.sha256(raw).hexdigest()
    wc = _get_lru("wash_cache", MAX_WASH_CACHE)
    if h in wc:
        wc.move_to_end(h)
        return wc[h]
    w = _wash_bytes(raw)
    _lru_put(wc, h, w, MAX_WASH_CACHE)
    return w

def _sketch_compute(img_bytes: bytes, target_w: int, target_h: int) -> bytes:
    arr = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if arr is None:
        raise RuntimeError("OpenCV decode failed")

    h_arr, w_arr = arr.shape[:2]
    if (w_arr * h_arr) > 25_000_000:
        raise ValueError("Bildauflösung zu groß (max ~25MP).")

    gray = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(255 - gray, (21, 21), 0)
    sketch = cv2.divide(gray, np.clip(255 - blurred, 1, 255), scale=256.0)
    norm = cv2.normalize(sketch, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)

    pil = Image.fromarray(norm).convert("L")
    sw, sh = pil.size
    s = min(sw, sh)
    pil = pil.crop(((sw - s) // 2, (sh - s) // 2, (sw + s) // 2, (sh + s) // 2)).resize((target_w, target_h), Image.LANCZOS)
    out = io.BytesIO()
    pil.point(lambda p: 255 if p > 200 else 0).convert("1").save(out, format="PNG", optimize=True)
    outv = out.getvalue()
    del arr, gray, blurred, sketch, norm, pil
    gc.collect()
    return outv

def _get_sketch_cached(img_bytes: bytes, target_w: int, target_h: int) -> bytes:
    cache = _get_lru("sketch_cache", MAX_SKETCH_CACHE)
    key = (hashlib.sha256(img_bytes).hexdigest(), int(target_w), int(target_h))
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    out = _sketch_compute(img_bytes, target_w, target_h)
    _lru_put(cache, key, out, MAX_SKETCH_CACHE)
    return out

# =========================================================
# OVERLAY (QUEST CARD)
# =========================================================
def _draw_quest_overlay(c, pb, sl, sr, stb, hour, mission: Mission, debug, pre_reader):
    hh = 0.75 * inch
    x0 = sl
    w = max(1.0, pb.full_w - sr - x0)
    ytb = pb.full_h - stb - hh
    zone = _get_zone_for_hour(hour)
    z_rgb = _get_hour_color(hour)

    c.saveState()
    c.setFillColor(colors.Color(z_rgb[0], z_rgb[1], z_rgb[2]))
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(1)
    c.rect(x0, ytb, w, hh, fill=1, stroke=1)

    c.setFillColor(colors.white if sum(z_rgb[:3]) < 1.5 else INK_BLACK)
    _set_font(c, True, 14)
    c.drawString(x0 + 0.18 * inch, ytb + hh - 0.5 * inch, f"{_fmt_hour(hour)}  {zone.icon}  {zone.name}")
    _set_font(c, False, 10)
    c.drawString(x0 + 0.18 * inch, ytb + 0.18 * inch, f"{zone.quest_type} • {zone.atmosphere}")

    cy = stb
    max_ch = ytb - cy - 0.15 * inch
    if pre_reader:
        ch, sc = min(max_ch, 2.45 * inch), None
    else:
        sc = _autoscale_mission_text(mission, w, x0, 0.18 * inch, max_ch)
        ch = min(max_ch, max(1.85 * inch, sc["needed"]))

    c.setFillColor(colors.white)
    c.setStrokeColor(INK_BLACK)
    c.rect(x0, cy, w, ch, fill=1, stroke=1)
    yc = cy + ch - 0.18 * inch
    c.setFillColor(INK_BLACK)

    if pre_reader:
        _set_font(c, True, 14)
        c.drawString(x0 + 0.18 * inch, yc - 10, _kid_short(mission.title, 3) or "MISSION")
        _set_font(c, True, 11)
        c.drawRightString(x0 + w - 0.18 * inch, yc - 10, f"+{int(mission.xp)} XP")
        sy = yc - 0.50 * inch
        _icon_run(c, x0 + 0.18 * inch, sy - 0.068 * inch, 0.34 * inch)
        _set_font(c, False, 12)
        c.drawString(x0 + 0.45 * inch, sy, _kid_short(mission.movement, 3) or "Bewegen!")
        _icon_brain(c, x0 + 0.18 * inch, sy - 0.46 * inch - 0.068 * inch, 0.34 * inch)
        _set_font(c, False, 12)
        c.drawString(x0 + 0.45 * inch, sy - 0.46 * inch, mission.thinking)
        _icon_check(c, x0 + 0.18 * inch, sy - 0.92 * inch - 0.068 * inch, 0.34 * inch)
        _set_font(c, False, 12)
        c.drawString(x0 + 0.45 * inch, sy - 0.92 * inch, _kid_short(mission.proof, 4) or "Haken!")
        _set_font(c, False, 8)
        c.setFillColor(INK_GRAY_70)
        c.drawString(x0 + 0.18 * inch, cy + 0.12 * inch, "Eltern: kurz vorlesen – Kind macht’s nach.")
    else:
        _set_font(c, True, sc["ts"])
        c.drawString(x0 + 0.18 * inch, yc - sc["tl"] + 2, f"MISSION: {mission.title}")
        _set_font(c, True, max(8, sc["ts"] - 2))
        c.drawRightString(x0 + w - 0.18 * inch, yc - sc["tl"] + 2, f"+{int(mission.xp)} XP")

        yt = yc - sc["tl"] - 0.10 * inch
        _set_font(c, True, sc["ls"])
        c.drawString(x0 + 0.18 * inch, yt - sc["ll"] + 2, "BEWEGUNG:")
        _set_font(c, False, sc["bs"])
        yy = yt - sc["ll"] + 2
        for l in sc["ml"]:
            c.drawString(x0 + 1.05 * inch, yy, l)
            yy -= sc["bl"]

        yt = yy - 0.06 * inch
        _set_font(c, True, sc["ls"])
        c.drawString(x0 + 0.18 * inch, yt - sc["ll"] + 2, "SUCHEN:")
        _set_font(c, False, sc["bs"])
        yy = yt - sc["ll"] + 2
        for l in sc["tl_lines"]:
            c.drawString(x0 + 0.90 * inch, yy, l)
            yy -= sc["bl"]

        c.rect(x0 + 0.18 * inch, cy + 0.18 * inch, 0.20 * inch, 0.20 * inch, fill=0, stroke=1)
        _set_font(c, True, sc["ls"])
        c.drawString(x0 + 0.43 * inch, cy + 0.20 * inch, "PROOF:")
        _set_font(c, False, sc["bs"])
        if mission.proof:
            c.drawString(
                x0 + 1.03 * inch,
                cy + 0.20 * inch,
                _fit_lines(_wrap_text_hard(mission.proof, FONTS["normal"], sc["bs"], w - 1.5 * inch), 1)[0]
            )

    if debug:
        _draw_kdp_debug_guides(c, pb, sl, sr, stb)
    c.restoreState()

# =========================================================
# COVER COLLAGE
# =========================================================
def _cover_collage_png(uploads, size_px: int, seed: int) -> Optional[bytes]:
    files = list(uploads or [])
    if not files:
        return None
    rng = np.random.default_rng(seed & 0xFFFFFFFF)
    idx = np.arange(len(files))
    rng.shuffle(idx)
    files = [files[i] for i in idx[: min(4, len(files))]]
    gap = max(10, size_px // 120)
    cell = (size_px - gap * 3) // 2
    canvas_img = Image.new("RGB", (size_px, size_px), (255, 255, 255))
    k = 0
    for r in range(2):
        for c_ in range(2):
            if k >= len(files):
                break
            try:
                sk = _sketch_compute(_wash_upload_to_bytes(files[k]), cell, cell)
                tile = Image.open(io.BytesIO(sk)).convert("RGB")
            except Exception:
                tile = Image.new("RGB", (cell, cell), (255, 255, 255))
            canvas_img.paste(tile, (gap + c_ * (cell + gap), gap + r * (cell + gap)))
            k += 1
            del tile
            gc.collect()
    ImageDraw.Draw(canvas_img).rectangle([0, 0, size_px - 1, size_px - 1], outline=(0, 0, 0), width=max(2, size_px // 250))
    out = io.BytesIO()
    canvas_img.save(out, format="PNG", optimize=True)
    return out.getvalue()

# =========================================================
# BUILDERS
# =========================================================
def build_interior(name, uploads, kdp, debug, preflight, paper, eddie, style, pre_reader, build_nonce) -> bytes:
    if not uploads:
        raise ValueError("Keine Uploads vorhanden. Bitte lade Fotos hoch.")

    MAX_UPLOADS = 48
    if len(uploads) > MAX_UPLOADS:
        raise ValueError(f"Zu viele Uploads (max {MAX_UPLOADS}).")

    MAX_TOTAL_UPLOAD_BYTES = 160 * 1024 * 1024
    total_bytes = 0
    for up in uploads:
        try:
            total_bytes += len(up.getbuffer())
        except Exception:
            try:
                total_bytes += len(_read_upload_bytes(up))
            except ValueError:
                pass
        if total_bytes > MAX_TOTAL_UPLOAD_BYTES:
            raise ValueError(f"Uploads insgesamt zu groß (max {MAX_TOTAL_UPLOAD_BYTES // (1024*1024)}MB). Bitte weniger/kleinere Bilder.")

    total = KDP_PAGES_FIXED
    MISSION_PAGES = 24

    pb = page_box(TRIM, TRIM, kdp_bleed=kdp)
    final = (list(uploads) * (MISSION_PAGES // len(uploads) + 1))[:MISSION_PAGES]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pb.full_w, pb.full_h))
    c.setTitle(f"{APP_TITLE} — Interior")
    c.setAuthor("Eddies World")
    c.setSubject(f"nonce={build_nonce}")

    schedule = build_book_schedule(_stable_seed(build_nonce), start_hour=6, count=MISSION_PAGES)

    seed_base = _stable_seed(name)
    nonce_seed = _stable_seed(build_nonce)
    current_page_idx = 0

    # INTRO
    sl, sr, stb = safe_margins_for_page(total, kdp, current_page_idx, pb)

    if preflight:
        _draw_preflight_facts_page(
            c=c,
            pb=pb,
            total_pages=total,
            kdp=bool(kdp),
            paper=str(paper),
            build_nonce=str(build_nonce),
        )
        if debug:
            _draw_kdp_debug_guides(c, pb, sl, sr, stb)
        _imprint_nonce(c, build_nonce)
        c.showPage()
        current_page_idx += 1
    else:
        c.setFillColor(colors.white)
        c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)
        gen = _name_genitive(name)
        c.setFillColor(INK_BLACK)
        _set_font(c, True, 34)
        c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 1.90 * inch, f"{gen} Abenteuerbuch")
        _set_font(c, False, 14)
        c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 2.35 * inch, "Erstellt mit")
        _set_font(c, True, 18)
        c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 2.70 * inch, "E. P. E.")
        _set_font(c, False, 14)
        c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 3.00 * inch, "Eddie's Print Engine")
        _draw_eddie(c, pb.full_w / 2, pb.full_h / 2, 1.20 * inch, style=style)
        c.setFillColor(INK_GRAY_70)
        _set_font(c, False, 13)
        c.drawCentredString(pb.full_w / 2, stb + 0.75 * inch, "24 Stunden • 24 Mini-Quests • Haken setzen")
        if debug:
            _draw_kdp_debug_guides(c, pb, sl, sr, stb)
        _imprint_nonce(c, build_nonce)
        c.showPage()
        current_page_idx += 1

    # CONTENT
    for i, up in enumerate(final):
        sl, sr, stb = safe_margins_for_page(total, kdp, current_page_idx, pb)

        img_png = _get_sketch_cached(
            _wash_upload_to_bytes(up),
            int(pb.full_w * DPI / 72),
            int(pb.full_h * DPI / 72),
        )
        c.drawImage(
            ImageReader(io.BytesIO(img_png)),
            0, 0, pb.full_w, pb.full_h
        )

        hour = (6 + i) % 24
        seed = int(seed_base ^ nonce_seed ^ (i << 1) ^ hour) & 0xFFFFFFFF
        shapes = _generate_shapes(pb, sl, sr, stb, bool(pre_reader), seed)
        _draw_shapes(c, shapes)

        tri = sum(1 for s in shapes if s.kind == "triangle")
        sq = sum(1 for s in shapes if s.kind == "square")
        st_ = sum(1 for s in shapes if s.kind == "star")
        t_shapes = len(shapes)

        # === v5.11 PRODUCTION PATCH: Sprache & 0-Logik ===
        def _de_plural(n: int, singular: str, plural: str) -> str:
            return singular if int(n) == 1 else plural

        str_tri = f"{tri} {_de_plural(tri, 'Dreieck', 'Dreiecke')}"
        str_sq  = f"{sq} {_de_plural(sq, 'Quadrat', 'Quadrate')}"
        str_st  = f"{st_} {_de_plural(st_, 'Stern', 'Sterne')}"

        q_data = schedule[hour]

        if pre_reader:
            m_think = f"{tri} △   {sq} □   {st_} ★"
            m_move = _kid_short(q_data["movement"], 3)
            m_proof = "Haken!"
        else:
            t_idx = i % 3
            if t_idx == 0:
                m_think = f"Finde {str_tri}, {str_sq} und {str_st}."
            elif t_idx == 1:
                m_think = f"Spüre insgesamt {t_shapes} versteckte Formen auf (△, □, ★)."
            else:
                m_think = f"Suche: {tri}x Dreieck, {sq}x Quadrat, {st_}x Stern."

            m_move = q_data["movement"]

            m_proof = q_data["proof"] or ""

            if ("Dreieck" in m_proof or "Dreie" in m_proof) and tri == 0:
                m_proof = "Zähle laut mit und hake die Mission ab."
            elif ("Quadrat" in m_proof or "Quadrate" in m_proof) and sq == 0:
                m_proof = "Verbinde alle gefundenen Formen mit einer Linie."
            elif ("Stern" in m_proof or "Sterne" in m_proof) and st_ == 0:
                m_proof = "Setze einen Punkt in jede gefundene Form."

            if tri == 1:
                m_proof = m_proof.replace("Dreiecke", "Dreieck")
            if sq == 1:
                m_proof = m_proof.replace("Quadrate", "Quadrat")
            if st_ == 1:
                m_proof = m_proof.replace("Sterne", "Stern")
        # ====================================================

        mission = Mission(
            title=q_data["title"],
            xp=q_data["xp"],
            movement=m_move,
            thinking=m_think,
            proof=m_proof,
        )

        _draw_quest_overlay(c, pb, sl, sr, stb, hour, mission, debug, pre_reader)
        if eddie:
            _draw_eddie(c, pb.full_w - sr - 0.18 * inch, stb + 0.18 * inch, 0.18 * inch, style=style)

        _imprint_nonce(c, build_nonce)
        c.showPage()
        current_page_idx += 1
        gc.collect()

    # OUTRO PAGE (CTA + VECTOR QR -> GitHub Start)
    sl, sr, stb = safe_margins_for_page(total, kdp, current_page_idx, pb)
    c.setFillColor(colors.white)
    c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)

    # Eddie oben
    _draw_eddie(c, pb.full_w / 2, pb.full_h - stb - 1.45 * inch, 0.85 * inch, style=style)

    c.setFillColor(INK_BLACK)
    _set_font(c, True, 26)
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 2.85 * inch, "Du willst dein eigenes Abenteuerbuch?")

    _set_font(c, False, 13)
    c.setFillColor(INK_GRAY_70)
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 3.35 * inch, "Dieses Buch ist eine feste Version.")
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 3.62 * inch, "Deins kann anders sein – mit euren Fotos.")

    c.setFillColor(INK_BLACK)
    _set_font(c, True, 14)
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 4.25 * inch, "• Name rein")
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 4.55 * inch, "• Fotos rein")
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 4.85 * inch, "• PDF raus")

    # Vector QR (unendlich scharf)
    qr_code = qr.QrCodeWidget(QR_URL)
    bounds = qr_code.getBounds()
    qr_w = bounds[2] - bounds[0]
    qr_h = bounds[3] - bounds[1]
    qr_size = 1.85 * inch
    scale = qr_size / max(qr_w, qr_h)
    d = Drawing(
        qr_size,
        qr_size,
        transform=[scale, 0, 0, scale, -bounds[0] * scale, -bounds[1] * scale]
    )
    d.add(qr_code)
    renderPDF.draw(d, c, (pb.full_w - qr_size) / 2, pb.full_h - stb - 7.35 * inch)

    # URL Text darunter
    c.setFillColor(INK_BLACK)
    _set_font(c, True, 12)
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 7.70 * inch, QR_TEXT)

    # Trust / Ehrlich
    _set_font(c, False, 11)
    c.setFillColor(INK_GRAY_70)
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 8.05 * inch, "Kein Gelaber. Einfach ausprobieren.")

    _set_font(c, True, 12)
    c.setFillColor(INK_BLACK)
    c.drawCentredString(pb.full_w / 2, stb + 1.00 * inch, "Kein Abo. Keine Anmeldung. Fertig.")

    if debug:
        _draw_kdp_debug_guides(c, pb, sl, sr, stb)
    _imprint_nonce(c, build_nonce)
    c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()

def build_cover(name, paper, uploads, style, build_nonce, debug, preflight) -> bytes:
    sw = max(float(KDP_PAGES_FIXED) * PAPER_FACTORS.get(paper, 0.002252) * inch, 0.001 * inch)
    sw = round(sw / (0.001 * inch)) * (0.001 * inch)

    cw, ch = (2 * TRIM) + sw + (2 * BLEED), TRIM + (2 * BLEED)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(cw, ch))
    c.setTitle(f"{APP_TITLE} — Cover")
    c.setAuthor("Eddies World")
    if build_nonce:
        c.setSubject(f"nonce={build_nonce}")

    c.setFillColor(colors.white)
    c.rect(0, 0, cw, ch, fill=1, stroke=0)

    c.setFillColor(INK_BLACK)
    c.rect(BLEED + TRIM, BLEED, sw, TRIM, fill=1, stroke=0)

    back_x = BLEED
    spine_x = BLEED + TRIM
    front_x = BLEED + TRIM + sw
    trim_y = BLEED

    if KDP_PAGES_FIXED >= SPINE_TEXT_MIN_PAGES:
        c.saveState()
        c.setFillColor(colors.white)
        _set_font(c, True, 10)
        c.translate(BLEED + TRIM + sw / 2, BLEED + TRIM / 2)
        c.rotate(90)
        c.drawCentredString(0, -4, f"{_name_genitive(name)} ABENTEUERBUCH".upper())
        c.restoreState()

    # BACK
    bx = back_x
    c.setFillColor(colors.white)
    c.rect(bx, BLEED, TRIM, TRIM, fill=1, stroke=0)
    _draw_eddie(c, bx + TRIM * 0.12, BLEED + TRIM * 0.86, TRIM * 0.06, style=style)
    c.setFillColor(INK_GRAY_70)
    _set_font(c, False, 12)
    c.drawString(bx + TRIM * 0.12, BLEED + TRIM * 0.12, "24 Missionen • 24 Stunden • KDP-ready")

    # FRONT
    fx = front_x
    c.setFillColor(colors.white)
    c.rect(fx, BLEED, TRIM, TRIM, fill=1, stroke=0)

    collage = _cover_collage_png(uploads, int(TRIM * DPI / inch * 0.72), _stable_seed(f"{name}|cover|{build_nonce or 'x'}"))
    if collage:
        cw_px = TRIM * 0.72
        c.drawImage(ImageReader(io.BytesIO(collage)), fx + (TRIM - cw_px) / 2, BLEED + TRIM * 0.16, cw_px, cw_px, mask="auto")
        c.setFillColor(colors.white)
        c.setStrokeColor(INK_BLACK)
        c.setLineWidth(1)
        c.roundRect(fx + TRIM * 0.10, BLEED + TRIM * 0.74, TRIM * 0.80, TRIM * 0.20, TRIM * 0.04, fill=1, stroke=1)

    gen = _name_genitive(name)
    c.setFillColor(INK_BLACK)
    _set_font(c, True, 30)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.88, f"{gen}")
    _set_font(c, True, 24)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.82, "ABENTEUERBUCH")
    _set_font(c, False, 11)
    c.setFillColor(INK_GRAY_70)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.77, "Erstellt mit E. P. E. — Eddie's Print Engine")
    _draw_eddie(c, fx + TRIM / 2, BLEED + TRIM * 0.60, TRIM * 0.14, style=style)

    if debug or preflight:
        bc_w, bc_h = 2.0 * inch, 1.2 * inch
        bc_x = BLEED + TRIM - 0.25 * inch - bc_w
        bc_y = BLEED + 0.25 * inch

        c.saveState()
        c.setStrokeColor(colors.red)
        c.setLineWidth(1)
        c.setDash(4, 4)
        c.rect(bc_x, bc_y, bc_w, bc_h, stroke=1, fill=0)
        c.setFillColor(colors.red)
        _set_font(c, True, 10)
        c.drawCentredString(bc_x + bc_w / 2, bc_y + 0.65 * inch, "KDP BARCODE ZONE")
        _set_font(c, False, 8)
        c.drawCentredString(bc_x + bc_w / 2, bc_y + 0.45 * inch, "2.0\" × 1.2\"")
        c.restoreState()

        _draw_cover_preflight_facts_strip(
            c,
            cw=cw, ch=ch,
            trim=TRIM, bleed=BLEED,
            spine_w=sw,
            build_nonce=str(build_nonce),
            paper=str(paper),
            back_x=back_x,
            spine_x=spine_x,
            front_x=front_x,
            trim_y=trim_y,
            barcode_x=bc_x, barcode_y=bc_y,
            barcode_w=bc_w, barcode_h=bc_h,
        )

        safe_margin = 0.25 * inch
        c.saveState()
        c.setStrokeColor(DEBUG_SAFE_COLOR)
        c.setLineWidth(1)
        c.setDash(3, 3)
        c.rect(back_x + safe_margin, trim_y + safe_margin, TRIM - 2 * safe_margin, TRIM - 2 * safe_margin, stroke=1, fill=0)
        c.rect(front_x + safe_margin, trim_y + safe_margin, TRIM - 2 * safe_margin, TRIM - 2 * safe_margin, stroke=1, fill=0)
        c.restoreState()

    if build_nonce:
        _imprint_nonce(c, build_nonce)

    c.save()
    buf.seek(0)
    return buf.getvalue()

# =========================================================
# UI
# =========================================================
st.set_page_config(page_title=APP_TITLE, layout="centered", page_icon=APP_ICON)

st.markdown(f"<h1 style='text-align:center; margin-bottom: 0;'>{APP_TITLE}</h1>", unsafe_allow_html=True)
st.caption(f"Build: {BUILD_TAG}")

if is_supporter:
    st.success("💖 **Unterstützer-Modus aktiv:** Unlimitierte Builds freigeschaltet. Danke!")
elif access_mode == "Community":
    st.info(f"🏫 **Community-Pass aktiv:** {builds_left} Builds in den letzten 24h verfügbar.")
elif access_mode == "Dev Mode":
    st.info("🧪 **Dev Mode aktiv:** Unlimitierter Zugriff (keine Stripe Secrets).")
else:
    st.info(f"🔓 **Open Access:** ({builds_left} kostenlose Builds in den letzten 24h übrig)")

if access_mode == "Free":
    with st.expander("🏫 Hast du einen Community-Pass? (Kitas, Schulen, Therapeuten)"):
        c_code = st.text_input("Code eingeben:", key="c_code_input")
        if st.button("Passwort aktivieren"):
            if c_code in COMMUNITY_TOKENS:
                st.session_state["community_pass"] = c_code
                st.success("Passwort akzeptiert! Seite wird neu geladen...")
                time.sleep(1)
                st.rerun()
            else:
                st.error("Ungültiger Code.")

if qd is None:
    st.warning("quest_data.py fehlt – Engine läuft trotzdem (Fallback-Welt aktiv).")
    if "_QD_IMPORT_ERROR" in globals() and _QD_IMPORT_ERROR:
        st.code(_QD_IMPORT_ERROR, language="text")

st.session_state.setdefault("assets", None)
st.session_state.setdefault("upload_sig", "")
st.session_state.setdefault("last_nonce", "")
_get_lru("sketch_cache", MAX_SKETCH_CACHE)
_get_lru("wash_cache", MAX_WASH_CACHE)

def _uploads_sig(ul) -> str:
    h = hashlib.sha256()
    for up in (ul or []):
        try:
            buf = up.getbuffer()
            if len(buf) > MAX_UPLOAD_BYTES:
                h.update(b"OVERSIZE")
                h.update(getattr(up, "name", "x").encode("utf-8", "ignore"))
                continue
            h.update(len(buf).to_bytes(8, "little"))
            data = bytes(buf[:2048]) + bytes(buf[-2048:]) if len(buf) > 4096 else bytes(buf)
            h.update(hashlib.sha256(data).digest())
        except Exception:
            try:
                b = _read_upload_bytes(up)
            except ValueError:
                h.update(b"OVERSIZE")
                h.update(getattr(up, "name", "x").encode("utf-8", "ignore"))
                continue
            h.update(len(b).to_bytes(8, "little"))
            h.update(hashlib.sha256(b[:2048]).digest())
    return h.hexdigest()

with st.container(border=True):
    c1, c2 = st.columns(2)
    name = c1.text_input("Name des Kindes", "Eddie")

    c2.markdown("**Seitenanzahl**")
    c2.info("📘 Fix 26 Seiten (KDP-Ready)")
    paper = c2.selectbox("Papier", list(PAPER_FACTORS.keys()), 0)

    st.divider()
    c3, c4 = st.columns(2)
    eddie_style = c3.selectbox("Eddie-Marke", ["tongue", "dog"], 0, help="Die lila Zunge ist unser Erkennungsmerkmal.")
    pre_reader_mode = c4.toggle("👶 Pre-Reader Modus", value=False, help="Weniger Text, mehr Icons.")

    with st.expander("⚙️ Erweiterte KDP & Druck-Einstellungen"):
        kdp = st.toggle("KDP Mode (Beschnittzugabe aktivieren)", True)
        eddie_guide = st.toggle("Eddie-Marke auf jeder Seite drucken", True)
        debug = st.toggle("🛠️ Preflight Debug (Rote Linien - NICHT drucken!)", False)
        preflight = st.toggle("📏 KDP Preflight Mode (Maße/Float-Werte auf Intro-Seite + Cover Strip/Boxes)", False)

    st.info("💡 **Tipp:** Es müssen keine Personen zu sehen sein! Haustiere, Zimmer, Spielzeug oder Garten ergeben fantastische Ausmalbilder.")
    uploads = st.file_uploader("Fotos hochladen (10-24 empfohlen)", accept_multiple_files=True, type=["jpg", "jpeg", "png", "webp"])

if uploads:
    st.success(f"✅ {len(uploads)} Fotos bereit für die Engine.")

if not can_build_limit:
    st.error("🛑 **Fair-Use Limit erreicht.** Du hast deine kostenlosen Questbücher für die letzten 24h generiert.")
    st.markdown("**Möchtest du unbegrenzt Bücher erstellen?** Werde Unterstützer.")
    st.link_button("💖 Unterstützer werden (Unlimitiert)", PAYMENT_LINK, type="primary")
    st.stop()

if st.button("🚀 QUESTBUCH GENERIEREN", disabled=not (uploads and name), type="primary"):
    nonce = _new_build_nonce()
    st.session_state["last_nonce"] = nonce
    sig = _uploads_sig(uploads)

    if st.session_state.upload_sig != sig:
        st.session_state.upload_sig = sig
        st.session_state["sketch_cache"].clear()
        st.session_state["wash_cache"].clear()

    with st.spinner("Engine läuft... (Waschen, Skizzieren, Shapes, Layouten)"):
        try:
            int_pdf = build_interior(
                name=name,
                uploads=uploads,
                kdp=bool(kdp),
                debug=bool(debug),
                preflight=bool(preflight),
                paper=str(paper),
                eddie=bool(eddie_guide),
                style=str(eddie_style),
                pre_reader=bool(pre_reader_mode),
                build_nonce=nonce,
            )
            cov_pdf = build_cover(
                name=name,
                paper=str(paper),
                uploads=uploads,
                style=str(eddie_style),
                build_nonce=nonce,
                debug=bool(debug),
                preflight=bool(preflight),
            )
            st.session_state.assets = {"int": int_pdf, "cov": cov_pdf, "name": name, "nonce": nonce}

            _log_build(client_ip)
            st.success(f"🎉 Assets bereit! (Noch {max(0, builds_left - 1)} kostenlose Builds in den letzten 24h)")
        except Exception as e:
            st.error(f"⚠️ Engine gestolpert: `{str(e)}`")

if st.session_state.assets:
    a = st.session_state.assets
    st.markdown("### 📥 Deine druckfertigen PDFs")
    col1, col2 = st.columns(2)
    col1.download_button("📘 Innenseiten (PDF)", a["int"], f"Int_{a['name']}.pdf", use_container_width=True)
    col2.download_button("🎨 Cover (PDF)", a["cov"], f"Cov_{a['name']}.pdf", use_container_width=True)
    st.caption(f"Security Nonce: `{a.get('nonce','')}`")

    if access_mode == "Free" and not is_supporter:
        st.markdown("---")
        st.markdown(
            "### ❤️ Hat es dir gefallen?\n"
            "E.P.E. Eddie's Print Engine ist ein **Community-Projekt**.\n"
            "Wenn du kannst, hilf uns, die Serverkosten zu tragen:"
        )
        st.link_button("☕ Spendiere uns einen Kaffee (Werde Unterstützer)", PAYMENT_LINK)

st.markdown("<div style='text-align:center; color:grey; margin-top: 50px;'>Eddies World © 2026 • Ein Projekt für jedes Kind.</div>", unsafe_allow_html=True)
