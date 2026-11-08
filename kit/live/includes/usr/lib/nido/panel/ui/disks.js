// Interfaccia del NAS — Dischi: salute, formattazione, montaggio, standby, spazio delle app
// Licenza GPL-3.0.
'use strict';

const FS_INFO = {
  ext4: ['Il più affidabile per Linux. Ideale per dati e app.', 'Consigliato', 'acc'],
  btrfs: ['Snapshot, compressione e controllo degli errori.', 'Per dati importanti', ''],
  exfat: ['Leggibile da Windows, Mac, TV e console.', 'Per USB', ''],
  ntfs: ['Formato di Windows, per dischi da scambiare con un PC.', 'Per Windows', ''],
  vfat: ['Compatibile con tutto, ma file al massimo di 4 GB.', 'Vecchi dispositivi', ''],
  xfs: ['Veloce con file molto grandi (video).', 'Avanzato', ''],
};
const STANDBY_TIMES = [[0, 'Mai'], [5, '5 min'], [10, '10 min'], [20, '20 min'], [30, '30 min'], [60, '1 ora'], [120, '2 ore'], [240, '4 ore']];
const PART_COLORS = ['#14b8a6', '#0ea5e9', '#f59e0b', '#8b5cf6', '#ec4899', '#22c55e'];
const APM_LABELS = [['', 'Non cambiare'], ['performance', 'Prestazioni'], ['balanced', 'Bilanciato'], ['saving', 'Risparmio']];

