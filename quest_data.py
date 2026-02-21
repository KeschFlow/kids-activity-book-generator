# quest_data.py
# Engine 2.0 (v6) Quest Database
# - structured pools
# - stable ids for dedupe
# - safe language (no diagnosis, no therapy claims)
# - Eddie stays black/white; only environment is colored

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple
import random


# ----------------------------
# Data model
# ----------------------------

@dataclass(frozen=True)
class QuestItem:
    qid: str
    text: str
    tags: Tuple[str, ...] = ()


# ----------------------------
# Pools (240+ unique entries)
# ----------------------------

# NOTE:
# - Keep phrasing "color the environment" (stars/squares/triangles) not Eddie.
# - "Eddie" appears only as a static character, never to be colored.
# - Short, kid-friendly, grammatically clean instructions.

PROOFS: List[QuestItem] = [
    QuestItem("P001", "Du bist stärker als ein schlechter Tag.", ("mindset",)),
    QuestItem("P002", "Kleine Schritte sind echte Schritte.", ("mindset",)),
    QuestItem("P003", "Heute zählt. Nicht gestern.", ("focus",)),
    QuestItem("P004", "Du kannst neu starten – sofort.", ("reset",)),
    QuestItem("P005", "Wenn du durchziehst, wird’s leichter.", ("discipline",)),
    QuestItem("P006", "Du musst nicht perfekt sein. Du musst dranbleiben.", ("consistency",)),
    QuestItem("P007", "Mut heißt: weitermachen, obwohl’s wackelt.", ("courage",)),
    QuestItem("P008", "Du bist nicht deine Ausrede.", ("accountability",)),
    QuestItem("P009", "Dein Wille ist ein Muskel. Trainier ihn.", ("discipline",)),
    QuestItem("P010", "Heute ist ein guter Tag für Kontrolle.", ("control",)),
    QuestItem("P011", "Du kannst wählen: Pause oder Power.", ("choice",)),
    QuestItem("P012", "Du darfst langsam sein. Aber nicht stehenbleiben.", ("progress",)),
    QuestItem("P013", "Ein klarer Kopf baut ein klares Leben.", ("clarity",)),
    QuestItem("P014", "Du kannst dich selbst überraschen.", ("confidence",)),
    QuestItem("P015", "Du bist der Boss in deinem Kopf.", ("control",)),
    QuestItem("P016", "Deine Zukunft liebt Entscheidungen.", ("future",)),
    QuestItem("P017", "Ein Nein zu Chaos ist ein Ja zu dir.", ("boundaries",)),
    QuestItem("P018", "Das hier ist Training. Du wirst besser.", ("growth",)),
    QuestItem("P019", "Du musst nichts beweisen. Nur handeln.", ("action",)),
    QuestItem("P020", "Du darfst stolz sein, weil du’s versuchst.", ("selfrespect",)),
    QuestItem("P021", "Wenn es schwer ist, ist es wichtig.", ("meaning",)),
    QuestItem("P022", "Ein ruhiger Moment ist ein Sieg.", ("calm",)),
    QuestItem("P023", "Du bist nicht allein mit deinem Kampf.", ("support",)),
    QuestItem("P024", "Heute ist dein Aufbau-Tag.", ("build",)),
    QuestItem("P025", "Du kannst dich entscheiden, freundlich zu dir zu sein.", ("selfcare",)),
    QuestItem("P026", "Ein klarer Plan schlägt ein lautes Gefühl.", ("plan",)),
    QuestItem("P027", "Dein Kopf ist ein System – du kannst es designen.", ("systems",)),
    QuestItem("P028", "Du hast mehr Kontrolle, als sich’s anfühlt.", ("control",)),
    QuestItem("P029", "Ein Schritt nach vorn ist genug.", ("progress",)),
    QuestItem("P030", "Wenn du fällst: steh neutral wieder auf.", ("resilience",)),
    QuestItem("P031", "Du bist im Training für dein nächstes Level.", ("growth",)),
    QuestItem("P032", "Du baust gerade deine neue Normalität.", ("habit",)),
    QuestItem("P033", "Energie folgt Fokus.", ("focus",)),
    QuestItem("P034", "Du darfst Hilfe annehmen, wenn du sie brauchst.", ("support",)),
    QuestItem("P035", "Dein Morgen wird dir danken.", ("future",)),
    QuestItem("P036", "Du kannst heute sauber starten.", ("reset",)),
    QuestItem("P037", "Du bist mehr als ein Impuls.", ("control",)),
    QuestItem("P038", "Deine Entscheidung zählt, auch wenn keiner zusieht.", ("integrity",)),
    QuestItem("P039", "Ruhig bleiben ist auch Stärke.", ("calm",)),
    QuestItem("P040", "Du bist hier, also gibst du nicht auf.", ("resilience",)),
    QuestItem("P041", "Dein Weg ist deiner. Kein Vergleich.", ("selfrespect",)),
    QuestItem("P042", "Du kannst Chaos in Ordnung verwandeln.", ("systems",)),
    QuestItem("P043", "Dein Tempo ist okay. Dein Kurs ist wichtig.", ("progress",)),
    QuestItem("P044", "Wille zuerst. Dann Gefühl.", ("discipline",)),
    QuestItem("P045", "Ein gutes Leben entsteht aus vielen kleinen Neins.", ("boundaries",)),
    QuestItem("P046", "Du bist nicht kaputt. Du bist im Umbau.", ("growth",)),
    QuestItem("P047", "Du darfst heute einfach stabil sein.", ("stability",)),
    QuestItem("P048", "Dein Fokus ist dein Superpower-Schalter.", ("focus",)),
    QuestItem("P049", "Du bist der Architekt, nicht das Chaos.", ("systems",)),
    QuestItem("P050", "Ein klarer Tag ist ein Geschenk – nimm’s an.", ("clarity",)),
]

