from __future__ import annotations
## ===== PUBLIC LINK (GLOBAL OVERRIDE) =====
PUBLIC_URL = "https://keschflow.github.io/eddies-print-engine/"

def fix_public_link(text: str) -> str:
    if not text:
        return text
    return (
        text
        .replace("keschflow.github.io/start", PUBLIC_URL)
        .replace("https://keschflow.github.io/start", PUBLIC_URL)
        .replace("http://keschflow.github.io/start", PUBLIC_URL)
    )
# app.py — E. P. E. Eddie's Print Engine — v6.0.0 (CLEAN CORE)
#
# v6 PRINCIPLES:
# - Data-only: quest_data.py (pools + dedupe via qid)
# - Layout-only: text_layout.py (ReportLab Paragraph wrapping + overflow gate)
# - Core engine: app.py orchestrates, no string-hacks, no QUEST_BANK
#
# MUST-HAVES:
# - KDP READY: Safe zones, 26 pages fixed
# - DUAL MODE: kid vs senior
# - QR CTA OUTRO: vector QR
# - SECURITY: upload caps, OpenCV 25MP guard, SQLite fair-use rate limit
# - QUALITY GATE: text overflow -> hard ValueError (crash build)
# =========================================================



import io
import os
import gc
import time
import math
import secrets
import hashlib
import sqlite3
import random
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
from text_layout import draw_wrapped_text  # Paragraph-based wrapping + fit gate

# --- PIL Hardening ---
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = 25_000_000  # ~25MP

# =========================================================
# QUEST DATA (REQUIRED FOR v6)
# =========================================================
try:
    import quest_data as qd
except Exception as e:
    qd = None
    _QD_IMPORT_ERROR = str(e)

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

def _de_plural(n: int, singular: str, plural: str) -> str:
    return singular if int(n) == 1 else plural

def _stable_seed(s: str) -> int:
    return int.from_bytes(hashlib.sha256(s.encode("utf-8")).digest()[:8], "big")

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
# --- SECRETS (Docker/Cloud safe) ---
try:
    _SECRETS = st.secrets  # may raise if secrets.toml is missing
except Exception:
    _SECRETS = {}

STRIPE_SECRET = _SECRETS.get("STRIPE_SECRET_KEY", "")
PAYMENT_LINK  = _SECRETS.get("STRIPE_PAYMENT_LINK", "https://buy.stripe.com/...")

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
# QUEST ZONES (optional in quest_data; fallback stub)
# =========================================================
@dataclass(frozen=True)
class ZoneStub:
    name: str
    icon: str
    quest_type: str
    atmosphere: str

def _zone_stub(hour: int) -> ZoneStub:
    if 6 <= hour <= 10: return ZoneStub("Morgen-Start", "🌤️", "Warm-up", "ruhig")
    if 11 <= hour <= 15: return ZoneStub("Mittags-Mission", "🌞", "Action", "wach")
    if 16 <= hour <= 20: return ZoneStub("Nachmittags-Boost", "🟣", "Abenteuer", "spielerisch")
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

BUILD_TAG = "v6.0.0-clean-core"

QR_URL = "https://keschflow.github.io/start/"
QR_TEXT = "keschflow.github.io/start"

# =========================================================
# PAGE GEOMETRY
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
# FONTS
# =========================================================
def _try_register_fonts() -> Dict[str, str]:
    n = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
    b = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    if os.path.exists(n):
        try: pdfmetrics.registerFont(TTFont("EDDIES_FONT", n))
        except Exception: pass
    if os.path.exists(b):
        try: pdfmetrics.registerFont(TTFont("EDDIES_FONT_BOLD", b))
        except Exception: pass
    return {
        "normal": "EDDIES_FONT" if "EDDIES_FONT" in pdfmetrics.getRegisteredFontNames() else "Helvetica",
        "bold": "EDDIES_FONT_BOLD" if "EDDIES_FONT_BOLD" in pdfmetrics.getRegisteredFontNames() else "Helvetica-Bold",
    }

