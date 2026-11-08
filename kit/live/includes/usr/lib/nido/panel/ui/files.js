// Interfaccia del NAS — File manager e cartelle di rete
// Licenza GPL-3.0.
'use strict';

const FM = {
  path: null, data: null, list: [], places: null, sel: new Set(), last: null, view: 'grid', search: null,
  uploads: [], trash: false, clip: null, sort: { by: 'name', dir: 1 }, ops: [], opsSeen: {},
};
const CHUNK = 8 * 1024 * 1024;
const KIND_COLORS = { pdf: '#ef4444', sheet: '#16a34a', doc: '#2563eb', slides: '#ea580c', text: '#6d5dfc', archive: '#64748b',
  video: '#ec4899', audio: '#0ea5e9', file: '#94a3b8', image: '#f59e0b' };
const ext = n => (n.includes('.') ? n.split('.').pop() : '').slice(0, 4).toUpperCase() || 'FILE';
const rawUrl = (p, dl) => '/api/files/raw?path=' + encodeURIComponent(p) + (dl ? '&dl=1' : '');
const thumbUrl = (p, e, s = 256) => `/api/files/thumb?path=${encodeURIComponent(p)}&s=${s}&m=${e.mtime || 0}`;
const join = (a, b) => (a.endsWith('/') ? a : a + '/') + b;
const dirOf = p => p.slice(0, p.lastIndexOf('/')) || '/';
const ARCH_RE = /\.(zip|7z|rar|tar|tgz|txz|tbz2|tar\.(gz|xz|bz2|zst))$/i;
const isArchive = e => !e.dir && ARCH_RE.test(e.name);
const canThumb = e => !e.dir && (e.kind === 'image' || e.kind === 'video') && !/\.(svg|ico)$/i.test(e.name);
const plural = (n, one, many) => `${nf(n)} ${n === 1 ? one : many}`;

function fileIcon(e, full) {
  if (e.dir) return `<div class="ficon folder ${e.shared ? 'share' : ''}"></div>`;
  if (canThumb(e)) return `<div class="ficon"><div class="thumb ${e.kind === 'video' ? 'vid' : ''}"><img src="${esc(thumbUrl(full, e))}" alt="" loading="lazy" data-fb="${esc(ext(e.name))}" data-fc="${KIND_COLORS[e.kind]}"></div></div>`;
  return `<div class="ficon doc" style="background:${KIND_COLORS[e.kind] || '#94a3b8'}">${esc(ext(e.name))}</div>`;
}
function miniIcon(e, full) {
  if (e.dir) return '<div class="mini folder"></div>';
  if (full && canThumb(e)) return `<div class="mini thumbm"><img src="${esc(thumbUrl(full, e))}" alt="" loading="lazy" data-fb="${esc(ext(e.name))}" data-fc="${KIND_COLORS[e.kind]}"></div>`;
  return `<div class="mini" style="background:${KIND_COLORS[e.kind] || '#94a3b8'}">${esc(ext(e.name))}</div>`;
}
// Miniatura non disponibile (formato non gestito, video senza ffmpegthumbnailer): torna l'icona del tipo
document.addEventListener('error', e => {
  const img = e.target;
  if (img.tagName !== 'IMG' || !img.dataset || !img.dataset.fb) return;
  const box = img.parentNode;
  if (box.classList.contains('thumb')) box.outerHTML = `<div class="ficon doc" style="background:${img.dataset.fc || '#94a3b8'};margin:-4px auto 0">${esc(img.dataset.fb)}</div>`;
  else { box.classList.remove('thumbm'); box.style.background = img.dataset.fc || '#94a3b8'; box.textContent = img.dataset.fb; }
}, true);

async function pageFiles(sub) {
  if (!S.admin) {
    $('#root').innerHTML = shell('files', 'File', null, `<div class="card"><div class="empty">${ic('lock')}<div>Il file manager è riservato agli amministratori.</div></div></div>`, { noSearch: true });
    return wireShell();
  }
  FM.view = store.get('fview', 'grid');
  FM.sort = store.get('fsort', { by: 'name', dir: 1 });
  FM.trash = sub === 'trash';
  FM.search = null;
  try { FM.clip = JSON.parse(sessionStorage.getItem('fclip') || 'null'); } catch (e) { FM.clip = null; }
  $('#root').innerHTML = shell('files', 'File', null, `
  <div class="card fm" id="fm">
    <div class="tree" id="ftree"><div class="empty"><span class="spin"></span></div></div>
    <div class="pane" id="fpane">
      <div class="tb" id="ftb"></div>
      <div class="clipbar" id="fclip" hidden></div>
      <div class="selbar" id="fsel" hidden></div>
      <div id="fbody" style="display:flex;flex-direction:column;flex:1;min-height:0;position:relative"></div>
      <div class="statusbar" id="fstatus"></div>
      <div class="fops" id="fops" hidden></div>
    </div>
    <div class="info" id="finfo"><div class="noinfo">Seleziona un file per vederne i dettagli</div></div>
  </div>
  <input type="file" id="fup" multiple hidden><input type="file" id="fupd" webkitdirectory multiple hidden>`, { noSearch: true });
  wireShell();
  $('#fup').onchange = e => { queueUploads([...e.target.files].map(f => ({ file: f, rel: f.name })), FM.path); e.target.value = ''; };
  $('#fupd').onchange = e => { queueUploads([...e.target.files].map(f => ({ file: f, rel: f.webkitRelativePath || f.name })), FM.path); e.target.value = ''; };
  wireDrop();
  wireKeys();
  await loadPlaces();
  drawClip();
  pollOps(true);
  if (sub === 'net') netDialog();
  if (FM.trash) return showTrash();
  await openDir(store.get('filesPath', null) || FM.places.favorites[0].path);
  every('fplaces', 20000, loadPlaces);
}

async function loadPlaces() {
  try { FM.places = await api('GET', '/files/places'); } catch (e) { return toast(e.message, 'bad'); }
  drawTree();
}

function drawTree() {
  const p = FM.places, cur = FM.path || '';
  if (!p || !$('#ftree')) return;
  const isOn = path => !FM.trash && !FM.search && cur === path;
  const disks = p.disks.map(d => {
    const pct = d.size ? 100 * (d.size - d.free) / d.size : 0;
    return `<a data-open="${esc(d.path)}" data-drop="${esc(d.path)}" class="${isOn(d.path) ? 'on' : ''}">${ic(d.icon)}${esc(d.name)}<small>${bytes(d.free)} liberi</small></a>
      <div class="dsk"><div class="bar ${pct > 85 ? 'warn' : ''}"><i style="width:${pct.toFixed(1)}%"></i></div></div>`;
  }).join('');
  const fav = p.favorites.map(f => `<a data-open="${esc(f.path)}" data-drop="${esc(f.path)}" ${f.pinned ? `data-pin="${esc(f.path)}"` : ''} class="${isOn(f.path) ? 'on' : ''}" title="${esc(f.path)}">${ic(f.icon)}<span class="tn">${esc(f.name)}</span>${f.pinned ? `<span class="unpin" data-unpin="${esc(f.path)}" title="Togli dai preferiti">${ic('x')}</span>` : ''}</a>`).join('');
  const net = p.network.map(n => `<a data-net="${esc(n.id)}" data-open="${n.mounted ? esc(n.path) : ''}" ${n.mounted ? `data-drop="${esc(n.path)}"` : ''} class="${isOn(n.path) ? 'on' : ''}" title="${esc(n.path)}"><span class="st ${n.mounted ? 'on' : ''}"></span>${esc(n.name)}<small>${esc(n.proto)}</small></a>`).join('') ||
    '<a data-newnet class="muted" style="font-size:12.5px">Collega un PC o un NAS…</a>';
  $('#ftree').innerHTML = `
    <div class="g">Dischi</div>${disks}
    <div class="g" id="favhead" title="Trascina qui una cartella per aggiungerla ai preferiti">Preferiti</div>${fav}
    <div class="g">Rete <span class="plus" data-newnet title="Collega una cartella di rete">${ic('plus')}</span></div>${net}
    <div class="g">Altro</div>
    <a data-trash class="${FM.trash ? 'on' : ''}">${ic('trash')}Cestino<small>${p.trash.size ? bytes(p.trash.size) : 'vuoto'}</small></a>
    <a data-links>${ic('link')}Link condivisi</a>`;
  $$('#ftree [data-open]').forEach(a => a.onclick = e => {
    if (e.target.closest('[data-unpin]')) return;
    if (a.dataset.net && !a.dataset.open) return netItemMenu(a, a.dataset.net);
    $('#ftree').classList.remove('open');
    FM.trash = false; openDir(a.dataset.open);
  });
  $$('#ftree [data-unpin]').forEach(x => x.onclick = e => { e.stopPropagation(); setFav(x.dataset.unpin, false); });
  $$('#ftree [data-net]').forEach(a => a.oncontextmenu = e => { e.preventDefault(); netItemMenu(a, a.dataset.net); });
  $$('#ftree [data-pin]').forEach(a => a.oncontextmenu = e => { e.preventDefault(); ctxMenu(e, [{ label: 'Apri', icon: 'folder', fn: () => openDir(a.dataset.pin) }, { label: 'Togli dai preferiti', icon: 'x', fn: () => setFav(a.dataset.pin, false) }]); });
  $$('#ftree [data-newnet]').forEach(a => a.onclick = () => netDialog());
  $('#ftree [data-trash]').onclick = () => { $('#ftree').classList.remove('open'); location.hash = 'files/trash'; };
  $('#ftree [data-links]').onclick = linksDialog;
  $$('#ftree [data-drop]').forEach(a => wireDropTarget(a, () => a.dataset.drop));
  // Cartelle trascinate sul titolo "Preferiti": entrano nei preferiti
  const fh = $('#favhead');
  fh.ondragover = e => { if (dragPaths(e)) { e.preventDefault(); e.dataTransfer.dropEffect = 'link'; fh.classList.add('droptarget'); } };
  fh.ondragleave = () => fh.classList.remove('droptarget');
  fh.ondrop = e => {
    e.preventDefault(); fh.classList.remove('droptarget');
    const ps = dragPaths(e) || [];
    const dirs = ps.filter(x => (FM.list.find(y => fullPath(y) === x) || {}).dir);
    if (!dirs.length) return toast('Nei preferiti vanno solo le cartelle', 'bad');
    dirs.forEach(d => setFav(d, true, true));
  };
}

async function setFav(path, on, quiet) {
  const r = await act(null, () => api('POST', '/files/favorite', { path, on }), quiet ? undefined : (on ? 'Aggiunta ai preferiti' : 'Tolta dai preferiti'));
  if (r) { if (quiet) toast('Aggiunta ai preferiti'); loadPlaces(); }
}
const isFav = path => (FM.places?.favorites || []).some(f => f.pinned && f.path === path);

/* --- cartella corrente ----------------------------------------------------- */

function sortList(list) {
  const { by, dir } = FM.sort;
  const kindOf = e => e.dir ? '' : (e.name.includes('.') ? e.name.split('.').pop().toLowerCase() : '');
  const cmpName = (a, b) => a.name.localeCompare(b.name, 'it', { numeric: true, sensitivity: 'base' });
  return [...list].sort((a, b) => {
    if (a.dir !== b.dir) return a.dir ? -1 : 1;           // le cartelle sempre prima
    let c = 0;
    if (by === 'mtime') c = (a.mtime || 0) - (b.mtime || 0);
    else if (by === 'size') c = (a.dir ? (a.calc ?? a.items ?? 0) : a.size || 0) - (b.dir ? (b.calc ?? b.items ?? 0) : b.size || 0);
    else if (by === 'kind') c = kindOf(a).localeCompare(kindOf(b)) || 0;
    return (c || cmpName(a, b)) * dir;
  });
}
function setSort(by) {
  FM.sort = FM.sort.by === by ? { by, dir: -FM.sort.dir } : { by, dir: by === 'name' || by === 'kind' ? 1 : -1 };
  store.set('fsort', FM.sort);
  FM.list = sortList(FM.list);
  drawToolbar(); drawFiles();
}

