// Interfaccia del NAS — App store, Docker Hub, installazione, Le mie app
// Licenza GPL-3.0.
'use strict';

const ST = { data: null, cat: 'Tutte', src: 'all', q: '', limit: 60 };
const srcInfo = id => (ST.data?.sources || []).find(s => s.id === id) || { name: id, color: '#94a3b8' };

/* ==========================================================================
   Catalogo
   ========================================================================== */

function storeTabs(active) {
  const n = S.badges.apps;
  return `<div class="seg store-tabs-seg" style="margin-bottom:16px">
    <button class="${active === 'store' ? 'on' : ''}" data-go="store">${ic('bag')}Esplora</button>
    <button class="${active === 'apps' ? 'on' : ''}" data-go="apps">${ic('grid')}Le mie app${n ? ` <span class="badge acc">${n}</span>` : ''}</button>
  </div>`;
}
function wireTabs() { $$('[data-go]').forEach(b => b.onclick = () => go(b.dataset.go)); }

async function pageStore() {
  try { ST.data = await api('GET', '/store/apps'); } catch (e) { return pageError(e); }
  drawStore();
  if (ST.data.building || !ST.data.built) {
    every('storebuild', 4000, async () => {
      try {
        const d = await api('GET', '/store/apps');
        const was = ST.data.apps.length;
        ST.data = d;
        if (!d.building) { clearInterval(S.timers.storebuild); drawStore(); toast(`Catalogo aggiornato: ${nf(d.apps.length)} app`); }
        else if (d.apps.length !== was) drawStore();
      } catch (e) { /* riprova */ }
    });
  }
}

function filtered() {
  const q = ST.q.trim().toLowerCase();
  return ST.data.apps.filter(a =>
    (ST.cat === 'Tutte' || a.category === ST.cat) &&
    (ST.src === 'all' || a.sources.includes(ST.src)) &&
    (!q || a.title.toLowerCase().includes(q) || (a.tagline || '').toLowerCase().includes(q) || (a.developer || '').toLowerCase().includes(q)));
}

function storeHead(mode) {
  const d = ST.data;
  const active = d.sources.filter(s => s.enabled);
  const cats = ['Tutte', ...d.categories];
  const chips = d.sources.map(s => {
    if (!s.enabled) return `<button class="chip optsrc" data-enable="${esc(s.id)}" title="${s.optional ? 'Fonte facoltativa: tocca per attivarla' : 'Fonte spenta: tocca per riattivarla'}">${ic('plus')}${esc(s.name)}<span class="n">da attivare</span></button>`;
    const count = d.apps.filter(a => a.sources.includes(s.id)).length;
    return `<button class="chip ${mode === 'store' && ST.src === s.id ? 'on' : ''}" data-src="${esc(s.id)}"><span class="srcdot" style="background:${esc(s.color)}"></span>${esc(s.name)}<span class="n">${s.ok === false && !count ? '!' : nf(count)}</span></button>`;
  }).join('');
  return `
  <div class="storehead">
    <label class="search" style="flex:1;max-width:460px;min-width:260px">${ic('search')}<input id="sq" value="${esc(mode === 'hub' ? store.get('hubq', '') : ST.q)}" placeholder="${mode === 'hub' ? 'Cerca un\'immagine su Docker Hub…' : `Cerca tra ${nf(d.apps.length)} app…`}" autocomplete="off"></label>
    ${mode === 'store' ? `<div class="seg" id="cats">${cats.slice(0, 7).map(c => `<button class="${ST.cat === c ? 'on' : ''}" data-cat="${esc(c)}">${esc(c)}</button>`).join('')}${cats.length > 7 ? `<select class="input sm" id="catmore" style="width:auto;border:0;background:none;height:30px"><option value="">Altro…</option>${cats.slice(7).map(c => `<option ${ST.cat === c ? 'selected' : ''}>${esc(c)}</option>`).join('')}</select>` : ''}</div>` : ''}
    <span class="grow"></span>
    ${S.admin && mode === 'store' ? `<button class="btn" id="storeref" title="Scarica di nuovo i cataloghi di tutte le fonti attive" ${d.building ? 'disabled' : ''}>${ic('refresh')}${d.building ? 'Aggiornamento…' : 'Aggiorna tutto'}</button>` : ''}
    ${S.admin ? `<button class="btn" id="addsrc">${ic('link')}Aggiungi fonte</button>` : ''}
  </div>
  <div class="chips" style="margin-bottom:18px">
    <button class="chip ${mode === 'store' && ST.src === 'all' ? 'on' : ''}" data-src="all">Tutte le fonti<span class="n">${nf(d.apps.length)}</span></button>
    ${chips}
    <button class="chip ${mode === 'hub' ? 'on' : ''}" data-hub>${ic('container')}Docker Hub</button>
  </div>
  ${d.building ? `<div class="alert info" style="margin-bottom:16px">${ic('refresh', 'pulse')}<div>Sto scaricando i cataloghi dalle fonti${d.apps.length ? '' : ': la prima volta può richiedere un minuto'}…</div></div>` : ''}`;
}

function wireStoreHead(mode) {
  const sq = $('#sq');
  if (mode === 'store') {
    let t;
    sq.oninput = () => { clearTimeout(t); t = setTimeout(() => { ST.q = sq.value; ST.limit = 60; drawGrid(); }, 120); };
    sq.onkeydown = e => { if (e.key === 'Enter' && !filtered().length && sq.value.trim().length > 1) { store.set('hubq', sq.value.trim()); go('hub'); } };
    $$('[data-cat]').forEach(b => b.onclick = () => { ST.cat = b.dataset.cat; ST.limit = 60; drawStore(); });
    const cm = $('#catmore');
    if (cm) cm.onchange = () => { if (cm.value) { ST.cat = cm.value; ST.limit = 60; drawStore(); } };
  } else {
    sq.onkeydown = e => { if (e.key === 'Enter') { store.set('hubq', sq.value.trim()); hubSearch(sq.value.trim()); } };
  }
  $$('[data-src]').forEach(b => b.onclick = () => { ST.src = b.dataset.src; ST.limit = 60; if (mode === 'hub') go('store'); else drawStore(); });
  $$('[data-hub]').forEach(b => b.onclick = () => { if (ST.q) store.set('hubq', ST.q); go('hub'); });
  $$('[data-enable]').forEach(b => b.onclick = () => enableSource(b, b.dataset.enable));
  const add = $('#addsrc');
  if (add) add.onclick = addSourceDialog;
  const ref = $('#storeref');
  if (ref) ref.onclick = e => act(e.currentTarget, () => api('POST', '/store/refresh'), 'Aggiornamento di tutte le fonti avviato').then(r => r && pageStore());
}

async function enableSource(btn, id) {
  const s = srcInfo(id);
  const note = id === 'zima' || id === 'unraid'
    ? ` I cataloghi ${id === 'zima' ? 'ZimaOS' : 'Unraid'} sono di terzi e vengono convertiti in automatico: alcune app potrebbero richiedere ritocchi. ${esc(S.about.name)} non è affiliato a ${id === 'zima' ? 'IceWhale Technology' : 'Lime Technology'}.` : '';
  const r = await act(btn, () => api('POST', '/store/sources/' + id, { enabled: true }));
  if (r) { toast(`Fonte ${s.name} attivata: scarico il catalogo.${note}`, 'info', 8000); pageStore(); }
}

