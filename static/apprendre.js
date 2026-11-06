let currentMode = 4;
let imageB64 = '';
let imageTab = false;
let currentLongueur = 'moyen';

function selectLongueur(longueur, el) {
  currentLongueur = longueur;
  document.querySelectorAll('[data-longueur]').forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
  document.getElementById('longueur-perso-box').style.display =
    longueur === 'perso' ? 'block' : 'none';
}

// Données flashcards/QCM
let fcCards = [], fcIndex = 0, fcScore = 0, fcFlipped = false;
let qcmData = [], qcmIndex = 0, qcmScore = 0, qcmAnswered = [];


function selectMode(mode, el) {
  currentMode = mode;
  document.querySelectorAll('.mode-grid .mode-card').forEach(c => c.classList.remove('selected'));
  el.classList.add('selected');
  document.getElementById('sum-mode').textContent = el.querySelector('.mode-name').textContent;
  document.getElementById('acc-mode').open = false;
  if (!document.getElementById('cours-texte').value.trim()) document.getElementById('acc-cours').open = true;
  document.getElementById('plan-card').style.display = mode === 11 ? 'block' : 'none';
  if (mode === 11) document.getElementById('plan-card').open = true;
  document.getElementById('longueur-card').style.display = mode === 2 ? 'block' : 'none';
}