async function openDir(path, keepSel) {
  let d;
  try { d = await api('GET', '/files/list?path=' + encodeURIComponent(path) + (store.get('hidden', false) ? '&hidden=1' : '')); } catch (e) {
    toast(e.message, 'bad');
    if (path !== '/DATA') return openDir('/DATA');
    return;
  }
  if (!$('#fbody')) return;
  const old = FM.path === d.path ? new Map(FM.list.filter(x => x.calc != null).map(x => [x.name, x.calc])) : new Map();
  FM.path = d.path; FM.data = d; FM.search = null; FM.trash = false;
  FM.list = sortList(d.entries.map(x => old.has(x.name) ? { ...x, calc: old.get(x.name) } : x));
  if (location.hash.startsWith('#files/')) history.replaceState(null, '', '#files');
  store.set('filesPath', d.path);
  if (!keepSel) { FM.sel.clear(); FM.last = null; } else { const ok = new Set(FM.list.map(fullPath)); FM.sel.forEach(k => { if (!ok.has(k)) FM.sel.delete(k); }); }
  drawTree(); drawToolbar(); drawFiles(); drawSel(); drawStatus(); drawClip();
  if (!keepSel) showInfo(null);
}
const refresh = () => FM.search ? runSearch(FM.search.q) : FM.trash ? showTrash() : openDir(FM.path, true);

function crumbs() {
  const p = FM.path;
  const roots = [...(FM.places?.disks || []), ...(FM.places?.network || [])].map(d => d.path).sort((a, b) => b.length - a.length);
  const root = roots.find(r => p === r || p.startsWith(r + '/')) || '/' + p.split('/')[1];
  const rootName = (FM.places?.disks || []).concat(FM.places?.network || []).find(d => d.path === root)?.name || root;
  const parts = p.slice(root.length).split('/').filter(Boolean);
  let acc = root;
  return `<span data-crumb="${esc(root)}">${esc(rootName)}</span>` + parts.map(x => { acc += '/' + x; return `<i>›</i><span data-crumb="${esc(acc)}">${esc(x)}</span>`; }).join('');
}

const SORTS = [['name', 'Ordina per nome'], ['mtime', 'Ordina per data'], ['size', 'Ordina per dimensione'], ['kind', 'Ordina per tipo']];
function sortItems() {
  return SORTS.map(([k, l]) => ({ label: l + (FM.sort.by === k ? (FM.sort.dir > 0 ? ' ↑' : ' ↓') : ''), icon: FM.sort.by === k ? 'check' : 'sort', fn: () => setSort(k) }));
}

function drawToolbar() {
  const t = $('#ftb');
  if (!t) return;
  if (FM.trash) {
    t.innerHTML = `<button class="iconbtn sm hide-tree" id="ftreebtn" title="Cartelle">${ic('menu')}</button><div class="crumbs"><span>${ic('trash')} Cestino</span></div><button class="btn sm danger" id="tempty">${ic('trash')}Svuota cestino</button>`;
    $('#tempty').onclick = async () => {
      if (!await ask('Svuota il cestino', 'Tutti gli elementi nel cestino verranno cancellati per sempre.', 'Svuota', true)) return;
      act(null, () => api('POST', '/files/trash/empty', {}), 'Cestino svuotato').then(() => { loadPlaces(); showTrash(); });
    };
  } else {
    t.innerHTML = `
      <button class="iconbtn sm" id="ftreebtn" title="Cartelle" style="display:none">${ic('menu')}</button>
      <button class="iconbtn sm" id="fback" title="Cartella superiore (Backspace)" ${FM.data && FM.data.parent && !FM.search ? '' : 'disabled'}>${ic('back')}</button>
      <div class="crumbs">${FM.search ? `<span>Ricerca "${esc(FM.search.q)}" in ${esc(FM.search.path.split('/').pop() || FM.search.path)}</span>` : crumbs()}</div>
      <label class="fsearch" id="fsearchbox" ${FM.search ? '' : 'hidden'}>${ic('search')}<input id="fq" placeholder="Cerca in questa cartella…" value="${esc(FM.search ? FM.search.q : '')}"></label>
      <button class="iconbtn sm ${FM.search ? 'on' : ''}" id="fsearch" title="Cerca">${ic('search')}</button>
      <button class="iconbtn sm" id="fsort" title="Ordina">${ic('sort')}</button>
      <div class="seg"><button class="${FM.view === 'grid' ? 'on' : ''}" data-view="grid" title="Griglia">${ic('grid')}</button><button class="${FM.view === 'list' ? 'on' : ''}" data-view="list" title="Elenco">${ic('list')}</button></div>
      <button class="iconbtn sm" id="fnew" title="Nuova cartella">${ic('newfolder')}</button>
      <button class="iconbtn sm" id="fmore" title="Altro">${ic('more')}</button>
      <button class="btn sm primary" id="fupl">${ic('upload')}<span class="l">Carica</span></button>`;
    $('#fback').onclick = goUp;
    $$('[data-crumb]').forEach(s => { s.onclick = () => openDir(s.dataset.crumb); wireDropTarget(s, () => s.dataset.crumb); });
    $$('[data-view]').forEach(b => b.onclick = () => setView(b.dataset.view));
    $('#fsort').onclick = () => popmenu($('#fsort'), sortItems());
    $('#fnew').onclick = newFolder;
    $('#fupl').onclick = () => popmenu($('#fupl'), [{ label: 'Carica file', icon: 'file', fn: () => $('#fup').click() }, { label: 'Carica una cartella', icon: 'folder', fn: () => $('#fupd').click() }]);
    $('#fmore').onclick = () => popmenu($('#fmore'), [
      { label: 'Nuovo file di testo', icon: 'file', fn: newTextFile },
      { label: 'Seleziona tutto', icon: 'check', kbd: 'Ctrl+A', fn: selectAll },
      { label: store.get('hidden', false) ? 'Nascondi i file nascosti' : 'Mostra i file nascosti', icon: 'eye', fn: () => { store.set('hidden', !store.get('hidden', false)); refresh(); } },
      { label: 'Aggiorna', icon: 'refresh', fn: refresh },
      { label: 'Collega una cartella di rete', icon: 'globe', fn: () => netDialog() },
    ]);
    const box = $('#fsearchbox'), fq = $('#fq');
    $('#fsearch').onclick = () => { if (FM.search) { openDir(FM.path); return; } box.hidden = !box.hidden; if (!box.hidden) fq.focus(); };
    fq.onkeydown = e => { if (e.key === 'Enter' && fq.value.trim().length > 1) runSearch(fq.value.trim()); if (e.key === 'Escape') { box.hidden = true; if (FM.search) openDir(FM.path); } };
  }
  const tb = $('#ftreebtn');
  if (tb) {
    tb.style.display = innerWidth <= 720 ? '' : 'none';
    tb.onclick = () => $('#ftree').classList.toggle('open');
  }
}
function setView(v) { FM.view = v; store.set('fview', v); drawToolbar(); drawFiles(); }
function goUp() { if (FM.data && FM.data.parent && !FM.search) openDir(FM.data.parent); }

async function runSearch(q) {
  const body = $('#fbody');
  body.innerHTML = '<div class="empty"><span class="spin lg"></span><div>Cerco…</div></div>';
  let r;
  try { r = await api('GET', `/files/search?path=${encodeURIComponent(FM.path)}&q=${encodeURIComponent(q)}`); } catch (e) { toast(e.message, 'bad'); return openDir(FM.path); }
  FM.search = { q, path: FM.path, partial: r.partial };
  FM.list = sortList(r.results.map(x => ({ ...x, full: x.path })));
  FM.sel.clear();
  drawToolbar(); drawFiles(); drawSel(); drawStatus();
}

const fullPath = e => e.full || join(FM.path, e.name);
const entries = () => FM.list;

function sizeText(e) {
  if (!e.dir) return bytes(e.size);
  if (e.calc != null) return bytes(e.calc);
  return e.items != null ? plural(e.items, 'elemento', 'elementi') : '';
}

function drawFiles() {
  const body = $('#fbody');
  if (!body) return;
  const list = entries();
  if (!list.length) {
    body.innerHTML = `<div class="empty fempty" id="fitems" style="flex:1">${ic(FM.search ? 'search' : 'folder')}<div>${FM.search ? 'Nessun risultato' : 'Cartella vuota'}</div>${FM.search ? '' : '<div class="subtle">Trascina qui i file per caricarli, o usa il tasto destro</div>'}</div>`;
    wireItems();
    return;
  }
  const arrow = k => FM.sort.by === k ? `<b class="sarr">${FM.sort.dir > 0 ? '↑' : '↓'}</b>` : '';
  if (FM.view === 'list') {
    body.innerHTML = `<div class="flist" id="fitems"><div class="frow head"><span></span><span data-sort="name">Nome${arrow('name')}</span><span data-sort="size">Dimensione${arrow('size')}</span><span data-sort="mtime">Modificato${arrow('mtime')}</span></div>` +
      list.map((e, i) => `<div class="frow file-it" data-i="${i}" draggable="true" ${e.dir ? 'data-dir' : ''}>${miniIcon(e, fullPath(e))}<span class="n">${esc(e.name)}${FM.search ? `<span class="muted" style="font-size:11.5px"> — ${esc(e.full.slice(0, -e.name.length - 1))}</span>` : ''}</span><span class="m">${sizeText(e)}</span><span class="m">${dateIt(e.mtime)}</span></div>`).join('') + '</div>';
    $$('[data-sort]', body).forEach(h => h.onclick = () => setSort(h.dataset.sort));
  } else {
    body.innerHTML = `<div class="files ${FM.sel.size > 1 ? 'multi' : ''}" id="fitems">` + list.map((e, i) => `<div class="file file-it" data-i="${i}" draggable="true" ${e.dir ? 'data-dir' : ''} title="${esc(e.name)}">
      <span class="ck">${ic('check')}</span>${fileIcon(e, fullPath(e))}<div class="nm">${esc(e.name)}</div><div class="sz">${sizeText(e)}</div></div>`).join('') + '</div>';
  }
  markSel();
  wireItems();
}

function wireItems() {
  const items = $('#fitems');
  if (!items) return;
  const list = entries();
  items.onclick = e => {
    if (items.dataset.marquee) { delete items.dataset.marquee; return; }
    const it = e.target.closest('.file-it');
    if (!it) { if (!e.ctrlKey && !e.metaKey && !e.shiftKey) { FM.sel.clear(); markSel(); drawSel(); showInfo(null); } return; }
    const i = +it.dataset.i, ent = list[i];
    const touch = matchMedia('(pointer:coarse)').matches;
    if (e.target.closest('.ck') || e.ctrlKey || e.metaKey) toggleSel(i);
    else if (e.shiftKey && FM.last != null) rangeSel(FM.last, i, false);
    else if (touch && ent.dir && !FM.sel.size) return openEntry(ent);
    else if (touch && FM.sel.size && !FM.sel.has(key(i))) toggleSel(i);
    else if (touch && FM.sel.size === 1 && FM.sel.has(key(i)) && !ent.dir) return openEntry(ent);
    else { FM.sel.clear(); FM.sel.add(key(i)); }
    if (!e.shiftKey) FM.last = i;
    markSel(); drawSel();
    showInfo(FM.sel.size === 1 ? selected()[0] : null);
  };
  items.ondblclick = e => { const it = e.target.closest('.file-it'); if (it) openEntry(list[+it.dataset.i]); };
  items.oncontextmenu = e => {
    e.preventDefault();
    const it = e.target.closest('.file-it');
    if (!it) { FM.sel.clear(); markSel(); drawSel(); showInfo(null); return ctxMenu(e, emptyActions()); }
    const i = +it.dataset.i;
    if (!FM.sel.has(key(i))) { FM.sel.clear(); FM.sel.add(key(i)); FM.last = i; markSel(); drawSel(); showInfo(list[i]); }
    ctxMenu(e, selActions(true));
  };
  // Trascinamento: verso le cartelle (sposta, con Ctrl copia)
  items.ondragstart = e => {
    const it = e.target.closest('.file-it');
    if (!it) return;
    const i = +it.dataset.i;
    if (!FM.sel.has(key(i))) { FM.sel.clear(); FM.sel.add(key(i)); markSel(); drawSel(); }
    const paths = selected().map(fullPath);
    e.dataTransfer.setData('application/x-nido-files', JSON.stringify(paths));
    e.dataTransfer.setData('text/plain', paths.join('\n'));
    e.dataTransfer.effectAllowed = 'copyMove';
    FM.dragging = paths;
    if (paths.length > 1) {
      const g = document.createElement('div');
      g.className = 'dragghost'; g.textContent = `${paths.length} elementi`;
      document.body.appendChild(g); e.dataTransfer.setDragImage(g, 10, 10); setTimeout(() => g.remove(), 0);
    }
  };
  items.ondragend = () => { FM.dragging = null; $$('.droptarget').forEach(x => x.classList.remove('droptarget')); };
  $$('.file-it[data-dir]', items).forEach(el => wireDropTarget(el, () => fullPath(list[+el.dataset.i]), true));
  wireMarquee(items);
}

