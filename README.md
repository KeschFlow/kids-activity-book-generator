# 🐶 Eddies – Quest & Activity Print Engine

**Eddies** ist eine modulare Streamlit-Anwendung zur Generierung von  
druckfertigen **Quest-, Activity- und Workbook-Büchern** als PDF.

Sie kombiniert:

- 📸 Foto → Sketch-Transformation  
- 🧭 24h-Quest-System (Gamification ohne Wettbewerb)  
- 🧠 Bewegung + Denken + XP  
- 🖨️ KDP-kompatible Print-Pipeline  
- 🔒 RAM-only Privacy-Verarbeitung  

> Fokus: deterministische Outputs, drucktechnische Korrektheit, Zero-Daten-Speicherung.

---

# 🧠 System-Architektur

Eddies ist modular aufgebaut:

| Modul | Aufgabe |
|--------|---------|
| `app.py` | Questbook Edition (Foto → 24h Missionsbuch) |
| `engine_sketch.py` | Aktivitätsgrafiken (Maze + Suchauftrag, deterministic) |
| `quest_data.py` | Zentrale Quest-Datenbank (Zones + Missions + Audience-Adapter) |
| `kern/pdf_engine.py` | Print-Geometrie + Bleed + Safe + Icon Registry |
| `app_trainer.py` | Fachsprach-Workbook (Vokabel + Bild + Notizen) |

Alle Editionen nutzen dieselbe Print-Engine.

---

# 🚀 Core Features

## 📸 Foto → Ausmalbild

- OpenCV Sketch-Engine (druckfreundliche Linien)
- Center-Crop + Resize (Quadrat, 300 DPI)
- Deterministische Verarbeitung (Seed-basiert)
- RAM-only Bildverarbeitung

---

## 🧭 24h Quest-System

- Jede Seite = 1 Stunde (Startzeit wählbar)
- 8 thematische Zonen (00–24h)
- Mission Overlay mit:
  - Bewegung
  - Denkaufgabe
  - Proof-Check
  - XP
- Automatische Schwierigkeitsanpassung (Alter → Stufe 1–5)
- Audience-Modi:
  - Kid
  - Adult
  - Senior

Gamification ohne Wettbewerb – Fokus auf Selbstwirksamkeit.

---

## 🧩 Aktivitäts-Engine (engine_sketch)

Optional generierbare Activity-Seiten:

- Labyrinth (seed-basiert)
- Suchaufträge
- Druckoptimierte Liniengrafik
- Kein Bildmaterial notwendig

---

## 🖨️ KDP Print Pipeline (Production-Ready)

### Formate
- Preview Mode: 8.5" × 8.5"
- KDP Print Mode: 8.75" × 8.75" (8.5" + 0.125" Bleed)

### Print-Sicherheit
- Safe-Zone korrekt berechnet
- Forced Compliance:
  - min. 24 Seiten
  - gerade Seitenzahl
- Preflight Check (300 DPI Ziel)
- QA-Warnseite im Preview-Modus
- Spine-Berechnung abhängig vom Papier
- Barcode-Keepout
- Spine-Text erst ab 79 Seiten

---

## 🎨 Cover + Publishing Assets

- CoverWrap PDF (Back + Spine + Front)
- Automatische Spine-Breite
- Listing.txt (KDP-Ready Textbundle)
- ZIP Export (Interior + Cover + Listing)

---

## 🧠 Eddie Trainer (Fachsprach Edition)

- Vokabel-Input (deutsch;übersetzung)
- Bild-Zyklus oder Icon-Fallback
- Notizbereich
- KDP-kompatibel
- Nutzt dieselbe Print-Engine

---

## 🎨 Icon System (Registry)

- Skalierbare Vektor-Piktogramme
- Drucksicher (kein Raster nötig)
- Erweiterbar über `ICON_DRAWERS`
- Einheitlicher Brand-Akzent (EDDIE_PURPLE)

---

## 🔒 Privacy-First

- Keine Speicherung von Uploads
- Verarbeitung ausschließlich im RAM
- Download als PDF/ZIP
- Keine Cloud-Datenbank

---

# 🧰 Tech Stack

- Streamlit
- OpenCV (headless)
- Pillow
- ReportLab
- Deterministic Random Engine

---

# 🎯 Design-Prinzipien

- Druck vor Design  
- Struktur vor Spielerei  
- Modularität vor Chaos  
- Wiederholbarkeit vor Zufall  

Eddies ist kein „Malbuch-Generator“.  
Es ist eine deterministische Print-Engine mit Gamification-Overlay.

---

# 🚀 Schnellstart (Lokal)

```bash
git clone https://github.com/KeschFlow/kids-activity-book-generator.git
cd kids-activity-book-generator

python -m venv .venv

# macOS / Linux
source .venv/bin/activate

# Windows
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt

# Quest Edition
streamlit run app.py

# Trainer Edition
streamlit run app_trainer.py
```

---

# 🔮 Roadmap

- KI-Image-Fallback für Trainer
- Mehrsprachige Quest-Datenbank
- Weitere Print-Formate (A4, 6x9, Workbook)
- Hub-App zur Modul-Auswahl
- SaaS-Version