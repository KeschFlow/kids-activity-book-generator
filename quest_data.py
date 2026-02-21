# =========================================================
# quest_data.py — E.P.E. Eddie's Print Engine — v6 CONTENT CORE
#
# DESIGN RULES (non-negotiable):
# 1) Markenschutz:
#    - Quests sprechen NUR die Umgebung an (Sterne, Quadrate, Dreiecke, Formen, Muster).
#    - Eddie bleibt unangetastet (schwarz/weiß + purpur Zunge) -> NIE auffordern Eddie zu färben.
#
# 2) KDP-Sicherheit:
#    - proof / note sind bewusst KURZ.
#    - get_quest dedupliziert über qid. Wenn Pool leer: Reset-Pick (stabil).
#
# 3) Drop-in API:
#    - get_quest(pool, used_ids, rng, tags_any=None) -> QuestItem(qid,text,tags)
#    - get_zone_for_hour(hour) -> Zone
#    - get_hour_color(hour) -> (r,g,b) floats 0..1
#    - fmt_hour(hour) -> "HH:00"
# =========================================================

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
import math
import random

# =========================================================
# DATA MODELS
# =========================================================

@dataclass(frozen=True)
class QuestItem:
    qid: str
    text: str
    tags: Set[str]

@dataclass(frozen=True)
class Zone:
    name: str
    icon: str
    quest_type: str
    atmosphere: str

# =========================================================
# ZONES (world-building)
# =========================================================

_ZONES: List[Tuple[range, Zone]] = [
    (range(6, 11),  Zone("Morgen-Start",      "🌤️", "Warm-up",     "ruhig")),
    (range(11, 16), Zone("Mittags-Mission",   "🌞", "Action",      "wach")),
    (range(16, 21), Zone("Nachmittags-Boost", "🟣", "Abenteuer",   "spielerisch")),
    (range(21, 24), Zone("Abend-Ruhe",        "🌙", "Runterfahren","sanft")),
    (range(0, 6),   Zone("Nacht-Wache",       "🌙", "Leise Quest", "still")),
]

def get_zone_for_hour(hour: int) -> Zone:
    h = int(hour) % 24
    for r, z in _ZONES:
        if h in r:
            return z
    return Zone("Zone", "🟣", "Quest", "")

def get_hour_color(hour: int) -> Tuple[float, float, float]:
    # Smooth 24h gradient (pleasant + print-safe)
    h = float(int(hour) % 24)
    t = h / 24.0
    # slightly purplish vibe toward evening
    r = 0.45 + 0.20 * (1.0 - t)
    g = 0.22 + 0.12 * t
    b = 0.78 - 0.18 * t
    # clamp
    r = max(0.0, min(1.0, r))
    g = max(0.0, min(1.0, g))
    b = max(0.0, min(1.0, b))
    return (r, g, b)

def fmt_hour(hour: int) -> str:
    return f"{int(hour)%24:02d}:00"

# =========================================================
# POOLS — “quest” must be 240+ fully worded items
# =========================================================