function dragPaths(e) {
  if (![...e.dataTransfer.types].includes('application/x-nido-files')) return null;
  try { return JSON.parse(e.dataTransfer.getData('application/x-nido-files') || 'null') || FM.dragging || []; } catch (x) { return FM.dragging || []; }
}
// Un elemento su cui si possono rilasciare file del NAS (sposta/copia) o del PC (carica lì)
function wireDropTarget(el, dest, isItem) {
  el.addEventListener('dragover', e => {
    const types = [...e.dataTransfer.types];
    const mine = types.includes('application/x-nido-files');
    if (!mine && !types.includes('Files')) return;
    const d = dest();
    if (mine && FM.dragging && FM.dragging.some(p => p === d || d.startsWith(p + '/'))) return;
    e.preventDefault(); e.stopPropagation();
    e.dataTransfer.dropEffect = mine ? (e.ctrlKey || e.metaKey ? 'copy' : 'move') : 'copy';
    el.classList.add('droptarget');
  });
  el.addEventListener('dragleave', () => el.classList.remove('droptarget'));
  el.addEventListener('drop', async e => {
    el.classList.remove('droptarget');
    const d = dest();
    const mine = dragPaths(e);
    if (mine) {
      e.preventDefault(); e.stopPropagation();
      if (mine.some(p => p === d || d.startsWith(p + '/'))) return;
      doTransfer(mine, d, !(e.ctrlKey || e.metaKey));
    } else if ([...e.dataTransfer.types].includes('Files') && isItem !== undefined) {
      e.preventDefault(); e.stopPropagation();
      queueUploads(await droppedFiles(e), d);
      $('#fpane').classList.remove('drop');
    }
  });
}

// Selezione con il rettangolo del mouse
function wireMarquee(items) {
  items.onmousedown = e => {
    if (e.button !== 0 || e.target.closest('.file-it') || e.target.closest('.frow.head') || matchMedia('(pointer:coarse)').matches) return;
    const box = items.getBoundingClientRect();
    if (e.clientX > box.left + items.clientWidth) return;   // barra di scorrimento
    const add = e.ctrlKey || e.metaKey || e.shiftKey;
    const before = new Set(add ? FM.sel : []);
    const sx = e.clientX - box.left + items.scrollLeft, sy = e.clientY - box.top + items.scrollTop;
    let mq = null, moved = false;
    const els = $$('.file-it', items).map(el => ({ el, k: key(+el.dataset.i), x: el.offsetLeft, y: el.offsetTop, w: el.offsetWidth, h: el.offsetHeight }));
    const move = ev => {
      const b = items.getBoundingClientRect();
      if (ev.clientY < b.top + 20) items.scrollTop -= 14; else if (ev.clientY > b.bottom - 20) items.scrollTop += 14;
      const cx = ev.clientX - b.left + items.scrollLeft, cy = ev.clientY - b.top + items.scrollTop;
      if (!moved && Math.abs(cx - sx) + Math.abs(cy - sy) < 5) return;
      moved = true;
      if (!mq) { mq = document.createElement('div'); mq.className = 'marquee'; items.appendChild(mq); }
      const x1 = Math.min(sx, cx), y1 = Math.min(sy, cy), x2 = Math.max(sx, cx), y2 = Math.max(sy, cy);
      Object.assign(mq.style, { left: x1 + 'px', top: y1 + 'px', width: x2 - x1 + 'px', height: y2 - y1 + 'px' });
      FM.sel = new Set(before);
      for (const it of els) if (it.x < x2 && it.x + it.w > x1 && it.y < y2 && it.y + it.h > y1) FM.sel.add(it.k);
      markSel();
    };
    const up = () => {
      removeEventListener('mousemove', move); removeEventListener('mouseup', up);
      if (mq) mq.remove();
      if (moved) { items.dataset.marquee = '1'; drawSel(); showInfo(FM.sel.size === 1 ? selected()[0] : null); }
    };
    addEventListener('mousemove', move); addEventListener('mouseup', up);
    if (!add) e.preventDefault();
  };
}

const key = i => fullPath(entries()[i]);
function toggleSel(i) { const k = key(i); if (FM.sel.has(k)) FM.sel.delete(k); else FM.sel.add(k); }
function rangeSel(a, b) { FM.sel.clear(); for (let i = Math.min(a, b); i <= Math.max(a, b); i++) FM.sel.add(key(i)); }
function selectOnly(name) { const i = entries().findIndex(e => e.name === name); if (i >= 0) { FM.sel.clear(); FM.sel.add(key(i)); FM.last = i; markSel(); drawSel(); showInfo(entries()[i]); const el = $(`.file-it[data-i="${i}"]`); if (el) el.scrollIntoView({ block: 'nearest' }); } }
function selectAll() { FM.sel = new Set(entries().map(fullPath)); markSel(); drawSel(); showInfo(null); }
function markSel() {
  $$('.file-it').forEach(el => el.classList.toggle('sel', FM.sel.has(key(+el.dataset.i))));
  const f = $('.files'); if (f) f.classList.toggle('multi', FM.sel.size > 1);
  const cut = FM.clip && FM.clip.cut ? new Set(FM.clip.paths) : null;
  $$('.file-it').forEach(el => el.classList.toggle('cut', !!(cut && cut.has(key(+el.dataset.i)))));
}
const selected = () => entries().filter(e => FM.sel.has(fullPath(e)));

function openEntry(e) {
  if (e.dir) return openDir(fullPath(e));
  preview(e);
}

/* --- menu e azioni ------------------------------------------------------------- */

function ctxMenu(e, items) { popmenu({ x: e.clientX, y: e.clientY }, items.filter(Boolean)); }

function selActions(menu) {
  const sel = selected(), one = sel.length === 1 ? sel[0] : null;
  if (!sel.length) return emptyActions();
  const allDirs = sel.every(x => x.dir);
  const a = [];
  if (one && !one.dir) a.push({ label: 'Apri', icon: 'eye', kbd: 'Invio', fn: () => preview(one) });
  if (one && one.dir) a.push({ label: 'Apri', icon: 'folder', kbd: 'Invio', fn: () => openDir(fullPath(one)) });
  if (one && !one.dir && (one.kind === 'text' || (one.kind === 'file' && one.size < 1024 * 1024))) a.push({ label: 'Modifica', icon: 'pencil', fn: () => editText(fullPath(one)) });
  a.push({ label: 'Scarica', icon: 'download', fn: () => downloadSel(sel) });
  a.push('-');
  a.push({ label: 'Taglia', icon: 'move', kbd: 'Ctrl+X', fn: () => setClip(sel, true), bar: true });
  a.push({ label: 'Copia', icon: 'copy', kbd: 'Ctrl+C', fn: () => setClip(sel, false), bar: true });
  if (FM.clip && one && one.dir) a.push({ label: 'Incolla nella cartella', icon: 'copy', fn: () => paste(fullPath(one)) });
  a.push({ label: 'Copia in…', icon: 'copy', fn: () => transferSel(sel, false) });
  a.push({ label: 'Sposta in…', icon: 'move', fn: () => transferSel(sel, true) });
  a.push('-');
  if (one) a.push({ label: 'Rinomina', icon: 'pencil', kbd: 'F2', fn: () => renameSel(one), bar: true });
  a.push({ label: 'Comprimi…', icon: 'archive', fn: () => compressDialog(sel), bar: true });
  if (one && isArchive(one)) a.push({ label: 'Estrai qui', icon: 'archive', fn: () => extractSel(one), bar: true });
  if (sel.some(x => x.dir)) a.push({ label: 'Calcola la dimensione', icon: 'disk', fn: () => calcSize(sel) });
  if (one && one.dir && !FM.search) a.push(isFav(fullPath(one)) ? { label: 'Togli dai preferiti', icon: 'star', fn: () => setFav(fullPath(one), false) } : { label: 'Aggiungi ai preferiti', icon: 'star', fn: () => setFav(fullPath(one), true) });
  a.push({ label: 'Permessi…', icon: 'lock', fn: () => permsDialog(sel) });
  if (one) a.push({ label: 'Condividi con un link', icon: 'link', fn: () => shareDialog(fullPath(one)) });
  a.push('-');
  a.push({ label: 'Elimina', icon: 'trash', kbd: 'Canc', fn: () => deleteSel(sel), danger: true, bar: true });
  void allDirs; void menu;
  return a;
}

function emptyActions() {
  if (FM.trash) return [];
  const inSearch = !!FM.search;
  return [
    { label: FM.clip ? `Incolla ${plural(FM.clip.paths.length, 'elemento', 'elementi')}` : 'Incolla', icon: 'copy', kbd: 'Ctrl+V', disabled: !FM.clip || inSearch, fn: () => paste(FM.path) },
    '-',
    { label: 'Nuova cartella', icon: 'newfolder', disabled: inSearch, fn: newFolder },
    { label: 'Nuovo file di testo', icon: 'file', disabled: inSearch, fn: newTextFile },
    { label: 'Carica file', icon: 'upload', disabled: inSearch, fn: () => $('#fup').click() },
    { label: 'Carica una cartella', icon: 'folder', disabled: inSearch, fn: () => $('#fupd').click() },
    '-',
    { label: 'Seleziona tutto', icon: 'check', kbd: 'Ctrl+A', fn: selectAll },
    { label: FM.view === 'grid' ? 'Vista a elenco' : 'Vista a griglia', icon: FM.view === 'grid' ? 'list' : 'grid', fn: () => setView(FM.view === 'grid' ? 'list' : 'grid') },
    ...sortItems(),
    '-',
    !inSearch && FM.path ? (isFav(FM.path) ? { label: 'Togli questa cartella dai preferiti', icon: 'star', fn: () => setFav(FM.path, false) } : { label: 'Aggiungi questa cartella ai preferiti', icon: 'star', fn: () => setFav(FM.path, true) }) : null,
    { label: 'Aggiorna', icon: 'refresh', fn: refresh },
  ].filter(Boolean);
}

function drawSel() {
  const bar = $('#fsel');
  if (!bar) return;
  if (!FM.sel.size || FM.trash) { bar.hidden = true; return; }
  bar.hidden = false;
  const acts = selActions().filter(x => x !== '-' && x.bar);
  bar.innerHTML = `<b>${FM.sel.size} selezionat${FM.sel.size === 1 ? 'o' : 'i'}</b>` +
    acts.map((x, k) => `<button class="btn sm ghost ${x.danger ? 'danger' : ''}" data-a="${k}" title="${esc(x.label)}${x.kbd ? ' (' + x.kbd + ')' : ''}">${ic(x.icon)}<span class="l">${esc(x.label.replace('…', ''))}</span></button>`).join('') +
    `<button class="btn sm ghost" id="selmore" title="Altre azioni">${ic('more')}</button><span class="grow"></span><button class="btn sm ghost" id="selx" title="Deseleziona (Esc)">${ic('x')}</button>`;
  $$('[data-a]', bar).forEach(b => b.onclick = () => acts[+b.dataset.a].fn());
  $('#selmore', bar).onclick = () => popmenu($('#selmore', bar), selActions());
  $('#selx', bar).onclick = () => { FM.sel.clear(); markSel(); drawSel(); showInfo(null); };
}