const minutesText = m => !m ? 'Mai' : m < 60 ? `${m} minuti` : m % 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m / 60} ${m === 60 ? 'ora' : 'ore'}`;
const healthBadge = d => ({
  buono: '<span class="badge ok"><span class="d"></span>Buono</span>',
  attenzione: '<span class="badge warn"><span class="d"></span>Da tenere d\'occhio</span>',
  guasto: '<span class="badge bad"><span class="d"></span>Guasto</span>',
  'in riposo': '<span class="badge acc">In standby</span>',
}[d.health] || (d.tran === 'usb' ? '<span class="badge acc">USB</span>' : d.tran === 'loop' ? '<span class="badge">Prova</span>' : '<span class="badge">Salute sconosciuta</span>'));

function diskKind(d) {
  if (d.tran === 'loop') return 'disco di prova';
  return [d.tran === 'usb' ? 'USB' : d.tran === 'nvme' ? 'NVMe' : d.tran ? d.tran.toUpperCase() : '', d.ssd ? 'SSD' : 'HDD'].filter(Boolean).join(' ');
}

let DK = null;   // ultimo elenco dei dischi

async function pageDisks() {
  let d;
  try { d = await api('GET', '/disks'); } catch (e) { return pageError(e); }
  DK = d;
  const total = d.disks.reduce((s, x) => s + (x.size || 0), 0);
  const toMount = d.disks.filter(x => !x.protected).flatMap(x => x.partitions.filter(p => !p.mounts.length && p.mountable));
  const sleeping = d.disks.filter(x => x.standby.state === 'standby').length;
  const warn = d.disks.filter(x => ['attenzione', 'guasto'].includes(x.health)).length;
  const sub = [`${d.disks.length} dischi`, bytes(total), toMount.length ? `${toMount.length} da montare` : '', sleeping ? `${sleeping} in standby` : '',
    warn ? `${warn} da controllare` : ''].filter(Boolean).join(' · ');

  const cards = d.disks.map(diskCard).join('');
  const blank = d.disks.filter(x => !x.protected && x.empty);
  const mountRows = d.disks.filter(x => !x.protected && (x.partitions.some(p => !p.mounts.length) || x.empty)).map(x => {
    const ps = x.partitions.filter(p => !p.mounts.length);
    return `<div class="item"><div class="dicon" style="width:40px;height:40px">${ic(x.tran === 'usb' ? 'usb' : 'disk')}</div>
      <div class="grow"><div class="t">${esc(x.display)}</div><div class="s">${x.empty ? 'Disco vuoto: va formattato prima di usarlo' : `${ps.length} ${ps.length === 1 ? 'partizione' : 'partizioni'} non montat${ps.length === 1 ? 'a' : 'e'}`} · ${bytes(x.size)} · ${esc(diskKind(x))}</div></div>
      ${x.empty ? `<button class="btn sm primary" data-fmt="${esc(x.path)}">${ic('disk')}Formatta</button>` : '<span class="badge">Non montato</span>'}</div>` +
      ps.map(p => `<div class="item" style="padding-left:52px"><div class="grow"><div class="t" style="font-weight:550">${esc(p.label || p.name)} ${p.fsname ? `<span class="badge" style="margin-left:4px">${esc(p.fsname)}</span>` : ''}</div>
        <div class="s">${bytes(p.size)}${p.parttype ? ' · ' + esc(p.parttype) : ''}${!p.fstype ? ' · non formattata' : ''}</div></div>
        ${p.mountable ? `<button class="btn sm primary" data-mount="${esc(p.path)}">${ic('link')}Monta</button>` : `<button class="btn sm" data-fmt="${esc(p.path)}">Formatta</button>`}</div>`).join('');
  }).join('');

  const sbRows = d.disks.map(x => {
    const s = x.standby;
    const st = x.protected ? 'non serve' : s.state === 'standby' ? `in standby${s.since ? ' da ' + ago(s.since).replace(' fa', '') : ''}` : s.state === 'active' ? 'attivo' : 'stato sconosciuto';
    const opts = STANDBY_TIMES.map(([m, t]) => `<option value="${m}" ${s.minutes === m ? 'selected' : ''}>${t}</option>`).join('') +
      (STANDBY_TIMES.some(([m]) => m === s.minutes) ? '' : `<option value="${s.minutes}" selected>${minutesText(s.minutes)}</option>`) + '<option value="custom">Personalizzato…</option>';
    return `<div class="item ${x.protected ? '' : 'clickable'}" ${x.protected ? '' : `data-sb="${esc(x.id)}"`}><div class="grow"><div class="t">${esc(x.display)} ${s.state === 'standby' ? '<span class="badge acc" style="margin-left:4px">in standby</span>' : ''}</div>
      <div class="s">${x.ssd ? 'SSD' : 'HDD'} · ${st}${s.spinups_today ? ` · ${s.spinups_today} accension${s.spinups_today === 1 ? 'e' : 'i'} oggi` : ''}${s.error ? ' · <span style="color:var(--warn)">' + esc(s.error) + '</span>' : ''}</div></div>
      <select class="input sm" style="width:150px" data-sbsel="${esc(x.id)}" ${x.protected ? 'disabled' : ''}>${x.protected ? '<option>Mai</option>' : opts}</select></div>`;
  }).join('');

  $('#root').innerHTML = shell('disks', 'Dischi', esc(sub), `
    ${d.disks.some(x => x.health === 'guasto') ? `<div class="alert bad" style="margin-bottom:16px">${ic('alert')}<div><b>Un disco segnala un guasto.</b> Copia subito i dati importanti su un altro disco e sostituiscilo.</div></div>` : ''}
    <div class="disks">${cards}</div>
    <div class="grid two-col" style="grid-template-columns:1fr 1fr;margin-top:16px;align-items:start">
      <div class="card"><h3>${ic('disk')}Dischi da montare ${toMount.length + blank.length ? `<span class="badge warn">${toMount.length + blank.length}</span>` : ''}</h3>
        ${mountRows ? `<div class="list">${mountRows}</div>
        <div class="alert info" style="margin-top:12px">${ic('info')}<div>I dati restano dove sono: montare non cancella niente. Se vuoi un formato diverso usa "Formatta".</div></div>`
        : `<div class="empty" style="padding:24px">${ic('check')}<div>Tutti i dischi sono montati.<br>Collega un disco e comparirà qui.</div></div>`}
      </div>
      <div class="card"><h3>${ic('moon')}Standby dei dischi <span class="more">${d.standby_service ? '' : '<span style="color:var(--warn)">servizio non attivo</span>'}</span></h3>
        <div class="list">${sbRows}</div>
        <div class="list"><div class="item clickable" id="sbsched" style="border-top:1px solid var(--line)"><div class="dicon" style="width:40px;height:40px">${ic('clock')}</div>
          <div class="grow"><div class="t">Programma settimanale ${d.schedule.enabled ? '<span class="badge ok" style="margin-left:4px">attivo</span>' : '<span class="badge" style="margin-left:4px">spento</span>'}</div>
          <div class="s">${esc(schedSummary(d.schedule, d.schedule_now))}</div></div>${ic('chevron')}</div></div>
        <div class="subtle" style="margin-top:10px">Un disco in standby si riaccende da solo quando serve (qualche secondo di attesa). Tocca un disco per le altre opzioni.</div>
      </div>
    </div>
    <div class="card" style="margin-top:16px" id="dockspace"><h3>${ic('container')}Spazio delle app <span class="more" id="dsload">calcolo…</span></h3><div id="dsbody" class="subtle">Immagini e dati delle app installate.</div></div>
    <div class="card" style="margin-top:16px" id="apploc"><h3>${ic('move')}Dove stanno le app <span class="more" id="alload">controllo…</span></h3><div id="albody" class="subtle"></div></div>`);
  wireShell();

  $$('[data-dmenu]').forEach(b => b.onclick = e => { e.stopPropagation(); diskMenu(b, d.disks.find(x => x.path === b.dataset.dmenu)); });
  $$('[data-fmt]').forEach(b => b.onclick = () => formatDialog(b.dataset.fmt));
  $$('[data-mount]').forEach(b => b.onclick = () => mountDialog(b.dataset.mount));
  $$('[data-smart]').forEach(b => b.onclick = () => smartDialog(b.dataset.smart));
  $('#sbsched').onclick = () => scheduleDialog();
  $$('[data-sb]').forEach(r => r.onclick = e => { if (!e.target.closest('select')) standbyDialog(r.dataset.sb); });
  $$('[data-sbsel]').forEach(s => s.onchange = async () => {
    const x = d.disks.find(k => k.id === s.dataset.sbsel);
    if (s.value === 'custom') { standbyDialog(x.id, true); return; }
    const r = await act(null, () => api('POST', '/disks/standby', { id: x.id, minutes: +s.value, backup_window: x.standby.backup_window, apm: x.standby.apm, schedule: x.standby.schedule }),
      `${x.display}: standby ${+s.value ? 'dopo ' + minutesText(+s.value) : 'disattivato'}`);
    if (r) x.standby.minutes = +s.value;
  });
  dockerSpace();
  appLocation();
  // Aggiorna da solo (stato dello standby, dischi collegati) se non ci sono finestre aperte
  every('disks', 30000, async () => { if (!$('#scrim') && !$('.menu') && !$('#allog')) { const y = window.scrollY; await pageDisks(); window.scrollTo(0, y); } });
}

function diskCard(d) {
  const used = d.root ? d.root.used : d.partitions.reduce((s, p) => s + (+p.fsused || 0), 0);
  const parts = d.partitions.length ? d.partitions.map((p, i) => {
    const c = d.protected ? (p.mounts.length ? '#6366f1' : '#94a3b8') : PART_COLORS[i % PART_COLORS.length];
    const pct = p.fssize ? Math.round(100 * p.fsused / p.fssize) : p.mounts.length ? 0 : 100;
    const bg = p.mounts.length ? `linear-gradient(90deg,${c} ${pct}%,color-mix(in srgb,${c} 28%,transparent) ${pct}%)` : `repeating-linear-gradient(135deg,color-mix(in srgb,${c} 55%,transparent) 0 6px,color-mix(in srgb,${c} 35%,transparent) 6px 12px)`;
    return `<div style="flex:${Math.max(0.06, (p.size || 1) / (d.size || 1))};background:${bg}" title="${esc(p.path)}${p.mounts[0] ? ' → ' + esc(p.mounts[0]) : ' · non montata'}">${esc([p.fsname, p.label].filter(Boolean).join(' · ') || 'vuota')}</div>`;
  }).join('') : '<div style="flex:1;background:var(--sunken);color:var(--ink-3)">nessuna partizione</div>';
  const mounted = d.partitions.filter(p => p.mounts.length);
  const subline = d.protected ? [(mounted.find(p => p.mounts.includes('/')) || mounted.find(p => p.fsname && !/fat/i.test(p.fsname)) || {}).fsname, 'sistema, Docker e app', `${bytes(used)} usati${d.root ? ' su ' + bytes(d.root.size) : ''}`].filter(Boolean).join(' · ')
    : mounted.length ? mounted.map(p => `${esc(p.fsname)} · ${bytes(p.fsused)} usati · <a href="#files" data-open="${esc(p.mounts[0])}" class="mono" style="color:inherit">${esc(p.mounts[0])}</a>`).join('<br>')
      : d.empty ? 'Disco vuoto, da formattare' : 'Non montato';
  const s = d.smart || {};
  const cells = s.available && !(s.standby && s.passed === undefined) ? [
    ['Salute', s.life != null ? s.life + '%' : s.passed === false ? 'Guasto' : 'Buona'],
    ['Temp.', s.temperature != null ? s.temperature + ' °C' : '—'],
    ['Ore', s.power_on_hours != null ? nf(s.power_on_hours) : '—'],
    ['Settori ko', s.bad_sectors != null ? nf(s.bad_sectors) : '—'],
  ] : [['Salute', s.standby ? 'in standby' : '—'], ['Formato', d.partitions.map(p => p.fsname).filter(Boolean).join(', ') || '—'],
    ['Usato', used ? bytes(used) : '—'], ['Standby', minutesText(d.standby.minutes)]];
  return `<div class="card dcard">
    <div class="head"><div class="dicon" style="${d.protected ? 'background:color-mix(in srgb,#6366f1 14%,transparent);color:#6366f1' : 'background:color-mix(in srgb,#14b8a6 14%,transparent);color:#0d9488'}">${ic(d.tran === 'usb' ? 'usb' : d.protected ? 'server' : 'disk')}</div>
      <div style="flex:1;min-width:0"><b>${esc(d.display)}</b><div class="muted" style="font-size:12.5px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(d.model || d.name)} · ${bytes(d.size)} · ${esc(diskKind(d))} · <span class="mono">${esc(d.path)}</span></div></div>
      ${healthBadge(d)}<button class="btn sm ghost" data-dmenu="${esc(d.path)}" title="Azioni">${ic('more')}</button></div>
    <div class="parts">${parts}</div>
    <div class="muted" style="font-size:12.5px">${subline}</div>
    <div class="smart ${s.available ? 'clickable' : ''}" ${s.available ? `data-smart="${esc(d.path)}" title="Dettagli SMART"` : ''}>${cells.map(([k, v]) => `<div><small>${k}</small><b>${esc(v)}</b></div>`).join('')}</div>
    ${s.test_running != null ? `<div class="row" style="margin-top:10px;font-size:12.5px"><span class="spin"></span>Test SMART in corso: ${s.test_running}%</div>` : ''}
  </div>`;
}

function diskMenu(btn, d) {
  const items = [];
  if (d.smart && d.smart.available) items.push({ label: 'Salute del disco (SMART)', icon: 'shield', fn: () => smartDialog(d.path) });
  if (!d.protected) {
    for (const p of d.partitions) {
      const n = p.label || p.name;
      if (p.mounts.length) {
        items.push({ label: `Apri "${n}" nei file`, icon: 'folder', fn: () => { store.set('filesPath', p.mounts[0]); go('files'); } });
        items.push({ label: `Smonta "${n}"`, icon: 'x', fn: () => unmountPart(p) });
      } else if (p.mountable) items.push({ label: `Monta "${n}"`, icon: 'link', fn: () => mountDialog(p.path) });
    }
    items.push({ label: 'Standby', icon: 'moon', fn: () => standbyDialog(d.id) });
    if (!d.ssd || d.tran === 'loop') items.push({ label: 'Spegni adesso', icon: 'moon', fn: () => act(null, () => api('POST', '/disks/sleep', { disk: d.path }), `${d.display} in standby`).then(r => r && pageDisks()) });
    items.push('-');
    if (d.partitions.length > 1) d.partitions.forEach(p => items.push({ label: `Formatta solo "${p.label || p.name}"`, icon: 'disk', danger: true, fn: () => formatDialog(p.path) }));
    items.push({ label: 'Formatta tutto il disco', icon: 'trash', danger: true, fn: () => formatDialog(d.path) });
  } else items.push({ label: 'Il disco di sistema non si modifica da qui', icon: 'lock', disabled: true, fn: () => {} });
  popmenu(btn, items);
}

async function unmountPart(p) {
  if (!await ask('Smonta il disco', `<b>${esc(p.label || p.name)}</b> non sarà più visibile in <span class="mono">${esc(p.mounts[0])}</span> e non verrà più montato all'avvio. I dati restano sul disco.<br><br>Le app e le condivisioni che lo usano non lo troveranno più.`, 'Smonta')) return;
  const r = await act(null, () => api('POST', '/disks/unmount', { device: p.path }), 'Disco smontato: ora puoi scollegarlo');
  if (r) pageDisks();
}

