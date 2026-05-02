# Generatore Modulo A2 — Juares 21 Sub 18

Applicazione web che permette di generare il **Modulo A2** del Comune di Milano (esenzione imposta di soggiorno per minori) caricando i documenti d'identità del gruppo.

## Come funziona

1. L'utente apre la pagina nel browser (qualunque dispositivo, anche cellulare)
2. Inserisce le date di check-in e check-out
3. Trascina i documenti d'identità di tutti i componenti del gruppo (foto)
4. L'AI di Google Gemini legge i documenti ed estrae nome, cognome, data di nascita, n. documento, ecc.
5. L'utente vede una schermata di conferma dei dati e può correggerli
6. Cliccando "Genera" scarica il modulo A2 in PDF, già compilato, pronto da inviare all'ospite per la firma

## Stack

- **Frontend**: HTML/CSS/JavaScript vanilla (no framework, no build)
- **Backend**: Python serverless functions su Vercel
- **AI Vision**: Google Gemini 2.0 Flash (free tier 1.500 req/giorno)
- **PDF**: pypdf + reportlab — riempie il template ufficiale con coordinate
- **Log**: Google Sheets via Apps Script Web App (opzionale, gratuito)

## Costo: zero

Tutti i servizi usati sono entro i tier gratuiti per i volumi della struttura (poche prenotazioni al mese).

---

## Setup — istruzioni passo passo

### Step 1 — Generare la chiave API Gemini

1. Vai su https://aistudio.google.com/app/apikey
2. Login con il tuo account Google
3. Clicca **"Create API key"** → **"Create API key in new project"**
4. Copia la chiave (sarà del tipo `AIzaSy...`). **Tienila al sicuro, è personale.**

### Step 2 — Creare il repository GitHub

1. Vai su https://github.com/new
2. Nome del repository: `moduli-juares21` (o quello che preferisci)
3. Visibilità: **Privato** (i dati anagrafici sono sensibili)
4. NON aggiungere README, .gitignore o licenza — abbiamo già tutto
5. Clicca "Create repository"

### Step 3 — Caricare il codice su GitHub

Da terminale, nella cartella del progetto:

```bash
cd "/percorso/a/moduli-juares21"
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/TUO_USER/moduli-juares21.git
git push -u origin main
```

(Sostituisci `TUO_USER` con il tuo nome utente GitHub.)

### Step 4 — Deploy su Vercel

1. Vai su https://vercel.com/new
2. Login con GitHub se non l'hai già fatto
3. **"Import Git Repository"** → seleziona `moduli-juares21`
4. Nella schermata di configurazione:
   - Framework Preset: **Other**
   - Build Command: lascia vuoto
   - Output Directory: `public`
5. Apri "Environment Variables" e aggiungi:
   - `GEMINI_API_KEY` = la chiave generata allo Step 1
   - (Per ora salta `GOOGLE_SHEETS_WEBHOOK`, lo aggiungiamo dopo)
6. Clicca **"Deploy"**

Dopo 1-2 minuti l'app sarà disponibile su un URL tipo `moduli-juares21-xyz123.vercel.app`. Tienilo da parte.

### Step 5 — Setup del log su Google Sheets (opzionale ma consigliato)

#### 5a. Crea il foglio

1. Vai su https://sheets.google.com → **"Vuoto"**
2. Rinominalo `Log moduli A2`
3. Nella riga 1 metti le intestazioni:
   `timestamp | sottoscritto | check-in | check-out | rif. | n. minori | anomalie`

#### 5b. Crea l'Apps Script

1. Nel foglio: **Estensioni → Apps Script**
2. Cancella il codice di default e incolla:

```javascript
function doPost(e) {
  try {
    const data = JSON.parse(e.postData.contents);
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheets()[0];
    sheet.appendRow([
      data.timestamp || new Date().toISOString(),
      data.sottoscritto || '',
      data.checkin || '',
      data.checkout || '',
      data.ref || '',
      data.nMinori || 0,
      data.anomalie || 0
    ]);
    return ContentService.createTextOutput(JSON.stringify({ok: true}))
      .setMimeType(ContentService.MimeType.JSON);
  } catch (err) {
    return ContentService.createTextOutput(JSON.stringify({error: err.toString()}))
      .setMimeType(ContentService.MimeType.JSON);
  }
}
```

3. **Salva** (icona disco)
4. **Deploy → Nuovo deploy** → tipo **"App web"**
5. Configura:
   - Esegui come: **Me**
   - Chi ha accesso: **Chiunque**