function drawStore() {
  const d = ST.data;
  const feat = !ST.q && ST.cat === 'Tutte' && ST.src === 'all' && d.featured.length;
  const grads = ['linear-gradient(135deg,#7c3aed,#2563eb 60%,#06b6d4)', 'linear-gradient(135deg,#0f766e,#22c55e)', 'linear-gradient(135deg,#9a3412,#f97316)'];
  const featured = feat ? `<div class="feature">${d.featured.map((id, k) => {
    const a = d.apps.find(x => x.id === id);
    return `<div class="fcard" data-app="${esc(a.id)}" style="background:${grads[k % 3]}">${appIcon(a, 'lg')}<button class="btn sm">${ic('eye')}Dettagli</button><b>${esc(a.title)}</b><span>${esc(a.tagline || a.category)}</span></div>`;
  }).join('')}</div>` : '';
  const active = d.sources.filter(s => s.enabled).length;
  $('#root').innerHTML = shell('store', 'App store', `${active} font${active === 1 ? 'e' : 'i'} attiv${active === 1 ? 'a' : 'e'} · ${nf(d.apps.length)} app${d.built ? ' · catalogo del ' + new Date(d.built).toLocaleDateString(LOCALE) : ''}`,
    storeTabs('store') + storeHead('store') + featured +
    `<div class="row" style="margin-bottom:10px"><b style="font-size:15px" id="gridtitle"></b><span class="grow"></span></div>
     <div class="storegrid" id="sgrid"></div><div class="more-row" id="smore"></div>
     <div class="attrib">${ic('info')}<div>I cataloghi vengono scaricati dai siti dei loro autori. App, nomi e icone appartengono ai rispettivi proprietari. ${esc(S.about.name)} non è affiliato a nessuno di loro; Docker Hub è indicato solo per compatibilità. <a href="#about">Informazioni e licenze</a></div></div>`, { noSearch: true });
  wireShell(); wireTabs(); wireStoreHead('store');
  $$('.fcard[data-app]').forEach(c => c.onclick = () => appDetail(c.dataset.app));
  drawGrid();
}

function drawGrid() {
  const list = filtered();
  const grid = $('#sgrid');
  if (!grid) return;
  $('#gridtitle').textContent = ST.q ? `${nf(list.length)} risultati per "${ST.q}"` : ST.cat !== 'Tutte' ? ST.cat : 'Tutte le app';
  if (!list.length) {
    grid.innerHTML = `<div class="card" style="grid-column:1/-1"><div class="empty">${ic('search')}<div>${ST.data.apps.length ? 'Nessuna app trovata nel catalogo.' : 'Il catalogo è vuoto: controlla la connessione a internet.'}</div>
      ${ST.q ? `<button class="btn primary" id="tohub">${ic('container')}Cerca "${esc(ST.q)}" su Docker Hub</button>` : ''}</div></div>`;
    const th = $('#tohub');
    if (th) th.onclick = () => { store.set('hubq', ST.q); go('hub'); };
    $('#smore').innerHTML = '';
    return;
  }
  grid.innerHTML = list.slice(0, ST.limit).map(a => `<div class="card scard" data-app="${esc(a.id)}">${appIcon(a)}<div><div class="t">${esc(a.title)}</div><div class="d">${esc(a.tagline || '')}</div>
    <div class="meta"><span class="badge">${esc(a.category)}</span><span class="srcs">${a.sources.map(id => `<span class="srcdot" style="background:${esc(srcInfo(id).color)}" title="${esc(srcInfo(id).name)}"></span>`).join('')}&nbsp;${a.sources.length === 1 ? esc(srcInfo(a.sources[0]).name) : a.sources.length + ' fonti'}</span>
    <button class="btn sm primary" data-install="${esc(a.id)}">Installa</button></div></div></div>`).join('');
  $$('.scard', grid).forEach(c => c.onclick = e => { if (e.target.closest('[data-install]')) return; appDetail(c.dataset.app); });
  $$('[data-install]', grid).forEach(b => b.onclick = e => { e.stopPropagation(); startInstall({ app: b.dataset.install }, b); });
  $('#smore').innerHTML = list.length > ST.limit ? `<button class="btn" id="morebtn">Mostra altre (${nf(list.length - ST.limit)})</button>` : '';
  const mb = $('#morebtn');
  if (mb) mb.onclick = () => { ST.limit += 90; drawGrid(); };
}

async function appDetail(id) {
  let a;
  try { a = await api('GET', '/store/app/' + id); } catch (e) { return toast(e.message, 'bad'); }
  const names = a.source_names || {};
  const shots = (a.screenshots || []).map(safeUrl).filter(Boolean);
  const m = modal(`${mhead(appIcon(a, 'lg'), esc(a.title), esc([a.developer, a.category].filter(Boolean).join(' · ')))}
    <div class="mb app-detail">
      ${a.tagline ? `<div style="font-size:15px;font-weight:550">${esc(a.tagline)}</div>` : ''}
      ${shots.length ? `<div class="shots">${shots.map(u => `<img src="${esc(u)}" alt="" loading="lazy" referrerpolicy="no-referrer">`).join('')}</div>` : ''}
      ${a.description ? `<div class="desc">${esc(a.description)}</div>` : ''}
      <div class="cols2">
        <div class="field"><label>Versione</label><div class="mono" style="font-size:13px">${esc(a.version)}</div></div>
        <div class="field"><label>Immagine</label><div class="mono" style="font-size:12.5px;word-break:break-all">${esc(a.image)}</div></div>
      </div>
      <div class="field"><label>Disponibile in</label><div class="srcpick">${a.sources.map((s, k) => `<button class="chip ${k === 0 ? 'on' : ''}" data-s="${esc(s.src)}"><span class="srcdot" style="background:${esc(srcInfo(s.src).color)}"></span>${esc(names[s.src] || s.src)}<span class="n">${esc(s.version)}</span></button>`).join('')}</div>
        ${a.sources.length > 1 ? '<span class="hint">La stessa app è in più fonti: scegli quale versione installare.</span>' : ''}</div>
      ${a.tips ? `<div class="alert info">${ic('info')}<div style="white-space:pre-wrap">${esc(a.tips)}</div></div>` : ''}
    </div>
    <div class="mf"><span class="grow">${a.services > 1 ? `${a.services} contenitori` : ''}</span><button class="btn" data-close>Chiudi</button><button class="btn primary" id="inst">${ic('download')}Installa</button></div>`, 'wide');
  let src = a.sources[0].src;
  $$('[data-s]', m).forEach(b => b.onclick = () => { src = b.dataset.s; $$('[data-s]', m).forEach(x => x.classList.toggle('on', x === b)); });
  $('#inst', m).onclick = e => startInstall({ app: a.id, source: src }, e.currentTarget);
}

/* ==========================================================================
   Docker Hub
   ========================================================================== */