function findDev(path) {
  for (const d of DK.disks) {
    if (d.path === path) return [d, null];
    const p = d.partitions.find(x => x.path === path);
    if (p) return [d, p];
  }
  return [null, null];
}

/* --- formattazione ------------------------------------------------------------------------ */

function formatDialog(path) {
  const [d, p] = findDev(path);
  if (!d) return;
  const whole = !p || p.whole;
  const target = p && !p.whole ? p : null;
  const expected = target ? (target.label || target.name) : d.display;
  const used = (target ? [target] : d.partitions).reduce((s, x) => s + (+x.fsused || 0), 0);
  let fs = d.tran === 'usb' ? 'exfat' : 'ext4';
  const m = modal(`${mhead(`<div class="dicon">${ic(d.tran === 'usb' ? 'usb' : 'disk')}</div>`, `Formatta "${esc(expected)}"`, `${esc(d.model || d.name)} · ${bytes(target ? target.size : d.size)} · ${esc(path)}`)}
    <div class="mb">
      <div class="alert bad">${ic('alert')}<div><b>Tutti i dati ${target ? 'della partizione' : 'del disco'} verranno cancellati</b>${used ? ` (${bytes(used)} usati)` : ''}. Se ti servono, copiali prima dal file manager.${whole && !target ? ' Verrà creata una sola partizione su tutto il disco.' : ''}</div></div>
      <div class="section-t">Formato</div>
      <div class="fsopts">${Object.entries(DK.formats).map(([k, n]) => `<div class="fsopt ${k === fs ? 'on' : ''}" data-fs="${k}"><b>${esc(n)}</b><span>${FS_INFO[k][0]}</span>${FS_INFO[k][1] ? `<span class="badge ${FS_INFO[k][2]} tag">${FS_INFO[k][1]}</span>` : ''}</div>`).join('')}</div>
      <div class="cols2">
        <div class="field"><label>Nome del disco</label><input class="input" id="flabel" value="${esc((p && p.label) || (d.display.startsWith('Disco di prova') ? 'Dati' : d.display) || 'Dati')}" maxlength="32"><span class="hint" id="fhint"></span></div>
        <div class="field"><label>Dopo la formattazione</label>
          <label class="row" style="height:38px;font-size:13px;cursor:pointer"><button type="button" class="toggle on" id="fauto"></button>Monta e tieni montato a ogni avvio</label></div>
      </div>
      <div class="field"><label>Per confermare scrivi <code class="k">${esc(expected)}</code></label><input class="input" id="fconf" placeholder="${esc(expected)}" autocomplete="off" spellcheck="false"></div>
      <div id="fprog" hidden class="progress-big"><div class="row" style="font-size:13px"><span id="fstep">Preparo…</span><span class="grow"></span><span class="muted" id="fpct">0%</span></div><div class="bar"><i id="fbar" style="width:0%"></i></div></div>
    </div>
    <div class="mf"><span class="grow">Formattazione veloce · di solito meno di un minuto</span><button class="btn" data-close>Annulla</button><button class="btn danger solid" id="fgo" disabled>Formatta</button></div>`);
  const hint = () => {
    const max = { ext4: 16, btrfs: 255, exfat: 15, ntfs: 32, vfat: 11, xfs: 12 }[fs];
    let v = $('#flabel', m).value.replace(/[^A-Za-z0-9 _-]/g, '').slice(0, max);
    if (fs === 'vfat') v = v.toUpperCase();
    $('#fhint', m).textContent = `Sarà montato in /media/${v.trim() || 'Dati'} · massimo ${max} caratteri`;
  };
  hint();
  $$('[data-fs]', m).forEach(o => o.onclick = () => { fs = o.dataset.fs; $$('[data-fs]', m).forEach(x => x.classList.toggle('on', x === o)); hint(); });
  $('#flabel', m).oninput = hint;
  $('#fauto', m).onclick = e => e.currentTarget.classList.toggle('on');
  $('#fconf', m).oninput = e => { $('#fgo', m).disabled = e.target.value.trim() !== expected; };
  $('#fgo', m).onclick = async e => {
    const btn = e.currentTarget;
    const r = await act(btn, () => api('POST', '/disks/format', { device: path, fs, label: $('#flabel', m).value, confirm: $('#fconf', m).value.trim(), auto: $('#fauto', m).classList.contains('on') }));
    if (!r) return;
    btn.disabled = true;
    $('#scrim').dataset.lock = '1';
    $('#fprog', m).hidden = false;
    try {
      const j = await followJob(r.job, j => { $('#fstep', m).textContent = j.step || 'Formatto…'; $('#fpct', m).textContent = j.progress + '%'; $('#fbar', m).style.width = j.progress + '%'; });
      delete $('#scrim').dataset.lock;
      if (j.state === 'done') { closeModal(); toast(`Disco pronto in ${j.result.mountpoint}`); }
      else { toast(j.error || 'Formattazione non riuscita', 'bad', 9000); closeModal(); }
    } finally { pageDisks(); }
  };
}