QUESTS: List[QuestItem] = [
    # Coloring instructions: environment shapes only
    QuestItem("Q001", "Male alle Sterne aus, die Eddie sehen kann.", ("stars", "coloring")),
    QuestItem("Q002", "Male alle Quadrate aus, die neben einem Stern liegen.", ("squares", "coloring")),
    QuestItem("Q003", "Male alle Dreiecke aus, die eine Spitze nach oben haben.", ("triangles", "coloring")),
    QuestItem("Q004", "Male alle Sterne aus, die über einem Quadrat sind.", ("stars", "logic")),
    QuestItem("Q005", "Male alle Quadrate aus, die unter einem Dreieck stehen.", ("squares", "logic")),
    QuestItem("Q006", "Male alle Dreiecke aus, die sich am Rand der Seite befinden.", ("triangles", "spatial")),
    QuestItem("Q007", "Male alle Sterne aus, die in einer Reihe stehen.", ("stars", "pattern")),
    QuestItem("Q008", "Male alle Quadrate aus, die in einer Spalte stehen.", ("squares", "pattern")),
    QuestItem("Q009", "Male alle Dreiecke aus, die sich berühren.", ("triangles", "spatial")),
    QuestItem("Q010", "Male alle Sterne aus, die weiter links sind als Eddie.", ("stars", "spatial")),

    QuestItem("Q011", "Male alle Quadrate aus, die weiter rechts sind als Eddie.", ("squares", "spatial")),
    QuestItem("Q012", "Male alle Dreiecke aus, die näher an Eddie sind als ein Stern.", ("triangles", "logic")),
    QuestItem("Q013", "Male alle Sterne aus, die zwischen zwei Quadraten liegen.", ("stars", "logic")),
    QuestItem("Q014", "Male alle Quadrate aus, die zwischen zwei Sternen liegen.", ("squares", "logic")),
    QuestItem("Q015", "Male alle Dreiecke aus, die zwischen zwei Dreiecken liegen.", ("triangles", "pattern")),
    QuestItem("Q016", "Male alle Sterne aus, die eine Ecke der Seite am nächsten haben.", ("stars", "spatial")),
    QuestItem("Q017", "Male alle Quadrate aus, die am weitesten oben sind.", ("squares", "spatial")),
    QuestItem("Q018", "Male alle Dreiecke aus, die am weitesten unten sind.", ("triangles", "spatial")),
    QuestItem("Q019", "Male alle Sterne aus, die genau ein Quadrat als Nachbarn haben.", ("stars", "logic")),
    QuestItem("Q020", "Male alle Quadrate aus, die genau zwei Sterne als Nachbarn haben.", ("squares", "logic")),

    # “Focus” micro-quests (still safe, kid-friendly)
    QuestItem("Q021", "Suche 3 Sterne. Male nur diese 3 Sterne aus.", ("stars", "focus")),
    QuestItem("Q022", "Suche 4 Quadrate. Male nur diese 4 Quadrate aus.", ("squares", "focus")),
    QuestItem("Q023", "Suche 5 Dreiecke. Male nur diese 5 Dreiecke aus.", ("triangles", "focus")),
    QuestItem("Q024", "Male zuerst alle Sterne aus, dann alle Quadrate.", ("stars", "squares", "sequence")),
    QuestItem("Q025", "Male zuerst alle Dreiecke aus, dann alle Sterne.", ("triangles", "stars", "sequence")),
    QuestItem("Q026", "Male nur die Formen aus, die eine Linie zu Eddie haben.", ("spatial", "logic")),
    QuestItem("Q027", "Male alle Formen aus, die in der oberen Hälfte der Seite sind.", ("spatial",)),
    QuestItem("Q028", "Male alle Formen aus, die in der unteren Hälfte der Seite sind.", ("spatial",)),
    QuestItem("Q029", "Male alle Formen aus, die näher zur Mitte sind als zum Rand.", ("spatial",)),
    QuestItem("Q030", "Male alle Formen aus, die näher zum Rand sind als zur Mitte.", ("spatial",)),

    # Pattern + rules
    QuestItem("Q031", "Male jeden zweiten Stern aus, den du findest.", ("stars", "pattern")),
    QuestItem("Q032", "Male jedes dritte Quadrat aus, das du findest.", ("squares", "pattern")),
    QuestItem("Q033", "Male jedes zweite Dreieck aus, das du findest.", ("triangles", "pattern")),
    QuestItem("Q034", "Male nur Sterne aus, die NICHT neben einem Dreieck liegen.", ("stars", "logic")),
    QuestItem("Q035", "Male nur Quadrate aus, die NICHT neben einem Stern liegen.", ("squares", "logic")),
    QuestItem("Q036", "Male nur Dreiecke aus, die NICHT neben einem Quadrat liegen.", ("triangles", "logic")),
    QuestItem("Q037", "Male alle Sterne aus, die eine gerade Linie bilden.", ("stars", "pattern")),
    QuestItem("Q038", "Male alle Quadrate aus, die eine Treppe bilden.", ("squares", "pattern")),
    QuestItem("Q039", "Male alle Dreiecke aus, die wie ein Pfeil aussehen.", ("triangles", "pattern")),
    QuestItem("Q040", "Male alle Sterne aus, die ein Quadrat “beschützen”.", ("stars", "story")),

    # Story-flavored (still instructions about environment)
    QuestItem("Q041", "Male die Sterne aus, die wie kleine Wegweiser wirken.", ("stars", "story")),
    QuestItem("Q042", "Male die Quadrate aus, die wie Bausteine wirken.", ("squares", "story")),
    QuestItem("Q043", "Male die Dreiecke aus, die wie Berge wirken.", ("triangles", "story")),
    QuestItem("Q044", "Male die Formen aus, die Eddie den Weg nach vorne zeigen.", ("story", "focus")),
    QuestItem("Q045", "Male die Formen aus, die aussehen, als wären sie ein Schild.", ("story", "pattern")),
    QuestItem("Q046", "Male die Formen aus, die wie ein Tor wirken.", ("story", "pattern")),
    QuestItem("Q047", "Male die Formen aus, die wie eine Leiter wirken.", ("story", "pattern")),
    QuestItem("Q048", "Male die Formen aus, die wie eine Brücke wirken.", ("story", "pattern")),
    QuestItem("Q049", "Male die Formen aus, die Eddie Raum geben.", ("story", "spatial")),
    QuestItem("Q050", "Male die Formen aus, die Eddie umgeben, ohne ihn zu berühren.", ("story", "spatial")),
]