function drawStatus() {
  const st = $('#fstatus');
  if (!st || FM.trash) return;
  const list = entries();
  const total = list.reduce((s, e) => s + (e.size || 0), 0);
  const sp = FM.data.space;
  st.innerHTML = `<span>${plural(list.length, 'elemento', 'elementi')}${total ? ' · ' + bytes(total) : ''}${FM.search && FM.search.partial ? ' (ricerca parziale)' : ''}</span>
    ${sp && sp.size ? `<span class="hide-m">${bytes(sp.free)} liberi su ${bytes(sp.size)}</span>` : ''}<div class="upl" id="uplbox"></div>`;
  drawUploads();
}

/* --- appunti: taglia, copia, incolla ------------------------------------------------ */

function setClip(sel, cut) {
  if (!sel.length) return;
  FM.clip = { paths: sel.map(fullPath), cut, from: FM.search ? null : FM.path };
  try { sessionStorage.setItem('fclip', JSON.stringify(FM.clip)); } catch (e) { /* */ }
  markSel(); drawClip();
  toast(`${plural(sel.length, 'elemento', 'elementi')} ${cut ? 'tagliat' + (sel.length === 1 ? 'o' : 'i') : 'copiat' + (sel.length === 1 ? 'o' : 'i')}: apri la cartella di destinazione e incolla (Ctrl+V)`, 'info');
}
function clearClip() { FM.clip = null; try { sessionStorage.removeItem('fclip'); } catch (e) { /* */ } markSel(); drawClip(); }
function drawClip() {
  const bar = $('#fclip');
  if (!bar) return;
  if (!FM.clip || FM.trash) { bar.hidden = true; return; }
  const c = FM.clip, n = c.paths.length;
  const name = n === 1 ? `"${c.paths[0].split('/').pop()}"` : plural(n, 'elemento', 'elementi');
  bar.hidden = false;
  bar.innerHTML = `${ic(c.cut ? 'move' : 'copy')}<span class="grow">${esc(name)} ${c.cut ? 'da spostare' : 'da copiare'}${c.from ? ` · da <b>${esc(c.from.split('/').pop() || c.from)}</b>` : ''}</span>
    <button class="btn sm primary" id="cpaste" ${FM.search ? 'disabled' : ''}>${ic('copy')}Incolla qui</button><button class="btn sm ghost" id="cclear" title="Svuota gli appunti">${ic('x')}</button>`;
  $('#cpaste').onclick = () => paste(FM.path);
  $('#cclear').onclick = clearClip;
}
async function paste(dest) {
  if (!FM.clip || !dest) return;
  const c = FM.clip;
  const ok = await doTransfer(c.paths, dest, c.cut);
  if (ok && c.cut) clearClip();
}

// Copia o sposta con il controllo dei nomi già presenti nella destinazione
async function doTransfer(paths, dest, move) {
  if (!paths.length) return false;
  if (move && paths.every(p => dirOf(p) === dest)) return true;   // stessa cartella: niente da fare
  let conf;
  try { conf = (await api('POST', '/files/conflicts', { dest, paths })).conflicts.filter(c => !c.same); } catch (e) { toast(e.message, 'bad'); return false; }
  let policy = { default: 'rename', names: {} };
  if (conf.length) {
    policy = await conflictDialog(conf, move ? 'Sposta' : 'Copia');
    if (!policy) return false;
  }
  const r = await act(null, () => api('POST', `/files/${move ? 'move' : 'copy'}`, { paths, dest, policy }));
  if (!r) return false;
  pollOps(true);
  return true;
}

// Finestra dei conflitti di nome: sovrascrivi, salta, rinomina, con "fai così per tutti"
function conflictDialog(list, verb) {
  return new Promise(res => {
    const names = {};
    let k = 0;
    const m = modal(`${mhead(`<div class="dicon">${ic('alert')}</div>`, 'Nomi già presenti', `<span id="cfn"></span>`)}<div class="mb" id="cfb"></div>
      <div class="mf"><label class="row" style="cursor:pointer;margin-right:auto;font-size:13px" id="cfallw"><input type="checkbox" id="cfall"> Fai così per tutti</label>
      <button class="btn" data-a="skip">Salta</button><button class="btn" data-a="rename">Tieni entrambi</button><button class="btn primary" data-a="overwrite">Sostituisci</button></div>`, 'sm');
    m.parentNode.dataset.lock = '1';
    S.onModalClose = () => res(null);
    const draw = () => {
      const c = list[k];
      $('#cfn', m).textContent = list.length > 1 ? `Conflitto ${k + 1} di ${list.length}` : '';
      const merge = c.src_dir && c.dst_dir;
      $('#cfb', m).innerHTML = `<div class="dialog-text">Nella destinazione esiste già ${c.dst_dir ? 'una cartella' : 'un file'} chiamat${c.dst_dir ? 'a' : 'o'} <b>${esc(c.name)}</b>.</div>
        <div class="cfcmp"><div><span class="subtle">${verb === 'Carica' ? 'Da caricare' : 'Da ' + verb.toLowerCase() + 're'}</span><b>${c.src_dir ? 'Cartella' : bytes(c.src_size || 0)}</b><span>${c.src_mtime ? dateIt(c.src_mtime) : ''}</span></div>
        <div><span class="subtle">Già presente</span><b>${c.dst_dir ? 'Cartella' : bytes(c.dst_size || 0)}</b><span>${dateIt(c.dst_mtime)}</span></div></div>
        ${merge ? '<div class="subtle" style="margin-top:8px">"Sostituisci" unisce le due cartelle: i file con lo stesso nome vengono sostituiti.</div>' : ''}`;
      $('#cfallw', m).style.display = list.length - k > 1 ? '' : 'none';
      $('[data-a=overwrite]', m).textContent = merge ? 'Unisci' : 'Sostituisci';
    };
    $$('[data-a]', m).forEach(b => b.onclick = () => {
      const a = b.dataset.a;
      if ($('#cfall', m).checked) {
        for (let j = k; j < list.length; j++) names[list[j].name] = a;
        k = list.length;
      } else { names[list[k].name] = a; k++; }
      if (k >= list.length) { S.onModalClose = null; closeModal(); res({ default: 'rename', names }); } else draw();
    });
    draw();
  });
}

/* --- tastiera ---------------------------------------------------------------------- */

function wireKeys() {
  const h = e => {
    if (S.page !== 'files' || $('#scrim') || $('.menu') || FM.trash) return;
    const t = e.target;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    const c = e.ctrlKey || e.metaKey, k = e.key.toLowerCase();
    const sel = selected();
    if (c && k === 'a') { e.preventDefault(); selectAll(); }
    else if (c && k === 'c' && sel.length) { e.preventDefault(); setClip(sel, false); }
    else if (c && k === 'x' && sel.length) { e.preventDefault(); setClip(sel, true); }
    else if (c && k === 'v' && FM.clip && !FM.search) { e.preventDefault(); paste(FM.path); }
    else if (e.key === 'Delete' && sel.length) { e.preventDefault(); deleteSel(sel, e.shiftKey); }
    else if (e.key === 'F2' && sel.length === 1) { e.preventDefault(); renameSel(sel[0]); }
    else if (e.key === 'Enter' && sel.length === 1) { e.preventDefault(); openEntry(sel[0]); }
    else if (e.key === 'Backspace' && !c) { e.preventDefault(); goUp(); }
    else if (e.key === 'Escape' && FM.sel.size) { FM.sel.clear(); markSel(); drawSel(); showInfo(null); }
    else if (['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp'].includes(e.key) && entries().length) {
      e.preventDefault();
      const n = entries().length;
      let i = FM.last ?? -1;
      let step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : -1;
      if (FM.view === 'grid' && (e.key === 'ArrowDown' || e.key === 'ArrowUp')) {
        const g = $('.files'); const cols = g ? getComputedStyle(g).gridTemplateColumns.split(' ').length : 1;
        step *= cols;
      }
      i = Math.max(0, Math.min(n - 1, i + step));
      if (e.shiftKey && FM.last != null) { FM.sel.add(key(i)); } else { FM.sel.clear(); FM.sel.add(key(i)); }
      FM.last = i; markSel(); drawSel(); showInfo(FM.sel.size === 1 ? selected()[0] : null);
      const el = $(`.file-it[data-i="${i}"]`); if (el) el.scrollIntoView({ block: 'nearest' });
    }
  };
  document.addEventListener('keydown', h);
  const before = e => { if (FM.uploads.some(u => u.state === 'run' || u.state === 'wait' || u.state === 'retry')) { e.preventDefault(); e.returnValue = ''; } };
  addEventListener('beforeunload', before);
  S.cleanup.push(() => { document.removeEventListener('keydown', h); removeEventListener('beforeunload', before); });
}

/* --- dettagli ------------------------------------------------------------------ */

async function showInfo(e) {
  const box = $('#finfo');
  if (!box) return;
  if (!e) {
    const sel = selected();
    const tot = sel.reduce((s, x) => s + (x.dir ? x.calc || 0 : x.size || 0), 0);
    box.innerHTML = `<div class="noinfo">${sel.length > 1 ? `${sel.length} elementi selezionati${tot ? ' · ' + bytes(tot) : ''}${sel.some(x => x.dir) ? `<div style="margin-top:10px"><button class="btn sm" id="icalc">${ic('disk')}Calcola la dimensione</button></div>` : ''}` : 'Seleziona un file per vederne i dettagli'}</div>`;
    const b = $('#icalc'); if (b) b.onclick = () => calcSize(sel, b);
    return;
  }
  const full = fullPath(e);
  const prev = canThumb(e) ? `<img src="${esc(thumbUrl(full, e, 512))}" alt="" data-fb="${esc(ext(e.name))}" data-fc="${KIND_COLORS[e.kind]}">` : e.dir ? '<div class="ficon folder" style="transform:scale(1.6)"></div>' : `<div class="big" style="background:${KIND_COLORS[e.kind] || '#94a3b8'}">${esc(ext(e.name))}</div>`;
  box.innerHTML = `<div class="prev">${prev}</div><div><b style="font-size:15px;word-break:break-word">${esc(e.name)}</b><div class="muted" style="font-size:12.5px" id="ikind">${e.dir ? 'Cartella' : bytes(e.size)}</div></div>
    <div class="row" style="gap:8px;flex-wrap:wrap"><button class="btn sm" id="iopen">${ic(e.dir ? 'folder' : 'eye')}Apri</button>${e.dir ? `<button class="btn sm" id="icalc">${ic('disk')}Dimensione</button>` : `<a class="btn sm" href="${esc(rawUrl(full, 1))}">${ic('download')}Scarica</a>`}<button class="btn sm" id="imore">${ic('more')}</button></div>
    <dl class="kv" id="ikv"><dt>Percorso</dt><dd class="mono" style="font-size:12px">${esc(full.slice(0, full.length - e.name.length))}</dd></dl>`;
  $('#iopen').onclick = () => openEntry(e);
  $('#imore').onclick = () => popmenu($('#imore'), selActions());
  const ib = $('#icalc'); if (ib) ib.onclick = () => calcSize([e], ib);
  let d;
  try { d = await api('GET', '/files/details?path=' + encodeURIComponent(full)); } catch (err) { return; }
  if (!box.isConnected || FM.sel.size !== 1) return;
  const kinds = { image: 'Immagine', video: 'Video', audio: 'Audio', pdf: 'Documento PDF', text: 'Testo', archive: 'Archivio', doc: 'Documento', sheet: 'Foglio di calcolo', slides: 'Presentazione', folder: 'Cartella', file: 'File' };
  const dsize = e.calc != null ? e.calc : d.size;
  $('#ikind').textContent = `${kinds[d.kind] || 'File'}${d.mime && !d.dir ? ' · ' + d.mime.split('/')[1].toUpperCase().slice(0, 10) : ''} · ${bytes(dsize)}${d.dir ? ` · ${nf(d.files)} file${d.partial && e.calc == null ? '+' : ''}` : ''}`;
  const rows = [];
  if (d.width) rows.push(['Dimensioni', `${d.width} × ${d.height}`]);
  if (d.taken) rows.push(['Scattata', d.taken.replace(/^(\d{4}):(\d\d):(\d\d)/, '$3/$2/$1')]);
  if (d.camera) rows.push(['Fotocamera', d.camera]);
  rows.push(['Modificato', dateIt(d.mtime)]);
  rows.push(['Percorso', `<span class="mono" style="font-size:12px">${esc(d.path.slice(0, d.path.length - d.name.length))}</span>`, true]);
  rows.push(['Permessi', `${esc(d.owner)}:${esc(d.group)} · <span class="mono" style="font-size:12px">${esc(d.mode)}</span> <a href="#" id="iperm" style="font-size:12px">Cambia</a>`, true]);
  $('#ikv').innerHTML = rows.map(([k, v, raw]) => `<dt>${k}</dt><dd>${raw ? v : esc(v)}</dd>`).join('');
  $('#iperm').onclick = ev => { ev.preventDefault(); permsDialog([e]); };
}