/* --- montaggio ------------------------------------------------------------------------------ */

function mountDialog(path) {
  const [d, p] = findDev(path);
  if (!d || !p) return;
  const ntfs = p.fstype === 'ntfs' || p.fstype === 'ntfs3';
  let ro = false;
  const name0 = p.label || (d.display.startsWith('Disco di prova') ? 'Disco' : d.display) || 'Disco';
  const m = modal(`${mhead(`<div class="dicon">${ic(d.tran === 'usb' ? 'usb' : 'disk')}</div>`, `Monta "${esc(p.label || p.name)}"`, `${esc(d.model || d.name)} · ${esc(p.fsname || '?')} · ${bytes(p.size)}`)}
    <div class="mb">
      <div class="cols2">
        <div class="field"><label>Nome nel NAS</label><input class="input" id="mname" value="${esc(name0)}" maxlength="40"><span class="hint">Così lo vedi nel file manager e nelle app</span></div>
        <div class="field"><label>Cartella</label><input class="input mono" id="mdir" readonly tabindex="-1"></div>
      </div>
      <div class="section-t">Come usarlo</div>
      <div class="grid" style="gap:10px">
        <div class="opt on" data-ro="0"><span class="radio"></span><div><b>Lettura e scrittura</b><span>Puoi aggiungere, modificare e cancellare file.</span></div></div>
        <div class="opt" data-ro="1"><span class="radio"></span><div><b>Solo lettura</b><span>Sicuro per dischi che arrivano da un altro PC: nessuna modifica possibile.</span></div></div>
      </div>
      <div class="list">
        <div class="item"><div class="grow"><div class="t">Monta a ogni avvio</div><div class="s">Il disco resta collegato anche dopo un riavvio</div></div><button class="toggle on" id="mauto"></button></div>
        <div class="item"><div class="grow"><div class="t">Condividi in rete</div><div class="s" id="mshare">Visibile da Windows e Mac per tutti gli utenti del NAS</div></div><button class="toggle" id="mshr"></button></div>
      </div>
      ${ntfs ? `<div class="alert info">${ic('info')}<div>Se Windows ha chiuso male il disco (spegnimento brusco o "avvio rapido"), ${esc(S.about.name)} lo sistema da solo prima di montarlo, senza toccare i tuoi file.</div></div>` : ''}
    </div>
    <div class="mf"><span class="grow">Nessun dato verrà cancellato</span><button class="btn" data-close>Annulla</button><button class="btn primary" id="mgo">${ic('link')}Monta</button></div>`);
  const upd = () => {
    const n = $('#mname', m).value.replace(/[^A-Za-z0-9 ._-]+/g, '').trim() || 'Disco';
    $('#mdir', m).value = '/media/' + n;
    $('#mshare', m).textContent = `Visibile da Windows e Mac come \\\\${S.about.hostname || 'nas'}\\${n}`;
  };
  upd();
  $('#mname', m).oninput = upd;
  $$('[data-ro]', m).forEach(o => o.onclick = () => { ro = o.dataset.ro === '1'; $$('[data-ro]', m).forEach(x => x.classList.toggle('on', x === o)); });
  $$('.toggle', m).forEach(t => t.onclick = () => t.classList.toggle('on'));
  $('#mgo', m).onclick = e => act(e.currentTarget, () => api('POST', '/disks/mount', {
    device: path, name: $('#mname', m).value, readonly: ro, auto: $('#mauto', m).classList.contains('on'), share: $('#mshr', m).classList.contains('on'),
  })).then(r => {
    if (!r) return;
    closeModal();
    toast(`Montato in ${r.mountpoint}${r.readonly ? ' (sola lettura)' : ''}`);
    (r.notes || []).forEach(n => toast(n, 'info', 8000));
    pageDisks();
  });
}