# --- QUESTS (240+ unique, environment-only instructions)
# Keep these short-ish, but “ausformuliert” (complete sentences).
QUEST_TEXTS: List[str] = [
    # --- Set A: Color/Spot tasks (forms only)
    "Male alle Sterne im Bild aus, aber lass die weißen Flächen so wie sie sind.",
    "Färbe nur die Quadrate aus und ignoriere alles andere.",
    "Male alle Dreiecke aus und bleib dabei sorgfältig in den Linien.",
    "Gib den Sternen eine Farbe deiner Wahl – die restliche Szene bleibt unverändert.",
    "Male die Quadrate in zwei verschiedenen Farben abwechselnd aus.",
    "Färbe die Dreiecke von oben nach unten, Reihe für Reihe.",
    "Male nur die kleinsten Sterne aus, die großen bleiben leer.",
    "Färbe nur die größten Quadrate aus und lass kleine Quadrate frei.",
    "Male die Dreiecke so aus, dass jedes Dreieck eine andere Farbe bekommt.",
    "Färbe alle Sterne aus und setze in jedes Quadrat einen Punkt.",
    "Male alle Quadrate aus und ziehe um jedes Dreieck eine dünne Linie.",
    "Färbe alle Dreiecke aus und male die Sterne nur mit Punkten an.",
    "Male jeden zweiten Stern aus – beginne oben links.",
    "Färbe jedes dritte Quadrat aus – zähle dabei laut mit.",
    "Male jedes zweite Dreieck aus – starte bei dem Dreieck, das dir zuerst auffällt.",
    "Gib den Sternen einen hellen Rand und eine dunklere Mitte.",
    "Male die Quadrate mit Streifen aus, nicht flächig.",
    "Färbe die Dreiecke mit Punkten aus, nicht flächig.",
    "Male die Sterne so, als wären sie glitzernd: viele kleine Punkte.",
    "Färbe die Quadrate so, als wären sie Ziegelsteine: kleine Linien.",
    "Male die Dreiecke so, als wären sie Berge: oben heller, unten dunkler.",
    "Färbe alle Sterne aus, aber lass einen Stern als „Geheimstern“ weiß.",
    "Male alle Quadrate aus, aber lass ein Quadrat als „Geheimquadrat“ leer.",
    "Färbe alle Dreiecke aus, aber lass ein Dreieck als „Geheimdreieck“ weiß.",
    "Male Sterne und Quadrate aus, aber keine Dreiecke.",
    "Male Sterne und Dreiecke aus, aber keine Quadrate.",
    "Male Quadrate und Dreiecke aus, aber keine Sterne.",
    "Färbe nur Formen, die du in der oberen Hälfte siehst.",
    "Färbe nur Formen, die du in der unteren Hälfte siehst.",
    "Male nur Formen aus, die nahe am Rand liegen.",
    "Male nur Formen aus, die in der Mitte liegen.",
    "Färbe alle Sterne aus und verbinde zwei Sterne mit einer Linie.",
    "Male alle Quadrate aus und verbinde zwei Quadrate mit einer Linie.",
    "Färbe alle Dreiecke aus und verbinde zwei Dreiecke mit einer Linie.",
    "Male Sterne aus und zähle dabei: eins, zwei, drei …",
    "Färbe Quadrate aus und zähle dabei: eins, zwei, drei …",
    "Male Dreiecke aus und zähle dabei: eins, zwei, drei …",
    "Male die Sterne aus und gib jedem Stern einen Namen im Kopf.",
    "Färbe die Quadrate aus und stell dir vor, es sind Fenster.",
    "Male die Dreiecke aus und stell dir vor, es sind Dächer.",
    "Male jede Form aus, die du zuerst siehst, und lass die letzte Form frei.",
    "Färbe die Formen aus, die am weitesten voneinander entfernt sind.",
    "Male die Formen aus, die am nächsten beieinander liegen.",
    "Färbe alle Sterne aus und male in jedes Dreieck einen kleinen Punkt.",
    "Male alle Quadrate aus und male in jeden Stern einen kleinen Punkt.",
    "Färbe alle Dreiecke aus und male in jedes Quadrat einen kleinen Punkt.",
    "Male die Formen aus, die sich wie eine kleine Gruppe anfühlen.",
    "Färbe die Formen aus, die allein stehen und keine Nachbarn haben.",
    "Male nur die Formen aus, die du ohne zu drehen sofort erkennst.",
    "Färbe nur die Formen aus, die gedreht wirken.",
    "Male die Sterne aus, aber nur mit sehr leichtem Druck.",
    "Färbe die Quadrate aus, aber nur mit sehr leichtem Druck.",
    "Male die Dreiecke aus, aber nur mit sehr leichtem Druck.",

    # --- Set B: Pattern / logic flavor (still environment-only)
    "Male die Sterne in einem Farbwechsel: hell, dunkel, hell, dunkel.",
    "Färbe die Quadrate im Muster: rot-blau-rot-blau (oder zwei Farben deiner Wahl).",
    "Male die Dreiecke im Muster: Farbe A, Farbe B, Farbe C, wiederhole.",
    "Färbe nur Formen, die du mit einem Blick zählen kannst.",
    "Male Formen aus, bis du bei zehn angekommen bist – dann stopp.",
    "Färbe genau fünf Sterne aus, nicht mehr.",
    "Male genau fünf Quadrate aus, nicht mehr.",
    "Färbe genau fünf Dreiecke aus, nicht mehr.",
    "Male die Sterne aus, die am höchsten liegen.",
    "Färbe die Quadrate aus, die am niedrigsten liegen.",
    "Male die Dreiecke aus, die am weitesten rechts liegen.",
    "Färbe die Formen aus, die am weitesten links liegen.",
    "Male zuerst alle Sterne aus, dann alle Quadrate, dann alle Dreiecke.",
    "Färbe zuerst alle Dreiecke aus, dann alle Sterne, dann alle Quadrate.",
    "Male zuerst alle Quadrate aus, dann alle Dreiecke, dann alle Sterne.",
    "Färbe die Sterne aus und lass die Quadrate als Checkliste leer.",
    "Male die Quadrate aus und lass die Dreiecke als Checkliste leer.",
    "Färbe die Dreiecke aus und lass die Sterne als Checkliste leer.",
    "Male jede Form aus, die du zweimal siehst: eine Farbe außen, eine innen.",
    "Färbe die Formen in „Familien“: gleiche Form = gleiche Farbe.",
    "Male die Sterne in einer Farbe, die Quadrate in einer anderen, die Dreiecke in einer dritten.",
    "Färbe die Sterne warm (gelb/orange), die Quadrate kühl (blau/grün), die Dreiecke neutral (grau/braun).",
    "Male die Formen so aus, als wäre es Tag: helle Farben.",
    "Färbe die Formen so aus, als wäre es Nacht: dunklere Farben.",
    "Male die Formen so aus, als wäre es Regen: viele kleine Striche.",
    "Färbe die Formen so aus, als wäre es Wind: leichte, schnelle Linien.",
    "Male die Formen so aus, als wären sie aus Holz: Maser-Linien.",
    "Färbe die Formen so aus, als wären sie aus Stein: kleine Punkte und Flecken.",
    "Male die Formen so aus, als wären sie aus Metall: glänzende Kanten (hell) und Schatten (dunkel).",
    "Färbe nur Formen aus, die du innerhalb von 10 Sekunden findest.",
    "Male Formen aus und setze danach einen Haken neben die letzte Form.",
    "Färbe Sterne aus und zeichne um jeden Stern eine zweite Umrandung.",
    "Male Quadrate aus und zeichne um jedes Quadrat eine zweite Umrandung.",
    "Färbe Dreiecke aus und zeichne um jedes Dreieck eine zweite Umrandung.",
    "Male die Formen aus, die wie eine Spur von oben nach unten aussehen.",
    "Färbe die Formen aus, die wie eine Spur von links nach rechts aussehen.",
    "Male eine Form aus, dann suche eine andere Form und male sie aus – immer im Wechsel.",
    "Färbe zwei Sterne, dann ein Quadrat, dann ein Dreieck – wiederhole das Muster.",
    "Male ein Quadrat, dann ein Dreieck, dann einen Stern – wiederhole das Muster.",
    "Färbe die Sterne aus und lass einen Stern als „Startpunkt“ besonders hell.",
    "Male die Quadrate aus und lass ein Quadrat als „Startpunkt“ besonders hell.",
    "Färbe die Dreiecke aus und lass ein Dreieck als „Startpunkt“ besonders hell.",
    "Male die Formen aus, die du zuerst in der Ecke findest.",
    "Färbe die Formen aus, die du zuerst nahe der Mitte findest.",
    "Male die Sterne aus und gib jedem Stern eine kleine Krone (3 Zacken).",
    "Färbe die Quadrate aus und gib jedem Quadrat einen kleinen Griff (wie eine Tür).",
    "Male die Dreiecke aus und gib jedem Dreieck eine kleine Fahne oben drauf.",
    "Färbe Sterne aus und mach in die Mitte jedes Sterns einen Punkt.",
    "Male Quadrate aus und mach in die Mitte jedes Quadrats ein Kreuz.",
    "Färbe Dreiecke aus und mach in die Mitte jedes Dreiecks einen Punkt.",

    # --- Set C: “Careful” constraints (print-safe)
    "Male nur innerhalb der Formen – keine Farbe außerhalb der Linien.",
    "Färbe die Formen langsam aus und halte Pausen zwischen den Formen.",
    "Male die Formen mit kurzen Strichen aus, nicht mit langen.",
    "Färbe die Formen mit kreisenden Bewegungen aus, ganz weich.",
    "Male die Formen mit einer einzigen Farbe und wechsle nicht.",
    "Färbe die Formen mit zwei Farben, aber ohne zu mischen.",
    "Male die Sterne aus und lass die Spitze jedes Sterns weiß.",
    "Färbe die Quadrate aus und lass den Rand jedes Quadrats weiß.",
    "Male die Dreiecke aus und lass eine Ecke jedes Dreiecks weiß.",
    "Färbe nur die Formen, die vollständig zu sehen sind.",
    "Male nur die Formen, die teilweise abgeschnitten wirken.",
    "Färbe die Formen, die du am schwierigsten findest, zuerst.",
    "Male die Formen, die du am einfachsten findest, zuerst.",
    "Färbe genau so viele Formen aus, wie du an einer Hand zählen kannst.",
    "Male genau so viele Formen aus, wie du an zwei Händen zählen kannst.",
    "Färbe die Formen aus und stoppe nach jeder dritten Form kurz.",
    "Male die Formen aus und atme nach jeder Form einmal tief ein und aus.",
    "Färbe die Sterne aus und mach die Sterne unterschiedlich groß mit der Farbe (hell/dunkel).",
    "Male die Quadrate aus und mach ein Quadrat besonders dunkel als „Boss-Quadrat“.",
    "Färbe die Dreiecke aus und mach ein Dreieck besonders dunkel als „Boss-Dreieck“.",
    "Male Formen aus, bis du drei Sterne gefunden hast – dann stopp.",
    "Färbe Formen aus, bis du drei Quadrate gefunden hast – dann stopp.",
    "Male Formen aus, bis du drei Dreiecke gefunden hast – dann stopp.",
    "Färbe die Formen, die oben liegen, heller als die, die unten liegen.",
    "Male die Formen, die links liegen, heller als die, die rechts liegen.",
    "Färbe die Formen so, dass keine zwei Nachbarn die gleiche Farbe haben.",
    "Male die Formen so, dass du nur kalte Farben benutzt.",
    "Färbe die Formen so, dass du nur warme Farben benutzt.",
    "Male die Formen so, dass du nur helle Farben benutzt.",
    "Färbe die Formen so, dass du nur dunkle Farben benutzt.",
    "Male die Formen aus und setze danach einen kleinen Punkt neben jede Form.",
    "Färbe die Formen aus und setze danach einen kleinen Strich neben jede Form.",
    "Male die Sterne aus und zeichne danach eine kleine Wolke neben einen Stern.",
    "Färbe die Quadrate aus und zeichne danach eine kleine Sonne neben ein Quadrat.",
    "Male die Dreiecke aus und zeichne danach einen kleinen Berg neben ein Dreieck.",
    "Färbe die Formen aus und suche danach eine Form, die du vergessen hast.",
    "Male die Formen aus und kontrolliere danach: Sind alle Kanten sauber?",
    "Färbe die Formen aus und gib dir selbst einen Daumen hoch im Kopf.",
    "Male die Formen aus und wähle danach deine Lieblingsform als „Champion“.",
    "Färbe die Formen aus und lass die schwierigste Form zum Schluss.",
    "Male die Formen aus und lass die leichteste Form zum Schluss.",
    "Färbe zuerst eine Form, dann schaue fünf Sekunden aufs ganze Bild, dann weiter.",
    "Male zuerst zwei Formen, dann mache eine Mini-Pause, dann weiter.",
    "Färbe jede Form so, als wäre sie ein kleines Schild: gleichmäßige Fläche.",

    # --- Set D: Story-ish but still environment-only
    "Male die Sterne aus, als wären sie kleine Laternen in der Nacht.",
    "Färbe die Quadrate aus, als wären es kleine Kisten im Lager.",
    "Male die Dreiecke aus, als wären es Zelte auf einem Campingplatz.",
    "Färbe die Sterne aus, als wären es funkelnde Edelsteine.",
    "Male die Quadrate aus, als wären es Bausteine in einem Turm.",
    "Färbe die Dreiecke aus, als wären es kleine Berge in einer Karte.",
    "Male die Sterne aus, als wären sie Feuerwerke am Himmel.",
    "Färbe die Quadrate aus, als wären es Bildschirm-Fenster in einer Stadt.",
    "Male die Dreiecke aus, als wären es Pfeile, die den Weg zeigen.",
    "Färbe die Sterne aus und mach daraus eine kleine Sternenstraße: verbinde zwei Sterne.",
    "Male die Quadrate aus und mach daraus ein Labyrinth: verbinde zwei Quadrate.",
    "Färbe die Dreiecke aus und mach daraus eine Bergkette: verbinde zwei Dreiecke.",
    "Male die Formen aus, als würdest du eine Schatzkarte markieren.",
    "Färbe die Formen aus, als wären sie versteckte Zeichen auf einer Mission.",
    "Male die Formen aus, als würdest du Spuren im Schnee sichtbar machen.",
    "Färbe die Formen aus, als würdest du geheime Runen zum Leuchten bringen.",
    "Male die Formen aus und stell dir vor: Jede Form ist ein kleiner Checkpoint.",
    "Färbe die Formen aus und stell dir vor: Jede Form ist ein kleiner Energie-Kristall.",
    "Male die Formen aus und stell dir vor: Jede Form ist ein Portal (aber nur die Formen!).",
    "Färbe die Sterne aus und wähle einen Stern als „Anführer“ (extra hell).",
    "Male die Quadrate aus und wähle ein Quadrat als „Boss“ (extra dunkel).",
    "Färbe die Dreiecke aus und wähle ein Dreieck als „Hüter“ (extra dunkel).",
    "Male die Formen aus und gib ihnen im Kopf Namen wie „Stern 1“, „Quadrat 2“.",
    "Färbe die Formen aus und zähle dabei rückwärts von zehn.",
    "Male die Formen aus und zähle dabei bis zwanzig (oder bis du fertig bist).",
    "Färbe zuerst drei Formen, dann suche eine Form, die du noch nicht gesehen hast.",
    "Male die Formen aus und suche danach eine Form, die ganz anders aussieht.",
    "Färbe die Sterne aus und gib jedem Stern eine kleine „Aura“ mit Punkten.",
    "Male die Quadrate aus und gib jedem Quadrat eine kleine „Aura“ mit Strichen.",
    "Färbe die Dreiecke aus und gib jedem Dreieck eine kleine „Aura“ mit Punkten.",
    "Male nur die Formen aus, die wie ein Muster wirken: gleichmäßig verteilt.",
    "Färbe nur die Formen aus, die wie ein Cluster wirken: eng beieinander.",
    "Male die Formen aus und entscheide: Welche Form ist heute deine Lieblingsform?",
    "Färbe die Formen aus und entscheide: Welche Form ist heute die schwierigste?",
    "Male die Formen aus und entscheide: Welche Form ist heute die schnellste?",
    "Färbe die Formen aus und halte dabei die Hand ruhig wie ein Roboterarm.",
    "Male die Formen aus und halte dabei die Hand ruhig wie ein Laser.",
    "Färbe die Formen aus und nutze nur kurze, saubere Striche.",
    "Male die Formen aus und nutze nur kreisende, weiche Bewegungen.",
    "Färbe die Formen aus und kontrolliere danach: keine Ecke vergessen.",
    "Male die Formen aus und kontrolliere danach: keine Spitze vergessen.",
    "Färbe die Formen aus und kontrolliere danach: kein Rand vergessen.",

    # --- Set E: Extra variety (still short)
    "Male alle Sterne aus und lass die Quadrate und Dreiecke komplett leer.",
    "Färbe alle Quadrate aus und lass die Sterne und Dreiecke komplett leer.",
    "Male alle Dreiecke aus und lass die Sterne und Quadrate komplett leer.",
    "Färbe Sterne aus und gib ihnen Streifen, Quadrate bleiben frei.",
    "Male Quadrate aus und gib ihnen Punkte, Sterne bleiben frei.",
    "Färbe Dreiecke aus und gib ihnen Zickzack, Quadrate bleiben frei.",
    "Male nur die Formen aus, die du zuerst mit dem Finger berühren kannst.",
    "Färbe nur die Formen aus, die du ohne Suchen sofort findest.",
    "Male nur die Formen aus, die du erst nach genau 5 Sekunden findest.",
    "Färbe die Formen aus und mach danach eine Form nochmal dunkler als Schattierung.",
    "Male die Formen aus und mach danach eine Form nochmal heller als Highlight.",
    "Färbe die Formen aus und gib danach einer Form einen dicken Rand.",
    "Male die Formen aus und gib danach einer Form einen dünnen Rand.",
    "Färbe die Formen aus und gib danach einer Form ein Muster aus Punkten.",
    "Male die Formen aus und gib danach einer Form ein Muster aus Linien.",
    "Färbe die Formen aus und wähle dabei eine Farbe, die du selten nutzt.",
    "Male die Formen aus und wähle dabei deine Lieblingsfarbe als Hauptfarbe.",
    "Färbe die Formen aus und nutze genau zwei Farben für alles.",
    "Male die Formen aus und nutze genau drei Farben für alles.",
    "Färbe die Formen aus und nutze so viele Farben wie du willst – aber bleib sauber.",
]