6. Clicca **"Deploy"** → autorizza l'app
7. Copia l'**URL del web app** (tipo `https://script.google.com/macros/s/AKfycb.../exec`)

#### 5c. Configura Vercel

1. Su Vercel → progetto → **Settings → Environment Variables**
2. Aggiungi `GOOGLE_SHEETS_WEBHOOK` = l'URL copiato sopra
3. **Redeploy** dal menu Deployments

A questo punto ogni modulo generato lascerà una riga nel Google Sheet.

### Step 6 — Consegna a tuo padre

Manda a tuo padre:
- L'URL Vercel (es. `moduli-juares21-xyz.vercel.app`)
- Una breve guida d'uso (vedi sotto)

Se vuoi un dominio custom (es. `moduli.juares21.it`), si può configurare gratis su Vercel da **Settings → Domains** se possiedi il dominio.

---

## Guida d'uso (per chi userà l'app)

> Apri il link nel browser. Trascina nei documenti d'identità le foto di tutti i componenti della prenotazione (sia adulti che minori). Inserisci le date e clicca "Analizza". Ti mostro i dati estratti: controllali e correggi se sbagliati. Poi clicca "Genera" e scarichi il PDF da mandare all'ospite per la firma.

---

## Note tecniche

### Privacy e sicurezza

- I documenti d'identità vengono inviati a Google Gemini per l'estrazione dei dati. Google dichiara di non usare i dati delle API a pagamento per addestramento; per la free tier potrebbero invece essere usati. Verificare i termini correnti su https://ai.google.dev/gemini-api/terms
- I documenti **non vengono salvati** sui server Vercel (transitano in memoria solo durante l'elaborazione)
- Il PDF generato non contiene tracce dei file originali
- Il log su Google Sheets contiene SOLO: timestamp, cognome del sottoscritto, date soggiorno, rif. prenotazione, n. minori, n. anomalie. NON contiene documenti d'identità né dati anagrafici dei minori.

### Limiti del free tier Gemini

- 15 richieste al minuto (RPM)
- 1.500 richieste al giorno (RPD)
- 1 milione di token al giorno

Per una struttura piccola con 1-3 prenotazioni minori al mese sono ampiamente sufficienti. Se i volumi crescono, si può passare al piano a pagamento (~0,001-0,005 € per modulo).

### Manutenzione

Il codice è autonomo e non ha dipendenze pesanti. L'unica manutenzione probabile nel medio termine è:
- Aggiornamento del modello Gemini (oggi `gemini-2.0-flash-exp`, in futuro versioni più stabili). Si modifica una riga in `api/extract.py`.
- Modifiche al template del modulo A2 da parte del Comune di Milano. In quel caso va sostituito `lib/modello_a2.pdf` ed eventualmente vanno aggiornate le coordinate in `lib/pdf_filler.py`.

### Sviluppo locale

```bash
# Installa dipendenze Python
pip install -r requirements.txt

# Installa Vercel CLI
npm i -g vercel

# Avvia in locale
vercel dev
# Apri http://localhost:3000
```

Servono comunque le env vars locali — copia `.env.example` in `.env.local` e compila i valori.

---

## Struttura cartella

```
moduli-juares21/
├── api/
│   ├── extract.py          # POST /api/extract — Gemini OCR
│   ├── generate.py         # POST /api/generate — riempie PDF
│   └── log.py              # POST /api/log — invia a Google Sheets
├── lib/
│   ├── modello_a2.pdf      # Template ufficiale Comune di Milano
│   └── pdf_filler.py       # Logica overlay PDF
├── public/
│   ├── index.html          # UI
│   ├── styles.css
│   └── app.js              # logica frontend (drag&drop, fetch, state)
├── requirements.txt        # deps Python
├── vercel.json             # config Vercel
├── .env.example            # template env vars
└── README.md               # questo file
```

---

## Cose che NON fa la v1

Da valutare per un'evoluzione successiva:
- Invio automatico via email all'ospite (richiede integrazione con un servizio SMTP)
- Salvataggio archivio PDF generati su Google Drive
- Riconoscimento automatico del "sub 1" da export Alloggiati Web (oggi va selezionato manualmente)
- Modulo A2 con più di 6 minori (oggi limite per ragioni di spazio sulla riga del modulo)
- Supporto a casi speciali del modulo A2 (esenzione per disabilità, residenti, day use, ecc. — oggi solo art. 5 lett. a)