FONTS = _try_register_fonts()

def _set_font(c: canvas.Canvas, bold: bool, size: int) -> float:
    c.setFont(FONTS["bold"] if bold else FONTS["normal"], size)
    return size * 1.22

def _kid_short(s: str, max_words: int = 4) -> str:
    s = (s or "").strip().replace("•", " ").replace("→", " ").replace("-", " ")
    return " ".join([w for w in s.split() if w and len(w) > 1][:max_words])

# =========================================================
# v6 QUEST SCHEDULING (quest_data pools + dedupe)
# =========================================================
@dataclass(frozen=True)
class ScheduledQuest:
    title: str
    xp: int
    thinking: str
    proof: str
    note: str

@dataclass
class QuestTrackers:
    used_proof: set
    used_quest: set
    used_note: set

def _new_trackers() -> QuestTrackers:
    return QuestTrackers(used_proof=set(), used_quest=set(), used_note=set())

def build_book_schedule(seed: int, start_hour: int, count: int) -> Tuple[Dict[int, ScheduledQuest], QuestTrackers]:
    if not qd or not hasattr(qd, "get_quest"):
        raise RuntimeError("quest_data.py missing/invalid: get_quest() required for v6.")

    rng = random.Random(int(seed) & 0xFFFFFFFFFFFFFFFF)
    tr = _new_trackers()
    schedule: Dict[int, ScheduledQuest] = {}

    for i in range(int(count)):
        hour = (int(start_hour) + i) % 24
        zone = _get_zone_for_hour(hour)

        q_item = qd.get_quest("quest", tr.used_quest, rng=rng)
        qid = getattr(q_item, "qid", "")
        if qid:
            tr.used_quest.add(qid)

        p_item = qd.get_quest("proof", tr.used_proof, rng=rng)
        pid = getattr(p_item, "qid", "")
        if pid:
            tr.used_proof.add(pid)

        n_text = ""
        try:
            n_item = qd.get_quest("note", tr.used_note, rng=rng)
            nid = getattr(n_item, "qid", "")
            if nid:
                tr.used_note.add(nid)
            n_text = (getattr(n_item, "text", "") or "").strip()
        except Exception:
            n_text = ""

        schedule[hour] = ScheduledQuest(
            title=f"{zone.quest_type}: {zone.name}",
            xp=10 + (i % 10) + (hour % 5),
            thinking=(getattr(q_item, "text", "") or "").strip(),
            proof=(getattr(p_item, "text", "") or "").strip(),
            note=n_text,
        )

    return schedule, tr

# =========================================================
# MISSIONS
# =========================================================
@dataclass
class Mission:
    title: str
    xp: int
    movement: str
    thinking: str
    proof: str

