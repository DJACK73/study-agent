(() => {
  const API = '/api/chat';
  const $ = (id) => document.getElementById(id);
  let cid = null, busy = false;

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

  function bulle(role, texte, pdf, err) {
    const m = $('msgs');
    const e = m.querySelector('.chat-empty'); if (e) e.remove();
    const d = document.createElement('div');
    d.className = 'msg ' + role + (err ? ' err' : '');
    if (role === 'user' || err) d.textContent = texte; else d.innerHTML = renderMarkdown(texte);
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
      const t = document.createElement('span'); t.className = 'conv-titre'; t.textContent = c.titre; t.title = c.titre;
      const dt = document.createElement('span'); dt.className = 'conv-date'; dt.textContent = heure(c.updated_at);
      const x = document.createElement('button'); x.className = 'conv-del'; x.textContent = '✕'; x.title = 'Supprimer';
      x.onclick = (ev) => { ev.stopPropagation(); supprimer(c.id, c.titre); };
      row.onclick = () => ouvrir(c.id);
      row.append(t, dt, x); box.appendChild(row);
    });
  }

  function actif(on) { $('inp').disabled = !on; $('btn-send').disabled = !on; if (on) $('inp').focus(); }

  async function ouvrir(id) {
    try {
      const d = await j(API + '/conversations/' + id);
      cid = id; $('msgs').innerHTML = '';
      (d.messages || []).forEach((m) => bulle(m.role, m.contenu, m.pdf_path));
      if (!(d.messages || []).length) $('msgs').innerHTML = '<div class="chat-empty">Discussion vide.</div>';
      actif(true); await liste();
    } catch (e) { showToast(e.message, 'error'); }
  }

  async function nouvelle() {
    try {
      const d = await j(API + '/conversations', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{}'});
      await ouvrir(d.id);
    } catch (e) { showToast(e.message, 'error'); }
  }

  async function supprimer(id, titre) {
    if (!confirm('Supprimer « ' + titre + ' » ? Les fichiers liés seront effacés.')) return;
    try {
      await j(API + '/conversations/' + id, {method:'DELETE'});
      if (id === cid) { cid = null; actif(false); $('msgs').innerHTML = '<div class="chat-empty">Choisis une discussion ou crée-en une.</div>'; }
      await liste();
    } catch (e) { showToast(e.message, 'error'); }
  }

  async function envoyer() {
    const txt = $('inp').value.trim();
    if (!txt || !cid || busy) return;
    busy = true; $('btn-send').disabled = true; $('inp').value = '';
    bulle('user', txt);
    const att = bulle('ai', '…');
    try {
      const d = await j(API + '/conversations/' + cid + '/messages', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({message: txt, web: $('chk-web').checked})
      });
      att.remove(); bulle('ai', d.reponse, d.pdf_path);
      if (d.web_statut && d.web_statut !== 'ok') showToast('Web : ' + d.web_statut, 'info');
      await liste();
    } catch (e) { att.remove(); bulle('ai', 'Erreur : ' + e.message, null, true); }
    busy = false; $('btn-send').disabled = false; $('inp').focus();
  }

  $('btn-new').onclick = nouvelle;
  $('btn-send').onclick = envoyer;
  $('inp').addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); envoyer(); } });
  liste().catch((e) => showToast(e.message, 'error'));
})();
