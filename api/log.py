"""
Endpoint: POST /api/log
Inoltra le righe di log a un Google Apps Script web app che le scrive in un Google Sheet.
URL del web app deve essere configurato come env var GOOGLE_SHEETS_WEBHOOK.
Best-effort: errori non bloccano il flusso utente.
"""
import os
import json
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler

WEBHOOK_URL = os.environ.get("GOOGLE_SHEETS_WEBHOOK", "")


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length).decode('utf-8')

            if not WEBHOOK_URL:
                # log non configurato — accettiamo silenziosamente
                self._ok({"status": "logging_disabled"})
                return

            payload = json.loads(body)
            req = urllib.request.Request(
                WEBHOOK_URL,
                data=json.dumps(payload).encode('utf-8'),
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            try:
                with urllib.request.urlopen(req, timeout=5) as resp:
                    resp.read()
                self._ok({"status": "logged"})
            except urllib.error.URLError as e:
                # log fallito ma non bloccante per l'utente
                self._ok({"status": "log_failed", "reason": str(e)[:120]})

        except Exception as e:
            self._ok({"status": "error", "reason": str(e)[:120]})

    def _ok(self, payload):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
