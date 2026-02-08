# ==========================================================
# QUEST DATABASE — v2.3+ (Unkaputtbar / Compat Edition)
# - 8 Zonen (Tageszeiten)
# - Missions: Bewegung + Denken + Proof + XP + Difficulty
# - 24h-Farb-System: 4 Familien x 6 Varianten (ohne Cyan)
# - Kompatibilitäts-Aliase: verhindert ImportError
# ==========================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple
import random


# ---------------------------
# DATA MODELS
# ---------------------------

@dataclass(frozen=True)
class Mission:
    id: str
    title: str
    movement: str
    thinking: str
    proof: str
    xp: int
    difficulty: int  # 1..5


@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    icon: str
    atmosphere: str
    quest_type: str
    time_ranges: List[Tuple[int, int]]  # (start, end_exclusive)
    missions: List[Mission]


# ---------------------------
# 24-STUNDEN FARB-SYSTEM
# 4 Familien x 6 Varianten = 24 Farben
# Keine Verläufe, kein Cyan/Türkis, starker Kontrast
# ---------------------------

RED6 = [
    (0.90, 0.10, 0.10),  # Rot
    (0.60, 0.00, 0.00),  # Dunkelrot
    (1.00, 0.40, 0.40),  # Hellrot
    (0.80, 0.00, 0.40),  # Beerenrot (Richtung Magenta)
    (1.00, 0.25, 0.00),  # Orangerot
    (0.50, 0.10, 0.10),  # Rostrot
]

BLUE6 = [
    (0.10, 0.10, 0.90),  # Blau
    (0.00, 0.00, 0.45),  # Navy
    (0.40, 0.50, 1.00),  # Kornblumenblau
    (0.20, 0.00, 0.70),  # Indigo
    (0.05, 0.20, 0.60),  # Ozeanblau (tief)
    (0.10, 0.10, 0.20),  # Mitternachtsblau
]

YELLOW6 = [
    (1.00, 0.85, 0.00),  # Goldgelb
    (1.00, 0.60, 0.00),  # Orange
    (0.95, 0.95, 0.60),  # Vanille/Creme
    (0.80, 0.70, 0.10),  # Senf
    (1.00, 0.75, 0.30),  # Apricot
    (0.92, 0.92, 0.92),  # Fast Weiß
]

GREEN6 = [
    (0.00, 0.65, 0.00),  # Grasgrün
    (0.00, 0.35, 0.00),  # Waldgrün
    (0.50, 0.80, 0.20),  # Limette/Apfelgrün
    (0.35, 0.45, 0.35),  # Salbei (grau-grün)
    (0.60, 0.90, 0.60),  # Pastellgrün
    (0.20, 0.30, 0.00),  # Moosgrün
]

# Rotation: R, B, Y, G, R, B, Y, G ... => Nachbarn sind NIE gleich.
HOUR_COLORS: List[Tuple[float, float, float]] = [
    RED6[0], BLUE6[0], YELLOW6[0], GREEN6[0],
    RED6[1], BLUE6[1], YELLOW6[1], GREEN6[1],
    RED6[2], BLUE6[2], YELLOW6[2], GREEN6[2],
    RED6[3], BLUE6[3], YELLOW6[3], GREEN6[3],
    RED6[4], BLUE6[4], YELLOW6[4], GREEN6[4],
    RED6[5], BLUE6[5], YELLOW6[5], GREEN6[5],
]


def get_hour_color(hour: int) -> Tuple[float, float, float]:
    """Gibt die spezifische Hintergrundfarbe für diese Stunde zurück (0..23)."""
    return HOUR_COLORS[hour % 24]