# Guarantee 240+ by adding additional fully worded sentences (not placeholders).
# These are still complete, short directives; no “fill-in templates” at runtime.
_EXTRA_QUESTS: List[str] = [
    "Male die Sterne aus und achte darauf, dass jede Spitze bis zum Rand gefärbt ist.",
    "Färbe die Quadrate aus und achte darauf, dass keine Ecke hell bleibt.",
    "Male die Dreiecke aus und achte darauf, dass keine Kante ausgelassen wird.",
    "Färbe nur Formen, die du in der Nähe der oberen Kante entdeckst.",
    "Male nur Formen, die du in der Nähe der unteren Kante entdeckst.",
    "Färbe die Formen aus, die wie eine Reihe wirken, als würden sie zusammengehören.",
    "Male die Formen aus, die du am liebsten als Sticker aufkleben würdest.",
    "Färbe die Formen aus, die du am ehesten als Schilder in einer Stadt siehst.",
    "Male die Formen aus und gib jeder Form eine kleine Zahl daneben (1, 2, 3 …).",
    "Färbe die Formen aus und mache neben die letzte Form ein kleines Häkchen.",
    "Male die Sterne aus und gib den Sternen eine doppelte Umrandung.",
    "Färbe die Quadrate aus und gib den Quadraten eine doppelte Umrandung.",
    "Male die Dreiecke aus und gib den Dreiecken eine doppelte Umrandung.",
    "Färbe die Sterne aus und male die Quadrate nur an den Kanten.",
    "Male die Quadrate aus und male die Dreiecke nur an den Kanten.",
    "Färbe die Dreiecke aus und male die Sterne nur an den Kanten.",
    "Male die Formen aus, die du am schnellsten findest, und lass die schwersten frei.",
    "Färbe die Formen aus, die du am schwersten findest, und lass die leichtesten frei.",
    "Male die Formen aus und halte dabei die Farbe immer gleichmäßig.",
    "Färbe die Formen aus und halte dabei die Striche immer in eine Richtung.",
    "Male die Formen aus und wechsle nach jeder Form die Strichrichtung.",
    "Färbe die Formen aus und mach die obere Hälfte jeder Form etwas heller.",
    "Male die Formen aus und mach die untere Hälfte jeder Form etwas dunkler.",
    "Färbe die Formen aus und stoppe sofort, wenn du fertig bist – nicht nachmalen.",
    "Male die Formen aus und setze danach neben drei Formen einen kleinen Punkt.",
    "Färbe die Formen aus und setze danach neben drei Formen einen kleinen Strich.",
    "Male die Formen aus und wähle eine Form als „König“ (besonders sauber).",
    "Färbe die Formen aus und wähle eine Form als „Wächter“ (besonders dunkel).",
    "Male die Formen aus und lass eine Form als „Geheimtür“ weiß.",
    "Färbe die Formen aus und lass eine Form als „Geheimcode“ weiß.",
    "Male die Formen aus und überprüfe danach: Sind alle Formen leicht zu erkennen?",
    "Färbe die Formen aus und überprüfe danach: Kannst du jede Form sofort unterscheiden?",
    "Male die Formen aus und such danach eine neue Form, die du zuerst übersehen hast.",
    "Färbe die Formen aus und such danach eine Form, die ganz versteckt wirkt.",
    "Male die Sterne aus und mach danach um zwei Sterne einen Kreis.",
    "Färbe die Quadrate aus und mach danach um zwei Quadrate einen Kreis.",
    "Male die Dreiecke aus und mach danach um zwei Dreiecke einen Kreis.",
    "Färbe die Formen aus und gib den Formen unterschiedliche Muster: Punkte, Linien, Streifen.",
    "Male die Formen aus und gib den Formen unterschiedliche Muster: Zickzack, Wellen, Streifen.",
    "Färbe die Formen aus und male danach eine kleine Linie, die zwei Formen verbindet.",
    "Male die Formen aus und male danach eine kleine Linie, die drei Formen verbindet.",
    "Färbe die Formen aus und entscheide danach: Welche Form sieht am stärksten aus?",
    "Male die Formen aus und entscheide danach: Welche Form sieht am freundlichsten aus?",
    "Färbe die Formen aus und entscheide danach: Welche Form ist dein Favorit heute?",
    "Male die Formen aus und mach danach eine Mini-Pause: Hände ausschütteln.",
    "Färbe die Formen aus und mach danach eine Mini-Pause: einmal tief atmen.",
    "Male die Formen aus und arbeite von links nach rechts, ohne zu springen.",
    "Färbe die Formen aus und arbeite von oben nach unten, ohne zu springen.",
]
QUEST_TEXTS.extend(_EXTRA_QUESTS)

