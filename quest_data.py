# ==========================================================
# QUEST DATABASE — Eddie's Welt (Golden Master v2.3)
# ==========================================================

from dataclasses import dataclass
from typing import List, Tuple
import random

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
    time_ranges: List[Tuple[int, int]]
    color: Tuple[float, float, float]
    missions: List[Mission]

ZONES: List[Zone] = [
    Zone(
        "wachturm","Der Wachturm","🏰","Aufwachen & Struktur","Skill Quest",
        [(6,9)], (0.95,0.95,0.85),
        [
            Mission("wt1","Rüstung anlegen","10 Kniebeugen","Plane deinen Start","✅ Haken",15,1),
            Mission("wt2","Zahn-Monster","2 Min Zähne putzen","Besiege die Bakterien","✅ Spiegel",20,1),
        ]
    ),
    Zone(
        "wilderpfad","Wilder Pfad","🌲","Erkunden","Exploration",
        [(9,12)], (0.85,0.95,0.85),
        [
            Mission("wp1","Musterjäger","Finde 3 rote Dinge","Zeichne ein Muster","✅ Skizze",25,2),
            Mission("wp2","Spurenleser","20 Schritte rückwärts","Finde einen Weg","✅ Karte",30,3),
        ]
    ),
    Zone(
        "taverne","Die Taverne","🍲","Energie tanken","Energy Quest",
        [(12,13)], (1.0,0.9,0.8),
        [
            Mission("tv1","Energie-Scan","Langsam essen","Errate Zutaten","✅ Liste",20,1),
        ]
    ),
    Zone(
        "werkstatt","Die Werkstatt","🔨","Bauen","Build Quest",
        [(13,15)], (0.9,0.9,1.0),
        [
            Mission("ws1","Brückenbauer","20 Armkreise","Baue eine Brücke","✅ Foto",30,3),
        ]
    ),
    Zone(
        "arena","Die Arena","⚔️","Action","Action Quest",
        [(15,17)], (1.0,0.85,0.85),
        [
            Mission("ar1","Schattenboxen","30s Boxen","Sei schneller","✅ Puls",35,3),
        ]
    ),
    Zone(
        "ratssaal","Der Ratssaal","🤝","Sozial","Social Quest",
        [(17,19)], (0.95,0.85,0.95),
        [
            Mission("rs1","Der Bote","Nachricht überbringen","Jemandem helfen","✅ Lächeln",40,4),
        ]
    ),
    Zone(
        "quellen","Die Quellen","🛁","Hygiene","Water Quest",
        [(19,21)], (0.8,0.95,1.0),
        [
            Mission("qq1","Zahn-Schutz","3 Min putzen","Schlaf vorbereiten","✅ Sauber",25,2),
        ]
    ),
    Zone(
        "trauminsel","Traum-Insel","🌙","Ruhe","Silent Quest",
        [(21,24),(0,6)], (0.15,0.15,0.35),
        [
            Mission("ti1","Traum-Fänger","Augen schließen","Bestes heute merken","✅ Gedanke",20,1),
        ]
    ),
]

def get_zone_for_hour(hour: int) -> Zone:
    h = hour % 24
    for z in ZONES:
        for s,e in z.time_ranges:
            if s <= h < e:
                return z
    return ZONES[0]

def pick_mission_for_time(hour: int, difficulty: int, seed: int) -> Mission:
    z = get_zone_for_hour(hour)
    rng = random.Random(seed)
    pool = [m for m in z.missions if m.difficulty <= difficulty]
    if not pool:
        pool = z.missions
    return rng.choice(pool)

def fmt_hour(hour: int) -> str:
    return f"{hour%24:02d}:00"

# Compat
zone_for_hour = get_zone_for_hour
pick_mission = pick_mission_for_time