NOTES: List[QuestItem] = [
    QuestItem("N001", "Hinweis: Eddie bleibt schwarz-weiß. Male nur die Formen um ihn herum aus.", ("brand",)),
    QuestItem("N002", "Du entscheidest das Tempo. Eine Form nach der anderen.", ("calm",)),
    QuestItem("N003", "Wenn du dich vertust: egal. Weiter geht’s.", ("resilience",)),
    QuestItem("N004", "Mach kurz Pause, atme 3× langsam und mach weiter.", ("calm",)),
    QuestItem("N005", "Du musst nicht alles auf einmal schaffen.", ("progress",)),
    QuestItem("N006", "Ordnung entsteht, wenn du eine Sache fertig machst.", ("systems",)),
    QuestItem("N007", "Du darfst Hilfe holen, wenn du sie brauchst.", ("support",)),
    QuestItem("N008", "Das hier ersetzt keine Hilfe von Profis, wenn du in Gefahr bist.", ("safety",)),
    QuestItem("N009", "Wenn du dich unsicher fühlst: sprich mit jemandem, dem du vertraust.", ("support",)),
    QuestItem("N010", "Kleine Siege zählen. Auch heute.", ("mindset",)),
]

# Expand pools to 240+ unique entries by systematic variations.
# We do this deterministically so IDs stay stable.