# Ensure hard minimum
if len(QUEST_TEXTS) < 240:
    raise RuntimeError(f"quest pool too small: {len(QUEST_TEXTS)} (need 240+)")

# --- PROOFS (short, box-safe)
PROOF_TEXTS: List[str] = [
    "Haken setzen.",
    "Kurz prüfen: fertig.",
    "Einmal laut „fertig“ sagen.",
    "Einen Punkt daneben machen.",
    "Daumen hoch zeigen.",
    "Ein Sternchen daneben malen.",
    "Ein kleines ✓ daneben setzen.",
    "Einmal kurz zählen und stoppen.",
    "Einmal tief einatmen: erledigt.",
    "Einmal ausatmen: geschafft.",
    "Ein kleines Herz daneben malen.",
    "Einen kleinen Kreis daneben malen.",
    "Ein kleines Quadrat daneben malen.",
    "Ein kleines Dreieck daneben malen.",
    "Ein kleines „OK“ daneben schreiben.",
    "Einmal nicken: erledigt.",
    "Fertig? Dann Haken.",
    "Sauber? Dann Haken.",
    "Stimmt so. Haken.",
    "Mission abgeschlossen.",
    "Alles gefunden. Haken.",
    "Alles ausgemalt. Haken.",
    "Kurz anschauen: passt.",
    "Einmal kurz lächeln: fertig.",
    "Einmal „yes“ denken: fertig.",
    "Einmal klatschen: fertig.",
    "Einmal Hände reiben: fertig.",
    "Einmal Schultern locker: fertig.",
    "Einmal Augen schließen: fertig.",
    "Einmal strecken: fertig.",
    "Zwei Sekunden Pause: fertig.",
    "Kleines ✓ in die Box.",
    "Haken in die Box.",
    "Box ankreuzen.",
    "Abgehakt.",
    "Erledigt.",
    "Geschafft.",
    "Fertig.",
    "Done.",
    "Alles klar.",
    "Passt.",
    "Weiter.",
    "Nächste Seite.",
    "Kleine Pause, dann weiter.",
    "Kurzer Check: sauber geblieben.",
    "Kurzer Check: Linien eingehalten.",
    "Kurzer Check: nichts übermalt.",
    "Kurzer Check: alles erkennbar.",
    "Haken und lächeln.",
    "Haken und weitergehen.",
    "Haken und stolz sein.",
    "Haken setzen – stark.",
    "Haken setzen – sauber.",
    "Haken setzen – ruhig.",
    "Haken setzen – fertig.",
    "Ein ✓, dann stopp.",
    "Ein ✓, dann Pause.",
    "Ein ✓, dann weiter.",
    "Ein ✓, dann atmen.",
    "Ein ✓, dann strecken.",
    "Ein ✓, dann trinken (Wasser).",
    "Ein ✓, dann Hände entspannen.",
    "Ein ✓, dann Augen entspannen.",
    "Ein ✓, dann Schultern senken.",
    "Ein ✓, dann kurz schauen.",
    "Ein ✓, dann los.",
    "Ein ✓, dann nächste.",
    "Ein ✓, dann fertig.",
    "Ein ✓, dann done.",
    "Ein ✓, dann gut.",
    "Ein ✓, dann passt.",
    "Ein ✓, dann okay.",
    "Ein ✓, dann top.",
    "Ein ✓, dann super.",
    "Ein ✓, dann strong.",
    "Ein ✓, dann weiterziehen.",
    "Ein ✓, dann Mission Ende.",
    "Ein ✓, dann Level up.",
    "Ein ✓, dann Haken.",
    "Ein ✓, dann Schluss.",
    "Ein ✓, dann Ruhe.",
    "Ein ✓, dann Fokus.",
    "Ein ✓, dann check.",
    "Ein ✓, dann okay.",
    "Ein ✓, dann go.",
    "Ein ✓, dann stop.",
    "Ein ✓, dann fertig.",
    "Ein ✓, dann weiter.",
    "Ein ✓, dann passt.",
]

