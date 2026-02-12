# 🐶 Eddies

**Eddies** ist eine Streamlit-App, die aus Fotos ein personalisiertes **Kids Activity / Malbuch** als PDF erzeugt.  
Optional erzeugt sie außerdem ein **KDP-kompatibles** Interior (8.5" × 8.5" mit Bleed/Anschnitt) inkl. **Preflight** und **QA-Warnseite** (nur Preview).

> Fokus: **druckfertige Outputs** + **RAM-only Verarbeitung** + **wiederholbare Ergebnisse**.

---

## ✅ Features

### 📸 Foto → Ausmalbild
- **Sketch-Engine:** Foto → kontrastreiche Schwarz-Weiß-Skizze zum Ausmalen (OpenCV)
- **Center-Crop + Resize:** konsistentes Seitenformat (Quadrat), ideal für Malbuchseiten

### 🧭 Quest-System (24h)
- **24h-Zyklus:** Jede Seite entspricht einer Stunde (Startzeit wählbar)
- **Zonen/Atmosphäre:** Stunden werden thematischen Zonen zugeordnet (z. B. Morgenstart, Vormittag, Abendwind)
- **Mission Overlay:** Jede Seite enthält:
  - **Bewegung**
  - **Denken**
  - **Proof-Checkbox**
  - **XP**
- **Schwierigkeitsgrad (Auto):** wird aus Alter/Profil abgeleitet (1–5)

### 🖨️ KDP / Print Pipeline
- **KDP-Printmode Toggle:**
  - **Preview Mode:** 8.5" × 8.5" (wie später sichtbar)
  - **KDP Print Mode:** 8.75" × 8.75" (8.5" Trim + 0.125" Bleed je Seite)
- **Safe-Zone korrekt:** Safe Zone wird im Print-Mode um den Bleed verschoben
- **Forced KDP Compliance:** Erzwingt **min. 24 Seiten** + **gerade Seitenzahl**
- **Preflight (300 DPI Ziel):** Prüft Upload-Auflösung und warnt bei zu kleinen Bildern
- **DPI-Guard QA-Seite:** Wenn Bilder zu klein sind, wird im **Preview Mode** automatisch eine **Warnseite** vorn eingefügt (nicht für KDP-Upload gedacht)

### 🎨 Cover + Listing
- **CoverWrap PDF:** Back + Spine + Front in einer Datei
  - Spine-Breite wird berechnet (abhängig von Papier)
  - Barcode-Keepout
  - Spine-Text erst ab **79 Seiten**
- **Listing.txt:** Ready-to-publish KDP Listing-Textbundle

### 🔒 Privacy-First
- **Keine Speicherung:** Verarbeitung nur im RAM (keine dauerhafte Speicherung von Fotos)
- Output wird als PDF/ZIP direkt zum Download bereitgestellt

---

## 🧰 Tech Stack

- **Streamlit**
- **OpenCV (headless)**
- **Pillow**
- **ReportLab**

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