async function calcSize(sel, btn) {
  const dirs = sel.filter(x => x.dir);
  if (!dirs.length) return;
  const r = await act(btn || null, () => api('POST', '/files/size', { paths: dirs.map(fullPath) }, { timeout: 60000 }));
  if (!r) return;
  for (const x of dirs) { const v = r.items[fullPath(x)]; if (v != null) x.calc = v; }
  if (FM.sort.by === 'size') FM.list = sortList(FM.list);
  drawFiles(); markSel();
  toast(`${dirs.length === 1 ? `"${dirs[0].name}"` : plural(dirs.length, 'cartella', 'cartelle')}: ${r.partial ? 'almeno ' : ''}${bytes(r.size)} · ${plural(r.files, 'file', 'file')}${r.partial ? ' (calcolo interrotto dopo 25 secondi)' : ''}`, 'info', 7000);
  if (FM.sel.size === 1) showInfo(selected()[0]); else showInfo(null);
}

/* --- anteprima ------------------------------------------------------------------ */

async function preview(e) {
  const list = entries().filter(x => !x.dir);
  let idx = list.indexOf(e);
  async function draw() {
    const cur = list[idx], full = fullPath(cur);
    let inner;
    if (cur.kind === 'image') inner = `<img src="${esc(rawUrl(full))}" alt="">`;
    else if (cur.kind === 'video') inner = `<video src="${esc(rawUrl(full))}" controls autoplay playsinline></video>`;
    else if (cur.kind === 'audio') inner = `<audio src="${esc(rawUrl(full))}" controls autoplay></audio>`;
    else if (cur.kind === 'pdf') inner = `<iframe src="${esc(rawUrl(full))}" title="PDF"></iframe>`;
    else if (cur.kind === 'text') inner = '<pre id="ptext">Carico…</pre>';
    else if (isArchive(cur)) inner = `<div class="empty" style="color:#c5c9db">${ic('archive')}<div>Archivio ${esc(ext(cur.name))}</div><button class="btn" id="pext">${ic('archive')}Estrai qui</button></div>`;
    else inner = `<div class="empty" style="color:#c5c9db">${ic('file')}<div>Anteprima non disponibile per questo tipo di file</div><a class="btn" href="${esc(rawUrl(full, 1))}">${ic('download')}Scarica</a></div>`;
    const m = modal(`${mhead(miniIcon(cur), esc(cur.name), `${bytes(cur.size)} · ${dateIt(cur.mtime)}`)}
      <div class="mb tight"><div class="preview">${inner}${list.length > 1 ? `<button class="nav-prev" id="pp">${ic('back')}</button><button class="nav-next" id="pn">${ic('chevron')}</button>` : ''}</div></div>
      <div class="mf"><span class="grow">${idx + 1} di ${list.length}</span>${cur.kind === 'text' ? `<button class="btn" id="pedit">${ic('pencil')}Modifica</button>` : ''}<button class="btn" id="pshare">${ic('link')}Condividi</button><a class="btn primary" href="${esc(rawUrl(full, 1))}">${ic('download')}Scarica</a></div>`, 'full');
    if (cur.kind === 'text') api('GET', '/files/text?path=' + encodeURIComponent(full)).then(r => { const p = $('#ptext', m); if (p) p.textContent = r.text + (r.truncated ? '\n\n… (file troncato nell\'anteprima)' : ''); }).catch(err => { const p = $('#ptext', m); if (p) p.textContent = err.message; });
    const pp = $('#pp', m), pn = $('#pn', m);
    if (pp) pp.onclick = () => { idx = (idx - 1 + list.length) % list.length; draw(); };
    if (pn) pn.onclick = () => { idx = (idx + 1) % list.length; draw(); };
    $('#pshare', m).onclick = () => shareDialog(full);
    const pe = $('#pedit', m); if (pe) pe.onclick = () => editText(full);
    const px = $('#pext', m); if (px) px.onclick = () => { closeModal(); extractSel(cur); };
    m.tabIndex = -1;
    m.onkeydown = ev => { if (ev.key === 'ArrowLeft' && pp) pp.click(); if (ev.key === 'ArrowRight' && pn) pn.click(); };
    m.focus();
  }
  draw();
}

/* --- editor di testo ----------------------------------------------------------- */

async function editText(path) {
  let f;
  try { f = await api('GET', '/files/edit?path=' + encodeURIComponent(path)); } catch (e) { return toast(e.message, 'bad'); }
  const m = modal(`${mhead(`<div class="dicon">${ic('pencil')}</div>`, esc(f.name), `<span class="mono">${esc(f.path)}</span>`)}
    <div class="mb tight edwrap"><div class="edgut" id="edg"></div><textarea id="edt" class="editor" spellcheck="false" autocapitalize="off" autocomplete="off" wrap="off" ${f.writable ? '' : 'readonly'}></textarea></div>
    <div class="mf"><span class="grow subtle" id="edst">${f.writable ? '' : 'Sola lettura'}</span><span class="subtle hide-m" id="edpos"></span><label class="row subtle" style="cursor:pointer;font-size:12.5px"><input type="checkbox" id="edwrap"> A capo</label>
      <button class="btn" id="edclose">Chiudi</button><button class="btn primary" id="edsave" ${f.writable ? '' : 'disabled'}>${ic('check')}Salva <kbd>Ctrl+S</kbd></button></div>`, 'full editorm');
  const ta = $('#edt', m), gut = $('#edg', m), st = $('#edst', m);
  ta.value = f.text;
  let saved = f.text, mtime = f.mtime;
  const dirty = () => ta.value !== saved;
  const lines = () => { const n = ta.value.split('\n').length; if (gut.childElementCount !== n) gut.textContent = Array.from({ length: n }, (_, i) => i + 1).join('\n'); };
  const pos = () => { const before = ta.value.slice(0, ta.selectionStart).split('\n'); $('#edpos', m).textContent = `Riga ${before.length}, colonna ${before[before.length - 1].length + 1}`; };
  lines(); pos();
  ta.oninput = () => { lines(); st.textContent = dirty() ? '● Modifiche non salvate' : ''; };
  ta.onscroll = () => { gut.scrollTop = ta.scrollTop; };
  ta.onkeyup = ta.onclick = pos;
  $('#edwrap', m).onchange = ev => { ta.wrap = ev.target.checked ? 'soft' : 'off'; gut.style.display = ev.target.checked ? 'none' : ''; };
  ta.onkeydown = ev => {
    if (ev.key === 'Tab' && !ev.ctrlKey) {
      ev.preventDefault();
      const s = ta.selectionStart, e2 = ta.selectionEnd;
      ta.setRangeText('  ', s, e2, 'end'); ta.oninput();
    } else if ((ev.ctrlKey || ev.metaKey) && ev.key.toLowerCase() === 's') { ev.preventDefault(); save(); }
    else if (ev.key === 'Escape') { ev.stopPropagation(); }
  };
  async function save(force) {
    const btn = $('#edsave', m);
    let r;
    try {
      btn.disabled = true;
      r = await api('POST', '/files/save', { path: f.path, text: ta.value, mtime, encoding: f.encoding, crlf: f.crlf, force: !!force });
    } catch (e) {
      btn.disabled = false;
      if (e.status === 409) {
        const host = $('#scrim'); host.style.display = 'none';
        const ok = await new Promise(res => {
          const d = document.createElement('div'); d.className = 'scrim'; d.style.zIndex = 31;
          d.innerHTML = `<div class="modal sm"><div class="mh"><div class="dicon">${ic('alert')}</div><div style="flex:1"><h2>Il file è cambiato</h2></div></div><div class="mb"><div class="dialog-text">${esc(e.message)}. Vuoi sovrascriverlo con il tuo testo?</div></div><div class="mf"><button class="btn" id="n">Annulla</button><button class="btn danger solid" id="y">Sovrascrivi</button></div></div>`;
          document.body.appendChild(d);
          $('#n', d).onclick = () => { d.remove(); res(false); };
          $('#y', d).onclick = () => { d.remove(); res(true); };
        });
        host.style.display = '';
        if (ok) return save(true);
        return;
      }
      return toast(e.message, 'bad');
    }
    btn.disabled = false;
    saved = ta.value; mtime = r.mtime;
    st.textContent = 'Salvato ' + new Date().toLocaleTimeString(LOCALE, { hour: '2-digit', minute: '2-digit' });
    if (dirOf(f.path) === FM.path) refresh();
  }
  $('#edsave', m).onclick = () => save();
  const tryClose = async () => {
    if (dirty() && !confirm('Ci sono modifiche non salvate. Chiudere senza salvare?')) return;
    S.onModalClose = null; closeModal();
  };
  $('#edclose', m).onclick = tryClose;
  $('[data-close]', m).onclick = tryClose;
  m.parentNode.dataset.lock = '1';
  setTimeout(() => ta.focus(), 50);
}

async function newTextFile() {
  if (FM.search || !FM.path) return;
  const name = await prompt2('Nuovo file di testo', 'Nome', 'nuovo.txt', 'Crea');
  if (!name) return;
  const r = await act(null, () => api('POST', '/files/newfile', { path: FM.path, name }));
  if (r) { await openDir(FM.path); selectOnly(r.path.split('/').pop()); editText(r.path); }
}
async function newFolder() {
  if (FM.search || !FM.path) return;
  const name = await prompt2('Nuova cartella', 'Nome', 'Nuova cartella', 'Crea');
  if (name) act(null, () => api('POST', '/files/mkdir', { path: FM.path, name })).then(r => r && openDir(FM.path).then(() => selectOnly(r.path.split('/').pop())));
}

/* --- operazioni ---------------------------------------------------------------- */

function downloadSel(sel) {
  if (sel.length === 1 && !sel[0].dir) { location.href = rawUrl(fullPath(sel[0]), 1); return; }
  const paths = sel.map(fullPath).join('\n');
  location.href = '/api/files/download?paths=' + encodeURIComponent(paths);
}

async function renameSel(e) {
  const name = await prompt2('Rinomina', 'Nuovo nome', e.name, 'Rinomina');
  if (!name || name === e.name) return;
  const r = await act(null, () => api('POST', '/files/rename', { path: fullPath(e), name }));
  if (r) { await refresh(); selectOnly(name); }
}

async function deleteSel(sel, permanent) {
  const names = sel.length === 1 ? `"${esc(sel[0].name)}"` : `${sel.length} elementi`;
  if (permanent) {
    if (!await ask('Elimina per sempre', `${names} ${sel.length === 1 ? 'verrà cancellato' : 'verranno cancellati'} senza passare dal cestino.`, 'Elimina per sempre', true)) return;
  } else if (!await ask('Sposta nel cestino', `${names} ${sel.length === 1 ? 'verrà spostato' : 'verranno spostati'} nel cestino. Potrai recuperarl${sel.length === 1 ? 'o' : 'i'} da "Cestino".`, 'Elimina', true)) return;
  const r = await act(null, () => api('POST', '/files/delete', { paths: sel.map(fullPath), permanent: !!permanent }), permanent ? 'Eliminato' : `Spostat${sel.length === 1 ? 'o' : 'i'} nel cestino`);
  if (r) { FM.sel.clear(); refresh(); loadPlaces(); showInfo(null); }
}

