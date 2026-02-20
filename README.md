# E. P. E. — Eddie’s Print Engine (v5.12.0 DUAL MODE)

Generate KDP-ready interior + cover PDFs from uploaded photos.

---

## 🚀 What’s New in v5.12.0

### 🎮 Dual Mode System
- Kid Mode → Gamification, XP, 24-color hour timeline
- Senior Mode → Calm layout, large typography, timeline hidden

### 🎨 24 Unique Hour Colors
- Each hour has a distinct print-friendly HSV color
- Optional 24-dot timeline (disabled in Senior Mode)

### 🧠 Smart Quest Logic
- Auto Singular/Plural correction
- 0-value fallback protection
- 240 dynamic quests + reserve bank
- Shape-count aware instructions

### 📘 KDP Ready
- 26 fixed pages (Intro + 24 missions + Outro)
- Safe Zones
- Barcode Box
- Cover Facts Strip
- Print geometry debug tools

### 🔐 Security Hardening
- 12MB per upload limit
- 160MB total upload cap
- OpenCV 25MP guard
- SQLite fair-use rate limit

### 🔗 QR Outro CTA
Vector-based QR (print sharp)
→ https://keschflow.github.io/start/

---

## 📦 Quickstart

python -m venv .venv
Windows: .venv\Scripts\activate
Mac/Linux: source .venv/bin/activate

pip install -r requirements.txt
streamlit run app.py

---

## 💳 Optional Stripe Configuration

Create .streamlit/secrets.toml:

STRIPE_SECRET_KEY="sk_live_xxx"
STRIPE_PAYMENT_LINK="https://buy.stripe.com/..."

Without secrets, the app runs in Dev Mode (unlocked for testing).

---

## 🏗 Architecture Overview

app.py                → Main Engine (v5.12.0 Dual Mode)
quest_data.py         → World-Building + Hour Colors
image_wash.py         → Upload hardening
analytics_app.py      → Optional analytics tools
app_trainer.py        → Experimental trainer mode
