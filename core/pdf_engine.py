from reportlab.pdfgen import canvas
from reportlab.lib.units import inch
from reportlab.lib import colors
import io

# Standard Druckformat (quadratisch 8.5x8.5)
TRIM = 8.5 * inch
SAFE = 0.5 * inch

def create_pdf():
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(TRIM, TRIM))
    return c, buffer

def save_pdf(c, buffer):
    c.save()
    buffer.seek(0)
    return buffer.getvalue()

def draw_title(c, text):
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(TRIM / 2, TRIM - SAFE, text)

def draw_word_page(c, word, sentence):
    c.setFont("Helvetica-Bold", 24)
    c.drawCentredString(TRIM / 2, TRIM - 2*inch, word)

    c.setFont("Helvetica", 16)
    c.drawCentredString(TRIM / 2, TRIM - 3*inch, sentence)

    c.showPage()

def draw_fill_blank_page(c, sentence):
    blank = sentence.replace("____", "__________")
    c.setFont("Helvetica", 18)
    c.drawString(SAFE, TRIM - 2*inch, blank)
    c.showPage()

def draw_quiz_page(c, question, options):
    c.setFont("Helvetica-Bold", 18)
    c.drawString(SAFE, TRIM - 2*inch, question)

    y = TRIM - 2.5*inch
    for option in options:
        c.setFont("Helvetica", 16)
        c.drawString(SAFE, y, option)
        y -= 0.5*inch

    c.showPage()
