# ==========================================================
# QUEST DATABASE (Single Source of Quest Truth) — v2.2
# - Zones: 8 thematische Lernwelten (00-24h)
# - Missions: Sportliche Aktivierung + Denkauftrag
# - XP: Gamification ohne Wettbewerb
# - Cloud-safe API: compat layer für alte/new app.py
# ==========================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple
import random


# ---------------------------
# DATA MODELS
# ---------------------------

@dataclass(frozen=True)
class Mission:
    id: str
    title: str
    movement: str        # Sportliche Aufgabe (ortsunabhängig)
    thinking: str        # Denkauftrag (konvergentes Ziel, mehrere Wege)
    proof: str           # Nachweis (Haken/Unterschrift/Code)
    xp: int
    difficulty: int      # 1..5


@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    icon: str
    atmosphere: str
    quest_type: str
    time_ranges: List[Tuple[int, int]]          # (start, end_exclusive), 0..24
    color: Tuple[float, float, float]           # RGB 0..1 für PDF Header
    missions: List[Mission]


# ---------------------------
# ZONES (8-Zonen-System)
# ---------------------------

ZONES: List[Zone] = [
    Zone(
        id="wachturm",
        name="Der Wachturm",
        icon="🏰",
        atmosphere="Aufwachen, Struktur",
        quest_type="Skill Quest",
        time_ranges=[(6, 9)],
        color=(0.95, 0.95, 0.85),
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
        color=(0.85, 0.95, 0.85),
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
        color=(1.0, 0.9, 0.8),
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
        color=(0.9, 0.9, 1.0),
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
        color=(1.0, 0.85, 0.85),
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
        color=(0.95, 0.85, 0.95),
        missions=[
            Mission("rs_01", "Der Bote", "Überbringe eine Nachricht flüsternd.", "ZIEL: Mache jemandem eine Freude.", "✅ Lächeln erhalten", 45, 4),
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
        color=(0.8, 0.95, 1.0),
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
        color=(0.15, 0.15, 0.35),
        missions=[
            Mission("ti_01", "Traum-Fänger", "Augen zu, tief atmen.", "ZIEL: Erinnere dich an das Beste heute.", "✅ Gedanke", 20, 1),
            Mission("ti_02", "Stille Wacht", "Liege 1 Min ganz still.", "ZIEL: Lausche in die Nacht.", "✅ Ruhe", 20, 1),
        ],
    ),
]


# ---------------------------
# INTERNAL HELPERS
# ---------------------------

def _clamp_rgb(rgb: Tuple[float, float, float]) -> Tuple[float, float, float]:
    return tuple(max(0.0, min(1.0, float(x))) for x in rgb)  # type: ignore

def _iter_hours_in_ranges(ranges: Iterable[Tuple[int, int]]) -> Iterable[int]:
    for start, end in ranges:
        start %= 24
        end %= 24
        if start < end:
            for h in range(start, end):
                yield h
        else:
            # wrap-around (z.B. 21-24 + 0-6 ist hier nicht nötig, aber robust)
            for h in range(start, 24):
                yield h
            for h in range(0, end):
                yield h


# ---------------------------
# PUBLIC API: TIME -> ZONE -> MISSION
# ---------------------------

def get_zone_for_hour(hour: int) -> Zone:
    h = hour % 24
    for z in ZONES:
        for start, end in z.time_ranges:
            if start <= h < end:
                return z
    return ZONES[0]  # Fallback: Wachturm


def pick_mission_for_time(
    hour: int,
    difficulty: int,
    seed: int,
    *,
    avoid_repeat: bool = True,
    page_index: int = 0,
) -> Mission:
    """
    Deterministische Mission-Auswahl pro Seite.
    - difficulty: 1..5
    - seed: Basis-Seed (Reproduzierbarkeit)
    - avoid_repeat: versucht Wiederholungen in der Zone zu vermeiden (best effort)
    - page_index: damit Seite 1..N unterschiedliche Picks bekommen
    """
    z = get_zone_for_hour(hour)

    diff = int(max(1, min(5, difficulty)))
    rng = random.Random(int(seed) + int(page_index) * 10007)

    pool = [m for m in z.missions if m.difficulty <= diff] or z.missions

    if not avoid_repeat or len(pool) <= 1:
        return rng.choice(pool)

    # "No-repeat": deterministic rotate/shuffle
    shuffled = pool[:]
    rng.shuffle(shuffled)
    idx = (int(seed) + int(page_index)) % len(shuffled)
    return shuffled[idx]


def fmt_hour(hour: int) -> str:
    return f"{hour % 24:02d}:00"


# ---------------------------
# VALIDATION (optional but recommended)
# ---------------------------

def validate_quest_db(raise_on_error: bool = False) -> List[str]:
    """
    Gibt eine Liste von Warnungen/Fehlern zurück.
    Wenn raise_on_error=True und es gibt Fehler -> ValueError.
    """
    issues: List[str] = []

    # Unique Zone IDs
    zone_ids = [z.id for z in ZONES]
    if len(zone_ids) != len(set(zone_ids)):
        issues.append("Zone IDs sind nicht eindeutig.")

    # Unique Mission IDs across all zones
    mission_ids: List[str] = [m.id for z in ZONES for m in z.missions]
    if len(mission_ids) != len(set(mission_ids)):
        issues.append("Mission IDs sind nicht eindeutig (global).")

    # Validate ranges and cover set (soft check)
    covered: set[int] = set()
    for z in ZONES:
        # clamp color
        _ = _clamp_rgb(z.color)

        if not z.time_ranges:
            issues.append(f"Zone '{z.id}' hat keine time_ranges.")
            continue

        for start, end in z.time_ranges:
            if not (0 <= start <= 24 and 0 <= end <= 24):
                issues.append(f"Zone '{z.id}' hat ungültige time_range ({start},{end}).")
            if start == end:
                issues.append(f"Zone '{z.id}' hat eine leere time_range ({start},{end}).")

        # add covered hours (best-effort)
        for h in _iter_hours_in_ranges(z.time_ranges):
            covered.add(h)

        # mission sanity
        for m in z.missions:
            if not (1 <= m.difficulty <= 5):
                issues.append(f"Mission '{m.id}' in Zone '{z.id}' hat difficulty außerhalb 1..5.")
            if m.xp < 0:
                issues.append(f"Mission '{m.id}' in Zone '{z.id}' hat negatives XP.")
            if not m.title.strip():
                issues.append(f"Mission '{m.id}' in Zone '{z.id}' hat leeren Titel.")

    # Soft coverage check: should cover most of day
    if len(covered) < 18:
        issues.append(f"Warnung: nur {len(covered)}/24 Stunden sind durch time_ranges abgedeckt.")

    if raise_on_error and issues:
        raise ValueError("Quest DB Validation failed:\n- " + "\n- ".join(issues))

    return issues


# ---------------------------
# UI HELPERS (optional)
# ---------------------------

def list_zones() -> List[Tuple[str, str]]:
    """Für Dropdowns: [(zone_id, '🏰 Der Wachturm'), ...]"""
    return [(z.id, f"{z.icon} {z.name}") for z in ZONES]

def get_zone_by_id(zone_id: str) -> Optional[Zone]:
    zid = (zone_id or "").strip()
    for z in ZONES:
        if z.id == zid:
            return z
    return None

def summarize_zone(zone: Zone) -> str:
    """Kurztext für UI/Logs."""
    return f"{zone.icon} {zone.name} · {zone.quest_type} · {zone.atmosphere}"


# ---------------------------
# COMPAT LAYER (WICHTIG!)
# ---------------------------
# Damit ALTE app.py und NEUE app.py Imports funktionieren:
zone_for_hour = get_zone_for_hour
pick_mission = pick_mission_for_time
