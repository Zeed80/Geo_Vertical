from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
import os

def generate_pdf_report(filepath, result, blueprint):
    c = canvas.Canvas(filepath, pagesize=A4)
    width, height = A4
    
    # Simple report generation
    # Assuming fonts might need registration for Russian support
    # For now using standard fonts or creating without explicit unicode check if font missing
    # ideally we load a ttf
    
    y = height - 50
    
    c.setFont("Helvetica-Bold", 16)
    c.drawString(50, y, "Расчет ветровой нагрузки (SP 20.13330.2016)")
    y -= 30
    
    c.setFont("Helvetica", 12)
    c.drawString(50, y, f"Объект: Башня {blueprint.total_height():.1f}м")
    y -= 20
    
    # Frequencies
    y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Собственные частоты:")
    y -= 20
    c.setFont("Helvetica", 12)
    for i, f in enumerate(result.natural_frequencies):
        c.drawString(70, y, f"f{i+1} = {f:.3f} Hz")
        y -= 15
        
    # Loads
    y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.drawString(50, y, "Ветровые нагрузки:")
    y -= 20
    c.setFont("Helvetica", 12)
    total_static = sum(result.static_load)
    total_dynamic = sum(result.dynamic_load)
    c.drawString(70, y, f"Суммарная статическая: {total_static/1000:.2f} kN")
    y -= 15
    c.drawString(70, y, f"Суммарная динамическая: {total_dynamic/1000:.2f} kN")
    y -= 15
    c.drawString(70, y, f"Полная расчетная: {sum(result.total_load)/1000:.2f} kN")
    
    c.save()