# =========================================================
# ICONS, SHAPES & BRANDING
# =========================================================
def _draw_eddie(c: canvas.Canvas, cx: float, cy: float, r: float, style: str = "tongue"):
    c.saveState()
    if style == "tongue":
        tw, th = r * 0.55, r * 0.70
        c.setFillColor(colors.HexColor(EDDIE_PURPLE)); c.setStrokeColor(INK_BLACK); c.setLineWidth(max(1.2, r * 0.06))
        c.roundRect(cx - tw / 2, cy - th / 2, tw, th, r * 0.18, stroke=1, fill=1)
        c.setLineWidth(max(0.8, r * 0.03)); c.line(cx, cy - th / 2 + th * 0.15, cx, cy - th / 2 + th * 0.45)
    else:
        c.setStrokeColor(INK_BLACK); c.setFillColor(colors.white); c.setLineWidth(max(1.2, r * 0.06))
        c.circle(cx, cy, r, stroke=1, fill=1)
        c.line(cx - r * 0.55, cy + r * 0.55, cx - r * 0.15, cy + r * 0.95); c.line(cx - r * 0.15, cy + r * 0.95, cx - r * 0.05, cy + r * 0.45)
        c.line(cx + r * 0.55, cy + r * 0.55, cx + r * 0.15, cy + r * 0.95); c.line(cx + r * 0.15, cy + r * 0.95, cx + r * 0.05, cy + r * 0.45)
        c.setFillColor(colors.HexColor(EDDIE_PURPLE))
        c.roundRect(cx - r * 0.12, cy - r * 0.45, r * 0.24, r * 0.28, r * 0.10, stroke=0, fill=1)
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
    shapes: List[ShapeSpec] = []
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
MAX_UPLOAD_BYTES = 12 * 1024 * 1024

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
    pil = pil.crop(((sw - s) // 2, (sh - s) // 2, (sw + s) // 2, (sw + s) // 2)).resize((target_w, target_h), Image.LANCZOS)
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
# OVERLAY (QUEST CARD) — Paragraph wrapping + HARD overflow gate
# =========================================================
def _draw_quest_overlay(c, pb, sl, sr, stb, hour, mission: Mission, debug, pre_reader, is_senior):
    hh = 0.75 * inch
    x0 = sl
    w = max(1.0, pb.full_w - sr - x0)
    ytb = pb.full_h - stb - hh
    zone = _get_zone_for_hour(hour)
    z_rgb = _get_hour_color(hour)

    c.saveState()
    # Header
    c.setFillColor(colors.Color(z_rgb[0], z_rgb[1], z_rgb[2]))
    c.setStrokeColor(INK_BLACK)
    c.setLineWidth(1)
    c.rect(x0, ytb, w, hh, fill=1, stroke=1)

    # Timeline (kid only)
    if not is_senior:
        pad_x = 0.25 * inch
        avail_w = w - 2 * pad_x
        step = avail_w / 23.0
        timeline_y = ytb + hh - 0.18 * inch
        for h_idx in range(24):
            hx = x0 + pad_x + h_idx * step
            dot_rgb = _get_hour_color(h_idx)
            c.setFillColor(colors.Color(*dot_rgb))
            if h_idx == hour:
                c.setStrokeColor(colors.white)
                c.setLineWidth(1.2)
                c.circle(hx, timeline_y, 4, fill=1, stroke=1)
            else:
                c.setStrokeColor(INK_BLACK)
                c.setLineWidth(0.5)
                c.circle(hx, timeline_y, 2, fill=1, stroke=1)

    # Header text
    c.setFillColor(colors.white if sum(z_rgb[:3]) < 1.5 else INK_BLACK)
    _set_font(c, True, 14)
    c.drawString(x0 + 0.18 * inch, ytb + hh - 0.48 * inch, f"{_fmt_hour(hour)}  {zone.icon}  {zone.name}")
    _set_font(c, False, 10)
    c.drawString(x0 + 0.18 * inch, ytb + 0.15 * inch, f"{zone.quest_type} • {zone.atmosphere}")

    # Card box
    cy = stb
    max_ch = ytb - cy - 0.15 * inch
    ch = min(max_ch, (2.45 * inch if (pre_reader and not is_senior) else 2.85 * inch))
    c.setFillColor(colors.white)
    c.setStrokeColor(INK_BLACK)
    c.rect(x0, cy, w, ch, fill=1, stroke=1)

    yc = cy + ch - 0.18 * inch
    c.setFillColor(INK_BLACK)

    if pre_reader and not is_senior:
        # Minimal kid layout (keep drawString)
        _set_font(c, True, 14)
        c.drawString(x0 + 0.18 * inch, yc - 10, _kid_short(mission.title, 3) or "MISSION")
        _set_font(c, True, 11)
        c.drawRightString(x0 + w - 0.18 * inch, yc - 10, f"+{int(mission.xp)} XP")

        _set_font(c, False, 12)
        c.drawString(x0 + 0.18 * inch, yc - 0.55 * inch, _kid_short(mission.movement, 4) or "Bewegen!")
        c.drawString(x0 + 0.18 * inch, yc - 1.00 * inch, mission.thinking or "")
        c.drawString(x0 + 0.18 * inch, yc - 1.45 * inch, _kid_short(mission.proof, 4) or "Haken!")

        _set_font(c, False, 8)
        c.setFillColor(INK_GRAY_70)
        c.drawString(x0 + 0.18 * inch, cy + 0.12 * inch, "Eltern: kurz vorlesen – Kind macht’s nach.")
    else:
        # Labels
        title_label = "TAGESIMPULS" if is_senior else "MISSION"
        move_label  = "BEWEGUNG:"
        think_label = "GEDANKEN:" if is_senior else "SUCHEN:"
        proof_label = "ERLEDIGT:" if is_senior else "PROOF:"

        # styles
        STYLE_BODY = "SeniorBody" if is_senior else "KidsText"

        # Geometry
        pad_left = 0.18 * inch
        pad_right = 0.18 * inch
        label_x = x0 + pad_left
        move_x  = x0 + 1.05 * inch
        think_x = x0 + 0.90 * inch
        proof_x = x0 + 1.03 * inch

        move_w  = (x0 + w - pad_right) - move_x
        think_w = (x0 + w - pad_right) - think_x
        proof_w = (x0 + w - pad_right) - proof_x

        # Title
        _set_font(c, True, 13 if not is_senior else 16)
        c.drawString(x0 + 0.18 * inch, yc - (13 * 1.22) + 2, f"{title_label}: {mission.title}")

        if not is_senior:
            _set_font(c, True, 11)
            c.drawRightString(x0 + w - 0.18 * inch, yc - (13 * 1.22) + 2, f"+{int(mission.xp)} XP")

        # Movement
        yt = yc - (13 * 1.22) - 0.10 * inch
        _set_font(c, True, 10 if not is_senior else 12)
        c.drawString(label_x, yt - (10 * 1.22) + 2, move_label)

        move_top = yt - (10 * 1.22) + 6
        move_h = 0.62 * inch if is_senior else 0.58 * inch
        ok = draw_wrapped_text(
            c, mission.movement or "",
            x=move_x, y=move_top, width=move_w, height=move_h,
            style_name=STYLE_BODY, return_fit=True
        )
        if not ok:
            raise ValueError("OVERFLOW: movement text does not fit card")

        # Thinking
        yt2 = (move_top - move_h) - 0.10 * inch
        _set_font(c, True, 10 if not is_senior else 12)
        c.drawString(label_x, yt2 - (10 * 1.22) + 2, think_label)

        think_top = yt2 - (10 * 1.22) + 6
        think_h = 0.70 * inch if is_senior else 0.66 * inch
        ok = draw_wrapped_text(
            c, mission.thinking or "",
            x=think_x, y=think_top, width=think_w, height=think_h,
            style_name=STYLE_BODY, return_fit=True
        )
        if not ok:
            raise ValueError("OVERFLOW: thinking text does not fit card")

        # Proof
        c.rect(x0 + 0.18 * inch, cy + 0.18 * inch, 0.20 * inch, 0.20 * inch, fill=0, stroke=1)
        _set_font(c, True, 10 if not is_senior else 12)
        c.drawString(x0 + 0.43 * inch, cy + 0.20 * inch, proof_label)

        proof_top = cy + 0.40 * inch
        proof_h = 0.32 * inch
        ok = draw_wrapped_text(
            c, mission.proof or "",
            x=proof_x, y=proof_top, width=proof_w, height=proof_h,
            style_name=STYLE_BODY, return_fit=True
        )
        if not ok:
            raise ValueError("OVERFLOW: proof text does not fit card")

        if is_senior:
            _set_font(c, False, 8)
            c.setFillColor(INK_GRAY_70)
            c.drawString(x0 + 0.18 * inch, cy + 0.08 * inch, "In Ruhe gemeinsam betrachten – ganz ohne Zeitdruck.")

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
def build_interior(name, uploads, kdp, debug, preflight, paper, eddie, style, pre_reader, build_nonce, is_senior) -> bytes:
    if not qd:
        raise RuntimeError(f"quest_data.py fehlt/fehlerhaft: {_QD_IMPORT_ERROR if '_QD_IMPORT_ERROR' in globals() else ''}")

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
            total_bytes += len(_read_upload_bytes(up))
        if total_bytes > MAX_TOTAL_UPLOAD_BYTES:
            raise ValueError(f"Uploads insgesamt zu groß (max {MAX_TOTAL_UPLOAD_BYTES // (1024*1024)}MB). Bitte weniger/kleinere Bilder.")

    total = KDP_PAGES_FIXED
    MISSION_PAGES = 24

    pb = page_box(TRIM, TRIM, kdp_bleed=bool(kdp))
    final = (list(uploads) * (MISSION_PAGES // len(uploads) + 1))[:MISSION_PAGES]

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(pb.full_w, pb.full_h))
    c.setTitle(f"{APP_TITLE} — Interior")
    c.setAuthor("Eddies World")
    c.setSubject(f"nonce={build_nonce}")

    schedule, trackers = build_book_schedule(_stable_seed(build_nonce), start_hour=6, count=MISSION_PAGES)

    seed_base = _stable_seed(name)
    nonce_seed = _stable_seed(build_nonce)
    current_page_idx = 0

    # INTRO PAGE (simple)
    sl, sr, stb = safe_margins_for_page(total, bool(kdp), current_page_idx, pb)
    c.setFillColor(colors.white)
    c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)
    gen = _name_genitive(name)
    c.setFillColor(INK_BLACK)
    _set_font(c, True, 34)

    book_title = f"{gen} Tagesbegleiter" if is_senior else f"{gen} Abenteuerbuch"
    subtitle = "24 Stunden • In Ruhe betrachten • Entspannen" if is_senior else "24 Stunden • 24 Mini-Quests • Haken setzen"
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 1.90 * inch, book_title)
    _set_font(c, False, 14)
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 2.35 * inch, "Erstellt mit")
    _set_font(c, True, 18)
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 2.70 * inch, "E. P. E.")
    _set_font(c, False, 14)
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 3.00 * inch, "Eddie's Print Engine")
    _draw_eddie(c, pb.full_w / 2, pb.full_h / 2, 1.20 * inch, style=style)
    c.setFillColor(INK_GRAY_70)
    _set_font(c, False, 13)
    c.drawCentredString(pb.full_w / 2, stb + 0.75 * inch, subtitle)

    if debug:
        _draw_kdp_debug_guides(c, pb, sl, sr, stb)
    _imprint_nonce(c, build_nonce)
    c.showPage()
    current_page_idx += 1

    # CONTENT PAGES
    for i, up in enumerate(final):
        sl, sr, stb = safe_margins_for_page(total, bool(kdp), current_page_idx, pb)

        # background sketch
        sk_bytes = _get_sketch_cached(
            _wash_upload_to_bytes(up),
            int(pb.full_w * DPI / 72),
            int(pb.full_h * DPI / 72),
        )
        c.drawImage(ImageReader(io.BytesIO(sk_bytes)), 0, 0, pb.full_w, pb.full_h)

        hour = (6 + i) % 24
        seed = int(seed_base ^ nonce_seed ^ (i << 1) ^ hour) & 0xFFFFFFFF
        shapes = _generate_shapes(pb, sl, sr, stb, bool(pre_reader) and not is_senior, seed)
        _draw_shapes(c, shapes)

        tri = sum(1 for s in shapes if s.kind == "triangle")
        sq  = sum(1 for s in shapes if s.kind == "square")
        st_ = sum(1 for s in shapes if s.kind == "star")
        t_shapes = len(shapes)

        q = schedule[hour]
        zone = _get_zone_for_hour(hour)

        # SENIOR
        if is_senior:
            senior_moves = [
                "Heben Sie die Schultern sanft an und lassen Sie sie wieder sinken (3×, im eigenen Tempo).",
                "Kreisen Sie Ihre Hände sanft aus den Handgelenken.",
                "Atmen Sie tief durch die Nase ein und langsam durch den Mund wieder aus.",
                "Ziehen Sie die Fußspitzen im Sitzen sanft an und lassen Sie wieder locker.",
                "Legen Sie die Hände flach auf den Tisch und spreizen Sie die Finger leicht.",
                "Neigen Sie den Kopf behutsam von einer Seite zur anderen.",
                "Reiben Sie Ihre Handflächen aneinander, bis sie sich warm anfühlen.",
            ]
            s_rng = np.random.default_rng(seed)
            m_move = str(s_rng.choice(senior_moves))
            m_think = f"Betrachten Sie das Bild in Ruhe. Entdecken Sie {t_shapes} Details im Bild (Formen oder Objekte) – ohne Zeitdruck."

            proof = "☐ Heute gemacht"
            # soft link to quest_data proof pool (short only)
            extra = (q.proof or "").strip()
            if extra and len(extra) <= 70:
                proof = f"☐ Heute gemacht — {extra}"

            mission = Mission(
                title="Aktiv bleiben",
                xp=0,
                movement=m_move,
                thinking=m_think,
                proof=proof,
            )

        # KID
        else:
            kid_moves = [
                "Mache 10 Kniebeugen.",
                "20 Sekunden Hampelmann.",
                "Streck dich so groß du kannst.",
                "Laufe 10 Sekunden auf der Stelle.",
                "Hüpfe 5x hoch in die Luft.",
                "Berühre 10x deine Zehenspitzen.",
                "Kreise deine Arme wie Windmühlen.",
                "Mache 5 Froschsprünge.",
                "Balanciere 10 Sekunden auf einem Bein.",
                "Mache 3 große Ausfallschritte.",
            ]
            km_rng = np.random.default_rng(seed)
            m_move = str(km_rng.choice(kid_moves))

            if pre_reader:
                m_think = f"{tri} △   {sq} □   {st_} ★"
                m_proof = "Haken!"
                title = "MISSION"
                xp = int(q.xp)
            else:
                str_tri = f"{tri} {_de_plural(tri, 'Dreieck', 'Dreiecke')}"
                str_sq  = f"{sq} {_de_plural(sq, 'Quadrat', 'Quadrate')}"
                str_st  = f"{st_} {_de_plural(st_, 'Stern', 'Sterne')}"

                base_think = (q.thinking or "").strip()

                # short count hint layer (deterministic)
                t_idx = i % 3
                if t_idx == 0:
                    hint = f"Finde {str_tri}, {str_sq} und {str_st}."
                elif t_idx == 1:
                    hint = f"Spüre insgesamt {t_shapes} Formen auf (△, □, ★)."
                else:
                    hint = f"Suche: {tri}x Dreieck, {sq}x Quadrat, {st_}x Stern."

                # Combine (kept compact; overflow gate will stop if too long)
                m_think = f"{base_think} {hint}".strip()
                if t_shapes == 0:
                    m_think = "Suche Formen (△, □, ★) im Bild. Wenn keine da sind: schaue nach Mustern oder Dingen."

                # proof from proof pool (+ optional note only if short)
                m_proof = (q.proof or "").strip()
                if q.note and len(q.note) <= 90:
                    # only attach if it won't explode the proof box
                    m_proof = f"{m_proof} {q.note}".strip()

                title = q.title or f"{zone.quest_type}: {zone.name}"
                xp = int(q.xp)

            mission = Mission(
                title=title,
                xp=xp,
                movement=m_move,
                thinking=m_think,
                proof=m_proof,
            )

        _draw_quest_overlay(c, pb, sl, sr, stb, hour, mission, bool(debug), bool(pre_reader), bool(is_senior))

        if eddie:
            _draw_eddie(c, pb.full_w - sr - 0.18 * inch, stb + 0.18 * inch, 0.18 * inch, style=style)

        _imprint_nonce(c, build_nonce)
        c.showPage()
        current_page_idx += 1
        gc.collect()

    # OUTRO PAGE (CTA + QR)
    sl, sr, stb = safe_margins_for_page(total, bool(kdp), current_page_idx, pb)
    c.setFillColor(colors.white)
    c.rect(0, 0, pb.full_w, pb.full_h, fill=1, stroke=0)

    _draw_eddie(c, pb.full_w / 2, pb.full_h - stb - 1.5 * inch, 0.8 * inch, style=style)

    c.setFillColor(INK_BLACK)
    _set_font(c, True, 24)
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 2.8 * inch, "Dieses Buch wurde generiert.")

    _set_font(c, False, 14)
    c.setFillColor(INK_GRAY_70)
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 3.4 * inch, "Mit E.P.E. — Eddie's Print Engine.")
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 3.7 * inch, "Aus ganz normalen Fotos.")

    c.setFillColor(INK_BLACK)
    _set_font(c, True, 15)
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 4.6 * inch, "1. Eigene Fotos hochladen.")
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 5.0 * inch, "2. Quests & Layout werden automatisch gebaut.")
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 5.4 * inch, "3. Als KDP-ready PDF herunterladen.")

    qr_code = qr.QrCodeWidget(QR_URL)
    bounds = qr_code.getBounds()
    qr_w = bounds[2] - bounds[0]
    qr_h = bounds[3] - bounds[1]
    qr_size = 1.85 * inch
    scale = qr_size / max(qr_w, qr_h)
    d = Drawing(qr_size, qr_size, transform=[scale, 0, 0, scale, -bounds[0] * scale, -bounds[1] * scale])
    d.add(qr_code)
    renderPDF.draw(d, c, (pb.full_w - qr_size) / 2, pb.full_h - stb - 7.65 * inch)

    c.setFillColor(INK_BLACK)
    _set_font(c, True, 12)
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 8.05 * inch, QR_TEXT)

    _set_font(c, False, 11)
    c.setFillColor(INK_GRAY_70)
    c.drawCentredString(pb.full_w / 2, pb.full_h - stb - 8.45 * inch, "3 kostenlose Bücher testen.")

    _set_font(c, True, 12)
    c.setFillColor(INK_BLACK)
    c.drawCentredString(pb.full_w / 2, stb + 1.05 * inch, "Kein Abo. Keine Anmeldung. Nur das Tool.")

    if debug:
        _draw_kdp_debug_guides(c, pb, sl, sr, stb)

    _imprint_nonce(c, build_nonce)
    c.showPage()

    c.save()
    buf.seek(0)
    return buf.getvalue()