function transferSel(sel, move) {
  pickFolder(FM.path, dest => doTransfer(sel.map(fullPath), dest, move), true);
}

function compressDialog(sel) {
  const base = sel.length === 1 ? sel[0].name.replace(/\.[^.]+$/, '') || sel[0].name : (FM.path.split('/').pop() || 'Archivio');
  let fmt = store.get('zipfmt', 'zip');
  const m = modal(`${mhead(`<div class="dicon">${ic('archive')}</div>`, 'Comprimi', plural(sel.length, 'elemento', 'elementi'))}
    <div class="mb"><div class="field"><label>Nome dell'archivio</label><input class="input" id="zn" value="${esc(base)}"></div>
      <div class="field"><label>Formato</label><div class="seg" id="zf">${[['zip', 'ZIP'], ['7z', '7z'], ['tar.gz', 'TAR.GZ']].map(([k, l]) => `<button data-f="${k}" class="${fmt === k ? 'on' : ''}">${l}</button>`).join('')}</div>
      <span class="hint">ZIP si apre ovunque; 7z comprime di più; TAR.GZ conserva i permessi (Linux).</span></div></div>
    <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="zgo">${ic('archive')}Comprimi</button></div>`, 'sm');
  $$('[data-f]', m).forEach(b => b.onclick = () => { fmt = b.dataset.f; $$('[data-f]', m).forEach(x => x.classList.toggle('on', x === b)); });
  $('#zgo', m).onclick = async e => {
    store.set('zipfmt', fmt);
    const r = await act(e.currentTarget, () => api('POST', '/files/compress', { paths: sel.map(fullPath), format: fmt, name: $('#zn', m).value.trim() }));
    if (r) { closeModal(); pollOps(true); }
  };
}

async function extractSel(e) {
  const r = await act(null, () => api('POST', '/files/extract', { path: fullPath(e) }));
  if (r) pollOps(true);
}

async function permsDialog(sel) {
  let p;
  try { p = await api('GET', '/files/perms?path=' + encodeURIComponent(fullPath(sel[0]))); } catch (e) { return toast(e.message, 'bad'); }
  const anyDir = sel.some(x => x.dir);
  const lv = { ...p.levels };
  const LV = [['none', 'Nessuno'], ['r', 'Lettura'], ['rw', 'Lettura e scrittura']];
  const row = (k, label, sub) => `<div class="permrow"><div><b>${label}</b><div class="subtle">${sub}</div></div><div class="seg" data-who="${k}">${LV.map(([v, l]) => `<button data-v="${v}" class="${(lv[k] === v || (v === 'r' && lv[k] === 'w')) ? 'on' : ''}">${l}</button>`).join('')}</div></div>`;
  const m = modal(`${mhead(`<div class="dicon">${ic('lock')}</div>`, 'Permessi', sel.length === 1 ? esc(sel[0].name) : plural(sel.length, 'elemento', 'elementi'))}
    <div class="mb">
      <div class="cols2"><div class="field"><label>Proprietario</label><select class="input" id="pown">${p.users.map(u => `<option ${u.name === p.owner ? 'selected' : ''}>${esc(u.name)}</option>`).join('')}${p.users.some(u => u.name === p.owner) ? '' : `<option selected>${esc(p.owner)}</option>`}</select></div>
      <div class="field"><label>Gruppo</label><select class="input" id="pgrp">${p.groups.map(g => `<option ${g.name === p.group ? 'selected' : ''}>${esc(g.name)}</option>`).join('')}${p.groups.some(g => g.name === p.group) ? '' : `<option selected>${esc(p.group)}</option>`}</select></div></div>
      ${row('owner', 'Proprietario', 'l\'utente scelto sopra')}${row('group', 'Gruppo', 'gli utenti del gruppo')}${row('other', 'Tutti gli altri', 'anche le app e gli ospiti delle condivisioni')}
      ${anyDir ? `<label class="row" style="cursor:pointer;margin-top:6px"><input type="checkbox" id="prec"> Applica anche a tutto il contenuto delle cartelle</label>` : ''}
      <div class="subtle" style="margin-top:8px">Adesso: <span class="mono">${esc(p.text)}</span> (${esc(p.mode)}) · ${esc(p.owner)}:${esc(p.group)}. Le condivisioni Samba aggiungono i loro permessi per utente.</div>
    </div>
    <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="pgo">${ic('check')}Applica</button></div>`);
  $$('[data-who]', m).forEach(g => $$('[data-v]', g).forEach(b => b.onclick = () => { lv[g.dataset.who] = b.dataset.v; $$('[data-v]', g).forEach(x => x.classList.toggle('on', x === b)); }));
  $('#pgo', m).onclick = async e => {
    const own = $('#pown', m).value, grp = $('#pgrp', m).value;
    const body = { paths: sel.map(fullPath), owner: own !== p.owner || sel.length > 1 ? own : null, group: grp !== p.group || sel.length > 1 ? grp : null, levels: lv, recursive: !!($('#prec', m) && $('#prec', m).checked) };
    const r = await act(e.currentTarget, () => api('POST', '/files/perms', body), body.recursive ? undefined : 'Permessi aggiornati');
    if (!r) return;
    closeModal();
    if (r.job) pollOps(true); else { refresh(); if (FM.sel.size === 1) showInfo(selected()[0]); }
  };
}

/* --- coda delle operazioni (copie, spostamenti, archivi, permessi) ----------------- */

const OPS_ICON = { copy: 'copy', move: 'move', compress: 'archive', extract: 'archive', perms: 'lock' };
function etaText(s) { if (s == null) return ''; if (s < 60) return `${s} s`; if (s < 3600) return `${Math.round(s / 60)} min`; return `${Math.floor(s / 3600)} h ${Math.round(s % 3600 / 60)} min`; }

async function pollOps(soon) {
  clearTimeout(FM.opsTimer);
  if (S.page !== 'files' || !$('#fops')) return;
  let r;
  try { r = await api('GET', '/files/ops'); } catch (e) { r = null; }
  if (r) {
    const hidden = store.get('opsHidden', []);
    const prev = FM.ops;
    FM.ops = r.jobs.filter(j => !hidden.includes(j.id));
    // Operazioni appena finite: aggiorno la cartella e avviso degli errori
    for (const j of FM.ops) {
      const was = prev.find(x => x.id === j.id);
      const ended = j.state === 'done' || j.state === 'failed';
      if (ended && (was ? (was.state === 'running' || was.state === 'queued') : !FM.opsSeen[j.id] && soon)) {
        if (j.state === 'failed' && !j.cancelled) toast(`${j.title}: ${j.error}`, 'bad', 9000);
        else if (j.state === 'done') toast(j.result && j.result.skipped ? `${j.title}: fatto (${j.result.skipped} saltati)` : `${j.title}: fatto`);
        refresh(); loadPlaces();
      }
      if (ended) FM.opsSeen[j.id] = true;
    }
    drawOps();
  }
  const busy = FM.ops.some(j => j.state === 'running' || j.state === 'queued');
  FM.opsTimer = setTimeout(() => pollOps(false), busy ? 1200 : 8000);
  S.cleanup.push(() => clearTimeout(FM.opsTimer));
}

function drawOps() {
  const box = $('#fops');
  if (!box) return;
  const list = FM.ops;
  if (!list.length) { box.hidden = true; return; }
  box.hidden = false;
  const running = list.filter(j => j.state === 'running' || j.state === 'queued').length;
  const collapsed = store.get('opsMin', false);
  box.innerHTML = `<div class="fopsh"><b>${running ? `${plural(running, 'operazione', 'operazioni')} in corso` : 'Operazioni finite'}</b><span class="grow"></span>
    ${!running ? `<button class="iconbtn sm" id="opsclr" title="Togli le finite">${ic('check')}</button>` : ''}<button class="iconbtn sm" id="opsmin" title="${collapsed ? 'Espandi' : 'Riduci'}">${ic(collapsed ? 'up' : 'minus')}</button></div>
    ${collapsed ? '' : `<div class="fopsl">${list.map(j => {
      const bt = j.bytes_total ? `${bytes(j.bytes_done)} di ${bytes(j.bytes_total)}` : j.items_done ? plural(j.items_done, 'elemento', 'elementi') : '';
      const sub = j.state === 'queued' ? 'In coda: parte quando finisce quella prima'
        : j.state === 'running' ? [bt, j.speed ? bytes(j.speed) + '/s' : '', j.eta != null ? 'mancano ' + etaText(j.eta) : ''].filter(Boolean).join(' · ')
        : j.state === 'done' ? 'Completata' + (j.result && j.result.skipped ? ` · ${j.result.skipped} saltati` : '')
        : j.cancelled ? 'Annullata' : 'Errore: ' + (j.error || '');
      return `<div class="fop ${j.state}"><div class="row" style="gap:8px">${ic(OPS_ICON[j.kind] || 'refresh')}<div class="grow" style="min-width:0"><div class="t">${esc(j.title)}</div><div class="s">${esc(sub)}</div>${j.state === 'running' && j.step ? `<div class="s mono">${esc(j.step)}</div>` : ''}</div>
        ${j.state === 'running' || j.state === 'queued' ? `<button class="iconbtn sm" data-cancel="${esc(j.id)}" title="Annulla">${ic('x')}</button>` : `<button class="iconbtn sm" data-hide="${esc(j.id)}" title="Togli">${ic('x')}</button>`}</div>
        ${j.state === 'running' ? `<div class="bar"><i style="width:${j.progress}%"></i></div>` : ''}</div>`;
    }).join('')}</div><div class="subtle" style="font-size:11.5px;padding:0 12px 10px">Continuano anche se chiudi la pagina.</div>`}`;
  $$('[data-cancel]', box).forEach(b => b.onclick = async () => { if (await ask('Annulla operazione', 'L\'operazione si ferma: i file già copiati restano, quello a metà viene tolto.', 'Annulla operazione', true)) act(b, () => api('POST', `/jobs/${b.dataset.cancel}/cancel`)).then(() => pollOps(true)); });
  $$('[data-hide]', box).forEach(b => b.onclick = () => hideOps([b.dataset.hide]));
  const c = $('#opsclr', box); if (c) c.onclick = () => hideOps(list.map(j => j.id));
  $('#opsmin', box).onclick = () => { store.set('opsMin', !collapsed); drawOps(); };
}
function hideOps(ids) {
  const h = store.get('opsHidden', []).concat(ids).slice(-200);
  store.set('opsHidden', h);
  FM.ops = FM.ops.filter(j => !ids.includes(j.id));
  drawOps();
}

/* --- caricamento ------------------------------------------------------------------ */

async function droppedFiles(e) {
  const items = [...(e.dataTransfer.items || [])].map(i => i.webkitGetAsEntry && i.webkitGetAsEntry()).filter(Boolean);
  if (!items.length) return [...e.dataTransfer.files].map(f => ({ file: f, rel: f.name }));
  const out = [];
  async function walk(entry, prefix) {
    if (entry.isFile) await new Promise(res => entry.file(f => { out.push({ file: f, rel: prefix + f.name }); res(); }, res));
    else if (entry.isDirectory) {
      const reader = entry.createReader();
      for (;;) {
        const batch = await new Promise(res => reader.readEntries(res, () => res([])));
        if (!batch.length) break;
        for (const c of batch) await walk(c, prefix + entry.name + '/');
      }
    }
  }
  for (const it of items) await walk(it, '');
  return out;
}

function wireDrop() {
  const pane = $('#fpane');
  let depth = 0;
  const external = e => [...e.dataTransfer.types].includes('Files') && ![...e.dataTransfer.types].includes('application/x-nido-files');
  pane.ondragenter = e => { if (external(e)) { depth++; pane.classList.add('drop'); e.preventDefault(); } };
  pane.ondragover = e => { if (external(e)) e.preventDefault(); };
  pane.ondragleave = () => { depth = Math.max(0, depth - 1); if (!depth) pane.classList.remove('drop'); };
  pane.ondrop = async e => {
    if (!external(e)) return;
    e.preventDefault(); depth = 0; pane.classList.remove('drop');
    if (FM.trash || FM.search) return toast('Apri prima una cartella', 'bad');
    queueUploads(await droppedFiles(e), FM.path);
  };
}

