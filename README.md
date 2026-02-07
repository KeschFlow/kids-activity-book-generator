# ✏️ Eddie’s Welt – Kids Activity Book Generator

**Eddie’s Welt** ist eine Streamlit-App, die aus Fotos ein personalisiertes **24-Stunden-Malbuch** als PDF erzeugt.  
Optimiert für Heimdruck (A4) und optional für **Amazon KDP** (8.5" × 8.5" mit Bleed/Anschnitt, Preflight-Check und Röntgen-Overlay).

---

## ✅ Features

- **Smart-Sort (EXIF):** Chronologische Sortierung, wenn EXIF vorhanden (sonst Upload-Reihenfolge)
- **Sketch-Engine:** Foto → kontrastreiche Schwarz-Weiß-Skizze zum Ausmalen
- **KDP-Ready:** 8.5" × 8.5" + **Bleed 0.125"** + Safe-Area / Trim-Overlay
- **Preflight-Ampel:** Bleed, Safe-Area, DPI und PDF-Budget (mit Gelb-Puffer)
- **Budget-Bremse:** Dynamische JPEG-Kompression für stabile PDF-Größen
- **Privacy-First:** Verarbeitung nur temporär (keine dauerhafte Speicherung)

---

## 🧰 Tech Stack

- Streamlit
- OpenCV (headless)
- Pillow
- ReportLab
- qrcode

---

## 🚀 Schnellstart (Lokal)

1) Repository klonen:
```bash
git clone https://github.com/KeschFlow/kids-activity-book-generator.git
cd kids-activity-book-generator
