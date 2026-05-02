// ============================================================
// Modulo A2 - Frontend logic
// ============================================================
const state = {
  files: [],          // File[] caricati
  extracted: [],      // [{id, fileName, cognome, nome, dataNascita, ...}]
  checkin: '',
  checkout: '',
  ref: ''
};

// --- DOM ---
const $ = (id) => document.getElementById(id);
const dropzone = $('dropzone');
const filesInput = $('files');
const filelist = $('filelist');
const extractBtn = $('extract-btn');
const generateBtn = $('generate-btn');
const backBtn = $('back-btn');
const restartBtn = $('restart-btn');
const checkinInput = $('checkin');
const checkoutInput = $('checkout');
const refInput = $('ref');
const loading = $('loading');
const loadingMsg = $('loading-msg');
const errorBox = $('error');
const errorMsg = $('error-msg');

// --- File picker / drag&drop ---
$('pick').addEventListener('click', (e) => {
  e.stopPropagation();
  filesInput.click();
});
filesInput.addEventListener('change', (e) => {
  addFiles(e.target.files);
  // reset so the same file can be re-selected
  e.target.value = '';
});
dropzone.addEventListener('click', (e) => {
  // only trigger if user clicked on the dropzone itself, not on the button or filelist
  if (e.target === dropzone || e.target.closest('p')) {
    filesInput.click();
  }
});
dropzone.addEventListener('dragover', (e) => { e.preventDefault(); dropzone.classList.add('over'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('over'));
dropzone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropzone.classList.remove('over');
  addFiles(e.dataTransfer.files);
});

function addFiles(fileList) {
  for (const f of fileList) {
    state.files.push(f);
  }
  renderFileList();
}

function renderFileList() {
  filelist.innerHTML = '';
  state.files.forEach((f, idx) => {
    const li = document.createElement('li');
    li.innerHTML = `<span>${escapeHtml(f.name)} <small>(${(f.size/1024).toFixed(0)} KB)</small></span>
                    <button class="remove" data-idx="${idx}" aria-label="Rimuovi">×</button>`;
    filelist.appendChild(li);
  });
  filelist.querySelectorAll('.remove').forEach(b => {
    b.addEventListener('click', (e) => {
      const idx = parseInt(e.target.dataset.idx);
      state.files.splice(idx, 1);
      renderFileList();
      updateExtractButton();
    });
  });
  updateExtractButton();
}

function updateExtractButton() {
  const hasDates = checkinInput.value && checkoutInput.value;
  extractBtn.disabled = state.files.length === 0 || !hasDates;
}

checkinInput.addEventListener('change', updateExtractButton);
checkoutInput.addEventListener('change', updateExtractButton);

// --- Extract ---
extractBtn.addEventListener('click', async () => {
  state.checkin = checkinInput.value;
  state.checkout = checkoutInput.value;
  state.ref = refInput.value;

  showLoading('Lettura documenti in corso… (può richiedere 20-40 secondi)');

  try {
    const fd = new FormData();
    fd.append('checkin', state.checkin);
    fd.append('checkout', state.checkout);
    state.files.forEach(f => fd.append('files', f));

    const r = await fetch('/api/extract', { method: 'POST', body: fd });
    if (!r.ok) {
      const txt = await r.text();
      throw new Error(`Errore server: ${r.status} ${txt.slice(0, 200)}`);
    }
    const data = await r.json();

    if (!data.persone || data.persone.length === 0) {
      throw new Error("Non sono riuscito a leggere nessun documento. Riprova con foto più nitide.");
    }

    state.extracted = data.persone.map((p, i) => ({ id: i, ...p, includeAsMinor: !!p.minore }));
    renderStep2();
    showStep(2);
  } catch (err) {
    showError(err.message);
  } finally {
    hideLoading();
  }
});

