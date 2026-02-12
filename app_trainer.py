import streamlit as st

from core import pdf_engine
from core.subject_data import SUBJECTS


st.set_page_config(page_title="Eddies Sprachtrainer", layout="centered", page_icon="📘")

st.title("📘 Eddies Sprachtrainer")
st.caption("Fachspezifische Vokabel- & Arbeitshefte als druckfertiges PDF (inkl. Lückentext & Quiz).")

col1, col2 = st.columns(2)
with col1:
    subject = st.selectbox("Fach auswählen", list(SUBJECTS.keys()))
with col2:
    level = st.selectbox("Sprachniveau", ["A1", "A2", "B1"])

st.divider()

st.subheader("Optionen")
c1, c2, c3 = st.columns(3)
with c1:
    include_vocab = st.toggle("Vokabelkarten", value=True)
with c2:
    include_cloze = st.toggle("Lückentexte", value=True)
with c3:
    include_quiz = st.toggle("Quiz (A/B/C)", value=True)

quiz_questions = st.slider("Anzahl Quizfragen", min_value=1, max_value=20, value=10, step=1)

seed = st.number_input("Seed (gleich = gleiches Heft)", min_value=1, max_value=999999, value=42, step=1)

st.divider()

st.subheader("Optional: Eigene Bilder (Handy-Upload)")
uploaded_images = st.file_uploader(
    "Wenn du Bilder hochlädst, werden sie auf den ersten Vokabelkarten verwendet (1 Bild pro Karte).",
    accept_multiple_files=True,
    type=["jpg", "jpeg", "png"],
)

entries = SUBJECTS[subject]
max_quiz = min(len(entries), 20)
quiz_questions = min(quiz_questions, max_quiz)

can_build = include_vocab or include_cloze or include_quiz

if st.button("📄 PDF generieren", disabled=not can_build):
    try:
        pdf_bytes = pdf_engine.build_trainer_pdf(
            subject_name=subject,
            level=level,
            entries=entries,
            uploaded_images=uploaded_images,
            include_vocab_pages=include_vocab,
            include_cloze_pages=include_cloze,
            include_quiz_pages=include_quiz,
            quiz_questions=quiz_questions,
            seed=int(seed),
            kdp_mode=False,  # worksheets: no bleed needed
        )

        st.success("Fertig ✅")
        st.download_button(
            "⬇ PDF herunterladen",
            data=pdf_bytes,
            file_name=f"{subject}_Sprachtrainer_{level}.pdf".replace(" ", "_"),
            mime="application/pdf",
        )
    except Exception as e:
        st.error(f"Fehler: {e}")
