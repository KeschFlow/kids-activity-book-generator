"""
Quest Database (v2.3)
This module defines the data structures and functions used to drive the
quest‑driven version of Eddie's world.  It contains eight themed zones
covering the 24‑hour day.  Each zone defines a handful of missions
including a physical movement task, a thinking challenge, a proof
mechanism and XP reward.  The core API exposes helpers to look up the
appropriate zone for a given hour and to select a mission based on a
requested difficulty level.  It also provides a helper to format
hours consistently for display in the PDF generator.

The data structures are immutable thanks to the use of dataclasses
with ``frozen=True``, ensuring that missions and zones cannot be
accidentally mutated at runtime.

Functions ``zone_for_hour`` and ``pick_mission`` are provided as
backwards compatible aliases so existing import sites from earlier
versions continue to work without changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Tuple
import random


@dataclass(frozen=True)
class Mission:
    """Represents a single mission within a zone.

    :param id: Unique identifier for the mission.
    :param title: Short title describing the mission.
    :param movement: A physical exercise or movement to perform.
    :param thinking: A cognitive challenge or objective.
    :param proof: The form of completion proof required.
    :param xp: Experience points awarded on completion.
    :param difficulty: Difficulty rating on a scale from 1 (easy) to 5 (hard).
    """

    id: str
    title: str
    movement: str
    thinking: str
    proof: str
    xp: int
    difficulty: int


@dataclass(frozen=True)
class Zone:
    """Represents a themed area of the day with its own missions.

    :param id: Unique identifier for the zone.
    :param name: Human‑readable name of the zone.
    :param icon: Emoji or symbol associated with the zone.
    :param atmosphere: Text describing the mood or setting.
    :param quest_type: High level classification of quests in the zone.
    :param time_ranges: List of (start, end_exclusive) hour tuples when the zone is active.
    :param color: RGB triple used for styling headers (values between 0 and 1).
    :param missions: List of missions available in this zone.
    """

    id: str
    name: str
    icon: str
    atmosphere: str
    quest_type: str
    time_ranges: List[Tuple[int, int]]
    color: Tuple[float, float, float]
    missions: List[Mission]


# ----------------------------------------------------------------------
# Zones definition
# ----------------------------------------------------------------------

ZONES: List[Zone] = [
    Zone(
        id="wachturm",
        name="Der Wachturm",
        icon="🏰",
        atmosphere="Aufwachen, Struktur",
        quest_type="Skill Quest",
        time_ranges=[(6, 9)],
        color=(0.95, 0.95, 0.85),  # Morgengelb
        missions=[
            Mission(
                "wt_01",
                "Rüstung anlegen",
                "10 Kniebeugen.",
                "ZIEL: Plane 2 Wege, dich morgens fertig zu machen.",
                "✅ Haken",
                15,
                1,
            ),
            Mission(
                "wt_02",
                "Fokus‑Reset",
                "30 s auf einem Bein stehen.",
                "ZIEL: Finde 2 Strategien für einen guten Start.",
                "✅ Notiz",
                20,
                2,
            ),
            Mission(
                "wt_03",
                "Zahn‑Monster",
                "2 Min Zähne putzen + 10 Hampelmänner.",
                "ZIEL: Besiege die Bakterien.",
                "✅ Sauberes Lächeln",
                20,
                1,
            ),
        ],
    ),
    Zone(
        id="wilder_pfad",
        name="Wilder Pfad",
        icon="🌲",
        atmosphere="Weg, Draußen, Erkunden",
        quest_type="Exploration",
        time_ranges=[(9, 12)],
        color=(0.85, 0.95, 0.85),  # Naturgrün
        missions=[
            Mission(
                "wp_01",
                "Musterjäger",
                "Finde 3 rote Dinge und berühre sie.",
                "ZIEL: Zeichne ein Muster, das du siehst.",
                "✅ Skizze",
                25,
                2,
            ),
            Mission(
                "wp_02",
                "Spurenleser",
                "Gehe 20 Schritte rückwärts.",
                "ZIEL: Finde einen Weg von A nach B.",
                "✅ Karte zeichnen",
                30,
                3,
            ),
        ],
    ),
    Zone(
        id="taverne",
        name="Die Taverne",
        icon="🍲",
        atmosphere="Essen, Energie tanken",
        quest_type="Energy Quest",
        time_ranges=[(12, 13)],
        color=(1.0, 0.9, 0.8),  # Suppen‑Orange
        missions=[
            Mission(
                "tv_01",
                "Energie‑Scan",
                "10× Kauen pro Bissen.",
                "ZIEL: Errate 3 Zutaten im Essen.",
                "✅ Liste",
                20,
                1,
            ),
            Mission(
                "tv_02",
                "Wasser‑Kraft",
                "Trinke ein Glas Wasser.",
                "ZIEL: Fühle, wie die Energie zurückkommt.",
                "✅ Check",
                15,
                1,
            ),
        ],
    ),
    Zone(
        id="werkstatt",
        name="Die Werkstatt",
        icon="🔨",
        atmosphere="Bauen, Kreativität",
        quest_type="Build Quest",
        time_ranges=[(13, 15)],
        color=(0.9, 0.9, 1.0),  # Werkstatt‑Blau
        missions=[
            Mission(
                "ws_01",
                "Brückenbauer",
                "20 Armkreise.",
                "ZIEL: Baue eine Brücke aus Dingen im Raum.",
                "✅ Foto/Skizze",
                30,
                3,
            ),
            Mission(
                "ws_02",
                "Turm‑Ingenieur",
                "10 Liegestütze an der Wand.",
                "ZIEL: Baue den höchsten Turm.",
                "✅ Höhe messen",
                35,
                4,
            ),
        ],
    ),
    Zone(
        id="arena",
        name="Die Arena",
        icon="⚔️",
        atmosphere="Sport, Action",
        quest_type="Action Quest",
        time_ranges=[(15, 17)],
        color=(1.0, 0.85, 0.85),  # Action‑Rot
        missions=[
            Mission(
                "ar_01",
                "Schatten‑Boxen",
                "30 s Boxen in die Luft.",
                "ZIEL: Sei schneller als dein Schatten.",
                "✅ Puls fühlen",
                35,
                3,
            ),
            Mission(
                "ar_02",
                "Lava‑Boden",
                "Berühre 1 Min nicht den Boden.",
                "ZIEL: Finde einen sicheren Weg.",
                "✅ Geschafft",
                40,
                4,
            ),
        ],
    ),
    Zone(
        id="ratssaal",
        name="Der Ratssaal",
        icon="🤝",
        atmosphere="Sozial, Familie, Helfen",
        quest_type="Social Quest",
        time_ranges=[(17, 19)],
        color=(0.95, 0.85, 0.95),  # Lila‑Gemeinschaft
        missions=[
            Mission(
                "rs_01",
                "Der Bote",
                "Überbringe eine Nachricht flüsternd.",
                "ZIEL: Mache jemanden glücklich.",
                "✅ Lächeln erhalten",
                45,
                4,
            ),
            Mission(
                "rs_02",
                "Tisch‑Ritter",
                "Decke den Tisch in unter 2 Min.",
                "ZIEL: Helfen ist Ehrensache.",
                "✅ Alles am Platz",
                40,
                3,
            ),
        ],
    ),
    Zone(
        id="quellen",
        name="Die Quellen",
        icon="🛁",
        atmosphere="Bad, Hygiene",
        quest_type="Water Quest",
        time_ranges=[(19, 21)],
        color=(0.8, 0.95, 1.0),  # Wasserblau
        missions=[
            Mission(
                "qq_01",
                "Schaum‑Krone",
                "Wasche dein Gesicht.",
                "ZIEL: Werde sauber für die Nacht.",
                "✅ Spiegel‑Check",
                25,
                2,
            ),
            Mission(
                "qq_02",
                "Zahn‑Schutz",
                "3 Min Putzen.",
                "ZIEL: Keine Chance für Karius.",
                "✅ Sauber",
                25,
                2,
            ),
        ],
    ),
    Zone(
        id="trauminsel",
        name="Traum‑Insel",
        icon="🌙",
        atmosphere="Schlaf, Ruhe",
        quest_type="Silent Quest",
        time_ranges=[(21, 24), (0, 6)],
        color=(0.15, 0.15, 0.35),  # Nachtblau
        missions=[
            Mission(
                "ti_01",
                "Traum‑Fänger",
                "Augen zu, tief atmen.",
                "ZIEL: Erinnere dich an das Beste heute.",
                "✅ Gedanke",
                20,
                1,
            ),
            Mission(
                "ti_02",
                "Stille Wacht",
                "Liege 1 Min ganz still.",
                "ZIEL: Lausche in die Nacht.",
                "✅ Ruhe",
                20,
                1,
            ),
        ],
    ),
]


def get_zone_for_hour(hour: int) -> Zone:
    """Return the zone active at the specified hour.

    Hours wrap around a 24‑hour day.  If no matching range is
    found (which should not occur), the first zone is returned as a
    fallback.

    :param hour: Hour of day (0‑23).  Values outside this range are
        normalised using modulo 24.
    :return: The zone covering the given hour.
    """
    h = hour % 24
    for zone in ZONES:
        for start, end in zone.time_ranges:
            if start <= h < end:
                return zone
    return ZONES[0]


def pick_mission_for_time(hour: int, difficulty: int, seed: int) -> Mission:
    """Select a mission for a given hour and difficulty.

    Random selection uses the provided seed to ensure deterministic
    choice across calls.  Missions with a difficulty rating greater
    than the requested level are excluded from the pool where
    possible; if none remain, the full mission list is used.

    :param hour: Hour of day (0‑23).
    :param difficulty: Maximum desired difficulty (1–5).
    :param seed: Seed value for the random number generator.
    :return: A single Mission instance.
    """
    zone = get_zone_for_hour(hour)
    rng = random.Random(seed)
    candidates = [m for m in zone.missions if m.difficulty <= difficulty]
    if not candidates:
        candidates = zone.missions
    return rng.choice(candidates)


def fmt_hour(hour: int) -> str:
    """Format an hour integer into 24‑hour HH:00 format.

    :param hour: Hour to format.
    :return: Formatted string with leading zero, e.g. ``03:00``.
    """
    return f"{hour % 24:02d}:00"


# ----------------------------------------------------------------------
# Backwards compatibility
# ----------------------------------------------------------------------

# Provide aliases for earlier version of the API.  External code that
# imports ``zone_for_hour`` or ``pick_mission`` will still work
# correctly after upgrading to this version.
zone_for_hour = get_zone_for_hour
pick_mission = pick_mission_for_time
