"""
Endpoint: POST /api/extract
Riceve documenti d'identità (multipart) + checkin/checkout
Chiama Gemini Vision per estrarre dati strutturati
Restituisce JSON con persone identificate e flag minore
"""
import os
import json
import base64
from datetime import datetime
from http.server import BaseHTTPRequestHandler
import cgi
import io

# google-generativeai per Gemini API
import google.generativeai as genai

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

EXTRACTION_PROMPT = """Sei un assistente che estrae dati anagrafici da documenti d'identità (carte d'identità, passaporti, permessi di soggiorno) di varie nazionalità.

Per OGNI documento allegato (anche se sono più immagini della stessa persona, fronte e retro), estrai una persona separata se i dati sono di soggetti diversi. Se due immagini sono fronte e retro dello STESSO documento (stesso nome, stesso numero), uniscile in una sola persona combinando i dati.

Restituisci ESCLUSIVAMENTE un JSON valido in questo formato:
{
  "persone": [
    {
      "cognome": "...",        // come scritto sul documento, in caratteri latini
      "nome": "...",
      "dataNascita": "gg/mm/aaaa",
      "luogoNascita": "...",   // città. Se non presente sul documento, lascia ""
      "provincia": "...",      // provincia italiana (es. "MI") se cittadino italiano, altrimenti codice paese (es. "RO" per Romania) o ""
      "documento": "...",      // codice fiscale italiano se disponibile, altrimenti numero passaporto/ID
      "comuneResidenza": "...",// comune di residenza se presente
      "provinciaResidenza": "...",
      "viaResidenza": "...",   // via + civico
      "nResidenza": "",
      "capResidenza": "",
      "cittadinanza": "...",   // codice paese ISO (IT, RO, BG, GR, ...)
      "fonti": ["nome_file_1.jpg"]  // file da cui hai preso i dati
    }
  ]
}

Regole importanti:
1. Per le carte d'identità italiane: il codice fiscale è sul retro. Se vedi solo il fronte, lascia "documento" vuoto.
2. Per i passaporti italiani con CIE: usa il codice fiscale, non il numero passaporto.
3. Per documenti stranieri: usa il numero del documento (passaporto o ID).
4. La data di nascita SEMPRE in formato gg/mm/aaaa (es. "11/02/2025").
5. Se un campo non è presente sul documento, lascia stringa vuota "".
6. Per cognomi composti o con caratteri speciali, mantieni la grafia esatta del documento.
7. NON inferire dati che non vedi - meglio lasciare "" che inventare.

Restituisci SOLO il JSON, senza markdown, senza commenti, senza testo prima o dopo."""


def calculate_age_at(birth_date_str: str, ref_date_str: str) -> float:
    """Calcola età in anni alla data di riferimento. Ritorna -1 se parsing fallisce."""
    try:
        bd = datetime.strptime(birth_date_str, '%d/%m/%Y')
        rd = datetime.strptime(ref_date_str, '%Y-%m-%d') if '-' in ref_date_str else datetime.strptime(ref_date_str, '%d/%m/%Y')
        delta = (rd - bd).days / 365.25
        return delta
    except Exception:
        return -1


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            if not GEMINI_API_KEY:
                self._json(500, {"error": "GEMINI_API_KEY non configurata"})
                return

            ctype = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in ctype:
                self._json(400, {"error": "Content-Type deve essere multipart/form-data"})
                return

            # Parse multipart
            fs = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={'REQUEST_METHOD': 'POST', 'CONTENT_TYPE': ctype}
            )
            checkin = fs.getvalue('checkin', '')
            # checkout = fs.getvalue('checkout', '')

            files = []
            if 'files' in fs:
                file_field = fs['files']
                items = file_field if isinstance(file_field, list) else [file_field]
                for item in items:
                    if hasattr(item, 'file') and item.filename:
                        item.file.seek(0)
                        files.append({
                            'name': item.filename,
                            'data': item.file.read(),
                            'mime': item.type or 'application/octet-stream'
                        })

            if not files:
                self._json(400, {"error": "Nessun file ricevuto"})
                return

            # Build Gemini request
            genai.configure(api_key=GEMINI_API_KEY)
            model = genai.GenerativeModel('gemini-2.5-flash')

            # Prepare parts: prompt + each image
            parts = [EXTRACTION_PROMPT + "\n\nFile allegati: " + ", ".join(f['name'] for f in files)]
            for f in files:
                parts.append({
                    'mime_type': self._normalize_mime(f['mime'], f['name']),
                    'data': f['data']
                })

            response = model.generate_content(
                parts,
                generation_config={
                    'temperature': 0.1,
                    'response_mime_type': 'application/json'
                }
            )

            raw = response.text
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                # try to clean
                cleaned = raw.strip().lstrip('`').rstrip('`').replace('json\n', '', 1)
                parsed = json.loads(cleaned)

            persone = parsed.get('persone', [])

            # Add minore flag
            for p in persone:
                age = calculate_age_at(p.get('dataNascita', ''), checkin)
                p['eta'] = round(age, 1) if age > 0 else None
                p['minore'] = bool(0 < age < 18)

            self._json(200, {"persone": persone})

        except Exception as e:
            import traceback
            self._json(500, {"error": f"Errore interno: {str(e)}", "trace": traceback.format_exc()[:500]})

    def _json(self, status, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _normalize_mime(self, mime: str, filename: str) -> str:
        m = (mime or '').lower()
        n = (filename or '').lower()
        if 'jpeg' in m or n.endswith('.jpg') or n.endswith('.jpeg'):
            return 'image/jpeg'
        if 'png' in m or n.endswith('.png'):
            return 'image/png'
        if 'webp' in m or n.endswith('.webp'):
            return 'image/webp'
        if 'pdf' in m or n.endswith('.pdf'):
            return 'application/pdf'
        return 'image/jpeg'  # fallback
