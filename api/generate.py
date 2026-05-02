"""
Endpoint: POST /api/generate
Riceve JSON con sottoscritto + minori + date
Genera il PDF riempito e lo restituisce come binary
"""
import os
import json
import sys
from http.server import BaseHTTPRequestHandler

# Path lib
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from lib.pdf_filler import build_overlay  # noqa: E402

TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), '..', 'lib', 'modello_a2.pdf')


def _to_dd_mm_yyyy(s: str) -> str:
    """Converte 'YYYY-MM-DD' (formato HTML date input) in 'gg/mm/aaaa'."""
    if not s:
        return ''
    if '-' in s and len(s) == 10:
        y, m, d = s.split('-')
        return f"{d}/{m}/{y}"
    return s


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')
            payload = json.loads(body)

            sottoscritto = payload.get('sottoscritto', {})
            minori = payload.get('minori', [])
            checkin = _to_dd_mm_yyyy(payload.get('checkin', ''))
            checkout = _to_dd_mm_yyyy(payload.get('checkout', ''))

            data = {
                'sottoscritto': sottoscritto,
                'minori': minori,
                'checkin': checkin,
                'checkout': checkout,
                'data_firma': checkin
            }

            pdf_bytes = build_overlay(data, TEMPLATE_PATH)

            cogn = (sottoscritto.get('cognome') or 'modulo').replace(' ', '_').upper()
            checkin_safe = checkin.replace('/', '-')
            filename = f"ModuloA2_{cogn}_{checkin_safe}.pdf"

            self.send_response(200)
            self.send_header('Content-Type', 'application/pdf')
            self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
            self.send_header('Content-Length', str(len(pdf_bytes)))
            self.end_headers()
            self.wfile.write(pdf_bytes)

        except Exception as e:
            import traceback
            err = json.dumps({
                "error": f"Errore generazione PDF: {str(e)}",
                "trace": traceback.format_exc()[:500]
            }).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(err)))
            self.end_headers()
            self.wfile.write(err)