async function queueUploads(list, dir) {
  if (!list.length || !dir) return;
  // Nomi già presenti: stessa finestra di copia e spostamento
  const tops = [...new Set(list.map(it => it.rel.split('/')[0]))];
  let conf = [];
  try { conf = (await api('POST', '/files/conflicts', { dest: dir, names: tops })).conflicts; } catch (e) { return toast(e.message, 'bad'); }
  const action = {};
  if (conf.length) {
    for (const c of conf) {
      const it = list.find(x => x.rel.split('/')[0] === c.name);
      c.src_dir = it.rel.includes('/'); c.src_size = it.file.size; c.src_mtime = Math.round(it.file.lastModified / 1000);
    }
    const pol = await conflictDialog(conf, 'Carica');
    if (!pol) return;
    Object.assign(action, pol.names);
  }
  const existing = new Set(dir === FM.path ? FM.list.map(e => e.name) : []);
  const renamedDir = {};
  for (const it of list) {
    const top = it.rel.split('/')[0];
    const a = action[top];
    if (a === 'skip') continue;
    let rel = it.rel, conflict = a === 'overwrite' ? 'overwrite' : 'rename';
    if (a === 'rename' && rel.includes('/')) {
      // Cartella con lo stesso nome: la nuova diventa "Nome (2)"
      if (!renamedDir[top]) { let k = 2; while (existing.has(`${top} (${k})`)) k++; renamedDir[top] = `${top} (${k})`; existing.add(renamedDir[top]); }
      rel = renamedDir[top] + rel.slice(top.length);
    }
    FM.uploads.push({ ...it, rel, dir, sent: 0, state: 'wait', conflict });
  }
  drawUploads();
  if (!FM.uploading) runUploads();
}

// Un blocco del caricamento; restituisce i byte arrivati sul NAS
function putChunk(u, offset, blob) {
  return new Promise((res, rej) => {
    const x = new XMLHttpRequest();
    x.open('PUT', `/api/files/upload?dir=${encodeURIComponent(u.dir)}&name=${encodeURIComponent(u.rel)}&offset=${offset}&total=${u.file.size}&conflict=${u.conflict}`);
    x.setRequestHeader('X-Nido', '1');
    x.timeout = 10 * 60 * 1000;
    x.upload.onprogress = ev => { u.sent = offset + ev.loaded; drawUploads(); };
    x.onload = () => {
      let j = {}; try { j = JSON.parse(x.responseText); } catch (e) { /* */ }
      if (x.status === 200) res(j.done ? u.file.size : offset + blob.size);
      else if (x.status === 409 && j.received != null) res(j.received);         // riprende da lì
      else { const err = new Error(j.error || 'Errore ' + x.status); err.fatal = x.status >= 400 && x.status < 500 && x.status !== 408 && x.status !== 429; rej(err); }
    };
    x.onerror = x.ontimeout = () => rej(new Error('Connessione interrotta'));
    x.onabort = () => { const err = new Error('Annullato'); err.fatal = true; err.abort = true; rej(err); };
    u.xhr = x;
    x.send(blob);
  });
}

async function runUploads() {
  FM.uploading = true;
  let done = 0, failed = 0;
  while (FM.uploads.some(u => u.state === 'wait')) {
    const u = FM.uploads.find(x => x.state === 'wait');
    u.state = 'run';
    try {
      const total = u.file.size;
      let offset = 0, tries = 0;
      // Lo stesso file caricato a metà (connessione caduta, pagina chiusa): si riparte da lì
      if (total > CHUNK) {
        try { offset = (await api('GET', `/files/upload/status?dir=${encodeURIComponent(u.dir)}&name=${encodeURIComponent(u.rel)}&total=${total}`)).received || 0; } catch (e) { offset = 0; }
        if (offset >= total) offset = 0;
        if (offset) toast(`${u.rel}: riprendo il caricamento da ${bytes(offset)}`, 'info');
      }
      do {
        if (u.state === 'cancel') throw Object.assign(new Error('Annullato'), { abort: true });
        const blob = u.file.slice(offset, Math.min(offset + CHUNK, total));
        try {
          offset = await putChunk(u, offset, blob);
          u.sent = offset; tries = 0;
          if (u.state === 'retry') u.state = 'run';
        } catch (e) {
          if (e.fatal || u.state === 'cancel') throw e;
          // Connessione caduta: aspetto e riprendo dal punto arrivato al NAS
          tries++;
          if (tries > 40) throw new Error('Connessione persa troppo a lungo: ricarica il file per riprendere');
          u.state = 'retry'; drawUploads();
          await sleep(Math.min(30000, 1500 * 2 ** Math.min(tries, 5)));
          while (!navigator.onLine && u.state !== 'cancel') await sleep(2000);
          try { offset = (await api('GET', `/files/upload/status?dir=${encodeURIComponent(u.dir)}&name=${encodeURIComponent(u.rel)}&total=${total}`, undefined, { timeout: 15000 })).received || 0; } catch (x) { /* riprovo */ }
        }
      } while (offset < total);
      u.state = 'done'; done++;
    } catch (e) {
      const cancelled = e.abort || u.state === 'cancel';
      u.state = 'fail'; failed++;
      if (!cancelled) toast(`${u.rel}: ${e.message}`, 'bad', 7000);
    }
    drawUploads();
    if (u.dir === FM.path && !FM.search && !FM.trash && !FM.uploads.some(x => x.state === 'wait' && x.dir === FM.path)) openDir(FM.path, true);
  }
  FM.uploading = false;
  if (done) toast(`Caricat${done === 1 ? 'o 1 file' : `i ${done} file`}${failed ? ` · ${failed} non riuscit${failed === 1 ? 'o' : 'i'}` : ''}`);
  FM.uploads = [];
  drawUploads();
  loadPlaces();
}

function drawUploads() {
  const box = $('#uplbox');
  if (!box) return;
  const all = FM.uploads;
  if (!all.length) { box.innerHTML = ''; return; }
  const total = all.reduce((s, u) => s + u.file.size, 0) || 1;
  const sent = all.reduce((s, u) => s + (u.state === 'done' ? u.file.size : u.sent), 0);
  const pct = Math.floor(100 * sent / total);
  const waiting = all.some(u => u.state === 'retry');
  box.innerHTML = `${ic('upload')}<span>${waiting ? 'Connessione persa: riprendo appena torna…' : `Carico ${all.length} file · ${pct}%`}</span><div class="bar ${waiting ? 'warn' : ''}"><i style="width:${pct}%"></i></div><button class="btn sm ghost" id="upstop" title="Annulla">${ic('x')}</button>`;
  $('#upstop').onclick = () => { FM.uploads.forEach(u => { if (u.state === 'wait' || u.state === 'retry') u.state = 'cancel'; if (u.xhr && u.state === 'run') { u.state = 'cancel'; u.xhr.abort(); } }); };
}

/* --- cestino ----------------------------------------------------------------------- */

async function showTrash() {
  FM.trash = true; FM.sel.clear();
  drawTree(); drawToolbar(); drawClip();
  $('#fsel').hidden = true;
  $('#fstatus').innerHTML = '';
  showInfo(null);
  let r;
  try { r = await api('GET', '/files/trash'); } catch (e) { return toast(e.message, 'bad'); }
  const body = $('#fbody');
  if (!r.items.length) { body.innerHTML = `<div class="empty" style="flex:1">${ic('trash')}<div>Il cestino è vuoto</div></div>`; return; }
  body.innerHTML = `<div class="flist"><div class="frow head" style="grid-template-columns:28px 1fr 110px 190px"><span></span><span>Nome</span><span>Dimensione</span><span>Eliminato</span></div>` +
    r.items.map((t, i) => `<div class="frow" style="grid-template-columns:28px 1fr 110px 190px;cursor:default" data-i="${i}">${miniIcon({ name: t.name || '', dir: t.dir, kind: t.kind })}<span class="n">${esc(t.name)}<div class="muted mono" style="font-size:11px;overflow:hidden;text-overflow:ellipsis">${esc(t.orig)}</div></span><span class="m">${bytes(t.size)}</span>
      <span class="row" style="gap:6px"><span class="m">${ago(t.deleted)}</span><span class="grow"></span><button class="btn sm ghost" data-rs="${i}" title="Ripristina">${ic('undo')}</button><button class="btn sm ghost danger" data-rm="${i}" title="Elimina per sempre">${ic('x')}</button></span></div>`).join('') + '</div>';
  const restore = t => act(null, () => api('POST', '/files/trash/restore', { trash: t.trash, id: t.id }), `"${t.name}" ripristinato`).then(x => x && (showTrash(), loadPlaces()));
  const forever = async t => {
    if (!await ask('Elimina per sempre', `"${esc(t.name)}" verrà cancellato e non si potrà recuperare.`, 'Elimina', true)) return;
    act(null, () => api('POST', '/files/trash/empty', { trash: t.trash, id: t.id })).then(x => x && (showTrash(), loadPlaces()));
  };
  $$('[data-rs]', body).forEach(b => b.onclick = () => restore(r.items[+b.dataset.rs]));
  $$('[data-rm]', body).forEach(b => b.onclick = () => forever(r.items[+b.dataset.rm]));
  $$('.frow[data-i]', body).forEach(row => row.oncontextmenu = e => {
    e.preventDefault();
    const t = r.items[+row.dataset.i];
    ctxMenu(e, [{ label: 'Ripristina', icon: 'undo', fn: () => restore(t) }, { label: 'Elimina per sempre', icon: 'x', danger: true, fn: () => forever(t) }]);
  });
}

/* --- link di condivisione ------------------------------------------------------------- */

async function shareDialog(path) {
  const name = path.split('/').pop();
  const m = modal(`${mhead(`<div class="dicon">${ic('link')}</div>`, `Condividi "${esc(name)}"`, 'Chi ha il link può scaricare il file senza account')}
    <div class="mb">
      <div class="field"><label>Scade dopo</label><div class="seg" id="sdays"><button data-d="1">1 giorno</button><button data-d="7" class="on">7 giorni</button><button data-d="30">30 giorni</button><button data-d="0">Mai</button></div></div>
      <div class="linkbox"><input class="input" id="slink" readonly placeholder="Premi Crea link"><button class="btn" id="scopy" disabled>${ic('copy')}Copia</button></div>
      <div class="alert info">${ic('info')}<div>Il link funziona per chi raggiunge il NAS: nella rete di casa, o da fuori se hai configurato l'accesso remoto.</div></div>
    </div>
    <div class="mf"><button class="btn" data-close>Chiudi</button><button class="btn primary" id="sgo">${ic('link')}Crea link</button></div>`, 'sm');
  let days = 7;
  $$('[data-d]', m).forEach(b => b.onclick = () => { days = +b.dataset.d; $$('[data-d]', m).forEach(x => x.classList.toggle('on', x === b)); });
  $('#sgo', m).onclick = async e => {
    const r = await act(e.currentTarget, () => api('POST', '/files/share', { path, days }));
    if (!r) return;
    $('#slink', m).value = `${location.origin}/s/${r.token}`;
    $('#scopy', m).disabled = false;
    $('#slink', m).select();
  };
  $('#scopy', m).onclick = async () => {
    const v = $('#slink', m).value;
    try { await navigator.clipboard.writeText(v); toast('Link copiato'); } catch (e) { $('#slink', m).select(); document.execCommand && document.execCommand('copy'); toast('Link copiato'); }
  };
}