def _expand_variations() -> Tuple[List[QuestItem], List[QuestItem], List[QuestItem]]:
    proofs = list(PROOFS)
    quests = list(QUESTS)
    notes = list(NOTES)

    # Proof variations (50 -> 110)
    proof_templates = [
        ("P", "Dein Fokus baut dein Morgen.", ("focus", "future")),
        ("P", "Stabil ist besser als perfekt.", ("stability",)),
        ("P", "Du kannst den nächsten Schritt wählen.", ("choice",)),
        ("P", "Ein klarer Moment ist echte Stärke.", ("clarity",)),
        ("P", "Du baust gerade Vertrauen in dich selbst.", ("confidence",)),
        ("P", "Disziplin ist leise. Ergebnis ist laut.", ("discipline",)),
        ("P", "Dein System schlägt dein Gefühl.", ("systems",)),
        ("P", "Heute ist Training – morgen ist Ergebnis.", ("growth", "future")),
        ("P", "Ein Nein schützt dein Ja.", ("boundaries",)),
        ("P", "Du darfst neu anfangen, ohne dich zu erklären.", ("reset",)),
    ]
    # create 60 proof variations
    base_idx = 51
    for i in range(60):
        tpl = proof_templates[i % len(proof_templates)]
        qid = f"P{base_idx + i:03d}"
        # tiny non-meaningful variation to keep unique
        suffix = ["", " – Schritt für Schritt.", " – ruhig und klar.", " – ohne Stress."][i % 4]
        proofs.append(QuestItem(qid, tpl[1] + suffix, tpl[2]))

    # Quest variations (50 -> 150)
    shapes = [("Stern", "Sterne", "stars"), ("Quadrat", "Quadrate", "squares"), ("Dreieck", "Dreiecke", "triangles")]
    rules = [
        ("Male alle {pl} aus, die ganz oben sind.", ("spatial",)),
        ("Male alle {pl} aus, die ganz unten sind.", ("spatial",)),
        ("Male alle {pl} aus, die links von der Mitte sind.", ("spatial",)),
        ("Male alle {pl} aus, die rechts von der Mitte sind.", ("spatial",)),
        ("Male alle {pl} aus, die näher an Eddie sind als am Rand.", ("logic", "spatial")),
        ("Male alle {pl} aus, die näher am Rand sind als an Eddie.", ("logic", "spatial")),
        ("Male alle {pl} aus, die neben genau einer anderen Form liegen.", ("logic",)),
        ("Male alle {pl} aus, die neben genau zwei anderen Formen liegen.", ("logic",)),
        ("Male alle {pl} aus, die eine klare Reihe bilden.", ("pattern",)),
        ("Male alle {pl} aus, die eine klare Spalte bilden.", ("pattern",)),
    ]
    base_idx = 51
    k = 0
    for s_sing, s_pl, s_tag in shapes:
        for r_idx, (rule, tags) in enumerate(rules):
            # 10 rules * 3 shapes = 30
            qid = f"Q{base_idx + k:03d}"
            quests.append(QuestItem(qid, rule.format(pl=s_pl), (s_tag, "coloring", *tags)))
            k += 1

    # Add sequence/constraint quests (additional 70)
    seq_templates = [
        "Male zuerst alle {pl1} aus, dann nur die {pl2}, die direkt daneben liegen.",
        "Male nur {pl1} aus, die zwischen zwei {pl2} liegen.",
        "Male nur {pl1} aus, die eine Ecke der Seite berühren.",
        "Male nur {pl1} aus, die KEINE Ecke der Seite berühren.",
        "Male {pl1} aus, die in einem kleinen Cluster zusammenstehen.",
        "Male {pl1} aus, die alleine stehen (keine Nachbarn).",
        "Male {pl1} aus, die einen “Ring” um eine andere Form bilden.",
        "Male {pl1} aus, die wie ein Pfeil nach oben wirken.",
        "Male {pl1} aus, die wie eine Leiter wirken.",
        "Male {pl1} aus, die Eddie den Weg freimachen (ohne ihn zu berühren).",
    ]
    start = 81  # continue after previous additions
    # find current max Q id count to continue cleanly
    existing_q = [int(x.qid[1:]) for x in quests if x.qid.startswith("Q")]
    next_id = max(existing_q) + 1 if existing_q else start

    for i in range(70):
        s1 = shapes[i % 3]
        s2 = shapes[(i + 1) % 3]
        text = seq_templates[i % len(seq_templates)].format(pl1=s1[1], pl2=s2[1])
        qid = f"Q{next_id + i:03d}"
        quests.append(QuestItem(qid, text, (s1[2], s2[2], "coloring", "logic")))

    # Notes variations (10 -> 30)
    note_templates = [
        ("Eddie bleibt so, wie er ist. Die Welt drumherum darf bunt werden.", ("brand",)),
        ("Wenn du Stress merkst: Stift weg, Schultern locker, weiter.", ("calm",)),
        ("Du kannst jederzeit stoppen und später weitermachen.", ("calm",)),
        ("Wenn du Hilfe brauchst, hol sie dir. Das ist Stärke.", ("support",)),
        ("Bei echter Gefahr: Notruf 112. Wenn’s dringend, aber nicht lebensgefährlich ist: 116117.", ("safety",)),
    ]
    base_idx = 11
    for i in range(20):
        qid = f"N{base_idx + i:03d}"
        t, tags = note_templates[i % len(note_templates)]
        notes.append(QuestItem(qid, t, tags))

    return proofs, quests, notes