/* --- standby -------------------------------------------------------------------------------- */

const DAY_SHORT = ['L', 'M', 'M', 'G', 'V', 'S', 'D'];
const DAY_NAMES = ['lun', 'mar', 'mer', 'gio', 'ven', 'sab', 'dom'];

function daysText(days) {
  const k = days.join(',');
  if (k === '0,1,2,3,4,5,6') return 'tutti i giorni';
  if (k === '0,1,2,3,4') return 'lun–ven';
  if (k === '5,6') return 'sab e dom';
  return days.map(x => DAY_NAMES[x]).join(', ');
}

function schedSummary(sc, now) {
  if (!sc.enabled) return 'Giorni e orari in cui i dischi vanno in standby o restano sempre accesi';
  const cur = now && now.mode ? (now.mode === 'on' ? 'Adesso sempre accesi' : 'Adesso fascia di standby') + (now.until ? ' ' + now.until : '') + ' · ' : '';
  return cur + sc.rules.map(r => `${r.mode === 'on' ? 'accesi' : 'standby'} ${daysText(r.days)} ${r.from}–${r.to}`).join(' · ');
}

function scheduleDialog() {
  const sc = JSON.parse(JSON.stringify(DK.schedule));
  if (!sc.rules.length) sc.rules = [{ mode: 'standby', days: [0, 1, 2, 3, 4, 5, 6], from: '01:00', to: '07:00' }];
  const row = (r, k) => `<div class="card" style="padding:12px;margin:0 0 10px" data-rule="${k}">
      <div class="row" style="gap:8px;flex-wrap:wrap;align-items:center">
        <select class="input sm" data-f="mode" style="width:170px"><option value="standby" ${r.mode === 'standby' ? 'selected' : ''}>Standby</option><option value="on" ${r.mode === 'on' ? 'selected' : ''}>Sempre accesi</option></select>
        <span class="subtle">dalle</span><input class="input sm" type="time" data-f="from" value="${esc(r.from)}" style="width:104px">
        <span class="subtle">alle</span><input class="input sm" type="time" data-f="to" value="${esc(r.to)}" style="width:104px">
        <span class="grow"></span><button class="iconbtn" data-del title="Togli la fascia">${ic('trash')}</button></div>
      <div class="chips" style="margin-top:10px">${DAY_SHORT.map((t, i) => `<span class="chip ${r.days.includes(i) ? 'on' : ''}" data-day="${i}" title="${DAY_NAMES[i]}" style="width:36px;justify-content:center;padding:0">${t}</span>`).join('')}</div></div>`;
  const m = modal(`${mhead(`<div class="dicon">${ic('clock')}</div>`, 'Programma settimanale dello standby', 'Uguale per tutti i dischi che lo seguono (il disco di sistema resta sempre acceso)')}
    <div class="mb">
      <div class="list"><div class="item"><div class="grow"><div class="t">Usa il programma</div><div class="s">Fuori dalle fasce vale il tempo scelto per ogni disco</div></div><button class="toggle ${sc.enabled ? 'on' : ''}" id="scen"></button></div></div>
      <div id="scrules" style="margin-top:12px"></div>
      <button class="btn sm" id="scadd">${ic('plus')}Aggiungi una fascia</button>
      <div class="field" style="margin-top:14px"><label>Nelle fasce di standby, spegni dopo</label><div class="row" style="gap:8px;align-items:center"><input class="input" type="number" min="1" max="120" id="scidle" value="${sc.idle}" style="max-width:110px"><span class="subtle">minuti senza attività</span></div>
        <span class="hint">Se in una fascia di standby un disco viene usato si riaccende, poi torna in standby dopo questi minuti.</span></div>
      <div class="alert info">${ic('info')}<div><b>Standby</b>: i dischi si spengono anche se il loro tempo è "Mai". <b>Sempre accesi</b>: non vanno mai in standby. Se due fasce si sovrappongono vince "Sempre accesi". Un orario come 23:00–07:00 passa la mezzanotte; la stessa ora di inizio e fine vuol dire tutto il giorno. L'orario dei backup resta valido.</div></div>
    </div>
    <div class="mf"><span class="grow"></span><button class="btn" data-close>Annulla</button><button class="btn primary" id="scsave">Salva</button></div>`);
  const read = () => { sc.rules = $$('[data-rule]', m).map(el => ({ mode: $('[data-f=mode]', el).value, from: $('[data-f=from]', el).value, to: $('[data-f=to]', el).value,
    days: $$('[data-day]', el).filter(c => c.classList.contains('on')).map(c => +c.dataset.day) })); };
  const draw = () => {
    $('#scrules', m).innerHTML = sc.rules.length ? sc.rules.map(row).join('') : '<div class="subtle" style="margin-bottom:10px">Nessuna fascia.</div>';
    $$('[data-day]', m).forEach(c => c.onclick = () => c.classList.toggle('on'));
    $$('[data-del]', m).forEach(b => b.onclick = () => { read(); sc.rules.splice(+b.closest('[data-rule]').dataset.rule, 1); draw(); });
  };
  draw();
  $('#scen', m).onclick = e => e.currentTarget.classList.toggle('on');
  $('#scadd', m).onclick = () => { read(); sc.rules.push({ mode: 'on', days: [0, 1, 2, 3, 4], from: '18:00', to: '23:00' }); draw(); };
  $('#scsave', m).onclick = e => { read();
    act(e.currentTarget, () => api('POST', '/disks/standby-schedule', { enabled: $('#scen', m).classList.contains('on'), idle: +$('#scidle', m).value, rules: sc.rules }),
      'Programma salvato').then(r => { if (r) { closeModal(); pageDisks(); } }); };
}