function switchTab(tab, btn) {
  imageTab = tab === 'image';
  document.querySelectorAll('.input-tab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  document.getElementById('tab-texte').style.display = tab === 'texte' ? 'block' : 'none';
  document.getElementById('tab-image').style.display = tab === 'image' ? 'block' : 'none';
}

function handleFile(file) {
  if (!file) return;
  const reader = new FileReader();
  reader.onload = e => {
    imageB64 = e.target.result.split(',')[1];
    document.getElementById('preview-img').src = e.target.result;
    document.getElementById('upload-zone').style.display = 'none';
    document.getElementById('upload-preview').style.display = 'block';
  };
  reader.readAsDataURL(file);
}

function handleDrop(e) {
  e.preventDefault();
  document.getElementById('upload-zone').classList.remove('drag');
  const file = e.dataTransfer.files[0];
  if (file && file.type.startsWith('image/')) handleFile(file);
}

function removeImage() {
  imageB64 = '';
  document.getElementById('upload-zone').style.display = 'block';
  document.getElementById('upload-preview').style.display = 'none';
  document.getElementById('preview-img').src = '';
}

function hideAllResults() {
  ['result-expose','result-text','result-flashcards','result-qcm']
    .forEach(id => document.getElementById(id).style.display = 'none');
}

function showInline(txt) {
  window._genBusy = true;
  document.getElementById('inline-load-txt').textContent = txt;
  const b = document.getElementById('inline-load');
  b.style.display = 'flex';
  b.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function hideInline() {
  window._genBusy = false;
  document.getElementById('inline-load').style.display = 'none';
}

async function lancer() {
  if (window._genBusy) { showToast('Génération en cours', 'info'); return; }
  const texte    = document.getElementById('cours-texte').value.trim();
  const contexte = document.getElementById('contexte').value.trim();

  if (!texte && !imageB64) {
    showToast('Ajoute un cours (texte ou image)', 'error'); return;
  }

  // Efface l'état vide
  ['acc-mode', 'acc-cours', 'ctx-card', 'longueur-card', 'plan-card'].forEach((id) => { document.getElementById(id).open = false; });
  document.getElementById('result-panel').querySelector('div').style.display = 'none';
  hideAllResults();
  showInline('Gemini analyse ton cours...', true);

  try {
    if (currentMode === 11) {
      // Mode mon plan
      const plan = document.getElementById('mon-plan').value.trim();
      if (!plan) { hideInline(); showToast('Ajoute ton plan', 'error'); return; }
      const data = await apiPost('/api/generer_plan', { texte, plan, image_b64: imageB64 });
      hideInline();
      if (data.error) { showToast(data.error, 'error'); return; }
      showTextResult(data.resultat, '✍️', 'Exposé depuis ton plan');

    } else if (currentMode === 2) {
      hideInline();
      await lancerPlan();
      return;
    } else {
      const data = await apiPost('/api/generer', {
        mode: currentMode, texte, image_b64: imageB64, contexte,
      });
      hideInline();
      if (data.error) { showToast(data.error, 'error'); return; }

      if (currentMode === 3) renderFlashcards(data.resultat);
      else if (currentMode === 4) renderQcm(data.resultat);
      else showTextResult(data.resultat,
        '🎓',
        'Examen');
    }
    showToast('Génération terminée !', 'success');
  } catch(e) {
    hideInline();
    if (e.name === 'AbortError') {
      document.getElementById('result-panel').querySelector('div').style.display = 'flex';
      showToast('Annulé', 'info'); return;
    }
    showToast('Erreur de connexion', 'error');
  }
}


function showResult(id) {
  document.getElementById(id).style.display = 'block';
  document.getElementById(id).scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function copyResult() {
  const t = document.getElementById('result-content').textContent;
  const ok = () => showToast('Copié', 'success');
  const ko = () => showToast('Copie impossible', 'error');
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(t).then(ok, ko);
  else ko();
}
const RE_CORRIGE = /^[ \t*_#]*-{2,}\s*corrig[ée]\s*-{2,}[ \t*_]*$/im;
function showTextResult(txt, icon, title) {
  const old = document.getElementById('btn-corrige');
  if (old) old.remove();
  const m = RE_CORRIGE.exec(txt);
  if (m && icon === '🎓') {
    const q = txt.slice(0, m.index), c = txt.slice(m.index);
    document.getElementById('result-icon').textContent = icon;
    document.getElementById('result-title').textContent = title;
    const box = document.getElementById('result-content');
    box.innerHTML = renderMarkdown(q.replace(/^#{4,6}\s+/gm, '### ')) +
      '<div id="corrige-box" style="display:none">' + renderMarkdown(c.replace(/^#{4,6}\s+/gm, '### ')) + '</div>';
    const b = document.createElement('button');
    b.id = 'btn-corrige'; b.className = 'btn btn-ghost btn-sm'; b.textContent = '👁 Afficher le corrigé';
    b.onclick = () => {
      const cb = document.getElementById('corrige-box');
      const on = cb.style.display === 'none';
      cb.style.display = on ? 'block' : 'none';
      b.textContent = on ? '🙈 Masquer le corrigé' : '👁 Afficher le corrigé';
    };
    document.querySelector('#result-text .result-header').insertBefore(b, document.querySelector('#result-text .result-header button'));
    showResult('result-text');
    return;
  }

  document.getElementById('result-icon').textContent = icon;
  document.getElementById('result-title').textContent = title;
  document.getElementById('result-content').innerHTML = renderMarkdown(txt.replace(/^#{4,6}\s+/gm, '### '));
  showResult('result-text');
}

// ── Option C — Exposé interactif ─────────────────────────
let exposePlan        = [];
let exposeIndex       = 0;
let exposeContenu     = '';
let exposeImageB64    = '';
let exposeSujet       = '';
let exposeAccumule    = '';  // texte de toutes les sections générées

async function lancerPlan() {
  const texte    = document.getElementById('cours-texte').value.trim();
  const contexte = document.getElementById('contexte').value.trim();
  exposeSujet    = texte.slice(0, 80) || 'Sujet';
  exposeContenu  = texte;
  exposeImageB64 = imageB64;

  showInline('Gemini construit le plan...', true);
  const consignePerso = currentLongueur === 'perso'
    ? (document.getElementById('longueur-perso-texte').value.trim() || '')
    : '';
  try {
    const data = await apiPost('/api/expose/plan', {
      sujet: exposeSujet, contexte, longueur: currentLongueur,
      consigne_perso: consignePerso
    });
    hideInline();
    if (data.error) { showToast(data.error, 'error'); return; }
    exposePlan     = data.plan;
    exposeIndex    = 0;
    exposeAccumule = '';
    afficherPlanEditeur();
    showResult('result-expose');
  } catch(e) {
    hideInline();
    if (e.name === 'AbortError') { showToast('Annulé', 'info'); return; }
    showToast('Erreur génération plan', 'error');
  }
}

function afficherPlanEditeur() {
  const el = document.getElementById('plan-editor');

  el.innerHTML = exposePlan.map((s, i) => `
    <div id="plan-row-${i}" style="display:flex;align-items:center;gap:8px;
         background:var(--bg3);border:1px solid var(--border);
         border-radius:var(--radius);padding:10px 14px;transition:border-color .2s;"
         onmouseenter="this.style.borderColor='var(--accent)'"
         onmouseleave="this.style.borderColor='var(--border)'">

      <!-- Numéro -->
      <span style="font-family:'JetBrains Mono',monospace;color:var(--accent2);
                   font-weight:700;min-width:28px;font-size:13px;">${romaniser(i+1)}.</span>

      <!-- Titre éditable -->
      <input class="input" value="${s.titre.replace(/"/g,'&quot;')}"
             style="flex:1;padding:6px 10px;font-size:13px;"
             oninput="exposePlan[${i}].titre = this.value"/>

      <!-- Boutons action -->
      <div style="display:flex;gap:4px;flex-shrink:0;">
        <button onclick="monterSection(${i})" title="Monter"
          style="background:none;border:1px solid var(--border);border-radius:6px;
                 color:var(--text3);cursor:pointer;padding:4px 7px;font-size:12px;
                 transition:all .15s;" ${i===0?'disabled style="opacity:.3;cursor:default;"':''}
          onmouseenter="this.style.background='var(--bg2)'"
          onmouseleave="this.style.background='none'">↑</button>

        <button onclick="descendreSection(${i})" title="Descendre"
          style="background:none;border:1px solid var(--border);border-radius:6px;
                 color:var(--text3);cursor:pointer;padding:4px 7px;font-size:12px;
                 transition:all .15s;" ${i===exposePlan.length-1?'disabled style="opacity:.3;cursor:default;"':''}
          onmouseenter="this.style.background='var(--bg2)'"
          onmouseleave="this.style.background='none'">↓</button>

        <button onclick="supprimerSection(${i})" title="Supprimer"
          style="background:none;border:1px solid rgba(255,107,107,.3);border-radius:6px;
                 color:var(--red);cursor:pointer;padding:4px 7px;font-size:12px;
                 transition:all .15s;"
          onmouseenter="this.style.background='rgba(255,107,107,.1)'"
          onmouseleave="this.style.background='none'">✕</button>
      </div>
    </div>
  `).join('');

  // Bouton ajouter une section
  el.innerHTML += `
    <button onclick="ajouterSection()"
      style="display:flex;align-items:center;gap:8px;width:100%;padding:10px 14px;
             background:transparent;border:1px dashed var(--border);border-radius:var(--radius);
             color:var(--text3);cursor:pointer;font-size:13px;font-family:'Inter',sans-serif;
             transition:all .2s;"
      onmouseenter="this.style.borderColor='var(--accent)';this.style.color='var(--accent2)'"
      onmouseleave="this.style.borderColor='var(--border)';this.style.color='var(--text3)'">
      <span style="font-size:16px;">+</span> Ajouter une section
    </button>`;

  document.getElementById('expose-step1').style.display = 'block';
  document.getElementById('expose-step2').style.display = 'none';
}

function romaniser(n) {
  const r = ['I','II','III','IV','V','VI','VII','VIII','IX','X',
             'XI','XII','XIII','XIV','XV'];
  return r[n-1] || n;
}

function ajouterSection() {
  exposePlan.push({
    numero: romaniser(exposePlan.length + 1),
    titre:  'Nouvelle section',
    points: []
  });
  afficherPlanEditeur();
  // Focus sur le nouvel input
  setTimeout(() => {
    const inputs = document.querySelectorAll('#plan-editor input');
    if (inputs.length) inputs[inputs.length - 1].focus();
  }, 50);
}

function supprimerSection(i) {
  if (exposePlan.length <= 1) {
    showToast('Il faut au moins une section', 'error'); return;
  }
  exposePlan.splice(i, 1);
  // Recalculer les numéros
  exposePlan.forEach((s, idx) => s.numero = romaniser(idx + 1));
  afficherPlanEditeur();
}

function monterSection(i) {
  if (i === 0) return;
  [exposePlan[i-1], exposePlan[i]] = [exposePlan[i], exposePlan[i-1]];
  exposePlan.forEach((s, idx) => s.numero = romaniser(idx + 1));
  afficherPlanEditeur();
}

function descendreSection(i) {
  if (i === exposePlan.length - 1) return;
  [exposePlan[i+1], exposePlan[i]] = [exposePlan[i], exposePlan[i+1]];
  exposePlan.forEach((s, idx) => s.numero = romaniser(idx + 1));
  afficherPlanEditeur();
}

async function regenererPlan() {
  await lancerPlan();
}

async function lancerGenerationSections() {
  exposeIndex    = 0;
  exposeAccumule = '';
  document.getElementById('expose-step1').style.display = 'none';
  document.getElementById('expose-step2').style.display = 'block';
  document.getElementById('expose-sections-content').innerHTML = '';
  await genererSection();
}

async function genererSection() {
  if (exposeIndex >= exposePlan.length) {
    // Terminé
    document.getElementById('expose-next-container').innerHTML =
      `<div style="display:flex;gap:12px;justify-content:center;">
        <span style="font-size:13px;color:var(--green);">✅ Exposé complet généré</span>
        <button class="btn btn-ghost btn-sm" onclick="exportExposePDF()">⬇️ Exporter PDF</button>
       </div>`;
    showToast('Exposé complet !', 'success');
    return;
  }

  const section  = exposePlan[exposeIndex];
  const total    = exposePlan.length;
  const pct      = Math.round(exposeIndex / total * 100);

  document.getElementById('expose-section-label').textContent =
    `Section ${exposeIndex + 1} / ${total} — ${section.titre}`;
  document.getElementById('expose-pct').textContent = pct + '%';
  document.getElementById('expose-progress').style.width = pct + '%';
  document.getElementById('expose-next-btn').disabled = true;
  document.getElementById('expose-next-btn').textContent = '⏳ Génération...';

  // Placeholder pendant génération
  const container = document.getElementById('expose-sections-content');
  const placeholder = document.createElement('div');
  placeholder.id = `section-${exposeIndex}`;
  placeholder.innerHTML = `
    <div style="background:var(--bg3);border:1px solid var(--border);
                border-radius:var(--radius-lg);padding:20px;">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">
        <div class="loader"></div>
        <span style="font-size:13px;color:var(--text2);">
          Génération de "${section.numero}. ${section.titre}"...
        </span>
        <button class="btn btn-ghost btn-sm" style="margin-left:auto" onclick="annulerRequete()">✕ Annuler</button>
      </div>
    </div>`;
  container.appendChild(placeholder);
  placeholder.scrollIntoView({ behavior: 'smooth', block: 'end' });

  try {
    const data = await apiPost('/api/expose/section', {
      sujet:             exposeSujet,
      plan:              exposePlan,
      index:             exposeIndex,
      contenu_precedent: exposeAccumule,
      texte:             exposeContenu,
      image_b64:         exposeImageB64,
      longueur:          currentLongueur,
      consigne_perso:    currentLongueur === 'perso'
        ? (document.getElementById('longueur-perso-texte').value.trim() || '')
        : ''
    });

    if (data.error) { showToast(data.error, 'error'); return; }

    exposeAccumule += '\n\n' + data.section;

    // Remplacer le placeholder par le vrai contenu
    placeholder.innerHTML = `
      <div style="background:var(--bg2);border:1px solid var(--border);
                  border-left:3px solid var(--accent);border-radius:var(--radius-lg);
                  padding:24px;" class="fade-in">
        <div style="font-size:11px;font-weight:600;text-transform:uppercase;
                    letter-spacing:.8px;color:var(--accent2);margin-bottom:12px;">
          ${section.numero}. ${section.titre}
        </div>
        <div class="md-output">${renderMarkdown(data.section)}</div>
      </div>`;

    // Bouton PDF partiel visible dès la 1ère section
    document.getElementById('expose-pdf-partial').style.display = 'inline-flex';

    exposeIndex++;
    const newPct = Math.round(exposeIndex / total * 100);
    document.getElementById('expose-pct').textContent = newPct + '%';
    document.getElementById('expose-progress').style.width = newPct + '%';

    if (exposeIndex < total) {
      document.getElementById('expose-next-btn').disabled  = false;
      document.getElementById('expose-next-btn').textContent =
        `▶ Générer "${exposePlan[exposeIndex].titre}"`;
      document.getElementById('expose-section-label').textContent =
        `Section ${exposeIndex} / ${total} générée`;
    } else {
      document.getElementById('expose-next-container').innerHTML =
        `<div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap;">
          <span style="font-size:13px;color:var(--green);align-self:center;">✅ Exposé complet</span>
          <button class="btn btn-secondary btn-sm" onclick="ouvrirEditeur()">✏️ Modifier</button>
          <button class="btn btn-ghost btn-sm" onclick="lancerTest()">🎯 Me tester</button>
          <button class="btn btn-ghost btn-sm" onclick="exportExposePDF()">⬇️ Exporter PDF</button>
         </div>`;
      document.getElementById('expose-section-label').textContent =
        `${total} / ${total} sections générées`;
      document.getElementById('expose-pct').textContent = '100%';
      document.getElementById('expose-progress').style.width = '100%';
      showToast('Exposé complet généré !', 'success');
    }
  } catch(e) {
    if (e.name === 'AbortError') {
      placeholder.remove();
      document.getElementById('expose-next-btn').disabled = false;
      document.getElementById('expose-next-btn').textContent = `▶ Générer "${section.titre}"`;
      showToast('Annulé', 'info'); return;
    }
    showToast('Erreur lors de la génération', 'error');
    document.getElementById('expose-next-btn').disabled  = false;
    document.getElementById('expose-next-btn').textContent = '🔄 Réessayer';
  }
}

// ── Flashcards ────────────────────────────────────────────
function parseJSON(raw) {
  let txt = raw.trim();
  if (txt.startsWith('```')) {
    txt = txt.split('```')[1];
    if (txt.startsWith('json')) txt = txt.slice(4);
  }
  return JSON.parse(txt);
}

function renderFlashcards(raw) {
  try {
    fcCards   = parseJSON(raw);
    fcIndex   = 0;
    fcScore   = 0;
    fcFlipped = false;
    updateFlashcard();
    showResult('result-flashcards');
  } catch(e) {
    showTextResult(raw, '🃏', 'Flashcards');
  }
}

function updateFlashcard() {
  if (!fcCards.length) return;
  const c = fcCards[fcIndex];
  document.getElementById('fc-question').textContent = c.question;
  document.getElementById('fc-answer').textContent   = c.reponse || c.answer || '';
  document.getElementById('fc-idx').textContent      = `${fcIndex+1} / ${fcCards.length}`;
  document.getElementById('fc-counter').textContent  = `${fcIndex+1}/${fcCards.length}`;
  document.getElementById('flashcard').classList.remove('flipped');
  fcFlipped = false;
}

function flipCard() {
  document.getElementById('flashcard').classList.toggle('flipped');
  fcFlipped = !fcFlipped;
}

function nextCard() { if (fcIndex < fcCards.length-1) { fcIndex++; updateFlashcard(); } }
function prevCard() { if (fcIndex > 0) { fcIndex--; updateFlashcard(); } }

function scoreCard(knew) {
  if (knew) fcScore++;
  const pct = Math.round(fcScore / fcCards.length * 100);
  document.getElementById('fc-score-text').textContent  = `${fcScore} / ${fcCards.length}`;
  document.getElementById('fc-progress-bar').style.width = `${pct}%`;
  if (fcIndex < fcCards.length-1) nextCard();
  else showToast(`Session terminée ! Score : ${fcScore}/${fcCards.length}`, 'success');
}

// ── QCM ───────────────────────────────────────────────────
function renderQcm(raw) {
  try {
    qcmData     = parseJSON(raw);
    qcmIndex    = 0;
    qcmScore    = 0;
    qcmAnswered = new Array(qcmData.length).fill(false);
    updateQcm();
    showResult('result-qcm');
  } catch(e) {
    showTextResult(raw, '✅', 'QCM');
  }
}

function updateQcm() {
  if (!qcmData.length) return;
  const q = qcmData[qcmIndex];
  document.getElementById('qcm-counter').textContent = `${qcmIndex+1}/${qcmData.length}`;
  const answered = qcmAnswered[qcmIndex];

  document.getElementById('qcm-content').innerHTML = `
    <div class="qcm-question">${q.question}</div>
    <div class="qcm-choices">
      ${q.choix.map((c,i) => `
        <button class="qcm-choice ${answered ? getChoiceClass(i,q) : ''}"
          onclick="answerQcm(${i})" ${answered ? 'disabled' : ''}>${c}</button>
      `).join('')}
    </div>
    ${answered ? `<div style="background:rgba(108,99,255,.08);border:1px solid rgba(108,99,255,.2);border-radius:var(--radius);padding:12px 16px;font-size:13.5px;">
      ℹ️ ${q.explication}
    </div>` : ''}
  `;
}

function getChoiceClass(i, q) {
  const letter = String.fromCharCode(65+i); // A, B, C, D
  return letter === q.reponse ? 'correct' : 'wrong';
}

function answerQcm(i) {
  if (qcmAnswered[qcmIndex]) return;
  qcmAnswered[qcmIndex] = true;
  const q = qcmData[qcmIndex];
  const letter = String.fromCharCode(65+i);
  if (letter === q.reponse) qcmScore++;
  const pct = Math.round(qcmScore / qcmData.length * 100);
  document.getElementById('qcm-score-text').textContent   = `${qcmScore} / ${qcmData.length}`;
  document.getElementById('qcm-progress-bar').style.width = `${pct}%`;
  updateQcm();
}

function nextQcm() { if (qcmIndex < qcmData.length-1) { qcmIndex++; updateQcm(); } }
function prevQcm() { if (qcmIndex > 0) { qcmIndex--; updateQcm(); } }

// ── Sélecteur de modèle PDF ───────────────────────────────
let _pdfCallback = null;  // fonction appelée après choix du modèle

const PDF_MODELES_INFO = [
  {
    id: 'academique',
    icon: '🎓',
    nom: 'Académique',
    desc: 'Noir & blanc · Times New Roman · sobre',
    couleur: '#555970'
  },
  {
    id: 'moderne',
    icon: '✨',
    nom: 'Moderne',
    desc: 'Couleurs · Inter · accents violets',
    couleur: '#6C63FF'
  },
  {
    id: 'medical',
    icon: '🏥',
    nom: 'Médical',
    desc: 'Tableaux · sections colorées · clinique',
    couleur: '#3DDC84'
  },
  {
    id: 'minimaliste',
    icon: '📋',
    nom: 'Minimaliste',
    desc: 'Très épuré · beaucoup d\'espace · lecture',
    couleur: '#FFD166'
  }
];

function ouvrirSelecteurPDF(callback) {
  _pdfCallback = callback;

  if (!document.getElementById('pdf-modal')) {
    const modal = document.createElement('div');
    modal.id = 'pdf-modal';
    modal.style.cssText = `
      display:none; position:fixed; inset:0; z-index:900;
      background:rgba(13,15,20,.85); backdrop-filter:blur(6px);
      align-items:center; justify-content:center; padding:24px;`;
    modal.innerHTML = `
      <div style="background:var(--bg2);border:1px solid var(--border);
                  border-radius:var(--radius-lg);width:100%;max-width:520px;
                  overflow:hidden;">
        <div style="padding:20px 24px;border-bottom:1px solid var(--border);
                    display:flex;align-items:center;gap:12px;">
          <span style="font-size:16px;font-weight:700;flex:1;">⬇️ Choisir le modèle PDF</span>
          <button onclick="fermerSelecteurPDF()" style="background:none;border:none;
            color:var(--text3);cursor:pointer;font-size:20px;">✕</button>
        </div>
        <div style="padding:20px 24px;display:grid;grid-template-columns:1fr 1fr;gap:12px;">
          ${PDF_MODELES_INFO.map(m => `
            <div onclick="choisirModele('${m.id}')"
              style="padding:18px;background:var(--bg3);border:1px solid var(--border);
                     border-radius:var(--radius-lg);cursor:pointer;transition:all .2s;
                     display:flex;flex-direction:column;gap:6px;"
              onmouseenter="this.style.borderColor='${m.couleur}';this.style.background='rgba(255,255,255,.03)'"
              onmouseleave="this.style.borderColor='var(--border)';this.style.background='var(--bg3)'">
              <span style="font-size:24px;">${m.icon}</span>
              <span style="font-size:14px;font-weight:600;color:var(--text);">${m.nom}</span>
              <span style="font-size:11px;color:var(--text3);line-height:1.4;">${m.desc}</span>
            </div>`).join('')}
        </div>
        <div style="padding:0 24px 20px;text-align:center;">
          <span style="font-size:11px;color:var(--text3);">
            Clique sur un modèle pour télécharger le PDF
          </span>
        </div>
      </div>`;
    document.body.appendChild(modal);
    modal.onclick = e => { if (e.target === modal) fermerSelecteurPDF(); };
  }

  document.getElementById('pdf-modal').style.display = 'flex';
}

function fermerSelecteurPDF() {
  document.getElementById('pdf-modal').style.display = 'none';
  _pdfCallback = null;
}

async function choisirModele(modele) {
  fermerSelecteurPDF();
  if (_pdfCallback) await _pdfCallback(modele);
}

// ── Export PDF texte (tous modes sauf flashcards) ─────────
function exportPDF() {
  const texte = document.getElementById('result-content').textContent;
  const titre = document.getElementById('result-title').textContent;
  ouvrirSelecteurPDF(async (modele) => {
    showLoading('Génération du PDF...');
    try {
      const res = await fetch('/api/export/pdf', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ texte, titre, modele })
      });
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `${titre.replace(/ /g,'_')}_${modele}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      showToast('PDF téléchargé !', 'success');
    } catch(e) { showToast('Erreur PDF', 'error'); }
    hideLoading();
  });
}

// ── Export PDF exposé interactif ──────────────────────────
async function exportExposePDF() {
  if (!exposeAccumule) { showToast('Aucun contenu à exporter', 'error'); return; }
  ouvrirSelecteurPDF(async (modele) => {
    showLoading('Génération du PDF...');
    try {
      const res = await fetch('/api/export/pdf', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ texte: exposeAccumule, titre: exposeSujet, modele })
      });
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = `expose_${exposeSujet.replace(/ /g,'_').slice(0,30)}_${modele}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      showToast('PDF téléchargé !', 'success');
    } catch(e) { showToast('Erreur PDF', 'error'); }
    hideLoading();
  });
}

// ── Export PDF flashcards ─────────────────────────────────
async function exportFlashcardsPDF() {
  if (!fcCards.length) { showToast('Aucune carte à exporter', 'error'); return; }
  const titre = document.getElementById('cours-texte').value.slice(0,40) || 'Flashcards';
  showLoading('Génération du PDF flashcards...');
  try {
    const res = await fetch('/api/export/flashcards', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ cards: fcCards, titre })
    });
    const blob = await res.blob();
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement('a');
    a.href     = url;
    a.download = `flashcards_${titre.replace(/ /g,'_')}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
    showToast('PDF flashcards téléchargé !', 'success');
  } catch(e) { showToast('Erreur PDF', 'error'); }
  hideLoading();
}
// ── Éditeur de contenu avant PDF ─────────────────────────
function ouvrirEditeur() {
  if (!exposeAccumule) { showToast('Aucun contenu à éditer', 'error'); return; }

  // Créer le modal s'il n'existe pas
  if (!document.getElementById('editeur-modal')) {
    const modal = document.createElement('div');
    modal.id = 'editeur-modal';
    modal.style.cssText = `
      display:none; position:fixed; inset:0; z-index:800;
      background:rgba(13,15,20,.85); backdrop-filter:blur(6px);
      align-items:center; justify-content:center; padding:24px;`;
    modal.innerHTML = `
      <div style="background:var(--bg2);border:1px solid var(--border);
                  border-radius:var(--radius-lg);width:100%;max-width:860px;
                  max-height:90vh;display:flex;flex-direction:column;overflow:hidden;">

        <!-- Header -->
        <div style="padding:18px 24px;border-bottom:1px solid var(--border);
                    display:flex;align-items:center;gap:12px;flex-shrink:0;">
          <span style="font-size:16px;font-weight:700;flex:1;">✏️ Modifier l'exposé</span>
          <span style="font-size:12px;color:var(--text3);">
            Modifie le texte librement avant d'exporter en PDF
          </span>
          <button onclick="fermerEditeur()" style="background:none;border:none;
            color:var(--text3);cursor:pointer;font-size:20px;padding:0 4px;">✕</button>
        </div>

        <!-- Barre d'outils -->
        <div style="padding:10px 24px;border-bottom:1px solid var(--border);
                    display:flex;gap:8px;flex-wrap:wrap;flex-shrink:0;background:var(--bg3);">
          <button onclick="insererFormat('# ')" class="btn btn-ghost btn-sm">H1</button>
          <button onclick="insererFormat('## ')" class="btn btn-ghost btn-sm">H2</button>
          <button onclick="insererFormat('### ')" class="btn btn-ghost btn-sm">H3</button>
          <button onclick="insererFormat('**','**')" class="btn btn-ghost btn-sm"><b>Gras</b></button>
          <button onclick="insererFormat('*','*')" class="btn btn-ghost btn-sm"><i>Italique</i></button>
          <button onclick="insererFormat('- ')" class="btn btn-ghost btn-sm">• Liste</button>
          <div style="width:1px;background:var(--border);margin:0 4px;"></div>
          <button onclick="reinitialiserEditeur()" class="btn btn-ghost btn-sm"
            style="color:var(--yellow);">↺ Réinitialiser</button>
        </div>

        <!-- Textarea -->
        <textarea id="editeur-textarea"
          style="flex:1;background:var(--bg2);border:none;outline:none;
                 color:var(--text);font-family:'JetBrains Mono',monospace;
                 font-size:13px;line-height:1.7;padding:24px;resize:none;
                 overflow-y:auto;min-height:400px;"></textarea>

        <!-- Footer -->
        <div style="padding:16px 24px;border-top:1px solid var(--border);
                    display:flex;gap:10px;justify-content:flex-end;flex-shrink:0;">
          <button onclick="fermerEditeur()" class="btn btn-ghost">Annuler</button>
          <button onclick="validerEditeur()" class="btn btn-primary">
            ✅ Valider et exporter PDF
          </button>
        </div>
      </div>`;
    document.body.appendChild(modal);
  }

  // Remplir avec le contenu actuel
  document.getElementById('editeur-textarea').value = exposeAccumule.trim();
  const modal = document.getElementById('editeur-modal');
  modal.style.display = 'flex';
  // Fermer sur clic extérieur
  modal.onclick = e => { if (e.target === modal) fermerEditeur(); };
}

function fermerEditeur() {
  document.getElementById('editeur-modal').style.display = 'none';
}

function validerEditeur() {
  const contenuEdite = document.getElementById('editeur-textarea').value.trim();
  if (!contenuEdite) { showToast('Contenu vide', 'error'); return; }
  exposeAccumule = contenuEdite;  // Met à jour le contenu global
  fermerEditeur();
  exportExposePDF();              // Exporte directement avec le contenu modifié
}

function reinitialiserEditeur() {
  // Remet le contenu original généré par Gemini
  if (confirm('Réinitialiser le texte ? Les modifications seront perdues.')) {
    document.getElementById('editeur-textarea').value = exposeAccumule.trim();
  }
}

function insererFormat(avant, apres = '') {
  const ta  = document.getElementById('editeur-textarea');
  const deb = ta.selectionStart;
  const fin = ta.selectionEnd;
  const sel = ta.value.substring(deb, fin);
  const rem = ta.value.substring(0, deb) + avant + sel + apres + ta.value.substring(fin);
  ta.value  = rem;
  ta.focus();
  ta.selectionStart = deb + avant.length;
  ta.selectionEnd   = deb + avant.length + sel.length;
}
// ── Test auto-évaluation ──────────────────────────────────
let testQuestions = [];
let testIndex     = 0;
let testScore     = 0;

async function lancerTest() {
  if (!exposeAccumule) { showToast('Génère d\'abord un exposé', 'error'); return; }

  // Créer modal si absent
  if (!document.getElementById('test-modal')) {
    const modal = document.createElement('div');
    modal.id = 'test-modal';
    modal.style.cssText = `
      display:none; position:fixed; inset:0; z-index:800;
      background:rgba(13,15,20,.85); backdrop-filter:blur(6px);
      align-items:center; justify-content:center; padding:24px;`;
    modal.innerHTML = `
      <div style="background:var(--bg2);border:1px solid var(--border);
                  border-radius:var(--radius-lg);width:100%;max-width:680px;
                  max-height:90vh;display:flex;flex-direction:column;overflow:hidden;">

        <div style="padding:18px 24px;border-bottom:1px solid var(--border);
                    display:flex;align-items:center;gap:12px;">
          <span style="font-size:16px;font-weight:700;flex:1;">🎯 Test de compréhension</span>
          <span id="test-compteur" style="font-size:12px;color:var(--text3);
                font-family:'JetBrains Mono',monospace;">0/5</span>
          <button onclick="fermerTest()" style="background:none;border:none;
            color:var(--text3);cursor:pointer;font-size:20px;">✕</button>
        </div>

        <div style="flex:1;overflow-y:auto;padding:28px;">
          <div id="test-body"></div>
        </div>

        <div style="padding:16px 24px;border-top:1px solid var(--border);
                    display:flex;gap:10px;justify-content:flex-end;">
          <button onclick="fermerTest()" class="btn btn-ghost">Fermer</button>
          <button id="test-btn-suivant" onclick="testSuivant()" class="btn btn-primary"
                  style="display:none;">Question suivante →</button>
          <button id="test-btn-valider" onclick="validerReponse()" class="btn btn-primary">
            ✅ Valider
          </button>
        </div>
      </div>`;
    document.body.appendChild(modal);
  }

  document.getElementById('test-modal').style.display = 'flex';
  document.getElementById('test-body').innerHTML =
    `<div style="text-align:center;padding:40px;">
       <div class="loader" style="width:32px;height:32px;margin:0 auto 16px;border-width:3px;"></div>
       <div style="color:var(--text2);">Gemini prépare les questions...</div>
     </div>`;

  try {
    const data = await apiPost('/api/expose/test', {
      contenu: exposeAccumule, sujet: exposeSujet
    });
    if (data.error) { showToast(data.error, 'error'); fermerTest(); return; }
    testQuestions = data.questions;
    testIndex     = 0;
    testScore     = 0;
    afficherQuestion();
  } catch(e) {
    showToast('Erreur lors de la génération du test', 'error');
    fermerTest();
  }
}

function afficherQuestion() {
  if (testIndex >= testQuestions.length) { afficherResultatTest(); return; }

  const q = testQuestions[testIndex];
  document.getElementById('test-compteur').textContent =
    `${testIndex + 1} / ${testQuestions.length}`;
  document.getElementById('test-btn-valider').style.display = 'inline-flex';
  document.getElementById('test-btn-suivant').style.display = 'none';

  document.getElementById('test-body').innerHTML = `
    <div style="margin-bottom:20px;">
      <div class="progress-bar" style="margin-bottom:20px;">
        <div class="progress-fill" style="width:${testIndex/testQuestions.length*100}%"></div>
      </div>
      <div style="font-size:16px;font-weight:600;line-height:1.5;margin-bottom:20px;">
        ${testIndex + 1}. ${q.question}
      </div>
      <textarea id="test-reponse" class="textarea"
        placeholder="Ta réponse..."
        style="min-height:100px;font-size:14px;"></textarea>
    </div>`;

  setTimeout(() => document.getElementById('test-reponse')?.focus(), 100);
}

async function validerReponse() {
  const reponse = document.getElementById('test-reponse')?.value.trim();
  if (!reponse) { showToast('Écris une réponse', 'error'); return; }

  const q = testQuestions[testIndex];
  document.getElementById('test-btn-valider').disabled = true;
  document.getElementById('test-btn-valider').textContent = '⏳ Correction...';

  try {
    const data = await apiPost('/api/expose/corriger', {
      question:         q.question,
      reponse_user:     reponse,
      reponse_attendue: q.reponse_attendue
    });

    testScore += data.score;

    const couleur = data.score === 2
      ? 'var(--green)' : data.score === 1 ? 'var(--yellow)' : 'var(--red)';
    const label   = data.score === 2 ? '✅ Correct' : data.score === 1
      ? '⚠️ Partiel' : '❌ Incorrect';

    // Afficher correction
    const existing = document.getElementById('test-body');
    existing.innerHTML += `
      <div style="background:var(--bg3);border-left:3px solid ${couleur};
                  border-radius:var(--radius);padding:14px 16px;margin-top:12px;
                  animation:fadeIn .3s ease;">
        <div style="font-weight:600;color:${couleur};margin-bottom:6px;">
          ${label} — ${data.score}/2 points
        </div>
        <div style="font-size:13.5px;color:var(--text2);line-height:1.6;">
          ${data.feedback}
        </div>
        <div style="font-size:12px;color:var(--text3);margin-top:8px;">
          Réponse attendue : ${q.reponse_attendue}
        </div>
      </div>`;

    document.getElementById('test-btn-valider').style.display = 'none';
    document.getElementById('test-btn-suivant').style.display = 'inline-flex';
    document.getElementById('test-btn-suivant').textContent =
      testIndex + 1 < testQuestions.length
        ? 'Question suivante →' : 'Voir le résultat →';

  } catch(e) {
    showToast('Erreur correction', 'error');
    document.getElementById('test-btn-valider').disabled = false;
    document.getElementById('test-btn-valider').textContent = '✅ Valider';
  }
}

function testSuivant() {
  testIndex++;
  afficherQuestion();
}

function afficherResultatTest() {
  const total   = testQuestions.length * 2;
  const pct     = Math.round(testScore / total * 100);
  const mention = pct >= 80 ? '🏆 Excellent !'
                : pct >= 60 ? '👍 Bien'
                : pct >= 40 ? '📈 En progrès'
                : '📚 À retravailler';

  document.getElementById('test-compteur').textContent = 'Résultat';
  document.getElementById('test-btn-valider').style.display = 'none';
  document.getElementById('test-btn-suivant').style.display = 'none';

  document.getElementById('test-body').innerHTML = `
    <div style="text-align:center;padding:24px 0;">
      <div style="font-size:52px;margin-bottom:12px;">${pct >= 80 ? '🏆' : pct >= 60 ? '👍' : pct >= 40 ? '📈' : '📚'}</div>
      <div style="font-size:24px;font-weight:700;margin-bottom:4px;">${testScore} / ${total} points</div>
      <div style="font-size:16px;color:var(--text2);margin-bottom:20px;">${mention}</div>
      <div class="progress-bar" style="max-width:300px;margin:0 auto 20px;height:10px;">
        <div class="progress-fill ${pct>=60?'green':pct>=40?'yellow':'red'}"
             style="width:${pct}%"></div>
      </div>
      <div style="font-size:13px;color:var(--text3);">
        ${pct < 60 ? 'Relis l\'exposé et retente — la répétition renforce la mémoire.' : 'Continue comme ça !'}
      </div>
    </div>`;
}

function fermerTest() {
  document.getElementById('test-modal').style.display = 'none';
}

// Longueur et plan : résumés + repli
document.querySelectorAll('[data-longueur]').forEach((el) => el.addEventListener('click', () => {
  document.getElementById('sum-long').textContent = el.querySelector('.mode-name').textContent;
  if (el.dataset.longueur !== 'perso') document.getElementById('longueur-card').open = false;
}));
document.getElementById('mon-plan').addEventListener('input', (e) => {
  const n = e.target.value.split('\n').filter((l) => l.trim()).length;
  document.getElementById('sum-plan').textContent = n ? n + ' sections' : 'vide';
});

// Résumés des étapes repliables
document.getElementById('cours-texte').addEventListener('input', (e) => {
  const n = e.target.value.length;
  document.getElementById('sum-cours').textContent = n ? n + ' caractères' : 'vide';
});
document.getElementById('contexte').addEventListener('input', (e) => {
  const v = e.target.value.trim();
  document.getElementById('sum-ctx').textContent = v ? v.slice(0, 30) + (v.length > 30 ? '…' : '') : 'aucun';
});

// Transfert depuis /discuter (bouton « Tester »)
(function () {
  try {
    const t = sessionStorage.getItem('quiz_depuis_chat');
    if (!t) return;
    sessionStorage.removeItem('quiz_depuis_chat');
    document.getElementById('cours-texte').value = t;
    document.getElementById('cours-texte').dispatchEvent(new Event('input'));
    showToast('Texte de la discussion chargé : clique sur Générer', 'info');
  } catch (_) {}
})();