async function pageHub() {
  if (!ST.data) { try { ST.data = await api('GET', '/store/apps'); } catch (e) { return pageError(e); } }
  const q = store.get('hubq', '');
  $('#root').innerHTML = shell('hub', 'App store', q ? `Ricerca su Docker Hub: "${esc(q)}"` : 'Cerca un\'immagine su Docker Hub', storeTabs('store') + storeHead('hub') + `
  <div class="grid two-col" style="grid-template-columns:1fr 330px;align-items:start">
    <div class="card"><h3>${ic('container')}Risultati da Docker Hub <span class="more" id="hubcount"></span></h3><div id="hubres"><div class="empty">${ic('search')}<div>Scrivi il nome di un'app o di un'immagine (es. <span class="mono">heimdall</span>, <span class="mono">linuxserver/plex</span>) e premi Invio.</div></div></div></div>
    <div class="grid">
      <div class="card" id="hubstore" hidden></div>
      <div class="card"><h3>${ic('info')}Come funziona</h3><div style="font-size:13px;color:var(--ink-2);display:grid;gap:8px">
        <div>Per un'immagine di Docker Hub il NAS legge dal registro porte, cartelle e variabili dichiarate e ti propone una configurazione pronta, che puoi cambiare prima di installare.</div>
        <div>Puoi anche scrivere un'immagine completa, anche di altri registri (es. <span class="mono">ghcr.io/gethomepage/homepage</span>) e premere Installa.</div>
        <div class="subtle">Docker Hub limita il numero di ricerche: i risultati restano in memoria per un'ora.</div></div></div>
    </div>
  </div>`, { noSearch: true });
  wireShell(); wireTabs(); wireStoreHead('hub');
  if (q) hubSearch(q);
}

async function hubSearch(q) {
  const box = $('#hubres');
  if (!box || !q) return;
  box.innerHTML = '<div class="empty"><span class="spin lg"></span><div>Cerco su Docker Hub…</div></div>';
  const direct = /[/:.]/.test(q);
  let r;
  try { r = await api('GET', '/hub/search?q=' + encodeURIComponent(q)); } catch (e) {
    box.innerHTML = `<div class="empty">${ic('alert')}<div>${esc(e.message)}</div>${direct ? `<button class="btn primary" data-img="${esc(q)}">${ic('download')}Installa ${esc(q)}</button>` : ''}</div>`;
    $$('[data-img]', box).forEach(b => b.onclick = () => startInstall({ image: b.dataset.img }, b));
    return;
  }
  const res = r.results;
  $('#hubcount').textContent = `${res.length} immagini`;
  const pulls = n => n >= 1e9 ? nf(n / 1e9, 1) + ' Mrd' : n >= 1e6 ? nf(n / 1e6, n >= 1e7 ? 0 : 1) + ' M' : n >= 1e3 ? nf(n / 1e3, 0) + ' mila' : nf(n);
  const rows = res.map(h => `<div class="hubrow">
      <div class="appicon sm" style="background:${h.official ? 'linear-gradient(140deg,#1d63ed,#0b3ea8)' : tileColor(h.image)}">${ic('container')}</div>
      <div style="min-width:0"><div class="t mono" style="font-size:13.5px">${esc(h.image)} ${h.official ? '<span class="badge off" style="font-family:var(--font)">Immagine ufficiale</span>' : ''}</div><div class="s">${esc(h.description || 'Nessuna descrizione')}</div></div>
      <div class="n">${ic('star')}${nf(h.stars)}</div><div class="n">${ic('dl')}${pulls(h.pulls)}</div>
      <button class="btn sm" data-img="${esc(h.image)}">Installa</button></div>`).join('');
  box.innerHTML = (direct && !res.some(h => h.image === q) ? `<div class="hubrow"><div class="appicon sm" style="background:${tileColor(q)}">${ic('container')}</div><div><div class="t mono">${esc(q)}</div><div class="s">Immagine scritta da te</div></div><div class="n"></div><div class="n"></div><button class="btn sm primary" data-img="${esc(q)}">Installa</button></div>` : '') +
    (rows || `<div class="empty">${ic('search')}<div>Nessuna immagine trovata.</div></div>`);
  $$('[data-img]', box).forEach(b => b.onclick = () => startInstall({ image: b.dataset.img }, b));
  const st = $('#hubstore');
  const matches = (ST.data.apps || []).filter(a => a.title.toLowerCase().includes(q.toLowerCase().split('/').pop().split(':')[0])).slice(0, 3);
  if (matches.length) {
    st.hidden = false;
    st.innerHTML = `<h3>${ic('bag')}Già negli store</h3>${matches.map(a => `<div class="row" style="margin-bottom:10px">${appIcon(a)}<div class="grow" style="min-width:0"><b>${esc(a.title)}</b><div class="muted" style="font-size:12.5px">${a.sources.map(s => esc(srcInfo(s).name)).join(' · ')}</div></div><button class="btn sm primary" data-app="${esc(a.id)}">Installa</button></div>`).join('')}
      <div class="alert info" style="margin-top:4px">${ic('info')}<div>Meglio la versione dello store: porte, cartelle e icona sono già impostate.</div></div>`;
    $$('[data-app]', st).forEach(b => b.onclick = () => startInstall({ app: b.dataset.app }, b));
  } else st.hidden = true;
}

/* ==========================================================================
   Installazione
   ========================================================================== */

async function startInstall(what, btn) {
  if (!S.admin) return toast('Serve un account amministratore', 'bad');
  const p = await act(btn, () => api('POST', '/apps/prepare', what));
  if (p) installDialog(p);
}

