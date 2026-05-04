"""
Generatore Modulo A2 — riempie il template PDF con i dati ricevuti.
Adattato dallo script genera_modulo_a2.py per girare in serverless function.
"""
import io
import os
import re
from typing import Dict, List, Any
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import landscape, A4

# Coordinate fisse del modulo A2 (estratte dal template originale)
PAGE_W = 841.92
PAGE_H = 595.32

STRUTTURA_FISSA = "Juares 21 Sub 18 - CIN IT015146B4X469D5AP - CIR 015146-CIM-07391"

# Mappa codice ISO 2 lettere -> nome paese in italiano (per fallback "Residente a [paese]")
PAESI_ITA = {
    'IT': 'Italia', 'RO': 'Romania', 'BG': 'Bulgaria', 'GR': 'Grecia',
    'HU': 'Ungheria', 'PL': 'Polonia', 'CZ': 'Repubblica Ceca', 'SK': 'Slovacchia',
    'FR': 'Francia', 'BE': 'Belgio', 'NL': 'Paesi Bassi', 'DE': 'Germania',
    'AT': 'Austria', 'CH': 'Svizzera', 'ES': 'Spagna', 'PT': 'Portogallo',
    'GB': 'Regno Unito', 'UK': 'Regno Unito', 'IE': 'Irlanda',
    'LT': 'Lituania', 'LV': 'Lettonia', 'EE': 'Estonia', 'FI': 'Finlandia',
    'SE': 'Svezia', 'NO': 'Norvegia', 'DK': 'Danimarca',
    'HR': 'Croazia', 'SI': 'Slovenia', 'RS': 'Serbia', 'BA': 'Bosnia ed Erzegovina',
    'MK': 'Macedonia del Nord', 'AL': 'Albania', 'ME': 'Montenegro', 'XK': 'Kosovo',
    'TR': 'Turchia', 'CY': 'Cipro', 'MT': 'Malta', 'LU': 'Lussemburgo',
    'RU': 'Russia', 'UA': 'Ucraina', 'BY': 'Bielorussia', 'MD': 'Moldavia',
    'IN': 'India', 'CN': 'Cina', 'JP': 'Giappone', 'KR': 'Corea del Sud',
    'US': 'Stati Uniti', 'CA': 'Canada', 'MX': 'Messico', 'BR': 'Brasile',
    'AR': 'Argentina', 'AU': 'Australia', 'NZ': 'Nuova Zelanda',
    'KZ': 'Kazakistan', 'UZ': 'Uzbekistan', 'PK': 'Pakistan', 'BD': 'Bangladesh',
    'TH': 'Thailandia', 'VN': 'Vietnam', 'PH': 'Filippine', 'ID': 'Indonesia',
    'MA': 'Marocco', 'EG': 'Egitto', 'TN': 'Tunisia', 'NG': 'Nigeria',
    'ZA': 'Sudafrica', 'IL': 'Israele', 'IR': 'Iran', 'IQ': 'Iraq',
    'SY': 'Siria', 'AF': 'Afghanistan',
}

# Pattern Codice Fiscale italiano
CF_REGEX = re.compile(r'^[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]$')


def _is_italian(p: dict) -> bool:
    cit = (p.get('cittadinanza') or '').upper().strip()
    if cit in ('IT', 'ITA', 'ITALIAN', 'ITALIANA', 'ITALIA'):
        return True
    doc = (p.get('documento') or '').upper().replace(' ', '')
    return bool(len(doc) == 16 and CF_REGEX.match(doc))


def _country_name(p: dict) -> str:
    """Ritorna il nome del paese in italiano dato il codice ISO 2 lettere della cittadinanza."""
    cit = (p.get('cittadinanza') or '').upper().strip()
    return PAESI_ITA.get(cit, '')


def _build_minore_description(m: dict) -> str:
    """Costruisce la stringa descrittiva di un minore per la sezione Art. 5 a) del modulo.
    Per italiani: usa il tipo di documento e il CF se disponibili.
    Per stranieri: usa il tipo di documento + numero."""
    cogn = (m.get('cognome') or '').strip()
    nome = (m.get('nome') or '').strip()
    dn = (m.get('dataNascita') or '').strip()
    ln = (m.get('luogoNascita') or '').strip()
    pv = (m.get('provincia') or '').strip()
    doc = (m.get('documento') or '').strip()
    num_doc = (m.get('numeroDocumento') or '').strip()
    tipo_doc = (m.get('tipoDocumento') or '').strip()

    parts = [f"{cogn} {nome}".strip()]
    if dn:
        parts.append(f"nato/a {dn}")
    if ln:
        if pv and len(pv) <= 3:
            parts.append(f"a {ln} ({pv})")
        else:
            parts.append(f"a {ln}")

    # Riferimento documento
    if _is_italian(m):
        # Italiano: priorità al CF; aggiungi tipo+numero documento se disponibile
        cf = doc if (len(doc.replace(' ', '')) == 16 and CF_REGEX.match(doc.upper().replace(' ', ''))) else ''
        if tipo_doc and num_doc:
            parts.append(f"{tipo_doc} n. {num_doc}")
        elif tipo_doc:
            parts.append(tipo_doc)
        if cf:
            parts.append(f"CF {cf}")
    else:
        # Straniero: tipo documento + numero
        n = num_doc or doc
        if tipo_doc and n:
            parts.append(f"{tipo_doc} n. {n}")
        elif n:
            parts.append(f"doc. n. {n}")

    return " - ".join(parts)


def _apply_residence_fallback(p: dict) -> None:
    """Per stranieri senza indirizzo: imposta comuneResidenza = 'Paese di [Nome]' (modifica in place)."""
    if _is_italian(p):
        return
    if p.get('comuneResidenza') or p.get('viaResidenza'):
        return  # ha già un indirizzo
    paese = _country_name(p)
    if paese:
        p['comuneResidenza'] = f"Paese di {paese}"


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

    # Fallback residenza per stranieri senza indirizzo
    _apply_residence_fallback(sottoscritto)

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

    # Specifica il tipo di documento sotto/accanto a "DI IDENTIFICAZIONE"
    # Spazio bianco a x≈240, top≈219 (sotto la riga "(solo nel caso di cittadino straniero)]")
    tipo_doc_sott = (sottoscritto.get('tipoDocumento') or '').strip()
    num_doc_sott = (sottoscritto.get('numeroDocumento') or '').strip()
    if tipo_doc_sott:
        if num_doc_sott and not _is_italian(sottoscritto):
            tipo_label = f"({tipo_doc_sott} n. {num_doc_sott})"
        else:
            tipo_label = f"({tipo_doc_sott})"
        _draw_text(c, 240, 219, tipo_label, 8)

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

    # Lista minori (max 6 righe nello spazio disponibile, font piccolo)
    base_top = 302
    line_h = 9
    for i, mn in enumerate(minori[:6]):
        text = _build_minore_description(mn)
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