async function linksDialog() {
  let r;
  try { r = await api('GET', '/files/shares'); } catch (e) { return toast(e.message, 'bad'); }
  const m = modal(`${mhead(`<div class="dicon">${ic('link')}</div>`, 'Link condivisi', `${r.links.length} link attiv${r.links.length === 1 ? 'o' : 'i'}`)}
    <div class="mb"><div class="list">${r.links.map(l => `<div class="item"><div class="grow"><div class="t">${esc(l.name)}</div><div class="s">${l.expires ? 'scade ' + dateIt(l.expires) : 'senza scadenza'} · ${nf(l.downloads)} download</div></div>
      <button class="btn sm ghost" data-cp="${esc(l.token)}" title="Copia link">${ic('copy')}</button><button class="btn sm ghost danger" data-del="${esc(l.token)}" title="Disattiva">${ic('trash')}</button></div>`).join('') || '<div class="empty">Nessun link condiviso</div>'}</div></div>
    <div class="mf"><button class="btn" data-close>Chiudi</button></div>`, 'sm');
  $$('[data-cp]', m).forEach(b => b.onclick = async () => { try { await navigator.clipboard.writeText(`${location.origin}/s/${b.dataset.cp}`); toast('Link copiato'); } catch (e) { toast(`${location.origin}/s/${b.dataset.cp}`, 'info', 10000); } });
  $$('[data-del]', m).forEach(b => b.onclick = () => act(b, () => api('DELETE', '/files/share/' + b.dataset.del), 'Link disattivato').then(x => x && linksDialog()));
}

/* ==========================================================================
   Cartelle di rete (SMB, NFS, WebDAV)
   ========================================================================== */

function netItemMenu(anchor, id) {
  const n = FM.places.network.find(x => x.id === id);
  if (!n) return;
  if (n.cloud) {   // servizio cloud (Impostazioni > Servizi cloud)
    const name = id.slice(6);
    return popmenu(anchor, [
      n.mounted ? { label: 'Apri', icon: 'folder', fn: () => openDir(n.path) } : { label: 'Ricollega', icon: 'link', fn: () => act(null, () => api('POST', `/cloud/remotes/${name}/mount`, { enabled: true, autoboot: true }, { timeout: 180000 }), 'Cartella collegata').then(r => r && (loadPlaces(), openDir(n.path))) },
      n.mounted ? { label: 'Scollega', icon: 'x', fn: () => act(null, () => api('POST', `/cloud/remotes/${name}/mount`, { enabled: false }), 'Cartella scollegata').then(() => { loadPlaces(); if (FM.path && FM.path.startsWith(n.path)) openDir('/DATA'); }) } : null,
      { label: 'Servizi cloud…', icon: 'gear', fn: () => { location.hash = '#settings/cloud'; } },
    ].filter(Boolean));
  }
  popmenu(anchor, [
    n.mounted ? { label: 'Apri', icon: 'folder', fn: () => openDir(n.path) } : { label: 'Ricollega', icon: 'link', fn: () => act(null, () => api('POST', `/net/mounts/${id}/mount`), 'Cartella collegata').then(r => r && (loadPlaces(), openDir(n.path))) },
    n.mounted ? { label: 'Scollega', icon: 'x', fn: () => act(null, () => api('POST', `/net/mounts/${id}/unmount`), 'Cartella scollegata').then(() => { loadPlaces(); if (FM.path && FM.path.startsWith(n.path)) openDir('/DATA'); }) } : null,
    '-',
    { label: 'Rimuovi', icon: 'trash', danger: true, fn: async () => { if (await ask('Rimuovi cartella di rete', `"${esc(n.name)}" verrà scollegata e dimenticata (password compresa). I file sul computer remoto non vengono toccati.`, 'Rimuovi', true)) act(null, () => api('DELETE', '/net/mounts/' + id), 'Cartella rimossa').then(() => { loadPlaces(); if (FM.path && FM.path.startsWith(n.path)) openDir('/DATA'); }); } },
  ].filter(Boolean));
}

function netDialog() {
  const st = { proto: 'smb', host: '', share: '', hosts: null, shares: null, guest: false, autoboot: true, readonly: false };
  const m = modal(`${mhead(`<div class="dicon">${ic('globe')}</div>`, 'Collega una cartella di rete', 'Windows, Mac, altri NAS (SMB), NFS e WebDAV')}
    <div class="mb" id="nb"></div>
    <div class="mf"><span class="grow" id="nfoot"></span><button class="btn" id="ntest">Prova</button><button class="btn primary" id="ngo">${ic('link')}Collega</button></div>`);
  function addr() {
    if (st.proto === 'smb') return st.host && st.share ? `\\\\${st.host}\\${st.share}` : '';
    if (st.proto === 'nfs') return st.host && st.share ? `${st.host}:${st.share}` : '';
    return st.share;
  }
  function draw() {
    const hosts = st.hosts === null ? `<div class="row subtle"><span class="spin"></span>Cerco computer e NAS nella rete…</div>` :
      st.hosts.length ? `<div class="list hosts">${st.hosts.map((h, k) => `<div class="item ${st.host === h.ip || st.host === h.name ? 'on' : ''}" data-h="${k}"><div class="dicon" style="width:38px;height:38px">${ic(h.kinds.some(k2 => /nas|zima|synology|qnap/i.test(k2)) ? 'server' : 'server')}</div><div class="grow"><div class="t">${esc(h.name)}</div><div class="s">${esc([h.kinds[0], h.ip, h.protos.map(p => p.toUpperCase()).join(' ')].filter(Boolean).join(' · '))}</div></div>${st.host === h.ip || st.host === h.name ? '<span class="badge acc">selezionato</span>' : '<button class="btn sm">Scegli</button>'}</div>`).join('')}</div>`
        : `<div class="subtle">Nessun computer trovato automaticamente (alcuni PC Windows non si annunciano): scrivi l'indirizzo qui sotto.</div>`;
    const shares = st.shares ? `<div class="field"><label>Cartelle condivise su ${esc(st.host)}</label><div class="chips">${st.shares.map(s => `<button class="chip ${st.share === s.name ? 'on' : ''}" data-sh="${esc(s.name)}" title="${esc(s.comment)}">${ic('folder')}${esc(s.name)}</button>`).join('') || '<span class="subtle">Nessuna cartella visibile: prova con utente e password.</span>'}</div></div>` : '';
    $('#nb', m).innerHTML = `
      <div class="row"><div class="section-t" style="margin:0">Trovati nella rete</div><span class="grow"></span><button class="btn sm ghost" id="nscan">${ic('refresh')}Cerca di nuovo</button></div>
      ${hosts}
      <div class="cols2">
        <div class="field"><label>Indirizzo</label><input class="input mono" id="naddr" value="${esc(addr())}" placeholder="${st.proto === 'smb' ? '\\\\PC-STUDIO\\Condivisa' : st.proto === 'nfs' ? 'nas.local:/export/dati' : 'https://cloud.example.com/remote.php/dav/files/me/'}"><span class="hint">${st.proto === 'smb' ? 'Anche smb://192.168.1.20/Condivisa' : st.proto === 'nfs' ? 'computer:/cartella' : 'Indirizzo WebDAV completo'}</span></div>
        <div class="field"><label>Protocollo</label><div class="seg">${['smb', 'nfs', 'webdav'].map(p => `<button data-p="${p}" class="${st.proto === p ? 'on' : ''}">${p === 'webdav' ? 'WebDAV' : p.toUpperCase()}</button>`).join('')}</div></div>
        ${st.proto !== 'nfs' ? `<div class="field"><label>Utente</label><input class="input" id="nuser" value="${esc(st.user || '')}" autocomplete="off" ${st.guest ? 'disabled' : ''}></div>
        <div class="field"><label>Password</label><input class="input" type="password" id="npass" value="${esc(st.pass || '')}" autocomplete="new-password" ${st.guest ? 'disabled' : ''}></div>` : ''}
      </div>
      ${shares}
      <div class="row" style="gap:20px;flex-wrap:wrap">
        <label class="row" style="cursor:pointer"><button class="toggle ${st.autoboot ? 'on' : ''}" data-t="autoboot"></button>Ricollega all'avvio</label>
        ${st.proto === 'smb' ? `<label class="row" style="cursor:pointer"><button class="toggle ${st.guest ? 'on' : ''}" data-t="guest"></button>Accesso ospite</label>` : ''}
        <label class="row" style="cursor:pointer"><button class="toggle ${st.readonly ? 'on' : ''}" data-t="readonly"></button>Sola lettura</label>
      </div>
      <div class="alert info">${ic('lock')}<div>La password viene salvata cifrata sul NAS e non compare mai nei log.</div></div>`;
    $('#nscan', m).onclick = scan;
    $$('[data-h]', m).forEach(x => x.onclick = () => { readForm(); const h = st.hosts[+x.dataset.h]; st.host = h.name.includes('.') || /^[\d.]+$/.test(h.name) ? h.name : h.ip; st.share = ''; if (h.protos.includes('nfs') && !h.protos.includes('smb')) st.proto = 'nfs'; draw(); loadShares(); });
    $$('[data-sh]', m).forEach(x => x.onclick = () => { readForm(); st.share = x.dataset.sh; draw(); });
    $$('[data-p]', m).forEach(x => x.onclick = () => { readForm(); st.proto = x.dataset.p; st.shares = null; draw(); });
    $$('[data-t]', m).forEach(x => x.onclick = () => { readForm(); st[x.dataset.t] = !st[x.dataset.t]; draw(); });
    $('#naddr', m).onchange = () => { readForm(); parseAddr(); };
    foot();
  }
  function readForm() {
    const u = $('#nuser', m), p = $('#npass', m), a = $('#naddr', m);
    if (u) st.user = u.value; if (p) st.pass = p.value;
    if (a && a.value.trim() !== addr()) { st.address = a.value.trim(); parseAddr(); }
  }
  function parseAddr() {
    const v = (st.address || '').trim();
    let x;
    if (st.proto === 'smb' && (x = v.match(/^(?:\\\\|\/\/|smb:\/\/)([^\\/]+)[\\/](.+)$/i))) { st.host = x[1]; st.share = x[2].replace(/\\/g, '/'); }
    else if (st.proto === 'nfs' && (x = v.match(/^(?:nfs:\/\/)?([^:/]+):?(\/.*)$/i))) { st.host = x[1]; st.share = x[2]; }
    else if (st.proto === 'webdav') { st.share = v; x = v.match(/^https?:\/\/([^/:]+)/i); st.host = x ? x[1] : ''; }
    foot();
  }
  function foot() {
    const leaf = st.host && st.share ? `${st.host.split('.')[0]}-${st.share.replace(/^\/+|\/+$/g, '').replace(/\//g, '-')}`.replace(/[^A-Za-z0-9._-]+/g, '-') : '';
    $('#nfoot', m).innerHTML = leaf ? `Sarà in <code class="k">/media/rete/${esc(leaf.slice(0, 60))}</code>` : '';
  }
  async function scan() {
    st.hosts = null; draw();
    try { st.hosts = (await api('GET', '/net/discover')).hosts; } catch (e) { st.hosts = []; toast(e.message, 'bad'); }
    if (m.isConnected) draw();
  }
  async function loadShares() {
    if (!st.host || st.proto === 'webdav') return;
    try {
      const r = await api('POST', '/net/shares', { proto: st.proto, host: st.host, user: st.guest ? '' : st.user || '', password: st.guest ? '' : st.pass || '' });
      st.shares = r.shares;
      if (st.shares.length === 1 && !st.share) st.share = st.shares[0].name;
    } catch (e) { st.shares = []; if (e.status !== 401) toast(e.message, 'bad'); else toast('Per vedere le cartelle servono utente e password del computer remoto', 'info'); }
    if (m.isConnected) draw();
  }
  const body = () => { readForm(); return { proto: st.proto, address: $('#naddr', m).value.trim(), user: st.guest ? '' : st.user, password: st.guest ? '' : st.pass, guest: st.guest, autoboot: st.autoboot, readonly: st.readonly }; };
  $('#ntest', m).onclick = e => act(e.currentTarget, () => api('POST', '/net/test', body()), r => `Collegamento riuscito: ${r.items} elementi trovati`);
  $('#ngo', m).onclick = async e => {
    const r = await act(e.currentTarget, () => api('POST', '/net/mounts', body()), 'Cartella di rete collegata');
    if (r) { closeModal(); await loadPlaces(); openDir(r.mountpoint); }
  };
  draw();
  scan();
}

ROUTES.files = pageFiles;