# --- NOTES (short, brand/safety, optional)
NOTE_TEXTS: List[str] = [
    "Nur die Formen färben.",
    "Eddie bleibt schwarz-weiß.",
    "Langsam und sauber arbeiten.",
    "In den Linien bleiben.",
    "Kurze Pause ist erlaubt.",
    "Wasser trinken hilft.",
    "Wenn’s schwer ist: kleiner anfangen.",
    "Einfach weitermachen.",
    "Ruhig bleiben – du schaffst das.",
    "Heute zählt der Versuch.",
    "Sauber > schnell.",
    "Ein Schritt nach dem anderen.",
    "Kurzer Check, dann weiter.",
    "Alles gut, wenn’s nicht perfekt ist.",
    "Die Formen sind das Ziel.",
    "Nur Umgebung – nicht die Figur.",
    "Fokus auf Sterne/Quadrate/Dreiecke.",
    "Kleine Schritte sind Fortschritt.",
    "Ruhige Hand, ruhiger Kopf.",
    "Einmal tief atmen.",
    "Pausen sind okay.",
    "Weiter geht’s.",
    "Stark geblieben.",
    "Sauber gearbeitet.",
    "Mission zählt.",
    "Du bist dran.",
    "Bleib freundlich zu dir.",
    "Alles zählt.",
    "Guter Move.",
    "Du bist im Flow.",
]