// --- Step 2 render ---
function renderStep2() {
  const container = $('extracted-list');
  container.innerHTML = '';

  state.extracted.forEach((p) => {
    const card = document.createElement('div');
    card.className = 'person-card';
    const badge = p.minore
      ? '<span class="badge minore">Minore</span>'
      : '<span class="badge adulto">Adulto</span>';

    card.innerHTML = `
      <h4>${escapeHtml(p.cognome || '?')} ${escapeHtml(p.nome || '?')}${badge}</h4>
      <div class="grid">
        <label>Cognome <input type="text" data-id="${p.id}" data-field="cognome" value="${escapeAttr(p.cognome || '')}"></label>
        <label>Nome <input type="text" data-id="${p.id}" data-field="nome" value="${escapeAttr(p.nome || '')}"></label>
        <label>Data di nascita <input type="text" data-id="${p.id}" data-field="dataNascita" placeholder="gg/mm/aaaa" value="${escapeAttr(p.dataNascita || '')}"></label>
        <label>Luogo di nascita <input type="text" data-id="${p.id}" data-field="luogoNascita" value="${escapeAttr(p.luogoNascita || '')}"></label>
        <label>Provincia / Stato <input type="text" data-id="${p.id}" data-field="provincia" value="${escapeAttr(p.provincia || '')}"></label>
        <label>N. documento o CF <input type="text" data-id="${p.id}" data-field="documento" value="${escapeAttr(p.documento || '')}"></label>
        <label>Comune residenza <input type="text" data-id="${p.id}" data-field="comuneResidenza" value="${escapeAttr(p.comuneResidenza || '')}"></label>
        <label>Via e civico <input type="text" data-id="${p.id}" data-field="viaResidenza" value="${escapeAttr(p.viaResidenza || '')}"></label>
      </div>
    `;
    container.appendChild(card);
  });

  // Sync edits back to state
  container.querySelectorAll('input').forEach(inp => {
    inp.addEventListener('input', () => {
      const id = parseInt(inp.dataset.id);
      const field = inp.dataset.field;
      const person = state.extracted.find(x => x.id === id);
      if (person) {
        person[field] = inp.value;
        // Recompute "minore" if dataNascita changed
        if (field === 'dataNascita') {
          person.minore = computeMinore(person.dataNascita, state.checkin);
          renderStep2();
        }
      }
    });
  });

  // Sottoscritto select - default a primo adulto
  const sel = $('sottoscritto-select');
  sel.innerHTML = '';
  state.extracted.forEach((p) => {
    const opt = document.createElement('option');
    opt.value = p.id;
    opt.textContent = `${p.cognome || '?'} ${p.nome || '?'}${p.minore ? ' (minore)' : ''}`;
    sel.appendChild(opt);
  });
  const firstAdult = state.extracted.find(p => !p.minore);
  if (firstAdult) sel.value = firstAdult.id;

  // Minori checkbox list
  const ml = $('minori-list');
  ml.innerHTML = '';
  state.extracted.forEach((p) => {
    const lbl = document.createElement('label');
    lbl.className = 'minore-row';
    lbl.innerHTML = `<input type="checkbox" data-id="${p.id}" ${p.includeAsMinor ? 'checked' : ''}>
                     ${escapeHtml(p.cognome || '?')} ${escapeHtml(p.nome || '?')}
                     <small>(${p.dataNascita || 'data nascita non disponibile'})</small>`;
    lbl.querySelector('input').addEventListener('change', (e) => {
      const id = parseInt(e.target.dataset.id);
      const person = state.extracted.find(x => x.id === id);
      if (person) person.includeAsMinor = e.target.checked;
    });
    ml.appendChild(lbl);
  });
}

function computeMinore(dataNascita, checkin) {
  if (!dataNascita || !checkin) return false;
  const m = dataNascita.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
  if (!m) return false;
  const dn = new Date(parseInt(m[3]), parseInt(m[2]) - 1, parseInt(m[1]));
  const ci = new Date(checkin);
  const age = (ci - dn) / (365.25 * 24 * 3600 * 1000);
  return age < 18;
}

