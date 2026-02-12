# kern/__init__.py
"""
Zentraler Einstiegspunkt für den Kern der Eddies-Plattform.
Alle öffentlichen Funktionen und Klassen werden hier exportiert,
damit man in app.py / app_trainer.py einfach schreiben kann:

    from kern import get_page_spec, draw_box, embed_image
"""

# PDF-Engine – Hauptfunktionen für Layout & Rendering
from .pdf_engine import (
    get_page_spec,      # Seitengröße & Ränder (KDP / A4)
    draw_box,           # Rechteck-Box mit optionalem Titel
    embed_image,        # Bild einbetten (skaliert, zentriert, RAM-only)
)

# Optional: Vokabel-Daten (Berufssprache) – nur wenn benötigt
# from .subject_data import SUBJECTS, AUTO_ICON

# Optional: Skizzen-Bibliothek (für Weg A – Standard-Motive statt Upload)
# from .assets.sketch_library import (
#     get_categories,
#     get_motifs,
#     load_sketch_bytes,
#     get_random_sketch,
# )

# Optional: Icon-Funktionen (Hammer, Gear, Medical-Cross etc.)
# from .pdf_engine import (
#     draw_icon_hammer,
#     draw_icon_wrench,
#     draw_icon_gear,
#     draw_icon_medical_cross,
#     draw_icon_briefcase,
#     draw_icon_book_open,
#     draw_icon_fork_knife,
#     draw_icon_computer,
# )

# ────────────────────────────────────────────────
# Hinweis für Entwickler:
# - Neue Submodule immer hier exportieren
# - Vermeide Wildcard-Imports (*)
# - Halte die Liste übersichtlich – nur wirklich häufig genutzte Funktionen
# ────────────────────────────────────────────────
