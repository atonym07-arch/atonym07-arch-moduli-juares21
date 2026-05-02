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

# Regola fondamentale: una persona = un documento di identità

Devi restituire UNA persona per ogni TITOLARE di documento. Il numero di persone restituite deve corrispondere al numero di documenti d'identità DIVERSI presenti nelle immagini, identificati per numero del documento.

## Casi particolari da gestire correttamente

1. **Più carte in una sola foto**: se in una foto vedi 2-4 documenti d'identità affiancati, ognuno è una persona separata. Identifica i loro numeri di documento (es. "DJL590919", "DJA655523") per non confonderli.
2. **Fronte e retro dello stesso documento**: se in due immagini diverse vedi lo stesso numero documento (es. una foto con i fronti e una con i retri delle stesse carte), abbinali e restituisci UNA SOLA persona per ogni numero documento, combinando le info dei due lati.
3. **NOMI DEI GENITORI sul retro non sono persone**: sui retri delle carte (italiane, polacche, ceche, ecc.) ci sono campi tipo "IMIONA RODZICÓW", "PARENTS GIVEN NAMES", "COGNOME E NOME DEL PADRE E DELLA MADRE", "MOTHER'S MAIDEN NAME". Questi indicano i genitori del titolare, NON sono persone separate. Ignorali completamente.
4. **NUMERO PERSONALE / PESEL / CNP** non è un'altra persona: è un identificativo aggiuntivo della stessa persona.

# Formato di output

Restituisci ESCLUSIVAMENTE un JSON valido in questo formato:
{
  "persone": [
    {
      "cognome": "...",
      "nome": "...",
      "dataNascita": "gg/mm/aaaa",
      "luogoNascita": "...",
      "provincia": "...",
      "documento": "...",
      "comuneResidenza": "...",
      "provinciaResidenza": "...",
      "viaResidenza": "...",
      "nResidenza": "",
      "capResidenza": "",
      "cittadinanza": "...",
      "numeroDocumento": "..."
    }
  ]
}

# Regole sui campi

1. Per le carte d'identità italiane: il codice fiscale è sul retro. Mettilo in "documento". Se vedi solo il fronte, lascia "documento" vuoto.
2. Per documenti stranieri: usa il numero del documento (passaporto o ID) in "documento" e anche in "numeroDocumento".
3. La data di nascita SEMPRE in formato gg/mm/aaaa.
4. Per le date sui documenti polacchi/ceche/lituani con formato "12.08.1988", convertile in "12/08/1988".
5. Se un campo non è presente sul documento, lascia stringa vuota "".
6. Per cognomi composti, accentati o con caratteri speciali, mantieni la grafia esatta del documento (es. "MAŁGORZATA", "JIŘÍ").
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


def _norm(s: str) -> str:
    return (s or '').strip().lower().replace(' ', '')


def _person_key(p: dict) -> str:
    """Chiave identificativa di una persona: cognome+nome+dataNascita normalizzati."""
    return f"{_norm(p.get('cognome',''))}|{_norm(p.get('nome',''))}|{_norm(p.get('dataNascita',''))}"


def _doc_key(p: dict) -> str:
    """Chiave identificativa di una persona basata sul numero documento, se presente."""
    d = (p.get('documento') or p.get('numeroDocumento') or '').strip().upper().replace(' ', '')
    return d if len(d) >= 5 else ''


def _is_ghost_entry(p: dict) -> bool:
    """Una entry è 'fantasma' (probabilmente nomi dei genitori) se ha pochi dati: niente data nascita, niente documento, niente luogo nascita."""
    has_birth = bool(p.get('dataNascita'))
    has_doc = bool(p.get('documento') or p.get('numeroDocumento'))
    has_place = bool(p.get('luogoNascita'))
    has_address = bool(p.get('comuneResidenza') or p.get('viaResidenza'))
    # se ha solo cognome/nome ma nessun altro campo significativo, è una entry fantasma
    significant = sum([has_birth, has_doc, has_place, has_address])
    return significant == 0


def _merge_persons(a: dict, b: dict) -> dict:
    """Unisce due entries della stessa persona, preferendo i campi non vuoti."""
    out = dict(a)
    for k, v in b.items():
        if not out.get(k) and v:
            out[k] = v
    return out


def deduplicate_persons(persone: list) -> list:
    """Rimuove duplicati e entries fantasma."""
    # Step 1: rimuovi fantasma
    cleaned = [p for p in persone if not _is_ghost_entry(p)]

    # Step 2: dedup per numero documento (più affidabile)
    by_doc = {}
    no_doc = []
    for p in cleaned:
        dk = _doc_key(p)
        if dk:
            if dk in by_doc:
                by_doc[dk] = _merge_persons(by_doc[dk], p)
            else:
                by_doc[dk] = p
        else:
            no_doc.append(p)

    # Step 3: dedup quelli senza documento per cognome+nome+data
    by_pk = {}
    for p in no_doc:
        pk = _person_key(p)
        if pk == '||':
            continue  # nessun dato utile
        if pk in by_pk:
            by_pk[pk] = _merge_persons(by_pk[pk], p)
        else:
            by_pk[pk] = p

    return list(by_doc.values()) + list(by_pk.values())


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

            # Deduplicate (rete di sicurezza contro entries duplicate o fantasma)
            persone = deduplicate_persons(persone)

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