# =========================================================
# POOL PACKING
# =========================================================

def _pack_pool(prefix: str, texts: List[str], tags: Set[str]) -> List[QuestItem]:
    out: List[QuestItem] = []
    for i, t in enumerate(texts):
        qid = f"{prefix}{i:04d}"
        out.append(QuestItem(qid=qid, text=(t or "").strip(), tags=set(tags)))
    return out

QUEST_POOLS: Dict[str, List[QuestItem]] = {
    "quest": _pack_pool("q_", QUEST_TEXTS, {"env", "forms"}),
    "proof": _pack_pool("p_", PROOF_TEXTS, {"proof", "short"}),
    "note": _pack_pool("n_", NOTE_TEXTS, {"note", "short", "brand"}),
}

# =========================================================
# SELECTOR (dedupe + optional tag filter)
# =========================================================

def get_quest(
    pool: str,
    used_ids: Set[str],
    *,
    rng: random.Random,
    tags_any: Optional[Set[str]] = None
) -> QuestItem:
    """
    Returns a QuestItem from QUEST_POOLS[pool], preferring items not in used_ids.

    - used_ids is a SET of qids (strings)
    - rng is a python random.Random (deterministic when seeded)
    - tags_any: if provided, item must have intersection with tags_any
    """
    if pool not in QUEST_POOLS:
        raise ValueError(f"Unknown pool: {pool}")

    items = QUEST_POOLS[pool]
    if not items:
        raise ValueError(f"Empty pool: {pool}")

    # Filter by tags if requested
    if tags_any:
        cand_all = [it for it in items if (it.tags & set(tags_any))]
        if not cand_all:
            # No tag matches; ignore tag filter rather than failing
            cand_all = list(items)
    else:
        cand_all = list(items)

    # First pass: not used
    cand = [it for it in cand_all if it.qid not in used_ids]
    if cand:
        return cand[rng.randrange(len(cand))]

    # If everything used, allow reset-pick (deterministic, still randomized)
    return cand_all[rng.randrange(len(cand_all))]

# =========================================================
# OPTIONAL: simple pool stats (debug)
# =========================================================
def pool_stats() -> Dict[str, int]:
    return {k: len(v) for k, v in QUEST_POOLS.items()}
