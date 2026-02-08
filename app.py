import streamlit as st
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm

from quest_data import (
    get_zone_for_hour,
    pick_mission_for_time,
    fmt_hour,
    validate_quest_db,
)

st.set_page_config(page_title="Quest-Logbuch Generator", page_icon="📘", layout="centered")

# -------- PDF / HUD Layout (A4 Print) --------
PAGE_SIZE = A4
M_L, M_R, M_T, M_B = 16*mm, 16*mm, 16*mm, 16*mm
HUD_TOP_H = 18*mm
HUD_BOTTOM_H = 22*mm


def _clamp_rgb(rgb):
    return tuple(max(0.0, min(1.0, float(x))) for x in rgb)


def draw_hud(c: canvas.Canvas, w: float, h: float, zone, hour: int, mission, difficulty: int, page_no: int):
    # Header background
    r, g, b = _clamp_rgb(zone.color)
    c.saveState()
    c.setFillColorRGB(r, g, b)
    c.rect(0, h - (HUD_TOP_H + M_T), w, HUD_TOP_H + M_T, fill=1, stroke=0)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(M_L, h - M_T - 12*mm, f"{zone.icon} {zone.name.upper()}")

    c.setFont("Helvetica", 10)
    c.drawString(M_L, h - M_T - 16*mm, f"{zone.quest_type} · {zone.atmosphere}")

    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(w - M_R, h - M_T - 12*mm, fmt_hour(hour))
    c.restoreState()

    # Footer mission card
    c.saveState()
    c.setFillColor(colors.white)
    c.setStrokeColor(colors.black)
    c.setLineWidth(1.2)
    c.roundRect(M_L, M_B, w - M_L - M_R, HUD_BOTTOM_H, 6, fill=1, stroke=1)

    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(M_L + 4*mm, M_B + HUD_BOTTOM_H - 8*mm, f"MISSION: {mission.title[:60]}")
    c.drawRightString(w - M_R - 4*mm, M_B + HUD_BOTTOM_H - 8*mm, f"+{mission.xp} XP")

    c.setFont("Helvetica", 10)
    c.drawString(M_L + 4*mm, M_B + 6*mm, f"DIFF: {difficulty}/5")
    c.drawRightString(w - M_R - 4*mm, M_B + 6*mm, f"PAGE: {page_no}")
    c.restoreState()


def draw_mission_text(c: canvas.Canvas, w: float, h: float, mission):
    y = M_B + HUD_BOTTOM_H + 8*mm
    c.setFont("Helvetica", 10)
    lines = [
        "Bewegung:",
        f"- {mission.movement}",
        "",
        "Denken (Ziel + mehrere Wege):",
        f"- {mission.thinking}",
        "",
        "Checkpoint:",
        f"- {mission.proof}",
    ]
    for line in lines:
        if y > h - (M_T + HUD_TOP_H) - 12*mm:
            break
        c.drawString(M_L, y, line[:120])
        y += 5*mm


def render_base_page_placeholder(c: canvas.Canvas, w: float, h: float, page_no: int):
    """
    Platzhalter, bis du deine Foto->Skizze Engine wieder einklinkst.
    """
    c.setLineWidth(1)
    x = M_L
    y = M_B + HUD_BOTTOM_H + 55*mm
    ww = w - M_L - M_R
    hh = h - (M_T + HUD_TOP_H) - y - 10*mm
    if hh < 40*mm:
        hh = 40*mm

    c.setFont("Helvetica-Bold", 14)
    c.drawString(x, y + hh + 6*mm, f"Aktivität / Skizze (Seite {page_no})")
    c.rect(x, y, ww, hh)

    c.setFont("Helvetica", 10)
    c.drawString(x + 4*mm, y + hh - 8*mm, "✎ Zeichne hier / löse hier")


def parse_start_hour(s: str) -> int:
    s = (s or "").strip()
    if not s:
        return 6
    if ":" in s:
        return int(s.split(":", 1)[0]) % 24
    return int(s) % 24


def build_pdf(pages: int, start_hour: int, difficulty: int, seed: int, show_text: bool):
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=PAGE_SIZE)
    w, h = PAGE_SIZE

    for p in range(1, pages + 1):
        hour = (start_hour + (p - 1)) % 24
        zone = get_zone_for_hour(hour)
        mission = pick_mission_for_time(hour, difficulty, seed, page_index=p)

        render_base_page_placeholder(c, w, h, p)  # <-- hier später Engine rein

        draw_hud(c, w, h, zone, hour, mission, difficulty, p)
        if show_text:
            draw_mission_text(c, w, h, mission)

        c.showPage()

    c.save()
    return buf.getvalue()


# -------- UI --------
st.title("📘 Quest-Logbuch Generator")
st.caption("Zeit → Zone → Mission. HUD oben/unten. Gamification ohne Wettbewerb.")

# Validation anzeigen (hilft beim Debug & verhindert Cloud-Schmerzen)
issues = validate_quest_db()
if issues:
    st.warning("Quest-DB Hinweise:\n- " + "\n- ".join(issues))

with st.form("f"):
    pages = st.selectbox("Seiten (KDP: 24)", [24, 16, 8], index=0)
    start_time = st.text_input("Startzeit (Stunde oder HH:MM)", value="06:00")
    difficulty = st.slider("Schwierigkeit (1–5)", 1, 5, 3)
    seed = st.number_input("Seed (Reproduzierbarkeit)", min_value=0, max_value=999999, value=1234, step=1)
    show_text = st.checkbox("Missionstext auf Seite drucken", value=True)
    go = st.form_submit_button("📄 PDF generieren")

if go:
    start_hour = parse_start_hour(start_time)
    pdf = build_pdf(int(pages), int(start_hour), int(difficulty), int(seed), bool(show_text))

    st.download_button(
        "⬇️ PDF herunterladen",
        data=pdf,
        file_name="quest_logbook.pdf",
        mime="application/pdf",
        use_container_width=True,
    )
