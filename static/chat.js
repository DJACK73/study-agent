(() => {
  const API = '/api/chat';
  const MAX_OCTETS = 10 * 1024 * 1024;
  const $ = (id) => document.getElementById(id);
  let cid = null, busy = false, fichier = null;
  let ctrl = null;
  const setSend = (on) => { const b = $('btn-send'); b.disabled = false; b.textContent = on ? '✕ Annuler' : 'Envoyer'; };

  async function j(url, opt) {
    const r = await fetch(url, opt);
    let d = null;
    try { d = await r.json(); } catch (_) {}
    if (!r.ok) throw new Error((d && d.error) || ('HTTP ' + r.status));
    return d;
  }
  const heure = (s) => {
    const d = new Date(String(s).replace(' ', 'T') + 'Z');
    return isNaN(d) ? '' : d.toLocaleString('fr-FR', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'});
  };

  // ---- Markdown (échappe d'abord, puis balises : jamais de HTML brut du modèle)
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const inl = (s) => s
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*\w])\*([^*\s][^*]*?)\*(?!\*)/g, '$1<em>$2</em>');
  const RE_H = /^(#{1,4})\s+(.+?)\s*#*\s*$/, RE_UL = /^\s*[-*•]\s+(.*)$/, RE_OL = /^\s*\d+[.)]\s+(.*)$/;
  const RE_ROW = /^\s*\|.*\|\s*$/, RE_SEP = /^\s*\|[\s:|-]+\|\s*$/;
  const cells = (l) => l.trim().replace(/^\||\|$/g, '').split('|').map((c) => inl(c.trim()));
  function md(src) {
    const L = esc(src).split('\n'), out = [];
    let i = 0;
    const special = (l) => /^```/.test(l) || RE_H.test(l) || RE_UL.test(l) || RE_OL.test(l) || RE_ROW.test(l);
    while (i < L.length) {
      const l = L[i];
      let m;
      if (!l.trim()) { i++; continue; }
      if (/^```/.test(l)) {
        const b = []; i++;
        while (i < L.length && !/^```/.test(L[i])) b.push(L[i++]);
        i++; out.push('<pre><code>' + b.join('\n') + '</code></pre>'); continue;
      }
      if ((m = l.match(RE_H))) { const n = Math.max(2, m[1].length); out.push(`<h${n}>${inl(m[2])}</h${n}>`); i++; continue; }
      if (RE_ROW.test(l) && i + 1 < L.length && RE_SEP.test(L[i + 1])) {
        const head = cells(l), rows = [];
        i += 2;
        while (i < L.length && RE_ROW.test(L[i])) rows.push(cells(L[i++]));
        out.push('<table><thead><tr>' + head.map((c) => `<th>${c}</th>`).join('') + '</tr></thead><tbody>' +
          rows.map((r) => '<tr>' + r.map((c) => `<td>${c}</td>`).join('') + '</tr>').join('') + '</tbody></table>');
        continue;
      }
      const lst = RE_UL.test(l) ? ['ul', RE_UL] : RE_OL.test(l) ? ['ol', RE_OL] : null;
      if (lst) {
        const it = [], n0 = (L[i].match(/^\s*(\d+)/) || [])[1];
        while (i < L.length && lst[1].test(L[i])) it.push('<li>' + inl(L[i++].match(lst[1])[1]) + '</li>');
        out.push((lst[0] === 'ol' && n0 ? `<ol start="${n0}">` : `<${lst[0]}>`) + it.join('') + `</${lst[0]}>`); continue;
      }
      const p = [inl(L[i++])];
      while (i < L.length && L[i].trim() && !special(L[i])) p.push(inl(L[i++]));
      out.push('<p>' + p.join('<br>') + '</p>');
    }
    return out.join('');
  }

  function bulle(role, texte, pdf, err, img) {
    const m = $('msgs');
    const e = m.querySelector('.chat-empty'); if (e) e.remove();
    const d = document.createElement('div');
    d.className = 'msg ' + role + (err ? ' err' : '') + (role === 'ai' && !err ? ' md-output' : '');
    if (role === 'ai' && !err) d.dataset.raw = texte;
    if (role === 'user' || err) d.textContent = texte; else d.innerHTML = md(texte);
    if (img) {
      const im = document.createElement('img'); im.src = img; im.alt = '';
      im.style.cssText = 'display:block;max-width:240px;max-height:240px;border-radius:8px;margin-bottom:8px';
      d.prepend(im);
    }
    if (pdf) {
      const a = document.createElement('a');
      a.className = 'pdf-card';
      a.href = API + '/pdf/' + encodeURIComponent(pdf.split('/').pop());
      a.target = '_blank'; a.textContent = '📄 Ouvrir le PDF';
      d.appendChild(a);
    }
    m.appendChild(d); m.scrollTop = m.scrollHeight;
    return d;
  }

  async function liste() {
    const items = await j(API + '/conversations');
    const box = $('conv-items'); box.innerHTML = '';
    items.forEach((c) => {
      const row = document.createElement('div');
      row.className = 'conv-item' + (c.id === cid ? ' active' : '');
      const t = document.createElement('span'); t.className = 'conv-titre'; t.textContent = c.titre; t.title = c.titre + ' (double-clic : renommer)';
      t.ondblclick = (ev) => { ev.stopPropagation(); renommer(c.id, c.titre); };
      const dt = document.createElement('span'); dt.className = 'conv-date'; dt.textContent = heure(c.updated_at);
      const x = document.createElement('button'); x.className = 'conv-del'; x.textContent = '✕'; x.title = 'Supprimer';
      x.onclick = (ev) => { ev.stopPropagation(); supprimer(c.id, c.titre); };
      row.onclick = () => ouvrir(c.id);
      row.append(t, dt, x); box.appendChild(row);
    });
  }

  function actif(on) { if (on) $('inp').focus(); }

  function chip() {
    const c = $('file-chip'); c.innerHTML = '';
    if (!fichier) return;
    const s = document.createElement('span'); s.className = 'chip'; s.textContent = '📎 ' + fichier.name + ' ✕'; s.title = 'Retirer';
    s.onclick = () => { fichier = null; $('file').value = ''; chip(); };
    c.appendChild(s);
  }

  async function ouvrir(id) {
    try {
      const d = await j(API + '/conversations/' + id);
      cid = id; $('msgs').innerHTML = '';
      (d.messages || []).forEach((m) => bulle(m.role, m.contenu, m.pdf_path, false,
        m.image_path ? API + '/img/' + encodeURIComponent(m.image_path.split('/').pop()) : null));
      if (!(d.messages || []).length) $('msgs').innerHTML = '<div class="chat-empty">Discussion vide.</div>';
      fichier = null; $('file').value = ''; chip();
      actif(true); await liste();
    } catch (e) { showToast(e.message, 'error'); }
  }

  async function nouvelle() {
    if (busy) return;
    cid = null; fichier = null; $('file').value = ''; chip();
    $('msgs').innerHTML = '<div class="chat-empty">Nouvelle discussion : écris ou joins un fichier.</div>';
    actif(true); await liste(); $('inp').focus();
  }

  async function renommer(id, ancien) {
    const n = prompt('Nouveau titre', ancien);
    if (!n || !n.trim() || n.trim() === ancien) return;
    try {
      await j(API + '/conversations/' + id, {method:'PATCH', headers:{'Content-Type':'application/json'}, body: JSON.stringify({titre: n.trim()})});
      await liste();
    } catch (e) { showToast(e.message, 'error'); }
  }

  async function supprimer(id, titre) {
    if (busy) { showToast('Attends la fin de la réponse', 'info'); return; }
    if (!confirm('Supprimer « ' + titre + ' » ? Les fichiers liés seront effacés.')) return;
    try {
      await j(API + '/conversations/' + id, {method:'DELETE'});
      if (id === cid) { cid = null; actif(false); $('msgs').innerHTML = '<div class="chat-empty">Choisis une discussion ou crée-en une.</div>'; }
      await liste();
    } catch (e) { showToast(e.message, 'error'); }
  }

  async function envoyer() {
    const txt = $('inp').value.trim();
    if ((!txt && !fichier) || busy) return;
    busy = true; setSend(true); $('inp').value = '';
    const f = fichier; fichier = null; $('file').value = ''; chip();
    if (!cid) {
      try {
        const d0 = await j(API + '/conversations', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
        cid = d0.id; $('msgs').innerHTML = '';
      } catch (e) {
        showToast(e.message, 'error'); $('inp').value = txt; fichier = f; chip();
        busy = false; setSend(false); return;
      }
    }
    bulle('user', txt || ('📎 ' + f.name), null, false,
      f && f.type.indexOf('image/') === 0 ? URL.createObjectURL(f) : null);
    const att = bulle('ai', '…');
    ctrl = new AbortController();
    try {
      let opt;
      if (f) {
        const fd = new FormData();
        fd.append('message', txt); fd.append('web', $('chk-web').checked ? '1' : '0'); fd.append('fichier', f);
        opt = {method:'POST', body: fd, signal: ctrl.signal};
      } else {
        opt = {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({message: txt, web: $('chk-web').checked}), signal: ctrl.signal};
      }
      const d = await j(API + '/conversations/' + cid + '/messages', opt);
      att.remove(); bulle('ai', d.reponse, d.pdf_path);
      if (d.web_statut && d.web_statut !== 'ok') showToast('Web : ' + d.web_statut, 'info');
      await liste();
    } catch (e) {
      att.remove();
      if (e.name === 'AbortError') showToast('Annulé', 'info');
      else bulle('ai', 'Erreur : ' + e.message, null, true);
    }
    busy = false; setSend(false); $('inp').focus();
  }

  $('btn-new').onclick = nouvelle;
  $('btn-send').onclick = () => { if (busy) { if (ctrl) ctrl.abort(); } else envoyer(); };
  $('file').onchange = () => {
    const f = $('file').files[0];
    if (!f) return;
    if (f.size > MAX_OCTETS) { showToast('Fichier > 10 Mo', 'error'); $('file').value = ''; return; }
    fichier = f; chip();
  };
  $('inp').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); envoyer(); } });
  const prendre = (f) => {
    if (!f) return;
    if (f.size > MAX_OCTETS) { showToast('Fichier > 10 Mo', 'error'); return; }
    fichier = f; chip();
  };
  $('inp').addEventListener('paste', (e) => {
    const f = e.clipboardData && e.clipboardData.files && e.clipboardData.files[0];
    if (f) { e.preventDefault(); prendre(f); }
  });
  const zone = document.querySelector('.chat-main');
  zone.addEventListener('dragover', (e) => e.preventDefault());
  zone.addEventListener('drop', (e) => { e.preventDefault(); prendre(e.dataTransfer.files[0]); });
  $('btn-quiz').onclick = () => {
    const l = [...document.querySelectorAll('#msgs .msg.ai')].filter((x) => x.dataset.raw && x.dataset.raw !== '…').pop();
    if (!l) { showToast('Aucune réponse à tester', 'info'); return; }
    try { sessionStorage.setItem('quiz_depuis_chat', l.dataset.raw); }
    catch (_) { showToast('Transfert impossible', 'error'); return; }
    location.href = '/apprendre';
  };
  liste().then(() => { $('inp').focus(); }).catch((e) => showToast(e.message, 'error'));
})();