function standbyDialog(id, custom = false) {
  const d = DK.disks.find(x => x.id === id);
  if (!d) return;
  const s = d.standby;
  let min = s.minutes;
  const isStd = () => STANDBY_TIMES.some(([v]) => v === min);
  const m = modal(`${mhead(`<div class="dicon">${ic('moon')}</div>`, `Standby di "${esc(d.display)}"`, `${esc(d.model || d.name)} · ${s.state === 'standby' ? 'ora in standby' + (s.since ? ' da ' + ago(s.since).replace(' fa', '') : '') : s.state === 'active' ? 'ora attivo' : 'stato sconosciuto'}`)}
    <div class="mb">
      <div class="section-t">Spegni il disco dopo</div>
      <div class="chips" id="sbchips">${STANDBY_TIMES.map(([v, t]) => `<span class="chip ${v === min ? 'on' : ''}" data-min="${v}">${t}</span>`).join('')}<span class="chip ${isStd() && !custom ? '' : 'on'}" data-min="custom">Personalizzato…</span></div>
      <div class="field" id="sbcust" ${isStd() && !custom ? 'hidden' : ''}><label>Minuti senza attività</label><input class="input" type="number" min="2" max="1440" id="sbmin" value="${min || 45}" style="max-width:160px"></div>
      <div class="grid" style="grid-template-columns:repeat(3,1fr);gap:10px">
        <div class="smart" style="grid-template-columns:1fr;margin:0"><div><small>Stato</small><b>${s.state === 'standby' ? 'In standby' : s.state === 'active' ? 'Attivo' : '—'}</b></div></div>
        <div class="smart" style="grid-template-columns:1fr;margin:0"><div><small>Accensioni oggi</small><b>${nf(s.spinups_today || 0)}</b></div></div>
        <div class="smart" style="grid-template-columns:1fr;margin:0"><div><small>Ultima attività</small><b>${s.last_io ? ago(s.last_io) : '—'}</b></div></div>
      </div>
      <div class="list">
        <div class="item"><div class="grow"><div class="t">Mai durante i backup</div><div class="s">Dalle <input class="input sm" id="wf" value="${esc(DK.window.from)}" style="width:72px;display:inline-block"> alle <input class="input sm" id="wt" value="${esc(DK.window.to)}" style="width:72px;display:inline-block"> resta acceso (orario uguale per tutti i dischi)</div></div><button class="toggle ${s.backup_window ? 'on' : ''}" id="sbw"></button></div>
        <div class="item"><div class="grow"><div class="t">Segue il programma settimanale</div><div class="s">${DK.schedule.enabled ? 'Nelle fasce del programma si spegne o resta acceso come stabilito lì' : 'Il programma ora è spento (Dischi → Programma settimanale)'}</div></div><button class="toggle ${s.schedule !== false ? 'on' : ''}" id="sbsc"></button></div>
        <div class="item"><div class="grow"><div class="t">Risparmio energetico del disco (APM)</div><div class="s">Il disco rallenta da solo quando lavora poco</div></div><select class="input sm" id="sbapm" style="width:150px">${APM_LABELS.map(([v, t]) => `<option value="${v}" ${s.apm === v ? 'selected' : ''}>${t}</option>`).join('')}</select></div>
      </div>
      ${s.error ? `<div class="alert bad">${ic('alert')}<div>Ultimo tentativo non riuscito: ${esc(s.error)}. Alcuni box USB non accettano lo standby.</div></div>` : ''}
      <div class="alert info">${ic('info')}<div>Tempi troppo brevi (meno di 10 minuti) fanno accendere e spegnere spesso il disco e lo consumano prima. Per gli HDD consigliamo 20–30 minuti.${d.ssd ? ' Questo è un SSD: lo standby serve a poco.' : ''}</div></div>
    </div>
    <div class="mf"><button class="btn" id="sbnow">${ic('moon')}Spegni adesso</button><span class="grow"></span><button class="btn" data-close>Annulla</button><button class="btn primary" id="sbsave">Salva</button></div>`);
  $$('[data-min]', m).forEach(c => c.onclick = () => {
    $$('[data-min]', m).forEach(x => x.classList.toggle('on', x === c));
    const cust = c.dataset.min === 'custom';
    $('#sbcust', m).hidden = !cust;
    if (!cust) min = +c.dataset.min; else $('#sbmin', m).focus();
  });
  $('#sbw', m).onclick = e => e.currentTarget.classList.toggle('on');
  $('#sbsc', m).onclick = e => e.currentTarget.classList.toggle('on');
  $('#sbnow', m).onclick = e => act(e.currentTarget, () => api('POST', '/disks/sleep', { disk: d.path }), `${d.display} in standby`).then(r => { if (r) { closeModal(); pageDisks(); } });
  $('#sbsave', m).onclick = e => {
    if (!$('#sbcust', m).hidden) min = +$('#sbmin', m).value;
    act(e.currentTarget, () => api('POST', '/disks/standby', { id, minutes: min, backup_window: $('#sbw', m).classList.contains('on'), apm: $('#sbapm', m).value, schedule: $('#sbsc', m).classList.contains('on'),
      window: { from: $('#wf', m).value, to: $('#wt', m).value } }), 'Standby salvato').then(r => { if (r) { closeModal(); pageDisks(); } });
  };
}

/* --- salute (SMART) ------------------------------------------------------------------------ */

