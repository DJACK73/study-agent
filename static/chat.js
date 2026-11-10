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

  function parseImgs(s) { try { return s ? JSON.parse(s) : null; } catch (e) { return null; } }

  function agrandir(x) {
    const o = document.createElement('div');
    o.style.cssText = 'position:fixed;inset:0;z-index:1000;background:rgba(0,0,0,.85);display:flex;align-items:center;justify-content:center;padding:16px;cursor:zoom-out';
    const im = document.createElement('img');
    im.src = x.url; im.alt = x.titre || '';
    im.style.cssText = 'max-width:96vw;max-height:94vh;background:#fff;border-radius:8px';
    const cle = (e) => { if (e.key === 'Escape') fermer(); };
    const fermer = () => { o.remove(); document.removeEventListener('keydown', cle); };
    o.onclick = fermer; document.addEventListener('keydown', cle);
    o.appendChild(im); document.body.appendChild(o);
  }

  function figIm(x) {
    const f = document.createElement('figure');
    f.style.cssText = 'margin:12px 0;max-width:520px';
    const im = document.createElement('img');
    im.src = x.url; im.alt = x.titre || ''; im.loading = 'lazy';
    im.style.cssText = 'display:block;width:100%;border-radius:8px;background:#fff;cursor:zoom-in';
    im.onclick = () => agrandir(x);
    const cap = document.createElement('figcaption');
    cap.style.cssText = 'font-size:12px;color:var(--text3);margin-top:4px';
    const a = document.createElement('a');
    a.href = x.page; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.textContent = x.titre || 'Source';
    a.style.color = 'var(--accent2)';
    cap.append(a, document.createTextNode(' \u00b7 ' + (x.auteur || '') + ' \u00b7 ' + (x.licence || '')));
    f.append(im, cap);
    return f;
  }

  function bulle(role, texte, pdf, err, img, imgs, srcs) {
    const m = $('msgs');
    const e = m.querySelector('.chat-empty'); if (e) e.remove();
    const d = document.createElement('div');
    d.className = 'msg ' + role + (err ? ' err' : '') + (role === 'ai' && !err ? ' md-output' : '');
    if (role === 'ai' && !err) d.dataset.raw = texte;
    const place = (imgs || []).filter((x) => typeof x.apres === 'number');
    const bas = (imgs || []).filter((x) => typeof x.apres !== 'number');
    if (role === 'user' || err) d.textContent = texte;
    else if (place.length) {
      const blocs = String(texte).split(/\n\s*\n/);
      let k = 0;
      const rendre = (fin) => {
        if (fin < k) return;
        const w = document.createElement('div');
        w.innerHTML = md(blocs.slice(k, fin + 1).join('\n\n'));
        d.appendChild(w); k = fin + 1;
      };
      place.slice().sort((a, b) => a.apres - b.apres).forEach((x) => {
        rendre(Math.min(x.apres, blocs.length - 1)); d.appendChild(figIm(x));
      });
      rendre(blocs.length - 1);
    } else d.innerHTML = md(texte);
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
    if (bas.length) {
      const g = document.createElement('div');
      g.style.cssText = 'display:flex;flex-wrap:wrap;gap:12px;margin-top:10px';
      bas.forEach((x) => {
        const f = document.createElement('figure');
        f.style.cssText = 'margin:0;max-width:240px';
        const im = document.createElement('img');
        im.src = x.url; im.alt = x.titre || ''; im.loading = 'lazy';
        im.style.cssText = 'display:block;width:100%;border-radius:8px;background:#fff';
        const cap = document.createElement('figcaption');
        cap.style.cssText = 'font-size:12px;color:var(--text3);margin-top:4px';
        const a = document.createElement('a');
        a.href = x.page; a.target = '_blank'; a.rel = 'noopener noreferrer'; a.textContent = x.titre || 'Source';
        cap.append(a, document.createTextNode(' \u00b7 ' + x.auteur + ' \u00b7 ' + x.licence));
        f.append(im, cap); g.appendChild(f);
      });
      d.appendChild(g);
    }
    if (srcs && srcs.length) {
      const box = document.createElement('div');
      box.style.cssText = 'margin-top:10px;padding-top:8px;border-top:1px solid var(--border);font-size:12px;color:var(--text3)';
      srcs.forEach((s, i) => {
        const row = document.createElement('div');
        const a = document.createElement('a');
        a.href = String(s.url || '').slice(0, 4) === 'http' ? s.url : '#';
        a.target = '_blank'; a.rel = 'noopener noreferrer';
        a.textContent = '[' + (i + 1) + '] ' + (s.titre || s.url || 'Source');
        a.style.color = 'var(--accent2)';
        row.appendChild(a); box.appendChild(row);
      });
      d.appendChild(box);
    }
    m.appendChild(d); m.scrollTop = m.scrollHeight;
    return d;
  }

  async function chargerImages(el, d) {
    const att = document.createElement('div');
    att.style.cssText = 'margin-top:8px;font-size:12px;color:var(--text3)';
    att.textContent = 'Recherche des images…';
    el.appendChild(att);
    const c = new AbortController();
    const t = setTimeout(() => c.abort(), 90000);
    try {
      const r = await j(API + '/messages/' + d.message_id + '/images',
        {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({slots: d.slots}), signal: c.signal});
      if (!el.isConnected) return;
      if (r.images && r.images.length) {
        const m = $('msgs'), st = m.scrollTop;
        const neu = bulle('ai', d.reponse, d.pdf_path, false, null, r.images, d.sources);
        el.replaceWith(neu); m.scrollTop = st;
      } else att.remove();
    } catch (e) {
      if (el.isConnected) att.textContent = 'Images indisponibles';
    } finally { clearTimeout(t); }
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
        m.image_path ? API + '/img/' + encodeURIComponent(m.image_path.split('/').pop()) : null, parseImgs(m.images_json), parseImgs(m.sources_json)));
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
      att.remove();
      const neu = bulle('ai', d.reponse, d.pdf_path, false, null, d.images, d.sources);
      if (d.slots && d.slots.length) chargerImages(neu, d);
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
    try { sessionStorage.setItem('quiz_depuis_chat', l.dataset.raw.replace(/\*+/g, '')); }
    catch (_) { showToast('Transfert impossible', 'error'); return; }
    location.href = '/apprendre';
  };
  liste().then(() => { $('inp').focus(); }).catch((e) => showToast(e.message, 'error'));
})();