// --- Generate ---
generateBtn.addEventListener('click', async () => {
  const sottoscrittoId = parseInt($('sottoscritto-select').value);
  const sott = state.extracted.find(p => p.id === sottoscrittoId);
  const minori = state.extracted.filter(p => p.includeAsMinor && p.id !== sottoscrittoId);

  if (!sott) { showError('Seleziona il sottoscritto.'); return; }
  if (minori.length === 0) { showError('Spunta almeno un minore.'); return; }

  showLoading('Generazione PDF…');

  try {
    const payload = {
      sottoscritto: sott,
      minori: minori,
      checkin: state.checkin,
      checkout: state.checkout,
      ref: state.ref
    };
    const r = await fetch('/api/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!r.ok) {
      const txt = await r.text();
      throw new Error(`Errore server: ${r.status} ${txt.slice(0, 200)}`);
    }
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const cogn = (sott.cognome || 'modulo').replace(/[^a-zA-Z0-9]/g, '_').toUpperCase();
    const fileName = `ModuloA2_${cogn}_${state.checkin}.pdf`;
    const a = $('download-link');
    a.href = url;
    a.download = fileName;
    a.textContent = `Scarica ${fileName}`;

    // Anomalie - campi vuoti per il sottoscritto
    const anomalie = [];
    if (!sott.luogoNascita) anomalie.push("Luogo di nascita del sottoscritto non rilevato dai documenti.");
    if (!sott.documento) anomalie.push("Codice fiscale o numero documento del sottoscritto non rilevato.");
    if (!sott.comuneResidenza) anomalie.push("Indirizzo di residenza del sottoscritto non rilevato.");
    minori.forEach(m => {
      if (!m.documento) anomalie.push(`Documento del minore ${m.cognome} ${m.nome} non rilevato.`);
    });

    const anomBox = $('anomalie-box');
    const anomList = $('anomalie-list');
    anomList.innerHTML = '';
    if (anomalie.length) {
      anomalie.forEach(a => {
        const li = document.createElement('li');
        li.textContent = a + ' Verrà compilato a mano dall\'ospite prima della firma.';
        anomList.appendChild(li);
      });
      anomBox.classList.remove('hidden');
    } else {
      anomBox.classList.add('hidden');
    }

    // Log async (fire and forget)
    fetch('/api/log', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        timestamp: new Date().toISOString(),
        sottoscritto: `${sott.cognome} ${sott.nome}`,
        checkin: state.checkin,
        checkout: state.checkout,
        ref: state.ref,
        nMinori: minori.length,
        anomalie: anomalie.length
      })
    }).catch(() => { /* logging is best-effort */ });

    showStep(3);
  } catch (err) {
    showError(err.message);
  } finally {
    hideLoading();
  }
});

backBtn.addEventListener('click', () => showStep(1));
restartBtn.addEventListener('click', () => {
  state.files = [];
  state.extracted = [];
  filesInput.value = '';
  refInput.value = '';
  renderFileList();
  showStep(1);
});

// --- Helpers ---
function showStep(n) {
  document.querySelectorAll('.step').forEach(s => s.classList.remove('active'));
  $(`step-${n}`).classList.add('active');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function showLoading(msg) {
  loadingMsg.textContent = msg || 'Caricamento…';
  loading.classList.remove('hidden');
}
function hideLoading() { loading.classList.add('hidden'); }

function showError(msg) {
  errorMsg.textContent = msg;
  errorBox.classList.remove('hidden');
}
$('error-close').addEventListener('click', () => errorBox.classList.add('hidden'));

function escapeHtml(s) {
  return String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function escapeAttr(s) { return escapeHtml(s).replace(/"/g, '&quot;'); }

$('privacy-link').addEventListener('click', (e) => {
  e.preventDefault();
  alert("I documenti caricati vengono inviati a Google Gemini per l'estrazione dei dati e poi scartati. Non vengono conservati né su questo sito né in archivi esterni. I dati estratti vengono usati solo per la compilazione del modulo richiesto.");
});
