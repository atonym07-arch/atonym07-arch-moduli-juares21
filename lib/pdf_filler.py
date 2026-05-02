"""
Generatore Modulo A2 — riempie il template PDF con i dati ricevuti.
Adattato dallo script genera_modulo_a2.py per girare in serverless function.
"""
import io
import os
from typing import Dict, List, Any
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, A4

# Coordinate fisse del modulo A2 (estratte dal template originale)
PAGE_W = 841.92
PAGE_H = 595.32

STRUTTURA_FISSA = "Juares 21 Sub 18 - CIN IT015146B4X469D5AP - CIR 015146-CIM-07391"


def _draw_text(c, x: float, y: float, text: str, size: int = 9):
    """Disegna testo a coordinate (x, y) - y in alto-down (verrà convertito)."""
    if not text:
        return
    c.setFont("Helvetica", size)
    c.drawString(x, PAGE_H - y, str(text))


def _split_date(date_str: str):
    """Spezza 'gg/mm/aaaa' in (gg, mm, aaaa) - tollerante."""
    if not date_str:
        return ('', '', '')
    parts = str(date_str).split('/')
    if len(parts) != 3:
        return ('', '', '')
    g, m, y = parts[0].strip(), parts[1].strip(), parts[2].strip()
    return (g, m, y)


def build_overlay(data: Dict[str, Any], template_path: str) -> bytes:
    """Costruisce un PDF di overlay con tutti i dati e lo unisce al template.
    Restituisce i bytes del PDF finale."""

    sottoscritto = data['sottoscritto']
    minori: List[Dict] = data.get('minori', [])
    checkin = data['checkin']      # dd/mm/yyyy
    checkout = data['checkout']
    data_firma = data.get('data_firma', checkin)

    # ---- Build overlay (2 pagine) ----
    overlay_buf = io.BytesIO()
    c = canvas.Canvas(overlay_buf, pagesize=(PAGE_W, PAGE_H))

    # --- PAGE 1 ---
    # Sottoscritto cognome+nome
    nomeCogn = f"{sottoscritto.get('cognome','')} {sottoscritto.get('nome','')}".strip()
    _draw_text(c, 110, 138, nomeCogn, 9)

    # Nato a / luogo nascita
    _draw_text(c, 490, 138, sottoscritto.get('luogoNascita', ''), 9)
    # Provincia (di nascita)
    _draw_text(c, 794, 138, sottoscritto.get('provincia', ''), 9)

    # Data nascita
    g, m, y = _split_date(sottoscritto.get('dataNascita', ''))
    _draw_text(c, 27, 156, g, 9)
    _draw_text(c, 50, 156, m, 9)
    _draw_text(c, 75, 156, y, 9)

    # Residenza comune / prov / via / n / cap
    _draw_text(c, 168, 156, sottoscritto.get('comuneResidenza', ''), 8)
    _draw_text(c, 442, 156, sottoscritto.get('provinciaResidenza', ''), 8)
    _draw_text(c, 522, 156, sottoscritto.get('viaResidenza', ''), 8)
    _draw_text(c, 746, 156, sottoscritto.get('nResidenza', ''), 8)
    _draw_text(c, 782, 156, sottoscritto.get('capResidenza', ''), 8)

    # Tel/Cell/Email
    _draw_text(c, 35, 174, sottoscritto.get('tel', ''), 8)
    _draw_text(c, 197, 174, sottoscritto.get('cell', ''), 8)
    _draw_text(c, 549, 174, sottoscritto.get('email', ''), 8)

    # Documento (CF o passaporto) nelle 16 caselle
    doc = (sottoscritto.get('documento', '') or '').upper().replace(' ', '')[:16]
    box_start_x = 273.6
    box_w = 34.8
    for i, ch in enumerate(doc):
        cx = box_start_x + i * box_w + box_w / 2
        c.setFont("Helvetica", 10)
        text_width = c.stringWidth(ch, "Helvetica", 10)
        c.drawString(cx - text_width / 2, PAGE_H - 207, ch)

    # DAL gg/mm/yyyy (check-in)
    cig, cim, ciy = _split_date(checkin)
    _draw_text(c, 126, 247, cig, 9)
    _draw_text(c, 157, 247, cim, 9)
    _draw_text(c, 187, 247, ciy, 9)

    # AL gg/mm/yyyy (check-out)
    cog, com, coy = _split_date(checkout)
    _draw_text(c, 253, 247, cog, 9)
    _draw_text(c, 288, 247, com, 9)
    _draw_text(c, 322, 247, coy, 9)

    # Struttura ricettiva
    _draw_text(c, 504, 247, STRUTTURA_FISSA, 7)

    # Casella Art. 5 a) - X
    c.setFont("Helvetica-Bold", 9)
    c.drawString(20, PAGE_H - 287, "X")

    # Lista minori (max 3 righe nello spazio disponibile, font piccolo)
    base_top = 302
    line_h = 9
    for i, mn in enumerate(minori[:6]):
        cogN = mn.get('cognome', '')
        nomN = mn.get('nome', '')
        dn = mn.get('dataNascita', '')
        ln = mn.get('luogoNascita', '')
        docN = mn.get('documento', '')

        parts = [f"{cogN} {nomN}".strip()]
        if dn:
            parts.append(f"nato/a {dn}")
        if ln:
            parts.append(f"a {ln}")
        if docN:
            parts.append(f"doc. {docN}")
        text = " - ".join(parts)
        _draw_text(c, 42, base_top + i * line_h, text, 7)

    c.showPage()

    # --- PAGE 2 ---
    _draw_text(c, 64, 99, data_firma, 9)
    c.showPage()

    c.save()
    overlay_buf.seek(0)

    # ---- Merge overlay con template ----
    template = PdfReader(template_path)
    overlay = PdfReader(overlay_buf)
    writer = PdfWriter()

    for i in range(len(template.pages)):
        page = template.pages[i]
        if i < len(overlay.pages):
            page.merge_page(overlay.pages[i])
        writer.add_page(page)

    out_buf = io.BytesIO()
    writer.write(out_buf)
    out_buf.seek(0)
    return out_buf.getvalue()