def best_text_color(rgb: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """
    Entscheidet ob Schwarz oder Weiß besser lesbar ist (Luma-Check).
    Gibt RGB zurück (0..1), passend für reportlab setFillColorRGB.
    """
    r, g, b = rgb
    luminance = (0.299 * r + 0.587 * g + 0.114 * b)
    # hell -> schwarz; dunkel -> weiß
    return (0.0, 0.0, 0.0) if luminance > 0.55 else (1.0, 1.0, 1.0)


# Alias (britische Schreibweise) – weil dein app.py das evtl. so importiert:
best_text_colour = best_text_color


# ---------------------------
# ZONEN (8-Zonen-System)
# Hinweis: "color" ist NICHT mehr nötig, weil 24h-Farben separat laufen.
# ---------------------------

ZONES: List[Zone] = [
    Zone(
        id="wachturm",
        name="Der Wachturm",
        icon="🏰",
        atmosphere="Aufwachen, Struktur",
        quest_type="Skill Quest",
        time_ranges=[(6, 9)],
        missions=[
            Mission("wt_01", "Rüstung anlegen", "10 Kniebeugen.", "ZIEL: Plane 2 Wege, dich morgens fertig zu machen.", "✅ Haken", 15, 1),
            Mission("wt_02", "Fokus-Reset", "30s auf einem Bein stehen.", "ZIEL: Finde 2 Strategien für einen guten Start.", "✅ Notiz", 20, 2),
            Mission("wt_03", "Zahn-Monster", "2 Min Zähne putzen + 10 Hampelmänner.", "ZIEL: Besiege die Bakterien.", "✅ Sauberes Lächeln", 20, 1),
        ],
    ),
    Zone(
        id="wilder_pfad",
        name="Wilder Pfad",
        icon="🌲",
        atmosphere="Weg, Draußen, Erkunden",
        quest_type="Exploration",
        time_ranges=[(9, 12)],
        missions=[
            Mission("wp_01", "Musterjäger", "Finde 3 rote Dinge und berühre sie.", "ZIEL: Zeichne ein Muster, das du siehst.", "✅ Skizze", 25, 2),
            Mission("wp_02", "Spurenleser", "Gehe 20 Schritte rückwärts.", "ZIEL: Finde einen Weg von A nach B.", "✅ Karte zeichnen", 30, 3),
        ],
    ),
    Zone(
        id="taverne",
        name="Die Taverne",
        icon="🍲",
        atmosphere="Essen, Energie tanken",
        quest_type="Energy Quest",
        time_ranges=[(12, 13)],
        missions=[
            Mission("tv_01", "Energie-Scan", "10x Kauen pro Bissen.", "ZIEL: Errate 3 Zutaten im Essen.", "✅ Liste", 20, 1),
            Mission("tv_02", "Wasser-Kraft", "Trinke ein Glas Wasser.", "ZIEL: Fühle, wie die Energie zurückkommt.", "✅ Check", 15, 1),
        ],
    ),
    Zone(
        id="werkstatt",
        name="Die Werkstatt",
        icon="🔨",
        atmosphere="Bauen, Kreativität",
        quest_type="Build Quest",
        time_ranges=[(13, 15)],
        missions=[
            Mission("ws_01", "Brückenbauer", "20 Armkreise.", "ZIEL: Baue eine Brücke aus Dingen im Raum.", "✅ Foto/Skizze", 30, 3),
            Mission("ws_02", "Turm-Ingenieur", "10 Liegestütze an der Wand.", "ZIEL: Baue den höchsten Turm.", "✅ Höhe messen", 35, 4),
        ],
    ),
    Zone(
        id="arena",
        name="Die Arena",
        icon="⚔️",
        atmosphere="Sport, Action",
        quest_type="Action Quest",
        time_ranges=[(15, 17)],
        missions=[
            Mission("ar_01", "Schatten-Boxen", "30s Boxen in die Luft.", "ZIEL: Sei schneller als dein Schatten.", "✅ Puls fühlen", 35, 3),
            Mission("ar_02", "Lava-Boden", "Berühre 1 Min nicht den Boden.", "ZIEL: Finde einen sicheren Weg.", "✅ Geschafft", 40, 4),
        ],
    ),
    Zone(
        id="ratssaal",
        name="Der Ratssaal",
        icon="🤝",
        atmosphere="Sozial, Familie, Helfen",
        quest_type="Social Quest",
        time_ranges=[(17, 19)],
        missions=[
            Mission("rs_01", "Der Bote", "Überbringe eine Nachricht flüsternd.", "ZIEL: Mache jemanden glücklich.", "✅ Lächeln erhalten", 45, 4),
            Mission("rs_02", "Tisch-Ritter", "Decke den Tisch in unter 2 Min.", "ZIEL: Helfen ist Ehrensache.", "✅ Alles am Platz", 40, 3),
        ],
    ),
    Zone(
        id="quellen",
        name="Die Quellen",
        icon="🛁",
        atmosphere="Bad, Hygiene",
        quest_type="Water Quest",
        time_ranges=[(19, 21)],
        missions=[
            Mission("qq_01", "Schaum-Krone", "Wasche dein Gesicht.", "ZIEL: Werde sauber für die Nacht.", "✅ Spiegel-Check", 25, 2),
            Mission("qq_02", "Zahn-Schutz", "3 Min Putzen.", "ZIEL: Keine Chance für Karius.", "✅ Sauber", 25, 2),
        ],
    ),
    Zone(
        id="trauminsel",
        name="Traum-Insel",
        icon="🌙",
        atmosphere="Schlaf, Ruhe",
        quest_type="Silent Quest",
        time_ranges=[(21, 24), (0, 6)],
        missions=[
            Mission("ti_01", "Traum-Fänger", "Augen zu, tief atmen.", "ZIEL: Erinnere dich an das Beste heute.", "✅ Gedanke", 20, 1),
            Mission("ti_02", "Stille Wacht", "Liege 1 Min ganz still.", "ZIEL: Lausche in die Nacht.", "✅ Ruhe", 20, 1),
        ],
    ),
]


# ---------------------------
# CORE API
# ---------------------------

def get_zone_for_hour(hour: int) -> Zone:
    """Zone für eine Stunde (0..23)."""
    h = hour % 24
    for z in ZONES:
        for start, end in z.time_ranges:
            if start <= h < end:
                return z
    return ZONES[0]


def pick_mission_for_time(hour: int, difficulty: int, seed: int) -> Mission:
    """Mission auswählen, gefiltert nach difficulty (<=) und seeded."""
    zone = get_zone_for_hour(hour)
    rng = random.Random(seed)

    # echte Schwierigkeits-Logik:
    pool = [m for m in zone.missions if m.difficulty <= int(difficulty)]
    if not pool:
        pool = zone.missions

    return rng.choice(pool)


def fmt_hour(hour: int) -> str:
    """HH:00 Format."""
    return f"{hour % 24:02d}:00"


# ---------------------------
# COMPAT LAYER (Import-Stabilität)
# ---------------------------

# Frühere Alias-Namen:
zone_for_hour = get_zone_for_hour
pick_mission = pick_mission_for_time

# Manche Versionen erwarten diese Namen:
get_zone_for_time = get_zone_for_hour  # falls irgendwo so importiert
get_zone_for_hour = get_zone_for_hour  # explizit