def build_cover(name, paper, uploads, style, build_nonce, debug, preflight, is_senior) -> bytes:
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

    # spine background
    c.setFillColor(INK_BLACK)
    c.rect(BLEED + TRIM, BLEED, sw, TRIM, fill=1, stroke=0)

    back_x = BLEED
    spine_x = BLEED + TRIM
    front_x = BLEED + TRIM + sw

    book_title_cov = "TAGESBEGLEITER" if is_senior else "ABENTEUERBUCH"
    subtitle_cov = "24 Impulse • 24 Stunden • KDP-ready" if is_senior else "24 Missionen • 24 Stunden • KDP-ready"

    # spine text
    if KDP_PAGES_FIXED >= SPINE_TEXT_MIN_PAGES:
        c.saveState()
        c.setFillColor(colors.white)
        _set_font(c, True, 10)
        c.translate(BLEED + TRIM + sw / 2, BLEED + TRIM / 2)
        c.rotate(90)
        c.drawCentredString(0, -4, f"{_name_genitive(name)} {book_title_cov}".upper())
        c.restoreState()

    # BACK
    bx = back_x
    c.setFillColor(colors.white)
    c.rect(bx, BLEED, TRIM, TRIM, fill=1, stroke=0)
    _draw_eddie(c, bx + TRIM * 0.12, BLEED + TRIM * 0.86, TRIM * 0.06, style=style)
    c.setFillColor(INK_GRAY_70)
    _set_font(c, False, 12)
    c.drawString(bx + TRIM * 0.12, BLEED + TRIM * 0.12, subtitle_cov)

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
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.82, book_title_cov)
    _set_font(c, False, 11)
    c.setFillColor(INK_GRAY_70)
    c.drawCentredString(fx + TRIM / 2, BLEED + TRIM * 0.77, "Erstellt mit E. P. E. — Eddie's Print Engine")
    _draw_eddie(c, fx + TRIM / 2, BLEED + TRIM * 0.60, TRIM * 0.14, style=style)

    # Barcode debug box (optional)
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
        c.drawCentredString(bc_x + bc_w / 2, bc_y + 0.45 * inch, '2.0" × 1.2"')
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
    st.error("quest_data.py fehlt/fehlerhaft — v6 benötigt die Pools.")
    if "_QD_IMPORT_ERROR" in globals() and _QD_IMPORT_ERROR:
        st.code(_QD_IMPORT_ERROR, language="text")
    st.stop()