async function smartDialog(path) {
  const d = DK.disks.find(x => x.path === path);
  const m = modal(`${mhead(`<div class="dicon">${ic('shield')}</div>`, `Salute di "${esc(d.display)}"`, `${esc(d.model || d.name)} · ${esc(path)}`)}<div class="mb" id="smb"><div class="loading-page" style="min-height:120px"><span class="spin lg"></span></div></div>
    <div class="mf"><span class="grow">Test SMART: il disco continua a funzionare durante il test</span><button class="btn" id="tshort">Test breve</button><button class="btn" id="tlong">Test completo</button></div>`, 'wide');
  const run = kind => e => act(e.currentTarget, () => api('POST', '/disks/smart-test', { disk: path, kind }), r => r.message);
  $('#tshort', m).onclick = run('short');
  $('#tlong', m).onclick = run('long');
  let s;
  try { s = await api('GET', '/disks/smart?disk=' + encodeURIComponent(path)); } catch (e) { $('#smb', m).innerHTML = `<div class="err">${esc(e.message)}</div>`; return; }
  if (!$('#smb', m)) return;
  if (s.standby && !s.attributes.length) {
    $('#smb', m).innerHTML = `<div class="alert info">${ic('moon')}<div>Il disco è in standby: per non svegliarlo i dati SMART non sono stati letti. Riprova quando è attivo.</div></div>`;
    return;
  }
  const kv = [['Stato', s.passed === false ? 'Guasto (SMART)' : s.passed ? 'Superato' : '—'], ['Vita residua', s.life != null ? s.life + '%' : '—'],
    ['Temperatura', s.temperature != null ? s.temperature + ' °C' : '—'], ['Ore di lavoro', s.power_on_hours != null ? nf(s.power_on_hours) : '—'],
    ['Accensioni', s.power_cycles != null ? nf(s.power_cycles) : '—'], ['Settori difettosi', s.bad_sectors != null ? nf(s.bad_sectors) : '—'],
    ['Numero di serie', s.serial || '—'], ['Firmware', s.firmware || '—'], ['Collegamento', s.interface || '—']];
  $('#smb', m).innerHTML = `
    <dl class="kv" style="grid-template-columns:140px 1fr 140px 1fr">${kv.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join('')}</dl>
    ${s.bad_sectors ? `<div class="alert bad">${ic('alert')}<div>Ci sono settori danneggiati o in attesa di essere sostituiti. Il disco può continuare a funzionare, ma fai un backup e tienilo d'occhio: se il numero cresce va cambiato.</div></div>` : ''}
    ${s.tests && s.tests.length ? `<div class="section-t">Ultimi test</div><table class="kvtable"><tr><th>Tipo</th><th>Risultato</th><th>A ore</th></tr>${s.tests.map(t => `<tr><td>${esc(t.type)}</td><td>${t.passed === false ? '<span class="badge bad">' + esc(t.result) + '</span>' : esc(t.result)}</td><td>${t.hours != null ? nf(t.hours) : ''}</td></tr>`).join('')}</table>` : ''}
    ${s.attributes && s.attributes.length ? `<div class="section-t">Attributi</div><div style="max-height:300px;overflow:auto"><table class="kvtable"><tr><th>ID</th><th>Nome</th><th>Valore</th><th>Peggiore</th><th>Soglia</th><th>Grezzo</th></tr>
      ${s.attributes.map(a => `<tr ${a.failed ? 'style="color:var(--bad)"' : ''}><td>${a.id}</td><td>${esc(a.name)}</td><td>${a.value ?? ''}</td><td>${a.worst ?? ''}</td><td>${a.thresh ?? ''}</td><td class="mono">${esc(a.raw)}</td></tr>`).join('')}</table></div>` : ''}
    ${s.nvme ? `<div class="section-t">NVMe</div><dl class="kv">${Object.entries(s.nvme).filter(([, v]) => typeof v !== 'object').map(([k, v]) => `<dt style="font-size:12px">${esc(k.replace(/_/g, ' '))}</dt><dd>${esc(nf(v))}</dd>`).join('')}</dl>` : ''}`;
}

/* --- spazio delle app (Docker) ------------------------------------------------------------- */

async function dockerSpace() {
  let r;
  try { r = await api('GET', '/docker/space'); } catch (e) { return; }
  const box = $('#dsbody');
  if (!box) return;
  if (!r.available) { $('#dsload').textContent = ''; box.textContent = 'Il motore delle app (Docker) non risponde.'; return; }
  const names = { Images: 'Immagini', Containers: 'Contenitori', 'Local Volumes': 'Volumi', 'Build Cache': 'Cache di compilazione' };
  $('#dsload').textContent = r.filesystem.size ? `${bytes(r.filesystem.used)} usati su ${bytes(r.filesystem.size)}` : '';
  box.innerHTML = `<div class="smart" style="margin-top:0">${r.types.map(t => `<div><small>${names[t.Type] || esc(t.Type)} (${esc(t.TotalCount)})</small><b>${esc(t.Size)}</b>${t.Reclaimable && !/^0B/.test(t.Reclaimable) ? `<div class="subtle">liberabili ${esc(t.Reclaimable.replace(/\s*\(.*\)/, ''))}</div>` : ''}</div>`).join('')}</div>
    <div class="row" style="margin-top:12px;flex-wrap:wrap"><button class="btn sm" id="prune">${ic('trash')}Togli le immagini non usate</button><span class="subtle">Le app installate non vengono toccate.</span></div>`;
  $('#prune').onclick = e => act(e.currentTarget, () => api('POST', '/docker/prune'), x => `Liberati ${bytes(x.freed)}`).then(x => x && dockerSpace());
}

/* --- sposta le app su un altro disco ------------------------------------------------------- */

async function appLocation() {
  let r;
  try { r = await api('GET', '/apps/location', undefined, { timeout: 240000 }); } catch (e) { const b = $('#albody'); if (b) b.textContent = e.message; return; }
  const box = $('#albody');
  if (!box) return;
  const sz = r.sizes, onDisk = r.location !== 'system';
  $('#alload').textContent = `${bytes(r.total)} in tutto`;
  const parts = `Docker ${bytes(sz.docker + sz.containerd)} · AppData ${bytes(sz.appdata)}`;
  const last = r.last && r.last.t && !r.last.ok ? `<div class="alert bad" style="margin-top:10px">${ic('alert')}<div>Ultimo tentativo non riuscito (${esc(new Date(r.last.t * 1000).toLocaleString(LOCALE))}): ${esc(r.last.error || '')}. Le app sono rimaste dov'erano.</div></div>` : '';
  if (r.running) {
    box.innerHTML = `<div class="row">${'<span class="spin"></span>'}<b>Spostamento in corso…</b><span class="subtle">le app sono ferme finché non finisce</span></div><pre class="logbox" id="allog" style="margin-top:10px;max-height:260px"></pre>`;
    followMoveLog();
    return;
  }
  if (onDisk) {
    const i = r.info;
    box.innerHTML = `<div class="row" style="flex-wrap:wrap;gap:10px"><div class="grow"><b style="color:var(--ink)">Sul disco ${esc(i.disk.split('/').pop())}</b><div class="subtle">${parts} · in <span class="mono">${esc(i.dest)}</span> · dal ${esc(new Date(i.moved * 1000).toLocaleDateString(LOCALE))}</div>
      <div class="subtle">I percorsi non sono cambiati (/var/lib/docker e /DATA/AppData): compose, condivisioni e backup restano uguali.</div></div>
      ${i.old_kept ? `<button class="btn sm" id="alfree">${ic('trash')}Libera lo spazio sul disco di sistema</button>` : ''}<button class="btn sm" id="alback">${ic('undo')}Riporta sul disco di sistema</button></div>${last}`;
    const fb = $('#alfree');
    if (fb) fb.onclick = async e => {
      if (!await ask('Libera lo spazio', 'Le copie vecchie di Docker e AppData sul disco di sistema vengono cancellate. Le app continuano a funzionare dal disco nuovo, ma per riportarle indietro servirà copiarle di nuovo.', 'Cancella le copie vecchie', true)) return;
      const x = await act(e.currentTarget, () => api('POST', '/apps/location/free'));
      if (x) { const j = await followJob(x.job).catch(() => null); if (j && j.state === 'done') toast('Spazio liberato'); else if (j) toast(j.error, 'bad'); appLocation(); }
    };
    $('#alback').onclick = () => moveDialog(r, true);
    return;
  }
  const ok = r.candidates.filter(c => c.ok);
  box.innerHTML = `<div class="row" style="flex-wrap:wrap;gap:10px"><div class="grow"><b style="color:var(--ink)">Sul disco di sistema</b><div class="subtle">${parts}</div></div>
    <button class="btn sm" id="almove" ${r.candidates.length ? '' : 'disabled'}>${ic('move')}Sposta su un altro disco…</button></div>
    ${r.candidates.length ? '' : '<div class="subtle" style="margin-top:6px">Per spostarle serve un disco dati montato "a ogni avvio" con ext4, XFS o Btrfs.</div>'}${last}`;
  const mb = $('#almove'); if (mb) mb.onclick = () => moveDialog(r, false);
  void ok;
}