function installDialog(p) {
  const st = { mode: 'simple', p, services: JSON.parse(JSON.stringify(p.services)), compose: p.compose, title: p.title, web: { ...p.web },
    limits: { ...p.limits }, autostart: p.autostart ?? true, autoupdate: p.autoupdate ?? true, composeDirty: false };
  const main = () => st.services.find(s => s.main) || st.services[0];
  const sub = p.edit ? `${esc(main().image)} · modifica l'installazione: i dati in AppData restano` : p.source === 'hub' ? `${esc(p.image)}${p.size ? ' · ' + bytes(p.size) : ''} · da Docker Hub` : `${esc(main().image)} · da ${esc(srcInfo(p.source).name)}`;
  const m = modal(`${mhead(appIcon({ title: p.title, icon: p.icon }, 'lg'), `${p.edit ? 'Modifica' : 'Installa'} ${esc(p.title)}`, sub)}
    <div class="mb" style="padding-bottom:0"><div class="seg" id="modes"><button data-m="simple" class="on">Semplice</button><button data-m="advanced">Avanzata</button><button data-m="compose">Compose</button></div></div>
    <div class="mb" id="ibody"></div>
    <div class="mf"><span class="grow" id="ifoot"></span><button class="btn" data-close>Annulla</button><button class="btn primary" id="igo">${p.edit ? ic('check') + 'Salva e riavvia' : ic('download') + 'Installa'}</button></div>`, 'wide');

  const field = (label, html, hint) => `<div class="field"><label>${label}</label>${html}${hint ? `<span class="hint">${hint}</span>` : ''}</div>`;
  function foot() {
    const l = st.limits;
    $('#ifoot', m).innerHTML = `${ic('shield')} ${l.cpus || l.memory ? `Avvio con limiti: ${l.cpus ? nf(l.cpus, l.cpus % 1 ? 1 : 0) + ' CPU' : ''}${l.cpus && l.memory ? ', ' : ''}${l.memory ? esc(l.memory.replace(/g$/, ' GB').replace(/m$/, ' MB')) + ' di RAM' : ''} (modificabili)` : 'Senza limiti di CPU e RAM'}`;
  }

  function simple() {
    const vols = [];
    st.services.forEach(s => s.volumes.forEach((v, k) => { if (v.type === 'bind') vols.push([s, k, v]); }));
    const lsio = st.services.some(s => 'PUID' in s.env);
    return `
      ${p.tips ? `<div class="alert info">${ic('info')}<div style="white-space:pre-wrap">${esc(p.tips)}</div></div>` : ''}
      ${p.store_match && p.store_match.length ? `<div class="alert info">${ic('bag')}<div><b>${esc(p.store_match[0].title)}</b> c'è anche nello store, con porte, cartelle e icona già impostate. <a href="#" id="usestore" style="font-weight:650">Installa quella</a></div></div>` : ''}
      <div class="cols2">
        ${field('Nome dell\'app', `<input class="input" id="ititle" value="${esc(st.title)}">`, `Nome tecnico: <span class="mono">${esc(p.name)}</span>`)}
        ${field('Indirizzo', `<div class="row" style="gap:6px"><span class="mono muted" style="font-size:12.5px;white-space:nowrap">${esc(st.web.scheme || 'http')}://${esc(location.hostname)}:</span><input class="input mono" id="iport" value="${esc(st.web.port || '')}" style="width:100px" inputmode="numeric" placeholder="nessuna"></div>`,
          p.edit ? 'Se la cambi, controllo che sia libera' : st.web.port ? 'Porta libera trovata in automatico' : 'Quest\'app non ha un\'interfaccia web')}
      </div>
      ${vols.length ? `<div class="section-t">Cartelle</div><div class="grid" style="gap:8px">${vols.map(([s, k, v]) => `
        <div class="maprow"><input class="input" data-vol="${esc(s.name)}|${k}" value="${esc(v.source)}"><span class="arrow">→</span><input class="input mono" value="${esc(v.target)}" disabled><button class="iconbtn sm" data-pick="${esc(s.name)}|${k}" title="Scegli cartella">${ic('folder')}</button></div>`).join('')}</div>` : ''}
      <div class="cols2">
        ${field('Accesso ai file come', `<select class="input" disabled><option>${esc(p.user.name)} (uid ${p.user.uid})</option></select>`, lsio ? 'PUID/PGID impostati da soli' : 'Utente del NAS')}
        ${field('Fuso orario', `<select class="input" disabled><option>${esc(p.timezone)}</option></select>`, 'Lo stesso del NAS')}
      </div>
      <div class="row" style="gap:20px;flex-wrap:wrap">
        <label class="row" style="cursor:pointer"><button type="button" class="toggle ${st.autostart ? 'on' : ''}" data-tg="autostart"></button>Avvia con il NAS</label>
        <label class="row" style="cursor:pointer"><button type="button" class="toggle ${st.autoupdate ? 'on' : ''}" data-tg="autoupdate"></button>Aggiorna automaticamente</label>
      </div>`;
  }

  const rowP = (s, p, k) => `<tr><td><input class="input mono" data-pp="${esc(s.name)}|${k}|published" value="${esc(p.published)}" placeholder="—" inputmode="numeric"></td><td><input class="input mono" data-pp="${esc(s.name)}|${k}|target" value="${esc(p.target)}" inputmode="numeric"></td>
    <td><select class="input" data-pp="${esc(s.name)}|${k}|protocol"><option ${p.protocol === 'tcp' ? 'selected' : ''}>tcp</option><option ${p.protocol === 'udp' ? 'selected' : ''}>udp</option></select></td><td class="act"><button class="iconbtn sm" data-del="ports|${esc(s.name)}|${k}">${ic('minus')}</button></td></tr>`;
  const rowV = (s, v, k) => `<tr><td><div class="row" style="gap:6px;flex-wrap:nowrap"><input class="input" data-vv="${esc(s.name)}|${k}|source" value="${esc(v.source)}" placeholder="${v.type === 'anon' ? 'volume anonimo' : ''}" style="flex:1;min-width:0"><button type="button" class="iconbtn sm" data-vpick="${esc(s.name)}|${k}" title="Scegli cartella">${ic('folder')}</button></div></td><td><input class="input mono" data-vv="${esc(s.name)}|${k}|target" value="${esc(v.target)}"></td>
    <td><select class="input" data-vv="${esc(s.name)}|${k}|read_only"><option value="">lettura e scrittura</option><option value="1" ${v.read_only ? 'selected' : ''}>sola lettura</option></select></td><td class="act"><button class="iconbtn sm" data-del="volumes|${esc(s.name)}|${k}">${ic('minus')}</button></td></tr>`;
  const rowE = (s, key, val, k) => `<tr><td><input class="input mono" data-ek="${esc(s.name)}|${k}" value="${esc(key)}"></td><td colspan="2"><input class="input mono" data-ev="${esc(s.name)}|${k}" value="${esc(val)}"></td><td class="act"><button class="iconbtn sm" data-del="env|${esc(s.name)}|${k}">${ic('minus')}</button></td></tr>`;

  function advanced() {
    return `
      <div class="cols2">
        ${field('Nome dell\'app', `<input class="input" id="ititle" value="${esc(st.title)}">`)}
        ${field('Porta dell\'interfaccia web', `<input class="input mono" id="iport" value="${esc(st.web.port || '')}" inputmode="numeric" placeholder="nessuna">`)}
      </div>
      ${st.services.map(s => `<div class="svcbox"><b>${ic('container')}${esc(s.name)} <span class="muted mono" style="font-weight:500;font-size:12px">${esc(s.image)}</span>${s.main ? '<span class="badge acc">principale</span>' : ''}</b>
        ${s.network_mode === 'host' ? '<div class="subtle">Usa la rete del NAS direttamente (network_mode: host): niente porte da mappare.</div>' : `
        <table class="kvtable"><thead><tr><th>Porta del NAS</th><th>Porta dell'app</th><th>Protocollo</th><th></th></tr></thead><tbody>${s.ports.map((pp, k) => rowP(s, pp, k)).join('')}</tbody></table>
        <button class="btn sm ghost" data-add="ports|${esc(s.name)}">${ic('plus')}Aggiungi porta</button>`}
        <table class="kvtable"><thead><tr><th>Cartella del NAS</th><th>Cartella nell'app</th><th>Accesso</th><th></th></tr></thead><tbody>${s.volumes.map((v, k) => rowV(s, v, k)).join('')}</tbody></table>
        <button class="btn sm ghost" data-add="volumes|${esc(s.name)}">${ic('plus')}Aggiungi cartella</button>
        <table class="kvtable"><thead><tr><th>Variabile</th><th colspan="2">Valore</th><th></th></tr></thead><tbody>${Object.entries(s.env).map(([kk, vv], k) => rowE(s, kk, vv, k)).join('')}</tbody></table>
        <button class="btn sm ghost" data-add="env|${esc(s.name)}">${ic('plus')}Aggiungi variabile</button>
        ${s.privileged || s.devices.length ? `<div class="alert bad">${ic('alert')}<div>Questo contenitore chiede ${s.privileged ? 'accesso completo al sistema (privileged)' : ''}${s.privileged && s.devices.length ? ' e ' : ''}${s.devices.length ? 'l\'accesso a dispositivi: ' + esc(s.devices.join(', ')) : ''}. Installalo solo se ti fidi della fonte.</div></div>` : ''}
      </div>`).join('')}
      <div class="section-t">Limiti</div>
      <div class="cols2">
        ${field('CPU (core)', `<input class="input" id="lcpu" value="${esc(st.limits.cpus ?? '')}" placeholder="nessun limite" inputmode="decimal">`, 'Es. 2 oppure 0.5')}
        ${field('RAM', `<input class="input" id="lmem" value="${esc(st.limits.memory ?? '')}" placeholder="nessun limite">`, 'Es. 512m oppure 2g')}
      </div>
      <div class="row" style="gap:20px;flex-wrap:wrap">
        <label class="row" style="cursor:pointer"><button type="button" class="toggle ${st.autostart ? 'on' : ''}" data-tg="autostart"></button>Avvia con il NAS</label>
        <label class="row" style="cursor:pointer"><button type="button" class="toggle ${st.autoupdate ? 'on' : ''}" data-tg="autoupdate"></button>Aggiorna automaticamente</label>
      </div>`;
  }

  function compose() {
    return `<div class="subtle">Il file docker-compose dell'app. Le variabili <span class="mono">$PUID $PGID $TZ $AppID</span> vengono impostate dal NAS.</div>
      <textarea class="input code" id="icompose" spellcheck="false">${esc(st.compose)}</textarea>
      <div class="cols2">
        ${field('Nome dell\'app', `<input class="input" id="ititle" value="${esc(st.title)}">`)}
        ${field('Porta dell\'interfaccia web', `<input class="input mono" id="iport" value="${esc(st.web.port || '')}" inputmode="numeric" placeholder="nessuna">`)}
      </div>`;
  }

  // Legge i campi della modalità corrente e li rimette nello stato
  function collect() {
    const t = $('#ititle', m); if (t) st.title = t.value.trim() || p.title;
    const pt = $('#iport', m); if (pt) st.web.port = pt.value.trim();
    $$('[data-vol]', m).forEach(i => { const [s, k] = i.dataset.vol.split('|'); st.services.find(x => x.name === s).volumes[+k].source = i.value.trim(); });
    $$('[data-pp]', m).forEach(i => { const [s, k, f] = i.dataset.pp.split('|'); st.services.find(x => x.name === s).ports[+k][f] = i.value.trim(); });
    $$('[data-vv]', m).forEach(i => { const [s, k, f] = i.dataset.vv.split('|'); st.services.find(x => x.name === s).volumes[+k][f] = f === 'read_only' ? !!i.value : i.value.trim(); });
    st.services.forEach(s => {
      const keys = $$(`[data-ek^="${CSS.escape(s.name)}|"]`, m);
      if (!keys.length && st.mode !== 'advanced') return;
      if (st.mode === 'advanced') {
        const env = {};
        keys.forEach(i => { const k = i.dataset.ek.split('|')[1]; const v = $(`[data-ev="${CSS.escape(s.name)}|${k}"]`, m); if (i.value.trim()) env[i.value.trim()] = v ? v.value : ''; });
        s.env = env;
      }
    });
    const lc = $('#lcpu', m), lm = $('#lmem', m);
    if (lc) st.limits.cpus = lc.value.trim() ? lc.value.trim().replace(',', '.') : null;
    if (lm) st.limits.memory = lm.value.trim() || null;
    const ta = $('#icompose', m);
    if (ta) { if (ta.value !== st.compose) st.composeDirty = true; st.compose = ta.value; }
  }

  function draw() {
    $('#ibody', m).innerHTML = st.mode === 'simple' ? simple() : st.mode === 'advanced' ? advanced() : compose();
    $$('[data-m]', m).forEach(b => b.classList.toggle('on', b.dataset.m === st.mode));
    $$('[data-tg]', m).forEach(b => b.onclick = () => { st[b.dataset.tg] = !st[b.dataset.tg]; b.classList.toggle('on', st[b.dataset.tg]); });
    $$('[data-pick]', m).forEach(b => b.onclick = () => {
      const [s, k] = b.dataset.pick.split('|');
      const inp = $(`[data-vol="${CSS.escape(b.dataset.pick)}"]`, m);
      pickFolder(inp.value || '/DATA', path => { inp.value = path; st.services.find(x => x.name === s).volumes[+k].source = path; }, true);
    });
    // Tabella "Avanzate": scelta della cartella del NAS navigando con il mouse
    $$('[data-vpick]', m).forEach(b => b.onclick = () => {
      const [s, k] = b.dataset.vpick.split('|');
      const inp = $(`[data-vv="${CSS.escape(b.dataset.vpick + '|source')}"]`, m);
      const start = (inp.value || '').startsWith('/') ? inp.value.replace(/\/+$/, '') : '/DATA';
      pickFolder(start, path => { inp.value = path; st.services.find(x => x.name === s).volumes[+k].source = path; }, true);
    });
    $$('[data-add]', m).forEach(b => b.onclick = () => {
      collect();
      const [what, s] = b.dataset.add.split('|');
      const svc = st.services.find(x => x.name === s);
      if (what === 'ports') svc.ports.push({ published: '', target: '', protocol: 'tcp', host_ip: '' });
      if (what === 'volumes') svc.volumes.push({ type: 'bind', source: `/DATA/AppData/${p.name}/`, target: '/', read_only: false, extra: {} });
      if (what === 'env') svc.env[''] = '';
      draw();
    });
    $$('[data-del]', m).forEach(b => b.onclick = () => {
      collect();
      const [what, s, k] = b.dataset.del.split('|');
      const svc = st.services.find(x => x.name === s);
      if (what === 'env') { const key = Object.keys(svc.env)[+k]; delete svc.env[key]; } else svc[what].splice(+k, 1);
      draw();
    });
    const us = $('#usestore', m);
    if (us) us.onclick = e => { e.preventDefault(); closeModal(); startInstall({ app: p.store_match[0].id }); };
    foot();
  }

  $$('[data-m]', m).forEach(b => b.onclick = async () => {
    collect();
    const to = b.dataset.m;
    if (to === st.mode) return;
    if (to === 'compose') {
      // Il compose rispecchia quello che hai scritto nei campi
      const r = await act(b, () => api('POST', '/apps/render', { name: p.name, compose: st.compose, services: st.services, web: st.web }));
      if (!r) return;
      st.compose = r.compose;
    } else if (st.mode === 'compose' && st.composeDirty) {
      if (!await ask('Torna ai campi', 'Le modifiche fatte a mano nel compose verranno perse se torni ai campi. Continuare?', 'Continua')) return;
      installDialog(p);
      return;
    }
    st.mode = to;
    draw();
  });
  $('#igo', m).onclick = async () => {
    collect();
    const body = { mode: st.mode, name: p.name, title: st.title, icon: p.icon, source: p.source, catalog_id: p.catalog_id,
      compose: st.compose, services: st.mode === 'compose' ? undefined : st.services, web: st.web,
      limits: st.limits, autostart: st.autostart, autoupdate: st.autoupdate };
    const btn = $('#igo', m);
    if (p.edit) {
      const r = await act(btn, () => api('POST', `/apps/${p.name}/reconfigure`, body));
      if (r) runJobDialog(r.job, st.title, { icon: p.icon, heading: 'Modifica di ' + st.title, okText: `Modifiche applicate: <b>${esc(st.title)}</b> è ripartita.`, done: () => installedDone(r.name, st), after: () => { if (S.page === 'apps') pageApps(); } });
      return;
    }
    const r = await act(btn, () => api('POST', '/apps/install', body));
    if (r) runJobDialog(r.job, st.title, { icon: p.icon, done: () => installedDone(r.name, st) });
  };
  draw();
}

function installedDone(name, st) {
  const port = st.web.port;
  return port ? `<a class="btn primary" href="${esc(`${st.web.scheme || 'http'}://${location.hostname}:${port}${st.web.index || '/'}`)}" target="_blank" rel="noopener">${ic('external')}Apri ${esc(st.title)}</a>` : '';
}

// Finestra di avanzamento di un'operazione lunga
function runJobDialog(id, title, opt = {}) {
  const m = modal(`${mhead(appIcon({ title, icon: opt.icon }, 'lg'), esc(opt.heading || 'Installazione di ' + title), '<span id="jstep">Avvio…</span>')}
    <div class="mb"><div class="progress-big"><div class="bar"><i id="jbar" style="width:3%"></i></div><div class="row subtle"><span id="jpct">0%</span><span class="grow"></span><a href="#" id="jlogt">Mostra dettagli</a></div></div>
      <pre class="logbox" id="jlog" hidden></pre><div id="jres"></div></div>
    <div class="mf"><span class="grow subtle">Puoi chiudere questa finestra: l'operazione continua sul NAS.</span><button class="btn" data-close>Chiudi</button></div>`);
  $('#jlogt', m).onclick = e => { e.preventDefault(); const l = $('#jlog', m); l.hidden = !l.hidden; e.target.textContent = l.hidden ? 'Mostra dettagli' : 'Nascondi dettagli'; };
  return followJob(id, j => {
    if (!m.isConnected) return;
    $('#jstep', m).textContent = j.step || '';
    $('#jbar', m).style.width = Math.max(3, j.progress) + '%';
    $('#jpct', m).textContent = j.progress + '%';
    const l = $('#jlog', m);
    const atEnd = l.scrollTop + l.clientHeight >= l.scrollHeight - 10;
    l.textContent = j.log || '';
    if (atEnd) l.scrollTop = l.scrollHeight;
    if (j.state === 'done') {
      $('#jstep', m).textContent = 'Fatto';
      const warn = j.result && j.result.warning;
      $('#jres', m).innerHTML = `<div class="alert ${warn ? 'bad' : 'info'}">${ic(warn ? 'alert' : 'check')}<div>${warn ? `L'app è installata ma non risponde ancora: ${esc(warn)}. Alcune app impiegano qualche minuto al primo avvio.` : opt.okText || `<b>${esc(title)}</b> è pronta.`}</div></div>`;
      if (opt.after) opt.after(j);
      const extra = opt.done ? opt.done(j) : '';
      if (extra) $('.mf', m).insertAdjacentHTML('beforeend', extra);
      S.badges.apps = S.badges.apps || 0;
    } else if (j.state === 'failed') {
      $('#jstep', m).textContent = 'Non riuscito';
      $('#jbar', m).style.background = 'var(--bad)';
      $('#jres', m).innerHTML = `<div class="alert bad">${ic('alert')}<div>${esc(j.error)}</div></div>`;
      $('#jlog', m).hidden = false;
      if (opt.after) opt.after(j);
    }
  }).catch(e => toast(e.message, 'bad'));
}

/* ==========================================================================
   Scelta di una cartella del NAS
   ========================================================================== */

function pickFolder(start, cb, allowNew) {
  const old = $('#scrim');
  if (old) old.style.display = 'none';
  const host = document.createElement('div');
  host.className = 'scrim';
  host.style.zIndex = 30;
  host.innerHTML = `<div class="modal sm">${mhead(`<div class="dicon">${ic('folder')}</div>`, 'Scegli una cartella', '<span class="mono" id="pkpath"></span>')}
    <div class="mb"><div class="picker" id="pk"></div></div>
    <div class="mf">${allowNew ? `<button class="btn" id="pknew">${ic('newfolder')}Nuova</button>` : ''}<span class="grow"></span><button class="btn" id="pkno">Annulla</button><button class="btn primary" id="pkok">Scegli</button></div></div>`;
  document.body.appendChild(host);
  const close = () => { host.remove(); if (old) old.style.display = ''; };
  $('[data-close]', host).onclick = close;
  $('#pkno', host).onclick = close;
  let cur = '/';
  async function load(path) {
    let r;
    // una cartella che non esiste ancora (es. la cartella dell'app prima dell'installazione): si parte dalla prima che c'è
    try { r = await api('GET', '/fs/dirs?path=' + encodeURIComponent(path)); } catch (e) { if (path !== '/') return load(path.replace(/\/+$/, '').replace(/\/[^/]*$/, '') || '/'); return toast(e.message, 'bad'); }
    cur = r.path;
    $('#pkpath', host).textContent = cur === '/' ? 'Cartelle del NAS' : cur;
    $('#pk', host).innerHTML = (r.parent !== null && cur !== '/' ? `<div class="row" data-p="${esc(r.parent || '/')}">${ic('up')}<span>Su</span></div>` : '') +
      r.dirs.map(d => `<div class="row" data-p="${esc(d)}">${ic('folder')}<span>${esc(d.split('/').pop() || d)}</span></div>`).join('') || '<div class="empty">Nessuna sottocartella</div>';
    $$('[data-p]', host).forEach(x => x.onclick = () => load(x.dataset.p));
  }
  $('#pkok', host).onclick = () => { if (cur === '/') return toast('Scegli una cartella dentro /DATA, /media o /mnt', 'bad'); close(); cb(cur); };
  const nb = $('#pknew', host);
  if (nb) nb.onclick = () => {
    if (cur === '/') return toast('Entra prima in una cartella', 'bad');
    if ($('#pkname', host)) return $('#pkname', host).focus();
    $('#pk', host).insertAdjacentHTML('beforebegin', `<div class="row" style="margin-bottom:8px"><input class="input sm" id="pkname" placeholder="Nome della nuova cartella"><button class="btn sm primary" id="pkmk">Crea</button></div>`);
    const inp = $('#pkname', host);
    inp.focus();
    const mk = async () => {
      const name = inp.value.trim();
      if (!name) return;
      const r = await act($('#pkmk', host), () => api('POST', '/files/mkdir', { path: cur, name }));
      if (r) { inp.parentNode.remove(); load(r.path); }
    };
    $('#pkmk', host).onclick = mk;
    inp.onkeydown = e => { if (e.key === 'Enter') mk(); };
  };
  load(start);
}

/* ==========================================================================
   Fonti dello store
   ========================================================================== */

function addSourceDialog() {
  const m = modal(`${mhead(`<div class="dicon">${ic('link')}</div>`, 'Aggiungi una fonte di app', S.about.stores_extra ? 'Store in formato CasaOS (.zip) o ZimaOS v2' : 'Zip di app in formato compose (come Big Bear)')}
    <div class="mb">
      <div class="field"><label>Indirizzo</label><input class="input mono" id="su" placeholder="https://…/store.zip"></div>
      <div class="field"><label>Nome (facoltativo)</label><input class="input" id="sn" placeholder="Il mio store"></div>
      <div class="alert info">${ic('info')}<div>Le app delle fonti aggiunte da te non sono controllate: installa solo da store di cui ti fidi.</div></div>
    </div>
    <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="ok">${ic('plus')}Aggiungi</button></div>`, 'sm');
  $('#ok', m).onclick = e => act(e.currentTarget, () => api('POST', '/store/sources', { url: $('#su', m).value, name: $('#sn', m).value }), 'Fonte aggiunta: scarico il catalogo').then(r => { if (r) { closeModal(); if (S.page === 'store') pageStore(); else render(); } });
}

/* ==========================================================================
   Le mie app
   ========================================================================== */

let APPS = null;

async function pageApps() {
  try { APPS = await api('GET', '/apps'); } catch (e) { return pageError(e); }
  S.badges.apps = APPS.apps.filter(a => a.update).length;
  drawApps();
  every('apps', 5000, async () => {
    if ($('#scrim')) return;
    try { const d = await api('GET', '/apps'); const busy = d.jobs.length || APPS.jobs.length; APPS = d; if (busy || true) drawAppsList(); } catch (e) { /* riprova */ }
  });
}

function appRow(a) {
  const job = (APPS.jobs || []).find(j => j.target === a.name && j.state === 'running');
  let right;
  if (job) {
    right = `<div style="width:220px"><div class="row" style="font-size:12.5px;margin-bottom:5px"><span>${esc(job.step || job.title)}</span><span class="grow"></span><span class="muted">${job.progress}%</span></div><div class="bar"><i style="width:${Math.max(3, job.progress)}%"></i></div></div><button class="btn sm" disabled>Attendi</button>`;
  } else if (a.update) {
    right = `<div style="text-align:right"><span class="badge acc">${ic('dl')}${esc(a.update.kind === 'digest' ? 'nuova build' : a.update.new || 'nuova versione')}</span>${a.update.kind === 'digest' ? `<div class="s" style="margin-top:3px">Stessa versione (${esc(a.update.new || a.version)}), contenuto aggiornato</div>` : ''}</div><button class="btn sm primary" data-upd="${esc(a.name)}">Aggiorna</button>`;
  } else if (a.last_update && a.last_update.ok === false && Date.now() / 1000 - a.last_update.t < 7 * 86400) {
    right = `<div style="text-align:right"><span class="badge warn">${a.last_update.rolled_back ? `Tornata alla ${esc(a.last_update.from || 'versione precedente')}` : 'Aggiornamento non riuscito'}</span><div class="s" style="margin-top:3px">${esc(a.last_update.reason || '')}</div></div>`;
  } else if (a.managed) {
    right = `<span class="badge ok hide-m">${ic('check')}Aggiornata</span>`;
  } else right = '<span class="badge">esterna</span>';
  const url = appUrl(a);
  return `<div class="item" data-name="${esc(a.name)}">${appIcon(a, 'sm')}<div class="grow"><div class="t">${esc(a.title)} ${stateBadge(a.state)}${a.health === 'unhealthy' ? ' <span class="badge bad">non in salute</span>' : ''}</div><div class="s mono">${esc(a.version)}${a.managed ? '' : ' · ' + esc(a.image)}</div></div>
    <div class="appactions">${right}${url && a.state === 'attiva' ? `<a class="btn sm ghost hide-m" href="${esc(url)}" target="_blank" rel="noopener" title="Apri">${ic('external')}</a>` : ''}<button class="btn sm ghost" data-menu="${esc(a.name)}" title="Altro">${ic('more')}</button></div></div>`;
}

function drawApps() {
  const s = APPS.settings;
  const n = APPS.apps.filter(a => a.update).length;
  $('#root').innerHTML = shell('apps', 'Le mie app', '', storeTabs('apps') + `
  <div class="grid two-col" style="grid-template-columns:1fr 320px;align-items:start">
    <div class="card">
      <div class="row" style="margin-bottom:6px;flex-wrap:wrap"><h3 style="margin:0">${ic('grid')}App installate</h3><span id="updbadge"></span><span class="grow"></span>
        <button class="btn sm" id="chk">${ic('refresh')}Controlla</button><button class="btn sm primary" id="updall" ${n ? '' : 'disabled'}>${ic('dl')}Aggiorna tutte${n ? ` (${n})` : ''}</button></div>
      <div class="subtle" id="checked"></div>
      <div class="list" id="applist"></div>
    </div>
    <div class="grid">
      <div class="card"><h3>${ic('refresh')}Aggiornamento automatico</h3>
        <div class="list">
          <div class="item"><div class="grow"><div class="t">Aggiorna da solo</div><div class="s">Solo versioni di correzione (es. 1.2.3 → 1.2.4)</div></div><button class="toggle ${s.autoupdate ? 'on' : ''}" id="sau"></button></div>
          <div class="item"><div class="grow"><div class="t">Quando</div><div class="s">Di notte, quando nessuno usa il NAS</div></div><select class="input sm" id="stime" style="width:96px">${['01:30', '02:30', '03:30', '04:30', '05:30'].concat(s.time).filter((v, i, a) => a.indexOf(v) === i).sort().map(t => `<option ${t === s.time ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
          <div class="item"><div class="grow"><div class="t">Se l'app non riparte</div><div class="s">Torna alla versione precedente</div></div><button class="toggle ${s.rollback ? 'on' : ''}" id="srb"></button></div>
        </div></div>
      <div class="card"><h3>${ic('shield')}Prima di ogni aggiornamento</h3>
        <div style="font-size:13px;color:var(--ink-2);display:grid;gap:8px">
          <div class="row">${ic('check')}Copia della configurazione dell'app</div>
          <div class="row">${ic('check')}Versione precedente tenuta da parte</div>
          <div class="row">${ic('check')}Controllo che l'app risponda dopo l'avvio</div>
        </div></div>
    </div>
  </div>`, { noSearch: true });
  wireShell(); wireTabs();
  drawAppsList();
  const save = (b, body) => act(b, () => api('POST', '/apps/settings', body), 'Impostazione salvata').then(r => { if (r) APPS.settings = r; });
  $('#sau').onclick = e => { const b = e.currentTarget; b.classList.toggle('on'); save(null, { autoupdate: b.classList.contains('on') }); };
  $('#srb').onclick = e => { const b = e.currentTarget; b.classList.toggle('on'); save(null, { rollback: b.classList.contains('on') }); };
  $('#stime').onchange = e => save(null, { time: e.target.value });
  $('#chk').onclick = async e => {
    const r = await act(e.currentTarget, () => api('POST', '/apps/check'));
    if (!r) return;
    const b = $('#chk');
    b.disabled = true; b.innerHTML = '<span class="spin"></span>Controllo…';
    const j = await followJob(r.job).catch(() => null);
    if (j && j.state === 'failed') toast(j.error, 'bad'); else toast('Controllo completato');
    pageApps();
  };
  $('#updall').onclick = async e => {
    const r = await act(e.currentTarget, () => api('POST', '/apps/update-all'));
    if (r) runJobDialog(r.job, `${r.apps.length} app`, { heading: `Aggiornamento di ${r.apps.length} app` }).then(() => pageApps());
  };
}

function drawAppsList() {
  const list = $('#applist');
  if (!list) return;
  const managed = APPS.apps.filter(a => a.managed), ext = APPS.apps.filter(a => !a.managed);
  const n = managed.filter(a => a.update).length;
  S.badges.apps = n;
  $('#updbadge').innerHTML = n ? `<span class="badge acc">${n} aggiornament${n === 1 ? 'o' : 'i'}</span>` : '';
  const ua = $('#updall');
  if (ua && !ua.querySelector('.spin')) { ua.disabled = !n; ua.innerHTML = `${ic('dl')}Aggiorna tutte${n ? ` (${n})` : ''}`; }
  $('#checked').textContent = APPS.checked ? `Ultimo controllo: ${ago(APPS.checked)}` : 'Versioni non ancora controllate';
  list.innerHTML = (managed.map(appRow).join('') || `<div class="empty">${ic('bag')}<div>Nessuna app installata.</div><a class="btn primary" href="#store">${ic('bag')}Vai all'App store</a></div>`) +
    (ext.length ? `<div class="section-t" style="margin:18px 0 0">Altri contenitori</div><div class="subtle" style="margin-top:8px">Avviati fuori dal NAS: puoi accenderli, spegnerli e leggerne i log.</div>` + ext.map(appRow).join('') : '') +
    (APPS.docker ? '' : `<div class="alert bad" style="margin-top:12px">${ic('alert')}<div>Il motore delle app (Docker) non risponde.</div></div>`);
  $$('[data-upd]', list).forEach(b => b.onclick = async () => {
    const a = APPS.apps.find(x => x.name === b.dataset.upd);
    const r = await act(b, () => api('POST', `/apps/${a.name}/update`));
    if (r) runJobDialog(r.job, a.title, { icon: a.icon, heading: `Aggiornamento di ${a.title}` }).then(() => pageApps());
  });
  $$('[data-menu]', list).forEach(b => b.onclick = () => appMenu(b, APPS.apps.find(x => x.name === b.dataset.menu)));
}

function appMenu(btn, a) {
  const url = appUrl(a);
  const doAct = what => act(null, () => api('POST', `/apps/${a.name}/${what}`), { start: 'App avviata', stop: 'App fermata', restart: 'App riavviata' }[what]).then(() => pageApps());
  const items = [];
  if (url) items.push({ label: 'Apri', icon: 'external', fn: () => open(url, '_blank', 'noopener') });
  if (a.state !== 'attiva') items.push({ label: 'Avvia', icon: 'play', fn: () => doAct('start') });
  if (a.state !== 'ferma') items.push({ label: 'Ferma', icon: 'stop', fn: () => doAct('stop') });
  items.push({ label: 'Riavvia', icon: 'restart', fn: () => doAct('restart') });
  items.push({ label: 'Log', icon: 'term', fn: () => appLogs(a) });
  if (a.managed) {
    items.push('-');
    items.push({ label: 'Modifica l\'installazione', icon: 'pencil', fn: () => editInstall(a) });
    items.push({ label: 'Impostazioni e limiti', icon: 'sliders', fn: () => appSettings(a) });
    items.push({ label: 'Mostra il compose', icon: 'code', fn: () => appCompose(a) });
    items.push('-');
    items.push({ label: 'Disinstalla', icon: 'trash', danger: true, fn: () => appRemove(a) });
  }
  popmenu(btn, items);
}

async function editInstall(a) {
  if (a.busy) return toast('C\'è già un\'operazione in corso su quest\'app', 'bad');
  const p = await act(null, () => api('GET', `/apps/${a.name}/edit`));
  if (p) installDialog(p);
}

async function appLogs(a) {
  const m = modal(`${mhead(appIcon(a, 'sm'), `Log di ${esc(a.title)}`, 'Ultime 300 righe · si aggiorna da solo')}
    <div class="mb"><pre class="logbox tall" id="lg">Carico…</pre></div>
    <div class="mf"><label class="row subtle" style="cursor:pointer;margin-right:auto"><button class="toggle on" id="lgf"></button>Segui</label><button class="btn" data-close>Chiudi</button></div>`, 'full');
  const follow = $('#lgf', m);
  follow.onclick = () => follow.classList.toggle('on');
  async function load() {
    try {
      const r = await api('GET', `/apps/${a.name}/logs?tail=300`);
      const l = $('#lg', m);
      if (!l) return;
      l.textContent = r.log || '(nessuna riga)';
      if (follow.classList.contains('on')) l.scrollTop = l.scrollHeight;
    } catch (e) { $('#lg', m).textContent = e.message; }
  }
  await load();
  const t = setInterval(() => { if (!m.isConnected) clearInterval(t); else if (follow.classList.contains('on')) load(); }, 3000);
}

function appSettings(a) {
  const l = a.limits || {};
  const m = modal(`${mhead(appIcon(a, 'sm'), `Impostazioni di ${esc(a.title)}`, esc(a.name))}
    <div class="mb">
      <div class="field"><label>Nome</label><input class="input" id="an" value="${esc(a.title)}"></div>
      <div class="section-t">Limiti (per ogni contenitore dell'app)</div>
      <div class="cols2">
        <div class="field"><label>CPU (core)</label><input class="input" id="ac" value="${esc(l.cpus ?? '')}" placeholder="nessun limite" inputmode="decimal"><span class="hint">Es. 2 oppure 0.5</span></div>
        <div class="field"><label>RAM</label><input class="input" id="am" value="${esc(l.memory ?? '')}" placeholder="nessun limite"><span class="hint">Es. 512m oppure 2g</span></div>
      </div>
      <label class="row" style="cursor:pointer"><button class="toggle ${a.autoupdate ? 'on' : ''}" id="aau"></button>Aggiorna automaticamente (solo correzioni, di notte)</label>
      <div class="subtle">Cambiare i limiti riavvia l'app.</div>
    </div>
    <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="ok">Salva</button></div>`, 'sm');
  $('#aau', m).onclick = e => e.currentTarget.classList.toggle('on');
  $('#ok', m).onclick = e => {
    const nl = { cpus: $('#ac', m).value.trim().replace(',', '.') || null, memory: $('#am', m).value.trim() || null };
    const body = { title: $('#an', m).value, autoupdate: $('#aau', m).classList.contains('on') };
    if ((nl.cpus || '') != (l.cpus ?? '') || (nl.memory || '') != (l.memory ?? '')) body.limits = nl;
    act(e.currentTarget, () => api('POST', `/apps/${a.name}`, body), 'Impostazioni salvate').then(r => { if (r) { closeModal(); pageApps(); } });
  };
}

async function appCompose(a) {
  let r;
  try { r = await api('GET', `/apps/${a.name}/compose`); } catch (e) { return toast(e.message, 'bad'); }
  modal(`${mhead(appIcon(a, 'sm'), `Compose di ${esc(a.title)}`, `/var/lib/nido/apps/${esc(a.name)}/docker-compose.yml`)}
    <div class="mb"><pre class="logbox tall">${esc(r.compose)}</pre></div>
    <div class="mf"><button class="btn" data-close>Chiudi</button></div>`, 'wide');
}

function appRemove(a) {
  const m = modal(`${mhead(appIcon(a, 'sm'), `Disinstalla ${esc(a.title)}`)}
    <div class="mb"><div class="dialog-text">L'app viene fermata e tolta dal NAS.</div>
      <label class="row" style="cursor:pointer"><button class="toggle" id="rd"></button>Cancella anche i dati dell'app (<span class="mono">/DATA/AppData/${esc(a.name)}</span>)</label>
      <div class="alert bad" id="rdw" hidden>${ic('alert')}<div>I dati cancellati non si possono recuperare.</div></div></div>
    <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn danger solid" id="ok">Disinstalla</button></div>`, 'sm');
  $('#rd', m).onclick = e => { e.currentTarget.classList.toggle('on'); $('#rdw', m).hidden = !e.currentTarget.classList.contains('on'); };
  $('#ok', m).onclick = async e => {
    const data = $('#rd', m).classList.contains('on');
    const r = await act(e.currentTarget, () => api('DELETE', `/apps/${a.name}${data ? '?data=1' : ''}`));
    if (!r) return;
    closeModal();
    toast(`Disinstallo ${a.title}…`, 'info');
    const j = await followJob(r.job).catch(() => null);
    if (j && j.state === 'done') toast(`${a.title} disinstallata`); else if (j) toast(j.error, 'bad');
    pageApps();
  };
}

ROUTES.store = pageStore;
ROUTES.hub = pageHub;
ROUTES.apps = pageApps;