st.session_state.setdefault("assets", None)
st.session_state.setdefault("upload_sig", "")
st.session_state.setdefault("last_nonce", "")
st.session_state.setdefault("mode", _qp("mode") or "kid")

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
            b = _read_upload_bytes(up)
            h.update(len(b).to_bytes(8, "little"))
            h.update(hashlib.sha256(b[:2048]).digest())
    return h.hexdigest()

with st.container(border=True):
    mode = st.radio(
        "Zielgruppe / Modus",
        options=["kid", "senior"],
        format_func=lambda m: "👶 Kinder (Abenteuer & XP)" if m == "kid" else "👵 Senioren (Ruhig & Würdevoll)",
        horizontal=True,
        key="mode",
    )
    is_senior = (mode == "senior")
    st.divider()

    c1, c2 = st.columns(2)
    name = c1.text_input("Name (für das Cover)", "Eddie")

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
        preflight = st.toggle("📏 Preflight Mode (derzeit nur Cover-Barcodebox)", False)

    st.info("💡 **Tipp:** Es müssen keine Personen zu sehen sein! Haustiere, Zimmer, Spielzeug oder Garten ergeben fantastische Ausmalbilder.")
    uploads = st.file_uploader("Fotos hochladen (10-24 empfohlen)", accept_multiple_files=True, type=["jpg", "jpeg", "png", "webp"])

if uploads:
    st.success(f"✅ {len(uploads)} Fotos bereit für die Engine.")

if not can_build_limit:
    st.error("🛑 **Fair-Use Limit erreicht.** Du hast deine kostenlosen Questbücher für die letzten 24h generiert.")
    st.markdown("**Möchtest du unbegrenzt Bücher erstellen?** Werde Unterstützer.")
    st.link_button("💖 Unterstützer werden (Unlimitiert)", PAYMENT_LINK, type="primary")
    st.stop()

if st.button("🚀 BUCH GENERIEREN", disabled=not (uploads and name), type="primary"):
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
                is_senior=is_senior
            )
            cov_pdf = build_cover(
                name=name,
                paper=str(paper),
                uploads=uploads,
                style=str(eddie_style),
                build_nonce=nonce,
                debug=bool(debug),
                preflight=bool(preflight),
                is_senior=is_senior
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
        st.link_button("☕ Spendiere uns einen Kaffee (Werde Unterstützer)", "https://ko-fi.com/eddiesworld")

st.markdown("<div style='text-align:center; color:grey; margin-top: 50px;'>Eddies World © 2026 • Ein Projekt für jedes Kind (und jeden Senior).</div>", unsafe_allow_html=True)