function moveDialog(r, back) {
  let pick = back ? null : (r.candidates.find(c => c.ok) || {}).path;
  const word = back ? 'RIPORTA' : 'SPOSTA';
  const m = modal(`${mhead(`<div class="dicon">${ic('move')}</div>`, back ? 'Riporta le app sul disco di sistema' : 'Sposta le app su un altro disco', `Docker e AppData · ${bytes(r.total)}`)}
    <div class="mb">
      ${back ? `<div class="dialog-text">Docker e i dati delle app vengono copiati di nuovo sul disco di sistema e le app ripartono da lì. La copia su <span class="mono">${esc(r.info.dest)}</span> resta: potrai cancellarla dal file manager.</div>`
    : `<div class="field"><label>Disco di destinazione</label><div class="list">${r.candidates.map(c => `<label class="item ${c.ok ? 'clickable' : ''}" style="${c.ok ? '' : 'opacity:.55'}"><input type="radio" name="ald" value="${esc(c.path)}" ${c.path === pick ? 'checked' : ''} ${c.ok ? '' : 'disabled'}><div class="grow"><div class="t">${esc(c.name)} <span class="badge">${esc(c.fstype)}</span></div><div class="s">${bytes(c.free)} liberi su ${bytes(c.size)}${c.why ? ' · ' + esc(c.why) : ''}</div></div></label>`).join('')}</div></div>`}
      <div class="alert info">${ic('info')}<div>Durante la copia <b>le app restano ferme</b> (dipende dai GB: anche più di un'ora). Prima di cambiare qualcosa la copia viene controllata con un secondo passaggio; se le app non ripartono si torna da soli alla situazione di prima. I percorsi non cambiano.</div></div>
      ${back ? '' : '<div class="subtle">Il disco scelto resterà sempre acceso mentre le app sono attive (niente standby). Se all’avvio il disco manca, le app non partono finché non lo ricolleghi.</div>'}
      <div class="field" style="margin-top:10px"><label>Per confermare scrivi <code class="k">${word}</code></label><input class="input" id="alconf" autocomplete="off" spellcheck="false" placeholder="${word}"></div>
    </div>
    <div class="mf"><button class="btn" data-close>Annulla</button><button class="btn primary" id="algo">${ic('move')}${back ? 'Riporta' : 'Sposta'}</button></div>`);
  $$('[name=ald]', m).forEach(x => x.onchange = () => { pick = x.value; });
  $('#algo', m).onclick = async e => {
    const conf = $('#alconf', m).value;
    const x = await act(e.currentTarget, () => back ? api('POST', '/apps/location/back', { confirm: conf }) : api('POST', '/apps/location/move', { path: pick, confirm: conf }));
    if (x) { closeModal(); toast(back ? 'Riporto le app sul disco di sistema…' : 'Sposto le app…', 'info'); appLocation(); }
  };
}

async function followMoveLog() {
  let off = 0;
  for (;;) {
    const box = $('#allog');
    if (!box) return;
    const r = await api('GET', '/apps/location/log?offset=' + off).catch(() => null);
    if (r) {
      off = r.offset;
      if (r.text) { box.textContent += r.text; box.scrollTop = box.scrollHeight; }
      if (!r.running) { await sleep(1000); appLocation(); dockerSpace(); return; }
    }
    await sleep(2000);
  }
}

document.addEventListener('click', e => {
  const a = e.target.closest('[data-open]');
  if (a) store.set('filesPath', a.dataset.open);
});

ROUTES.disks = pageDisks;
