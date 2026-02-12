# 🐶 Eddies

**Eddies** ist eine Streamlit-App, die aus Fotos ein personalisiertes **Kids Activity / Malbuch** als PDF erzeugt.  
Optional erzeugt sie außerdem ein **KDP-kompatibles** Interior (8.5" × 8.5" mit Bleed/Anschnitt) inkl. **Preflight** und **QA-Warnseite** (nur Preview).

---

## ✅ Features

- **Sketch-Engine:** Foto → kontrastreiche Schwarz-Weiß-Skizze zum Ausmalen
- **KDP-Printmode Toggle:**
  - **Preview Mode:** 8.5" × 8.5" (wie später sichtbar)
  - **KDP Print Mode:** 8.75" × 8.75" (8.5" Trim + 0.125" Bleed je Seite)
- **Safe-Zone korrekt:** Safe Zone wird im Print-Mode um den Bleed verschoben
- **Forced KDP Compliance:** Erzwingt **min. 24 Seiten** + **gerade Seitenzahl**
- **Preflight (300 DPI Ziel):** Prüft Upload-Auflösung und warnt bei zu kleinen Bildern
- **DPI-Guard QA-Seite:** Wenn Bilder zu klein sind, wird im **Preview Mode** automatisch eine **Warnseite** vorn eingefügt (nicht für KDP-Upload gedacht)
- **CoverWrap PDF:** Back + Spine + Front in einer Datei, Spine-Breite berechnet, Barcode-Keepout, Spine-Text erst ab 79 Seiten
- **Listing.txt:** Ready-to-publish KDP Listing-Textbundle
- **Privacy-First:** Verarbeitung nur im RAM (keine dauerhafte Speicherung)

---

## 🧰 Tech Stack

- Streamlit
- OpenCV (headless)
- Pillow
- ReportLab

---

## 🚀 Schnellstart (Lokal)

```bash
git clone https://github.com/KeschFlow/kids-activity-book-generator.git
cd kids-activity-book-generator

python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
streamlit run app.py