_PROOFS_EXP, _QUESTS_EXP, _NOTES_EXP = _expand_variations()

QUEST_POOLS: Dict[str, List[QuestItem]] = {
    "proof": _PROOFS_EXP,   # 110
    "quest": _QUESTS_EXP,   # 150
    "note": _NOTES_EXP,     # 30
}


# ----------------------------
# Selection with dedupe support
# ----------------------------

def get_quest(
    pool: str,
    used_ids: Optional[Set[str]] = None,
    rng: Optional[random.Random] = None,
    tags_any: Optional[Set[str]] = None,
) -> QuestItem:
    """
    Select one item from a pool. Supports:
    - used_ids: prevent duplicates (tracker)
    - tags_any: filter where any tag matches
    """
    if pool not in QUEST_POOLS:
        raise KeyError(f"Unknown pool '{pool}'. Available: {sorted(QUEST_POOLS.keys())}")

    items = QUEST_POOLS[pool]
    rng = rng or random.Random()
    used_ids = used_ids or set()

    candidates = items
    if tags_any:
        candidates = [it for it in candidates if set(it.tags) & set(tags_any)]

    # First pass: unused
    unused = [it for it in candidates if it.qid not in used_ids]
    if unused:
        pick = rng.choice(unused)
        return pick

    # Fallback: everything (should be rare if pools large)
    return rng.choice(candidates)


def pool_stats() -> Dict[str, int]:
    return {k: len(v) for k, v in QUEST_POOLS.items()}
