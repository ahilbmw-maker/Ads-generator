// ═══ NABIRANJE ZALOGE — logika ═══
let ITEMS = [];           // vse postavke iz seje
let SESSION = null;       // celotna seja
let EXTRA_POS = {};        // sku → [sekundarne lokacije] (backup zaloga)
const MARKET_KEY = 'zaloga_market';  // localStorage: aktivni trg (ostane ob osvežitvi)
let MARKET = (function(){ try { return localStorage.getItem(MARKET_KEY) || 'slo'; } catch(e){ return 'slo'; } })();
const EXPANDED_KEY = 'zaloga_expanded';  // localStorage: kateri zavihki odprti (per naprava)

// market query suffix za fetch klice
function mq(extra) {
  const sep = extra && extra.includes('?') ? '&' : '?';
  return (extra || '') + sep + 'market=' + MARKET;
}
function isRS() { return MARKET === 'rs'; }

// ── Preklop trga ──
function switchMarket(m) {
  if (m === MARKET) return;
  MARKET = m;
  try { localStorage.setItem(MARKET_KEY, m); } catch(e) {}
  document.getElementById('mtab-slo').classList.toggle('active', m === 'slo');
  document.getElementById('mtab-rs').classList.toggle('active', m === 'rs');
  _toggleImportBtn();
  setExpanded({});  // počisti odprte zavihke ob preklopu
  lastUpdate = null;
  loadSession();
}

// Gumb "Uvoz dobavnice" je samo na RS trgu
function _toggleImportBtn() {
  const b = document.getElementById('importIkonkaBtn');
  if (b) b.style.display = (MARKET === 'rs') ? 'inline-flex' : 'none';
}

// ── Ob nalaganju: označi shranjeni trg ──
function initMarketTab() {
  const slo = document.getElementById('mtab-slo');
  const rs = document.getElementById('mtab-rs');
  if (slo) slo.classList.toggle('active', MARKET === 'slo');
  if (rs) rs.classList.toggle('active', MARKET === 'rs');
  _toggleImportBtn();
}

// ── Skupine ──
const GROUP_ORDER = (g) => {
  if (g.startsWith('Polica ')) return [0, g];
  if (/^P\d+$/.test(g)) return [1, parseInt(g.slice(1))];
  if (g === 'Paleta') return [2, 0];
  if (g === 'Pod Mizo') return [2, 1];
  if (g === 'Ikonka') return [2, 2];
  if (g === 'Amio') return [2, 3];
  if (g === 'neznano') return [2, 4];
  if (g === 'Ni podatka') return [3, 0];
  return [2, g];
};

function getExpanded() {
  try { return JSON.parse(localStorage.getItem(EXPANDED_KEY) || '{}'); }
  catch(e) { return {}; }
}
function setExpanded(map) {
  try { localStorage.setItem(EXPANDED_KEY, JSON.stringify(map)); } catch(e) {}
}

// ── Nalaganje seje ──
async function loadSession() {
  try {
    const r = await fetch(mq('/zaloga-current'));
    const data = await r.json();
    if (data.ok && data.items && data.items.length) {
      SESSION = data;
      ITEMS = data.items;
      // naloži sekundarne (backup) lokacije — ista baza kot "Zaloga in vračila"
      try {
        const er = await fetch('/zaloga-extra-positions');
        const ed = await er.json();
        EXTRA_POS = (ed && ed.ok && ed.extra) ? ed.extra : {};
      } catch(e) { EXTRA_POS = {}; }
      // VAROVALKA: ob novi zaznavi padca seštevka pokaži toast (samo enkrat na spremembo)
      const ig = data.integrity;
      if (ig && ig.ok === false) {
        const sig = ig.dropped_items + ':' + ig.dropped_qty;
        if (sig !== _lastIntegritySig) {
          _lastIntegritySig = sig;
          const p = [];
          if (ig.dropped_items > 0) p.push(`${ig.dropped_items} postavk`);
          if (ig.dropped_qty > 0) p.push(`${ig.dropped_qty} kosov`);
          toast(`⚠️ Seštevek se je zmanjšal — manjka ${p.join(' in ')}! Preveri izbris.`, 6000);
        }
      } else if (ig && ig.ok) {
        _lastIntegritySig = '';
      }
      render();
      document.getElementById('archiveBtn').style.display = '';
      document.getElementById('globalStat').style.display = '';
      fetchSkuImages();  // v ozadju naloži slike izdelkov
    } else {
      showEmpty();
    }
  } catch(e) {
    showEmpty();
  }
}

// ── Slike izdelkov (preview za nove delavce) ──
let SKU_IMAGES = {};   // { SKU: url }
let _lastIntegritySig = '';  // VAROVALKA: zadnja zaznana signatura padca seštevka (da toast ne spamira)
async function fetchSkuImages() {
  try {
    const skus = [...new Set(ITEMS.map(it => it.sku).filter(Boolean))];
    if (!skus.length) return;
    const naziv_map = {};
    ITEMS.forEach(it => { if (it.sku && it.naziv) naziv_map[it.sku] = it.naziv; });
    const r = await fetch('/zaloga-sku-images', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ skus, naziv_map })
    });
    const data = await r.json();
    if (data.ok && data.images) {
      SKU_IMAGES = data.images;
      applySkuImages();
    }
  } catch(e) { /* tiho — slike niso kritične */ }
}

// Ročna prisilna osvežitev feed cache-a (po dodajanju novega izdelka).
// Obide tedenski TTL, nato znova naloži slike v trenutni seji.
async function refreshFeed() {
  const btn = document.getElementById('refreshFeedBtn');
  if (!btn) return;
  if (btn.dataset.busy === '1') return;
  const orig = btn.innerHTML;
  btn.dataset.busy = '1';
  btn.disabled = true;
  btn.innerHTML = '⏳ Osvežujem…';
  try {
    const r = await fetch('/zaloga-refresh-feed', { method: 'POST' });
    const data = await r.json();
    if (data.ok) {
      btn.innerHTML = '✓ Osveženo';
      // znova poberi slike za trenutno sejo
      await fetchSkuImages();
    } else {
      btn.innerHTML = (data.note && data.note.indexOf('poteka') >= 0) ? '⏳ Že teče…' : '✗ Napaka';
    }
  } catch(e) {
    btn.innerHTML = '✗ Napaka';
  } finally {
    setTimeout(() => {
      btn.innerHTML = orig;
      btn.disabled = false;
      btn.dataset.busy = '0';
    }, 2500);
  }
}

// Vstavi sličice v že izrisane postavke (brez polnega re-renderja)
function applySkuImages() {
  ITEMS.forEach(it => {
    const url = SKU_IMAGES[it.sku];
    if (!url) return;
    const holder = document.querySelector(`#imgthumb-${it.idx}`);
    if (holder && !holder.dataset.loaded) {
      holder.dataset.loaded = '1';
      holder.innerHTML = `<img src="${esc(url)}" alt="" loading="lazy" onclick="event.stopPropagation();openImgPreview('${jsStr(url)}','${jsStr(it.sku)}')">`;
      holder.classList.add('has-img');
    }
  });
}

// Povečava slike
function openImgPreview(url, sku) {
  const html = `
    <div class="img-preview-overlay" id="imgPreviewOverlay" onclick="closeImgPreview()">
      <div class="img-preview-box" onclick="event.stopPropagation()">
        <img src="${esc(url)}" alt="${esc(sku)}">
        <div class="img-preview-sku">${esc(sku)}</div>
        <button class="img-preview-close" onclick="closeImgPreview()">✕ Zapri</button>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}
function closeImgPreview() {
  const o = document.getElementById('imgPreviewOverlay');
  if (o) o.remove();
}

// ── Popravek pozicije med nabiranjem → čakajoči seznam taba "Sprememba pozicij" ──
function openPozEdit(sku, currentPoz, naziv) {
  // odstrani morebitni obstoječi
  const ex = document.getElementById('pozEditOverlay');
  if (ex) ex.remove();
  const html = `
    <div class="img-preview-overlay" id="pozEditOverlay" onclick="closePozEdit()">
      <div class="poz-edit-box" onclick="event.stopPropagation()">
        <div class="poz-edit-head">
          <span>📍 Sprememba pozicije</span>
          <button class="poz-edit-x" onclick="closePozEdit()">✕</button>
        </div>
        <div class="poz-edit-cur">
          <div class="poz-edit-sku">${esc(sku)}</div>
          <div class="poz-edit-naziv">${esc(naziv||'')}</div>
          <div class="poz-edit-trenutno">trenutno: <b>${esc(currentPoz||'—')}</b></div>
        </div>
        <label class="poz-edit-label">Nova pozicija:</label>
        <input type="text" id="pozEditInput" class="poz-edit-input" value="${esc(currentPoz||'')}" placeholder="npr. 07-4D" autocomplete="off">
        <label class="poz-edit-photo">
          📷 Slikaj pozicijo
          <input type="file" accept="image/*" capture="environment" style="display:none" onchange="pozEditPhoto(event,'${jsStr(sku)}')">
        </label>
        <div class="poz-edit-status" id="pozEditStatus"></div>
        <button class="poz-edit-save" onclick="savePozEdit('${jsStr(sku)}','${jsStr(naziv||'')}')">✓ Dodaj v "Sprememba pozicij"</button>
        <div class="poz-edit-hint">Popravek gre v čakajoči seznam — potrdiš ga v zavihku <b>Sprememba pozicij</b>.</div>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  setTimeout(() => { const i = document.getElementById('pozEditInput'); if (i) { i.focus(); i.select(); } }, 50);
}

function closePozEdit() {
  const o = document.getElementById('pozEditOverlay');
  if (o) o.remove();
}

async function pozEditPhoto(ev, sku) {
  const f = ev.target.files && ev.target.files[0];
  if (!f) return;
  const status = document.getElementById('pozEditStatus');
  status.textContent = '⏳ Prepoznavam pozicijo s slike...';
  status.style.color = 'var(--text-dim)';
  try {
    const b64full = await new Promise((res, rej) => {
      const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(f);
    });
    const mt = (b64full.match(/^data:([^;]+);/) || [])[1] || 'image/jpeg';
    const b64 = b64full.split(',')[1];
    const r = await fetch('/pozicije-recognize-pos', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ image: b64, media_type: mt })
    });
    const d = await r.json();
    if (d && d.position) {
      const inp = document.getElementById('pozEditInput');
      if (inp) inp.value = d.position;
      status.textContent = '✓ Prepoznano: ' + d.position;
      status.style.color = 'var(--green, #16a34a)';
    } else {
      status.textContent = '⚠ Ni bilo mogoče prepoznati — vpiši ročno.';
      status.style.color = '#d97706';
    }
  } catch(e) {
    status.textContent = '⚠ Napaka pri prepoznavi — vpiši ročno.';
    status.style.color = '#dc2626';
  }
}

async function savePozEdit(sku, naziv) {
  const inp = document.getElementById('pozEditInput');
  const status = document.getElementById('pozEditStatus');
  const pos = (inp.value || '').trim();
  if (!pos) { status.textContent = '⚠ Vpiši pozicijo.'; status.style.color = '#dc2626'; return; }
  status.textContent = '⏳ Dodajam...';
  status.style.color = 'var(--text-dim)';
  try {
    const r = await fetch('/pozicije-pending-save', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ action:'add', item:{ sku, position: pos, title: naziv } })
    });
    const d = await r.json();
    if (d.ok) {
      status.textContent = '✓ Dodano v "Sprememba pozicij" (' + (d.items?d.items.length:'?') + ' čaka)';
      status.style.color = 'var(--green, #16a34a)';
      setTimeout(closePozEdit, 1100);
    } else {
      status.textContent = '⚠ ' + (d.error || 'Napaka');
      status.style.color = '#dc2626';
    }
  } catch(e) {
    status.textContent = '⚠ Napaka pri shranjevanju.';
    status.style.color = '#dc2626';
  }
}

function showEmpty() {
  ITEMS = [];
  document.getElementById('wrap').innerHTML = `
    <div class="empty-state" id="emptyState">
      <div class="icon">📋</div>
      <h2 style="color:var(--text-dim);font-weight:700">Ni aktivnega seznama</h2>
      <p style="margin-top:8px;font-size:13px">Naloži CSV izvoz za začetek nabiranja.</p>
    </div>`;
  document.getElementById('archiveBtn').style.display = 'none';
  document.getElementById('globalStat').style.display = 'none';
}

// ── Upload CSV ──
document.getElementById('csvInput').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  toast('⏳ Nalagam in obdelujem...');
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await fetch(mq('/zaloga-upload'), { method: 'POST', body: fd });
    const data = await r.json();
    if (data.ok) {
      toast(`✓ Naloženih ${data.count} postavk`);
      await loadSession();
    } else {
      toast('✗ ' + (data.error || 'napaka'));
    }
  } catch(err) {
    toast('✗ ' + err.message);
  }
  e.target.value = '';
});

// ── Uvoz dobavnice (RS): doda police Ikonka/Amio/neznano + kol>1 v čakajoče ──
document.getElementById('importInput').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  toast('⏳ Uvažam dobavnico...');
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await fetch(mq('/zaloga-import-ikonka'), { method: 'POST', body: fd });
    const data = await r.json();
    if (data.ok) {
      const g = data.groups || {};
      const gtxt = Object.keys(g).length ? ' (' + Object.entries(g).map(([k,v])=>`${k}: ${v}`).join(', ') + ')' : '';
      let msg = `✓ Uvoženo: ${data.added_police} na police${gtxt}, ${data.added_cakajoce} v čakajoče`;
      if (data.merged_dups > 0) msg += ` · 🔗 ${data.merged_dups} podvojenih SKU združenih`;
      toast(msg);
      await loadSession();
    } else {
      toast('✗ ' + (data.error || 'napaka'));
    }
  } catch(err) {
    toast('✗ ' + err.message);
  }
  e.target.value = '';
});

// ── HS PLUS (oba trga): označi obstoječe postavke po SKU z vizualno značko ──
// Pomen: izdelek pride danes (v sistemu je, fizično še ne) → nabiralec naj ne označi "ni zaloge".
document.getElementById('hsplusInput').addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if (!file) return;
  toast('⏳ Označujem HS PLUS...');
  const fd = new FormData();
  fd.append('file', file);
  try {
    const r = await fetch(mq('/zaloga-hsplus-upload'), { method: 'POST', body: fd });
    const data = await r.json();
    if (data.ok) {
      let t = `✓ HS PLUS: označenih ${data.matched} postavk`;
      if (data.unmatched > 0) t += ` (${data.unmatched} SKU ni v seznamu)`;
      toast(t);
      await loadSession();
    } else {
      toast('✗ ' + (data.error || 'napaka'));
    }
  } catch(err) {
    toast('✗ ' + err.message);
  }
  e.target.value = '';
});

// ── SKLADIŠČE (oba trga, sejni tag): prilepi SKU-je → označi postavke ──
function openSkladisce() {
  document.getElementById('skladOverlay').style.display = 'flex';
  document.getElementById('skladInput').value = '';
  document.getElementById('skladStatus').textContent = '';
  renderSkladList();
  setTimeout(() => document.getElementById('skladInput').focus(), 50);
}
function closeSkladisce() {
  document.getElementById('skladOverlay').style.display = 'none';
}
function renderSkladList() {
  const el = document.getElementById('skladList');
  const skus = (SESSION && SESSION.skladisce_skus) || [];
  if (!skus.length) { el.innerHTML = '<div style="font-size:12px;color:var(--text-dim);text-align:center;padding:8px">Ni SKU na seznamu</div>'; return; }
  el.innerHTML = `<div style="font-size:11px;color:var(--text-dim);margin-bottom:4px">Na seznamu (${skus.length}):</div>
    <div style="display:flex;flex-wrap:wrap;gap:5px;max-height:160px;overflow-y:auto">` +
    skus.map(s => `<span style="display:inline-flex;align-items:center;gap:4px;font-size:12px;padding:3px 8px;background:#fef3c7;color:#92400e;border:1px solid #fcd34d;border-radius:6px">
      ${esc(s)} <span onclick="removeSkladisce('${esc(s).replace(/'/g,"\\'")}')" style="cursor:pointer;font-weight:700">✕</span></span>`).join('') + '</div>';
}
async function addSkladisce() {
  const raw = document.getElementById('skladInput').value.trim();
  if (!raw) { document.getElementById('skladStatus').innerHTML = '<span style="color:#dc2626">Prilepi vsaj en SKU</span>'; return; }
  const st = document.getElementById('skladStatus');
  st.textContent = '⏳ označujem...';
  try {
    const r = await fetch(mq('/zaloga-skladisce'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ market: MARKET, action: 'add', raw }) });
    const d = await r.json();
    if (d.ok) {
      let msg = `✓ Označenih ${d.marked} postavk · ${d.skladisce_skus.length} SKU na seznamu`;
      if (d.ni_najdenih && d.ni_najdenih.length) msg += ` <span style="color:#d97706">(${d.ni_najdenih.length} SKU ni v tej seji)</span>`;
      st.innerHTML = '<span style="color:#16a34a">' + msg + '</span>';
      document.getElementById('skladInput').value = '';
      await loadSession();
      renderSkladList();
    } else { st.innerHTML = '<span style="color:#dc2626">✗ ' + esc(d.error || 'napaka') + '</span>'; }
  } catch (e) { st.innerHTML = '<span style="color:#dc2626">✗ napaka</span>'; }
}
async function removeSkladisce(sku) {
  try {
    const r = await fetch(mq('/zaloga-skladisce'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ market: MARKET, action: 'remove', sku }) });
    const d = await r.json();
    if (d.ok) { await loadSession(); renderSkladList(); }
  } catch (e) {}
}
async function clearSkladisce() {
  if (!confirm('Počistim cel seznam Skladišče2 za to sejo?')) return;
  try {
    const r = await fetch(mq('/zaloga-skladisce'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ market: MARKET, action: 'clear' }) });
    const d = await r.json();
    if (d.ok) {
      document.getElementById('skladStatus').innerHTML = '<span style="color:#16a34a">✓ Počiščeno</span>';
      await loadSession();
      renderSkladList();
    }
  } catch (e) {}
}

function groupItems() {
  const groups = {};
  ITEMS.forEach(it => {
    (groups[it.group] = groups[it.group] || []).push(it);
  });
  // sortiraj postavke znotraj skupine po poziciji
  Object.values(groups).forEach(arr => arr.sort((a,b) => (a.poz||'').localeCompare(b.poz||'', 'sl', {numeric:true})));
  return groups;
}

// ── Filter "Samo odprto": skrij dokončane (100%) police ──
function getDoneFilter() {
  return localStorage.getItem('zaloga_only_open') === '1';
}
function setDoneFilter(on) {
  localStorage.setItem('zaloga_only_open', on ? '1' : '0');
}
function syncFilterToggleLabel() {
  const lbl = document.getElementById('filterSwitchLabel');
  const input = document.getElementById('filterSwitchInput');
  const on = getDoneFilter();
  if (input) input.checked = on;   // stikalo odraža stanje
  if (!lbl) return;
  // oznaka je VEDNO "Nedokončano" (+ število nedokončanih); nikoli prazna
  let label = 'Nedokončano';
  try {
    const groups = groupItems();
    let open = 0;
    Object.values(groups).forEach(items => {
      const s = groupStat(items);
      if (!(s.total > 0 && s.todo === 0)) open++;  // ni dokončana
    });
    label = `Nedokončano (${open})`;
  } catch (e) { /* če štetje spodleti, ostane "Nedokončano" brez številke */ }
  lbl.textContent = label;
}
// stikalo: checked = prikaži samo odprte (filter ON), unchecked = vse
function setDoneFilterMode(on) {
  setDoneFilter(!!on);
  render();                 // render sam pokliče syncFilterToggleLabel()
  syncFilterToggleLabel();  // + takoj, da sta stikalo in oznaka zagotovo osvežena
}
// ohrani staro ime za morebitne klice (preklopi stanje)
function toggleDoneFilter() { setDoneFilterMode(!getDoneFilter()); }

// ── Render ──
function render() {
  const groups = groupItems();
  const expanded = getExpanded();
  const onlyOpen = getDoneFilter();
  const groupNames = Object.keys(groups).sort((a,b) => {
    const ga = GROUP_ORDER(a), gb = GROUP_ORDER(b);
    if (ga[0] !== gb[0]) return ga[0] - gb[0];
    if (typeof ga[1] === 'number' && typeof gb[1] === 'number') return ga[1] - gb[1];
    return String(ga[1]).localeCompare(String(gb[1]), 'sl', {numeric:true});
  });

  let html = '<div class="shelves">';
  let hiddenDone = 0;
  groupNames.forEach(g => {
    const items = groups[g];
    const isOpen = !!expanded[g];
    const stat = groupStat(items);
    // polica je "dokončana" ko ima vsaka postavka odločitev (✓ ali ✗) — nobena ni več todo
    const isDone = stat.total > 0 && stat.todo === 0;
    // filter "Samo odprto": skrij dokončane police (a pusti odprto, če jo ravno gledaš)
    if (onlyOpen && isDone && !expanded[g]) { hiddenDone++; return; }
    html += `
      <div class="shelf ${isOpen ? 'open' : ''}${isDone ? ' shelf-done' : ''}" id="shelf-${cssId(g)}">
        <div class="shelf-head" onclick="toggleShelf('${jsStr(g)}')">
          <span class="shelf-head-fill" aria-hidden="true" style="--fill-ok:${stat.qPctOk}%;--fill-ni:${stat.qPctOk + stat.qPctNi}%"></span>
          <span class="shelf-chevron">▶</span>
          <span class="shelf-name">${esc(g)}</span>
          <span class="shelf-count">${items.length} postavk</span>
          <div class="shelf-head-spacer"></div>
          <div class="shelf-prog">
            <div class="shelf-prog-bar prog-seg-wrap">${progBarSegments(stat)}</div>
            <span class="shelf-prog-pct" style="color:var(--text)">${isDone ? '✓ ' : ''}${stat.pctOkDisplay}%</span>
          </div>
        </div>
        <div class="shelf-body">
          ${isRS() ? shelfBoxBar(g, items) : ''}
          <div class="item-head">
            <span>ID naročila</span><span>Slika</span><span>SKU</span><span>Pozicija</span>
            <span>Naziv</span><span class="h-qty">Količina</span><span class="h-status">Status</span>
          </div>
          ${_sortMankoTop(items).map(it => itemRow(it)).join('')}
        </div>
      </div>`;
  });
  // RS: sekcija dodatnih boxov (viški) — pod zadnjo polico
  if (isRS()) html += extraBoxesSection();
  // RS: sekcija "Čakajoče" (velike postavke za razdelitev) — čisto na koncu
  if (isRS()) html += cakajoceSection();
  // filter aktiven in vse police dokončane → sporočilo
  if (onlyOpen && hiddenDone > 0 && !html.includes('class="shelf ')) {
    html += `<div class="empty-state"><div class="icon">✓</div>Vse police so dokončane!<br><span style="font-size:13px;color:var(--text-dim)">${hiddenDone} dokončanih skritih — klikni "Prikaži vse"</span></div>`;
  }
  html += '</div>';

  // Sidebar (manjko + skupna statistika)
  html += renderSidebar();

  document.getElementById('wrap').innerHTML = html;
  document.body.classList.toggle('market-slo', !isRS());
  document.body.classList.toggle('market-rs', isRS());
  updateGlobalStat();
  updateMobileBoxBar();  // poskrbi za prikaz (RS+mobile) ali skritje (SLO/desktop)
  syncFilterToggleLabel();
  updatePackingBtn();    // zgornji gumb "Packing lista" (samo RS + ko obstajajo boxi)
}

// prikaži/skrij zgornji gumb za carinski PDF (RS + ko obstaja kakšen box: zaklenjene postavke ALI razdeljeni)
function updatePackingBtn() {
  const btn = document.getElementById('packingPdfBtn');
  if (!btn) return;
  const xlsBtn = document.getElementById('packingXlsxBtn');
  const csvBtn = document.getElementById('packingCsvBtn');
  const pboxes = getPackingBoxes();
  // boxi iz polic (zaklenjene postavke z box oznako)
  const lockedBoxes = new Set();
  (ITEMS || []).forEach(it => {
    if (it.box && it.status === 'ok') lockedBoxes.add(String(it.box));
  });
  Object.keys(pboxes).forEach(b => lockedBoxes.add(String(b)));
  const show = isRS() && lockedBoxes.size > 0;
  // na mobile gumbi NIKOLI (prekriva se s 'Samo odprto' ipd.)
  if (isMobile()) { btn.style.display = 'none'; if(xlsBtn)xlsBtn.style.display='none'; if(csvBtn)csvBtn.style.display='none'; return; }
  btn.style.display = show ? 'inline-flex' : 'none';
  if (xlsBtn) xlsBtn.style.display = show ? 'inline-flex' : 'none';
  if (csvBtn) csvBtn.style.display = show ? 'inline-flex' : 'none';
  if (show) btn.textContent = `📄 Packing lista (${lockedBoxes.size})`;
}

// ── RS: zbir zasedenih box številk (1..100) ──
// Box je "zaseden", če ima vsaj eno zaklenjeno postavko, je dodatni box,
// ALI je uporabljen v čakajočih (packing_boxes) — vse sinhrono, da predlog ne trči.
function usedBoxNumbers() {
  const used = new Set();
  (ITEMS || []).forEach(it => {
    if (it.locked && it.box != null && String(it.box).trim() !== '') {
      const n = parseInt(String(it.box).trim(), 10);
      if (!isNaN(n)) used.add(n);
    }
  });
  const xb = getExtraBoxes();
  Object.keys(xb).forEach(b => {
    const n = parseInt(String(b).trim(), 10);
    if (!isNaN(n)) used.add(n);
  });
  // čakajoče (packing_boxes) — da police in čakajoče delijo isti prostor številk
  const pb = (typeof getPackingBoxes === 'function') ? getPackingBoxes() : {};
  Object.keys(pb || {}).forEach(b => {
    const n = parseInt(String(b).trim(), 10);
    if (!isNaN(n)) used.add(n);
  });
  return used;
}

// Najmanjša neuporabljena številka boxa (1..100), oz. '' če so vse zasedene
function nextFreeBox() {
  const used = usedBoxNumbers();
  for (let i = 1; i <= 100; i++) if (!used.has(i)) return String(i);
  return '';
}

// Globalno število obkljukanih (status ok) izdelkov BREZ dodeljenega boxa — čez vse police
function globalPendingCount() {
  return (ITEMS || []).filter(it => it.status === 'ok' && !it.locked).length;
}

// ── RS: box vrstica pri polici ──
function shelfBoxBar(group, items, mobileMode) {
  const lockedCount = items.filter(it => it.locked).length;
  const globalPending = globalPendingCount();  // obkljukani brez boxa — čez VSE police
  const used = usedBoxNumbers();
  const suggested = nextFreeBox();
  // opcije BOX1..BOX100; zasedeni dobijo ✓ (dovolimo izbiro — lahko dodajaš v obstoječi box)
  let opts = '';
  for (let i = 1; i <= 100; i++) {
    const isUsed = used.has(i);
    const sel = (String(i) === suggested) ? ' selected' : '';
    opts += `<option value="${i}"${sel}${isUsed ? ' data-used="1"' : ''}>${isUsed ? '✓ ' : ''}BOX${i}</option>`;
  }
  // unikatni id: mobilni sticky bar uporablja predpono "m-", da se ne podvaja z inline barom
  const inputId = (mobileMode ? 'mboxinput-' : 'boxinput-') + cssId(group);
  const cls = 'shelf-box-bar' + (mobileMode ? ' shelf-box-bar-mobile' : '');
  // značka: koliko obkljukanih čaka na box (globalno). Mobile = samo število, desktop = "N čaka"
  const countBadge = globalPending
    ? `<span class="sbb-count" title="Obkljukanih brez boxa (čez vse police)">✓ ${globalPending}${mobileMode ? '' : ' čaka'}</span>`
    : '';
  return `
    <div class="${cls}" onclick="event.stopPropagation()">
      <span class="sbb-icon">📦</span>
      <span class="sbb-label">Box:</span>
      <select class="sbb-select" id="${inputId}" onclick="event.stopPropagation()" onchange="markBoxSelect(this)">
        ${opts}
      </select>
      ${countBadge}
      <button class="sbb-save" onclick="lockBox('${jsStr(group)}', ${mobileMode ? 'true' : 'false'})">
        🔒 ${mobileMode ? 'Zakleni' : 'Shrani in zakleni'}
      </button>
      ${lockedCount ? `<span class="sbb-locked">${lockedCount} zaklenjenih</span>` : ''}
    </div>`;
}

// vizualno označi, ali je izbrani box že zaseden (zelena obroba)
function markBoxSelect(sel) {
  const opt = sel.options[sel.selectedIndex];
  if (opt && opt.getAttribute('data-used') === '1') sel.classList.add('sbb-select-used');
  else sel.classList.remove('sbb-select-used');
}

// ── RS: zakleni VSE obkljukane (čez vse police) v izbrani box ──
async function lockBox(group, mobileMode) {
  const id = (mobileMode ? 'mboxinput-' : 'boxinput-') + cssId(group);
  const inp = document.getElementById(id);
  const box = inp ? inp.value.trim() : '';
  if (!box) { toast('Izberi box'); if (inp) inp.focus(); return; }
  const pending = globalPendingCount();
  if (!pending) { toast('Ni obkljukanih izdelkov brez boxa'); return; }
  try {
    const r = await fetch('/zaloga-lock-box', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ market: MARKET, global: true, box })
    });
    const data = await r.json();
    if (data.ok) {
      // posodobi lokalno — VSE police
      ITEMS.forEach(it => {
        if (it.status === 'ok' && !it.locked) { it.box = box; it.locked = true; }
      });
      toast(`✓ ${data.locked} postavk → Box ${box}`);
      render();
      if (isRS()) updateMobileBoxBar();  // osveži spodnji bar (nov predlog boxa)
    } else {
      toast('✗ ' + (data.error || 'napaka'));
    }
  } catch(e) { toast('✗ ' + e.message); }
}

// ── RS: odkleni eno postavko ──
async function unlockItem(idx) {
  if (!confirm('Odklenem to postavko?\n\nBox dodelitev se odstrani, lahko jo ponovno zakleneš.')) return;
  try {
    const r = await fetch('/zaloga-lock-box', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ market: MARKET, unlock_idx: idx })
    });
    const data = await r.json();
    if (data.ok) {
      const it = ITEMS.find(x => x.idx === idx);
      if (it) { it.locked = false; it.box = ''; }
      toast('✓ Odklenjeno');
      render();
    } else { toast('✗ ' + (data.error || 'napaka')); }
  } catch(e) { toast('✗ ' + e.message); }
}

// ── RS: shrani opombo (dodatni box) ──
function commitOpomba(idx, val, el) {
  const it = ITEMS.find(x => x.idx === idx);
  if (!it) return;
  const newVal = (val || '').trim();
  const changed = it.opomba !== newVal;
  it.opomba = newVal;
  saveItem(idx, { opomba: it.opomba });
  refreshSidebarAndStats();
  // vizualni feedback "shranjeno"
  if (el && changed) {
    el.classList.add('iop-saved');
    el.style.borderColor = 'var(--ok)';
    el.style.background = 'var(--ok-bg)';
    const tag = document.createElement('span');
    tag.className = 'iop-saved-tag';
    tag.textContent = '✓ shranjeno';
    el.parentElement.appendChild(tag);
    setTimeout(() => {
      el.style.borderColor = '';
      el.style.background = '';
      el.classList.remove('iop-saved');
      tag.remove();
    }, 1500);
  }
}

// ── RS: dostop do dodatnih boxov ──
function getExtraBoxes() {
  return (SESSION && SESSION.extra_boxes) ? SESSION.extra_boxes : {};
}

// ── RS: odpri dialog "V box" za postavko ──
function openBoxDialog(idx) {
  const it = ITEMS.find(x => x.idx === idx);
  if (!it) return;
  // kos iz opombe (prvo število) ali privzeto qty
  let kos = it.qty || 1;
  const m = (it.opomba || '').match(/\d+/);
  if (m) kos = parseInt(m[0]);
  if (!kos || kos < 1) kos = 1;

  const boxes = getExtraBoxes();
  const keys = Object.keys(boxes).sort((a,b)=>String(a).localeCompare(String(b),'sl',{numeric:true}));

  const existing = keys.length ? keys.map(b => {
    const totalKos = boxes[b].reduce((s,e)=>s+(e.kos||0),0);
    return `<button class="bxd-pick" onclick="addToExtraBox(${idx}, '${jsStr(b)}', ${kos})">
      <span class="bxd-pick-ico">📦</span>
      <span class="bxd-pick-name">Box ${esc(b)}</span>
      <span class="bxd-pick-kos">${totalKos} kos</span>
    </button>`;
  }).join('') : '<div class="bxd-empty">Še ni dodatnih boxov — ustvari prvega zgoraj.</div>';

  const html = `
    <div class="bxd-overlay" id="bxdOverlay" onclick="if(event.target===this)closeBoxDialog()">
      <div class="bxd-modal">
        <div class="bxd-title">${esc(it.sku)} × ${kos} → v kateri dodatni box?</div>
        <div class="bxd-create">
          <input type="text" id="bxdNewNum" class="bxd-new-input" placeholder="Nova št. boxa (npr. 99)"
            inputmode="numeric" onkeydown="if(event.key==='Enter')createAndAdd(${idx}, ${kos})">
          <button class="bxd-create-btn" onclick="createAndAdd(${idx}, ${kos})">➕ Ustvari</button>
        </div>
        ${keys.length ? '<div class="bxd-or">ali izberi obstoječega:</div>' : ''}
        <div class="bxd-list">${existing}</div>
        <button class="bxd-cancel" onclick="closeBoxDialog()">Prekliči</button>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
  setTimeout(()=>{ const el=document.getElementById('bxdNewNum'); if(el) el.focus(); }, 50);
}

function closeBoxDialog() {
  const o = document.getElementById('bxdOverlay');
  if (o) o.remove();
}

function createAndAdd(idx, kos) {
  const inp = document.getElementById('bxdNewNum');
  const box = inp ? inp.value.trim() : '';
  if (!box) { toast('Vpiši št. novega boxa'); if(inp) inp.focus(); return; }
  addToExtraBox(idx, box, kos);
}

let _extraBoxBusy = false;  // zaščita pred dvojnim klikom (mobile)
async function addToExtraBox(idx, box, kos) {
  if (_extraBoxBusy) return;  // klic že poteka — prepreči dvojno dodajanje
  const it = ITEMS.find(x => x.idx === idx);
  if (!it) return;
  _extraBoxBusy = true;
  try {
    const r = await fetch('/zaloga-extra-box', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ market: MARKET, action:'add', box, sku: it.sku, naziv: it.naziv, idx, kos })
    });
    const data = await r.json();
    if (data.ok) {
      if (SESSION) SESSION.extra_boxes = data.extra_boxes;
      // backend morda označi nabrano če cel kos
      await loadSession();
      closeBoxDialog();
      toast(`✓ ${it.sku} × ${kos} → Box ${box}`);
    } else {
      toast('✗ ' + (data.error || 'napaka'));
    }
  } catch(e) { toast('✗ ' + e.message); }
  finally { _extraBoxBusy = false; }
}

async function removeFromExtraBox(box, sku) {
  if (!confirm(`Odstranim ${sku} iz Box ${box}?`)) return;
  try {
    const r = await fetch('/zaloga-extra-box', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ market: MARKET, action:'remove_item', box, sku })
    });
    const data = await r.json();
    if (data.ok) { if(SESSION) SESSION.extra_boxes = data.extra_boxes; render(); toast('✓ Odstranjeno'); }
    else toast('✗ ' + (data.error||'napaka'));
  } catch(e) { toast('✗ ' + e.message); }
}

// Preimenuj (uredi številko) dodatnega boxa
async function renameExtraBox(oldBox) {
  const nw = prompt(`Nova številka za Box ${oldBox}:`, oldBox);
  if (nw === null) return;                 // preklic
  const newBox = String(nw).trim();
  if (!newBox || newBox === String(oldBox)) return;
  try {
    const r = await fetch('/zaloga-extra-box', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ market: MARKET, action:'rename_box', box: oldBox, new_box: newBox })
    });
    const data = await r.json();
    if (data.ok) { if(SESSION) SESSION.extra_boxes = data.extra_boxes; render(); toast(`✓ Box ${oldBox} → ${newBox}`); }
    else toast('✗ ' + (data.error||'napaka'));
  } catch(e) { toast('✗ ' + e.message); }
}

// ── RS: sekcija "Dodatni boxi (viški)" ──
function extraBoxesSection() {
  const boxes = getExtraBoxes();
  const keys = Object.keys(boxes).sort((a,b)=>String(a).localeCompare(String(b),'sl',{numeric:true}));
  if (!keys.length) return '';  // skrito dokler ni vsaj 1
  const cards = keys.map(b => {
    const items = boxes[b];
    const totalKos = items.reduce((s,e)=>s+(e.kos||0),0);
    const lines = items.map(e => `
      <div class="ebx-line">
        <span class="ebx-line-sku">${esc(e.sku)}</span>
        <button class="ebx-copy-btn" onclick="copySkuFromManko(this,'${esc(e.sku)}')" title="Kopiraj kodo">📋 Kopiraj</button>
        <span class="ebx-line-kos">× ${e.kos}</span>
        <button class="ebx-line-del" onclick="removeFromExtraBox('${jsStr(b)}','${jsStr(e.sku)}')" title="Odstrani">✕</button>
      </div>`).join('');
    return `
      <div class="ebx-card">
        <div class="ebx-head">
          <span class="ebx-name">📦 Box ${esc(b)} <button class="ebx-rename" onclick="renameExtraBox('${jsStr(b)}')" title="Uredi številko boxa">✏️</button></span>
          <span class="ebx-meta">${totalKos} kos · ${items.length} ${items.length===1?'izdelek':(items.length===2?'izdelka':'izdelkov')}</span>
        </div>
        ${lines}
      </div>`;
  }).join('');
  return `
    <div class="extra-boxes-section">
      <div class="ebx-section-head">
        <span class="ebx-section-ico">🗄️</span>
        <span class="ebx-section-title">Dodatni boxi (viški)</span>
        <span class="ebx-section-count">${keys.length} box${keys.length===1?'':(keys.length===2?'a':'ov')}</span>
      </div>
      ${cards}
    </div>`;
}

// ════════════════════════════════════════════════════════════════
//  ČAKAJOČE — velike postavke za razdelitev v več packing boxov (carina)
// ════════════════════════════════════════════════════════════════
let CAKAJ_OPEN = null;   // idx odprte (razširjene) postavke
let CAKAJ_KOS = {};      // idx → trenutna vrednost sliderja
let CAKAJ_BOX = {};      // idx → izbrana št. boxa

function getCakajoce() { return (SESSION && SESSION.cakajoce) ? SESSION.cakajoce : []; }
function getPackingBoxes() { return (SESSION && SESSION.packing_boxes) ? SESSION.packing_boxes : {}; }

function _usedBoxNums() {
  // VSE zasedene številke (police zaklenjene + viški + čakajoče) — isti vir kot usedBoxNumbers().
  // Dodatno zajamemo še ok-postavke z box (tudi nezaklenjene), za predlog v čakajočih.
  const used = new Set();
  // baza: usedBoxNumbers() vrne števila (police locked + viški + packing_boxes)
  if (typeof usedBoxNumbers === 'function') {
    usedBoxNumbers().forEach(n => used.add(String(n)));
  }
  // ok-postavke z dodeljenim boxom (tudi če še niso zaklenjene)
  (ITEMS || []).forEach(it => { if (it.box && it.status === 'ok') used.add(String(it.box)); });
  return used;
}

function _nextBoxNum() {
  // predlagaj naslednjo prosto številko — VIŠJO od vseh zasedenih (police + čakajoče),
  // da se NIKOLI ne prekriva z boxom iz police
  const used = _usedBoxNums();
  let max = 0;
  used.forEach(b => { const n = parseInt(b); if (!isNaN(n) && n > max) max = n; });
  return String(max + 1 || 1);
}

function cakajoceSection() {
  const list = getCakajoce();
  const pboxes = getPackingBoxes();
  if (!list.length) return '';   // skrito dokler ni vsaj 1
  const onlyOpen = getDoneFilter();

  const rows = list.map(c => {
    const need = c.qty || 0;
    const assigned = c.assigned || 0;
    const ostane = Math.max(0, need - assigned);
    const isOpen = CAKAJ_OPEN === c.idx;
    const isDone = c.done || ostane === 0;
    const boxCount = Object.keys(pboxes).filter(b => pboxes[b].some(e => e.sku === c.sku)).length;

    // filter "Samo odprto": skrij zaključene (razdeljene) čakajoče — razen če so odprte
    if (onlyOpen && isDone && !isOpen) return '';

    if (!isOpen) {
      // DROBNA vrstica (zaprta) — done obarvana svetlo zeleno
      return `
        <div class="cak-row${isDone ? ' cak-row-done' : ''}" onclick="cakajToggle(${c.idx})">
          <span class="cak-chev">▶</span>
          <span class="cak-sku">${esc(c.sku)}</span>
          <span class="cak-naziv">${esc(c.naziv)}</span>
          ${isDone
            ? `<span class="cak-done">✓ razdeljeno</span>`
            : `<span class="cak-rem">še <b>${ostane}</b>/${need}</span>`}
          <span class="cak-boxcount">${boxCount} box</span>
        </div>`;
    }

    // RAZŠIRJENA vrstica (slider razdelilnik)
    const cur = (CAKAJ_KOS[c.idx] != null) ? CAKAJ_KOS[c.idx] : Math.min(ostane, ostane);
    const curVal = Math.max(0, Math.min(cur, ostane));
    const selBox = CAKAJ_BOX[c.idx] || _nextBoxNum();
    const pctFill = ostane ? Math.round(curVal / ostane * 100) : 0;
    const poShran = Math.max(0, ostane - curVal);

    // obstoječi boxi za izbiro: VEDNO dropdown (tudi pri 1-3, da ne zavzame vrstic na mobile)
    const boxKeys = Object.keys(pboxes).sort((a,b)=>String(a).localeCompare(String(b),'sl',{numeric:true}));
    const boxDropdown = boxKeys.length ? `
      <select class="cak-boxselect" onclick="event.stopPropagation()" onchange="cakajPickBox(${c.idx}, this.value)">
        <option value="" ${!boxKeys.includes(String(selBox))?'selected':''} disabled>Izberi obstoječi box…</option>
        ${boxKeys.map(b => {
          const bKos = pboxes[b].reduce((s,e)=>s+(e.kos||0),0);
          return `<option value="${esc(b)}" ${String(selBox)===String(b)?'selected':''}>📦 BOX ${esc(b)} · ${bKos} kos · ${pboxes[b].length} izd.</option>`;
        }).join('')}
      </select>` : '';

    // že dodeljeni boxi te postavke
    const myBoxes = Object.keys(pboxes).filter(b => pboxes[b].some(e => e.sku === c.sku))
      .sort((a,b)=>String(a).localeCompare(String(b),'sl',{numeric:true}))
      .map(b => {
        const e = pboxes[b].find(x => x.sku === c.sku);
        return `<span class="cak-chip" style="${boxStyle(b)}">📦 BOX${esc(b)} · ${e.kos} <span class="cak-chip-x" onclick="cakajRemoveAssign(${c.idx},'${jsStr(b)}')" title="Odstrani">✕</span></span>`;
      }).join('');

    return `
      <div class="cak-row-open">
        <div class="cak-head" onclick="cakajToggle(${c.idx})">
          <span class="cak-chev">▼</span>
          <span class="cak-sku">${esc(c.sku)}</span>
          <span class="cak-naziv">${esc(c.naziv)}</span>
          <span class="cak-rem">še <b>${ostane}</b>/${need}</span>
        </div>
        <div class="cak-body">
          ${ostane > 0 ? `
          <div class="cak-slider" onpointerdown="cakajSliderDown(event,${c.idx},${ostane})">
            <div class="cak-slider-fill" style="width:${pctFill}%"></div>
            <div class="cak-slider-val"><b id="cakVal-${c.idx}">${curVal}</b> kosov v box</div>
          </div>
          <div class="cak-slider-meta"><span>0</span><span>ostane: <b>${poShran}</b></span><span>${ostane}</span></div>
          <div class="cak-controls">
            <button class="cak-pm" onclick="cakajStep(${c.idx},-1,${ostane})">−</button>
            <button class="cak-pm" onclick="cakajStep(${c.idx},1,${ostane})">+</button>
            <button class="cak-all" onclick="cakajStep(${c.idx},9999,${ostane})">Vse (${ostane})</button>
          </div>
          <div class="cak-boxrow">
            <div class="cak-boxlbl">V kateri box?</div>
            <div class="cak-boxbtns">
              ${boxDropdown}
              <button class="cak-boxbtn cak-newbox${!_usedBoxNums().has(String(selBox))?' active':''}" onclick="cakajPickBox(${c.idx},'${jsStr(_nextBoxNum())}')">＋ Nov (${_nextBoxNum()})</button>
            </div>
            <div class="cak-boxmanual">
              <span class="cak-boxmanual-lbl">ali ročno:</span>
              <input type="text" inputmode="numeric" class="cak-boxinput" value="${esc(String(selBox))}"
                onclick="event.stopPropagation()"
                onchange="cakajPickBox(${c.idx}, this.value.trim())"
                onkeydown="if(event.key==='Enter'){this.blur();}"
                placeholder="št. boxa">
            </div>
          </div>
          <button class="cak-save" onclick="cakajAssign(${c.idx})">✓ Dodaj ${curVal} kos v BOX ${esc(selBox)}</button>
          <div class="cak-bulk">
            <div class="cak-bulk-lbl">⚡ Hitra razdelitev v več boxov</div>
            <div class="cak-bulk-row">
              <input type="number" min="1" class="cak-bulk-kos" id="cakBulkKos${c.idx}" placeholder="kos/box" onclick="event.stopPropagation()">
              <span class="cak-bulk-x">×</span>
              <span class="cak-bulk-info">od BOX</span>
              <input type="number" min="1" class="cak-bulk-start" id="cakBulkStart${c.idx}" value="${_nextBoxNum()}" onclick="event.stopPropagation()">
              <button class="cak-bulk-btn" onclick="cakajAssignBulk(${c.idx})">Razdeli</button>
            </div>
            <div class="cak-bulk-hint">Razdeli ${ostane} kos po N v zaporedne bokse. Ostanek (če ni deljivo) ostane.</div>
          </div>
          ` : `<div class="cak-complete">✓ Vse razdeljeno (${need} kosov)</div>`}
          ${myBoxes ? `<div class="cak-mychips">${myBoxes}</div>` : ''}
          ${(ostane > 0 && assigned > 0) ? `<button class="cak-closemiss" onclick="cakajCloseMissing(${c.idx},${ostane})">✓ Zaključi — ${ostane} v manjko</button>` : ''}
          <button class="cak-return" onclick="cakajReturn(${c.idx})">↩ Vrni v polico</button>
        </div>
      </div>`;
  }).join('');

  const totalBoxes = Object.keys(pboxes).length;

  return `
    <div class="cak-section">
      <div class="cak-section-head">
        <span>⏳</span>
        <span class="cak-section-title">Čakajoče · razdelitev v bokse</span>
        <span class="cak-section-count">${list.length}</span>
      </div>
      ${rows}
    </div>`;
}

async function prenesiVCakajoce(idx) {
  const it = ITEMS.find(x => x.idx === idx);
  if (!it) return;
  if (!confirm(`Prenesti "${it.sku}" (${it.qty} kos) v čakajoče za razdelitev v bokse?\nPostavka bo odstranjena iz police.`)) return;
  try {
    const r = await fetch('/zaloga-cakajoce', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ market: MARKET, action:'transfer', idx })
    });
    const d = await r.json();
    if (d.ok) {
      SESSION.cakajoce = d.cakajoce;
      SESSION.packing_boxes = d.packing_boxes;
      // odstrani iz lokalnega ITEMS
      ITEMS = ITEMS.filter(x => x.idx !== idx);
      CAKAJ_OPEN = idx;  // odpri jo takoj
      render();
    } else { alert(d.error || 'Napaka'); }
  } catch(e) { alert('Napaka pri prenosu'); }
}

function cakajToggle(idx) {
  CAKAJ_OPEN = (CAKAJ_OPEN === idx) ? null : idx;
  render();
}

function cakajStep(idx, delta, ostane) {
  let v = (CAKAJ_KOS[idx] != null) ? CAKAJ_KOS[idx] : ostane;
  if (delta === 9999) v = ostane;
  else v = Math.max(0, Math.min(ostane, v + delta));
  CAKAJ_KOS[idx] = v;
  render();
}

function cakajPickBox(idx, box) {
  box = String(box || '').trim();
  if (!box) return;   // prazen vnos → ignoriraj
  CAKAJ_BOX[idx] = box;
  render();
}

// slider drag (pointer)
function cakajSliderDown(ev, idx, ostane) {
  ev.preventDefault();
  const track = ev.currentTarget;
  const setFromX = (clientX) => {
    const r = track.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (clientX - r.left) / r.width));
    CAKAJ_KOS[idx] = Math.round(ratio * ostane);
    // posodobi samo prikaz med vlečenjem (brez polnega renderja za gladkost)
    const fill = track.querySelector('.cak-slider-fill');
    const val = document.getElementById('cakVal-' + idx);
    if (fill) fill.style.width = Math.round(ratio*100) + '%';
    if (val) val.textContent = CAKAJ_KOS[idx];
  };
  setFromX(ev.clientX);
  const move = (e) => setFromX(e.clientX);
  const up = () => {
    document.removeEventListener('pointermove', move);
    document.removeEventListener('pointerup', up);
    render();  // poln render ob koncu (osveži "ostane", gumb)
  };
  document.addEventListener('pointermove', move);
  document.addEventListener('pointerup', up);
}

async function cakajAssign(idx) {
  const c = getCakajoce().find(x => x.idx === idx);
  if (!c) return;
  const ostane = Math.max(0, (c.qty||0) - (c.assigned||0));
  const kos = (CAKAJ_KOS[idx] != null) ? CAKAJ_KOS[idx] : ostane;
  if (kos <= 0) { alert('Izberi količino'); return; }
  const box = CAKAJ_BOX[idx] || _nextBoxNum();
  try {
    const r = await fetch('/zaloga-cakajoce', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ market: MARKET, action:'assign', idx, box, sku: c.sku, naziv: c.naziv, kos })
    });
    const d = await r.json();
    if (d.ok) {
      SESSION.cakajoce = d.cakajoce;
      SESSION.packing_boxes = d.packing_boxes;
      delete CAKAJ_KOS[idx];   // reset slider
      delete CAKAJ_BOX[idx];
      render();
    } else { alert(d.error || 'Napaka'); }
  } catch(e) { alert('Napaka pri shranjevanju'); }
}

// Hitra razdelitev: X kosov po N v zaporedne bokse od start_box naprej
async function cakajAssignBulk(idx) {
  const c = getCakajoce().find(x => x.idx === idx);
  if (!c) return;
  const kosEl = document.getElementById('cakBulkKos' + idx);
  const startEl = document.getElementById('cakBulkStart' + idx);
  const kosPerBox = parseInt(kosEl && kosEl.value);
  const startBox = parseInt(startEl && startEl.value);
  if (!kosPerBox || kosPerBox < 1) { alert('Vnesi količino na box'); return; }
  if (!startBox || startBox < 1) { alert('Vnesi začetno št. boxa'); return; }
  const ostane = Math.max(0, (c.qty||0) - (c.assigned||0));
  const nBoxes = Math.floor(ostane / kosPerBox);
  if (nBoxes < 1) { alert(`Premalo kosov (${ostane}) za en box po ${kosPerBox}`); return; }
  const ostanek = ostane - nBoxes * kosPerBox;
  const zadnji = startBox + nBoxes - 1;
  let msg = `Razdelim ${nBoxes * kosPerBox} kos v ${nBoxes} boxov (BOX ${startBox}–${zadnji}, po ${kosPerBox}).`;
  if (ostanek > 0) msg += `\nOstane ${ostanek} kos nerazdeljenih.`;
  if (!confirm(msg)) return;
  try {
    const r = await fetch('/zaloga-cakajoce', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ market: MARKET, action:'assign_bulk', idx, sku: c.sku, naziv: c.naziv,
                             kos_per_box: kosPerBox, start_box: startBox })
    });
    const d = await r.json();
    if (d.ok) {
      SESSION.cakajoce = d.cakajoce;
      SESSION.packing_boxes = d.packing_boxes;
      delete CAKAJ_KOS[idx]; delete CAKAJ_BOX[idx];
      let t = `✓ Razdeljeno v ${d.created_boxes.length} boxov`;
      if (d.ostanek > 0) t += ` (${d.ostanek} ostane)`;
      toast(t);
      render();
    } else { alert(d.error || 'Napaka'); }
  } catch(e) { alert('Napaka pri shranjevanju'); }
}

async function cakajRemoveAssign(idx, box) {
  const c = getCakajoce().find(x => x.idx === idx);
  if (!c) return;
  try {
    const r = await fetch('/zaloga-cakajoce', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ market: MARKET, action:'remove_assign', idx, box, sku: c.sku })
    });
    const d = await r.json();
    if (d.ok) { SESSION.cakajoce = d.cakajoce; SESSION.packing_boxes = d.packing_boxes; render(); }
  } catch(e) {}
}

async function cakajCloseMissing(idx, ostane) {
  const c = getCakajoce().find(x => x.idx === idx);
  if (!c) return;
  if (!confirm(`Zaključim "${c.sku}"?\n\nRazdeljeni kosi ostanejo v boxih, preostalih ${ostane} kos pa gre v MANJKO.`)) return;
  try {
    const r = await fetch('/zaloga-cakajoce', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ market: MARKET, action:'close_missing', idx, sku: c.sku })
    });
    const d = await r.json();
    if (d.ok) {
      SESSION.cakajoce = d.cakajoce;
      if (d.packing_boxes) SESSION.packing_boxes = d.packing_boxes;
      toast(`✓ Zaključeno — ${ostane} kos v manjko`);
      render();
    } else { alert(d.error || 'Napaka'); }
  } catch(e) { alert('Napaka pri shranjevanju'); }
}

async function cakajReturn(idx) {
  if (!confirm('Vrniti postavko nazaj v polico? Vse dodelitve v bokse za to postavko bodo odstranjene.')) return;
  try {
    const r = await fetch('/zaloga-cakajoce', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ market: MARKET, action:'return', idx })
    });
    const d = await r.json();
    if (d.ok) {
      SESSION.cakajoce = d.cakajoce;
      SESSION.packing_boxes = d.packing_boxes;
      if (CAKAJ_OPEN === idx) CAKAJ_OPEN = null;
      await loadSession();  // ponovno naloži, da se postavka vrne v ITEMS
      render();
    }
  } catch(e) {}
}

function cakajPdf() { packingExport('/zaloga-packing-pdf', 'packing_lista.pdf', 'PDF'); }
function cakajXlsx() { packingExport('/zaloga-packing-xlsx', 'packing_lista.xlsx', 'XLS'); }
function cakajCsv() { packingExport('/zaloga-packing-csv', 'packing_lista.csv', 'CSV'); }

function packingExport(endpoint, filename, label) {
  fetch(endpoint, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ market: MARKET })
  }).then(r => {
    if (!r.ok) return r.json().then(e => { throw new Error(e.error||'Napaka'); });
    return r.blob();
  }).then(blob => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = filename;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }).catch(e => alert(e.message || ('Napaka pri ' + label)));
}

// Razvrsti postavke police: manjko (✗ cel ali ✓ delni) na VRH (kot pripeto),
// znotraj skupin ohrani razvrstitev po poziciji. Ostale (todo, polno OK) sledijo.
function _sortMankoTop(items) {
  const manko = [], rest = [];
  (items || []).forEach(it => { (_isManko(it) ? manko : rest).push(it); });
  return manko.concat(rest);
}

function itemRow(it) {
  // Barvanje: ok+polno → zelena; ok ampak delno nabrano (npr. 5/6) → oranžno-rdeča (partial);
  // ni (cel manjko ✗) → močna rdeča (full-miss)
  let cls = '';
  if (it.status === 'ok') {
    cls = (it.picked < it.qty) ? 'partial' : 'ok';
  } else if (it.status === 'ni') {
    cls = 'full-miss';
  }
  const mismatch = it.picked !== it.qty ? 'qty-mismatch' : '';
  const rs = isRS();
  const locked = rs && it.locked;

  // RS spodnja vrsta:
  //  - ZAKLENJEN: na MOBILE → spodnja vrsta (BOX + Odkleni); na DESKTOP → inline v vrstici izdelka
  //  - ODKLENJEN: polje "Dodatni box" za vnos razlike + gumb V box
  let opombaRow = '';
  let boxInline = '';  // desktop: BOX značka + odkleni v isti vrstici (prazen prostor desno od naziva)
  if (rs && locked) {
    // mobilna spodnja vrsta (skrita na desktopu prek CSS)
    opombaRow = `
      <div class="item-locked-row">
        <span class="item-box-badge" style="${boxStyle(it.box)}">📦 BOX ${esc(it.box)} 🔒</span>
        <button class="item-unlock" onclick="event.stopPropagation();unlockItem(${it.idx})" title="Odkleni in uredi">🔓 Odkleni</button>
      </div>`;
    // desktop inline (skrit na mobile prek CSS)
    boxInline = `
      <div class="item-box-inline">
        <span class="item-box-badge" style="${boxStyle(it.box)}">📦 BOX ${esc(it.box)} 🔒</span>
        <button class="item-unlock" onclick="event.stopPropagation();unlockItem(${it.idx})" title="Odkleni in uredi">🔓 Odkleni</button>
      </div>`;
  } else if (rs) {
    opombaRow = `
      <div class="item-opomba">
        <button class="iop-cakaj" onclick="event.stopPropagation();prenesiVCakajoce(${it.idx})" title="Prenesi v čakajoče (razdelitev v več boxov)">⏳ Prenesi v čakajoče</button>
      </div>`;
  }

  // sličica izdelka (če že naložena)
  const imgUrl = SKU_IMAGES[it.sku];
  const thumbInner = imgUrl
    ? `<img src="${esc(imgUrl)}" alt="" loading="lazy" onclick="event.stopPropagation();openImgPreview('${jsStr(imgUrl)}','${jsStr(it.sku)}')">`
    : '';
  const thumb = `<span class="item-thumb ${imgUrl?'has-img':''}" id="imgthumb-${it.idx}" ${imgUrl?'data-loaded="1"':''}>${thumbInner}</span>`;

  return `
    <div class="item ${cls} ${locked?'item-locked':''} ${rs?'item-rs':''}" id="item-${it.idx}">
      <span class="id-col">${esc(it.id || '—')}</span>
      <div class="item-mobile-top">
        ${thumb}
        <span class="sku" style="${_skuFontStyle(it.sku)}">${esc(it.sku)}</span>
        ${_pozCellHtml(it)}
      </div>
      <div class="item-naziv-wrap">
        <span class="naziv" title="${esc(it.naziv)}">${esc(it.naziv)}${it.low ? '<span class="tag-low">Nizka zaloga</span>' : ''}${it.hsplus ? '<span class="tag-hsplus">📦 HS PLUS</span>' : ''}${(!it.id || String(it.id).trim() === '' || String(it.id).trim() === '—') ? '<span class="tag-supplier">🏷 Majhni dobavitelji</span>' : ''}${it.skladisce ? '<span class="tag-sklad">🏬 Skladišče2</span>' : ''}</span>
        ${boxInline}
      </div>
      <div class="item-bottom">
        <div class="qty-step ${mismatch}">
          <button class="qty-btn" onclick="changeQty(${it.idx}, -1)">−</button>
          <div style="display:flex;flex-direction:column;align-items:center" onclick="editQty(${it.idx})" title="Klikni za vnos števila">
            <span class="qty-val" id="qtyval-${it.idx}">${it.picked}</span>
            <span class="qty-need">/ ${it.qty}</span>
          </div>
          <button class="qty-btn" onclick="changeQty(${it.idx}, 1)">+</button>
        </div>
        <div class="item-actions">
          <button class="act-btn act-ok ${it.status==='ok'?'active':''}" onclick="setStatus(${it.idx}, 'ok')" title="Nabrano">✓</button>
          <button class="act-btn act-ni ${it.status==='ni'?'active':''}" onclick="setStatus(${it.idx}, 'ni')" title="Ni na zalogi">✕</button>
        </div>
      </div>
      ${opombaRow}
    </div>`;
}

// ── Direkten vnos količine (klik na cifro) ──
function editQty(idx) {
  const it = ITEMS.find(x => x.idx === idx);
  if (!it) return;
  const span = document.getElementById('qtyval-' + idx);
  if (!span || span.querySelector('input')) return;  // že v urejanju
  const cur = it.picked;
  // Zamenjaj span vsebino z inputom
  span.innerHTML = `<input type="number" inputmode="numeric" value="${cur}" min="0"
    style="width:64px;text-align:center;font-size:20px;font-weight:800;padding:4px;border:2px solid var(--accent);border-radius:8px;background:var(--panel);color:var(--text);font-family:inherit"
    onclick="event.stopPropagation()" onkeydown="if(event.key==='Enter')this.blur()" onblur="commitQty(${idx}, this.value)">`;
  const inp = span.querySelector('input');
  inp.focus();
  inp.select();
}

function commitQty(idx, val) {
  const it = ITEMS.find(x => x.idx === idx);
  if (!it) return;
  let n = parseInt(val);
  if (isNaN(n) || n < 0) n = 0;
  it.picked = n;
  refreshItem(it);
  refreshSidebarAndStats();
  saveItem(idx, { picked: it.picked });
}

// ── Statistika skupine ──
function groupStat(items) {
  const total = items.length;
  const ok = items.filter(it => it.status === 'ok').length;
  const ni = items.filter(it => it.status === 'ni').length;
  const todo = total - ok - ni;
  const done = ok + ni;
  // odstotki po POSTAVKAH (zaokroženi tako da vsota = 100)
  const pctOk = total ? Math.round(ok / total * 100) : 0;
  const pctNi = total ? Math.round(ni / total * 100) : 0;
  const pctTodo = total ? (100 - pctOk - pctNi) : 0;
  const pct = total ? Math.round(done / total * 100) : 0;  // skupno obdelano (compat)

  // odstotki po KOSIH (za natančnejši graf — delni manjko se vidi kot rdeč košček)
  let qNeed = 0, qOk = 0, qMiss = 0, qTodo = 0;
  items.forEach(it => {
    const q = it.qty || 0;
    qNeed += q;
    if (it.status === 'ok') { qOk += it.picked; qMiss += Math.max(0, q - it.picked); }
    else if (it.status === 'ni') { qMiss += q; }
    else { qTodo += q; }
  });
  const qPctOk = qNeed ? Math.round(qOk / qNeed * 100) : 0;
  const qPctNi = qNeed ? Math.round(qMiss / qNeed * 100) : 0;
  const qPctTodo = qNeed ? Math.max(0, 100 - qPctOk - qPctNi) : 0;

  // varni odstotek za prikaz: 100% SAMO če je vse obdelano (sicer navzdol, da 99.x% ni 100%)
  const allDone = total > 0 && done >= total;
  const pctOkDisplay = allDone ? 100 : Math.min(99, Math.floor(total ? ok / total * 100 : 0));

  return { total, done, ok, ni, todo, pct, pctOk, pctNi, pctTodo, pctOkDisplay, allDone,
           qNeed, qOk, qMiss, qTodo, qPctOk, qPctNi, qPctTodo };
}

// ── Tekstovni razrez (npr. "90% nabrano · 5% ni najdeno · 5% še nabirajo") ──
function statBreakdownText(s) {
  if (!s.total) return '';
  const parts = [];
  if (s.pctOk > 0) parts.push(`${s.pctOk}% nabrano`);
  if (s.pctNi > 0) parts.push(`${s.pctNi}% ni najdeno`);
  if (s.pctTodo > 0) parts.push(`${s.pctTodo}% še nabirajo`);
  return parts.join(' · ');
}

// ── Segmentiran bar (zeleno / rdeče / sivo) — po KOSIH (delni manjko = rdeč košček) ──
function progBarSegments(s) {
  return `
    <div class="prog-seg prog-seg-ok" style="width:${s.qPctOk}%"></div>
    <div class="prog-seg prog-seg-ni" style="width:${s.qPctNi}%"></div>
    <div class="prog-seg prog-seg-todo" style="width:${s.qPctTodo}%"></div>`;
}

// ── Sidebar ──
let SIDEBAR_TAB = 'manjko';  // RS aktivni tab (Opombe odstranjen)

function mankoItemHtml(it) {
  const missingQty = it.status === 'ni' ? it.qty : (it.qty - it.picked);
  return `
    <div class="manko-item">
      <div class="top">
        <span class="msku" onclick="copySkuFromManko(this,'${esc(it.sku)}')" title="Klikni za kopiranje SKU" style="cursor:pointer;user-select:none">${esc(it.sku)} <span class="mpoz-copy-icon">⎘</span></span>
        <span class="mqty">manjka ${missingQty}${it.status==='ni'?' (cela)':''}</span>
      </div>
      <div class="mnaziv" title="${esc(it.naziv)}">${esc(it.naziv)}</div>
      <div class="mpoz-badge mpoz-jump" onclick="jumpToItem(${it.idx})" title="Klikni za skok na postavko" style="cursor:pointer;user-select:none">📍 ${esc(it.poz)} <span class="mpoz-jump-icon">↗</span></div>
      <div class="mpoz-detail">potrebno ${it.qty} · nabrano ${it.status==='ni'?0:it.picked}</div>
    </div>`;
}

function opombaItemHtml(it) {
  return `
    <div class="opomba-item">
      <div class="top">
        <span class="osku">${esc(it.sku)}</span>
        <span class="oboxnote">${esc(it.opomba)}</span>
      </div>
      <div class="onaziv" title="${esc(it.naziv)}">${esc(it.naziv)}</div>
      <div class="opoz-badge" onclick="copySkuFromManko(this,'${esc(it.sku)}')" title="Klikni za kopiranje SKU" style="cursor:pointer;user-select:none">📍 ${esc(it.poz)} <span class="mpoz-copy-icon">⎘</span></div>
    </div>`;
}

function boxiHtml() {
  // zberi zaklenjene postavke po boxu
  const boxes = {};
  ITEMS.forEach(it => {
    if (it.locked && it.box) (boxes[it.box] = boxes[it.box] || []).push(it);
  });
  const keys = Object.keys(boxes).sort((a,b) => String(a).localeCompare(String(b),'sl',{numeric:true}));
  if (!keys.length) return '<div class="manko-empty">Še ni zaklenjenih boxov.</div>';
  return keys.map(b => `
    <div class="box-group">
      <div class="box-group-head" style="${boxStyle(b)}">📦 BOX ${esc(b)} <span class="box-group-count">${boxes[b].length}</span></div>
      ${boxes[b].map(it => `
        <div class="box-line">
          <span class="box-line-sku" onclick="copySkuFromManko(this,'${esc(it.sku)}')" title="Kopiraj SKU" style="cursor:pointer">${esc(it.sku)} <span class="mpoz-copy-icon">⎘</span></span>
          <span class="box-line-poz">${esc(it.poz)}</span>
        </div>`).join('')}
    </div>`).join('');
}

function _hsplusManjko() {
  // SKU-ji ki so HKRATI na HS PLUS seznamu (hsplus) IN v manjku.
  // Manjko = ni-postavke (cela qty) + ok-postavke z delnim manjkom (qty - picked).
  const out = [];
  (ITEMS || []).forEach(it => {
    if (!it.hsplus) return;
    let manjka = 0;
    if (it.status === 'ni') manjka = it.qty || 0;                       // cela postavka manjka
    else if (it.status === 'ok' && it.picked < it.qty) manjka = it.qty - it.picked;  // delni manjko
    else if (it.status === '' ) manjka = it.qty || 0;                   // še ne obdelano → rabimo vse
    if (manjka > 0) out.push({ sku: it.sku, naziv: it.naziv, poz: it.poz, manjka });
  });
  out.sort((a,b) => (a.poz||'').localeCompare(b.poz||'', 'sl', {numeric:true}));
  return out;
}

function hsplusHtml() {
  const list = _hsplusManjko();
  if (!list.length) return '<div class="manko-empty">Ni HS PLUS izdelkov v manjku.</div>';
  return `
    <div class="hsplus-hint">📦 Ti izdelki pridejo danes — pobrati je treba prikazano količino iz HS PLUS prihoda.</div>
    <button class="hsplus-print-btn" onclick="printHsplus()">🖨️ Natisni seznam</button>
    ${list.map(it => `
      <div class="box-line hsplus-line">
        <span class="box-line-sku" onclick="copySkuFromManko(this,'${esc(it.sku)}')" title="Kopiraj SKU" style="cursor:pointer">${esc(it.sku)} <span class="mpoz-copy-icon">⎘</span></span>
        <span class="hsplus-right"><span class="hsplus-qty">${it.manjka} kos</span><span class="box-line-poz">${esc(it.poz)}</span></span>
      </div>`).join('')}`;
}

// Natisni HS PLUS seznam (SKU + količina + pozicija)
function printHsplus() {
  const list = _hsplusManjko();
  if (!list.length) { alert('Ni HS PLUS izdelkov v manjku.'); return; }
  const danes = new Date().toLocaleDateString('sl-SI');
  const rows = list.map(it => `<tr><td>${esc(it.sku)}</td><td style="text-align:center;font-weight:700">${it.manjka}</td><td>${esc(it.poz)}</td></tr>`).join('');
  const w = window.open('', '_blank');
  w.document.write(`<!DOCTYPE html><html><head><meta charset="utf-8"><title>HS PLUS seznam</title>
    <style>
      body{font-family:Arial,sans-serif;padding:24px;color:#111}
      h1{font-size:20px;margin:0 0 4px}
      .sub{color:#666;font-size:13px;margin-bottom:18px}
      table{width:100%;border-collapse:collapse}
      th,td{border:1px solid #ccc;padding:8px 10px;font-size:14px;text-align:left}
      th{background:#f0f0f0;text-transform:uppercase;font-size:12px;letter-spacing:0.5px}
      tr:nth-child(even) td{background:#fafafa}
    </style></head><body>
    <h1>📦 HS PLUS — seznam za pobrati</h1>
    <div class="sub">${danes} · ${list.length} izdelkov · pobrati iz današnjega HS PLUS prihoda</div>
    <table><thead><tr><th>SKU</th><th style="text-align:center">Količina</th><th>Pozicija</th></tr></thead>
    <tbody>${rows}</tbody></table>
    <script>window.onload=function(){window.print();}<\/script>
    </body></html>`);
  w.document.close();
}

// Je postavka v manjku? Manjko = ni-postavka ali ok z delnim manjkom.
// IZJEMA: če je HS PLUS in dobava (hsplus_qty) pokrije CELOTEN manjko → ni več manjko (danes pride).
function _isManko(it) {
  let manjka = 0;
  if (it.status === 'ni') manjka = it.qty || 0;
  else if (it.status === 'ok' && it.picked < it.qty) manjka = it.qty - it.picked;
  else return false;
  if (manjka <= 0) return false;
  // HS PLUS pokritje: če dobava pokrije ves manjko, odstrani iz Manjko
  if (it.hsplus && (it.hsplus_qty != null) && it.hsplus_qty >= manjka) return false;
  return true;
}

function renderSidebar() {
  const manko = ITEMS.filter(_isManko);
  const opombe = ITEMS.filter(it => it.opomba && it.opomba.trim());
  let totalOk = ITEMS.filter(it => it.status === 'ok').length;
  let totalNi = ITEMS.filter(it => it.status === 'ni').length;
  let totalQtyNeed = ITEMS.reduce((s,it) => s + it.qty, 0);
  let totalQtyPicked = ITEMS.filter(it=>it.status==='ok').reduce((s,it) => s + it.picked, 0);
  // manjkajoči KOSI: "ni" → cela količina; "ok" z delnim primanjkljajem → razlika
  let totalQtyMissing = ITEMS.reduce((s,it) => {
    if (it.status === 'ni') return s + it.qty;
    if (it.status === 'ok' && it.picked < it.qty) return s + (it.qty - it.picked);
    return s;
  }, 0);
  let totalItems = ITEMS.length;

  // ── ČAKAJOČE (RS uvoz dobavnice, kol>1): združi postavke IN kose ──
  // Vsaka čakajoča = 1 postavka (šteje v "Vseh postavk" od začetka).
  // assigned = razdeljeni (nabrani) kosi → vedno štejejo kot nabrani.
  // PREOSTANEK (need - assigned) gre v "Manjka (kosov)" SAMO ko je čakajoča ZAKLJUČENA (done).
  // Dokler ni zaključena (še razdeljujemo / nedotaknjena) → preostanek NE šteje v manjko.
  const cak = getCakajoce();
  if (cak && cak.length) {
    cak.forEach(c => {
      const need = c.qty || 0;
      const assigned = Math.min(c.assigned || 0, need);
      const ostane = Math.max(0, need - assigned);
      const isFull = assigned >= need;          // vse razdeljeno
      const isClosed = !!c.done;                 // zaključena (poln ali z manjkom)
      totalItems += 1;
      totalQtyNeed += need;
      totalQtyPicked += assigned;
      // obdelana/nabrana postavka: ko je polna ALI zaključena z manjkom
      if (isFull || isClosed) { totalOk += 1; }
      // preostanek v manjko le ob zaključku z manjkom
      if (isClosed && ostane > 0) { totalQtyMissing += ostane; }
    });
  }

  const totalDone = totalOk + totalNi;

  // ── VAROVALKA: opozori, če so skupne postavke/kosi padli pod baseline (možna napaka/izbris) ──
  let integrityBanner = '';
  const ig = SESSION && SESSION.integrity;
  if (ig && ig.ok === false) {
    const parts = [];
    if (ig.dropped_items > 0) parts.push(`${ig.dropped_items} postavk`);
    if (ig.dropped_qty > 0) parts.push(`${ig.dropped_qty} kosov`);
    integrityBanner = `
      <div class="integrity-warn" title="Skupni seštevek je padel pod doslej zabeleženo vrednost — možen izbris ali napaka.">
        <span class="iw-ico">⚠️</span>
        <div class="iw-txt">
          <b>Pozor: seštevek se je zmanjšal!</b>
          <span>Manjka ${parts.join(' in ')} glede na prej (${ig.cur_items}/${ig.peak_items} postavk, ${ig.cur_qty}/${ig.peak_qty} kosov). Preveri, ali je prišlo do izbrisa.</span>
        </div>
      </div>`;
  }

  const statCard = `
    <div class="side-card">
      <h3>📊 Skupna statistika</h3>
      ${integrityBanner}
      <div class="stat-rows">
        <div class="stat-row"><span class="lbl">Vseh postavk</span><span class="val">${totalItems}</span></div>
        <div class="stat-row"><span class="lbl">Obdelanih</span><span class="val">${totalDone}</span></div>
        <div class="stat-row"><span class="lbl">Nabrano (OK)</span><span class="val ok">${totalOk}</span></div>
        <div class="stat-row"><span class="lbl">Manjka (postavk)</span><span class="val ni">${totalNi}</span></div>
        <div class="stat-row"><span class="lbl">Manjka (kosov)</span><span class="val ni">${totalQtyMissing}</span></div>
        <div class="stat-row" style="border-top:1px solid var(--border);padding-top:10px;margin-top:2px">
          <span class="lbl">Kosov nabrano</span><span class="val">${totalQtyPicked} / ${totalQtyNeed}</span></div>
      </div>
    </div>`;

  const hsCount = _hsplusManjko().length;   // samo HS PLUS ki so v manjku

  if (!isRS()) {
    // SLO — tabi Manjko + HS PLUS (HS PLUS samo če obstaja kak označen)
    let tabContent;
    if (SIDEBAR_TAB === 'hsplus') {
      tabContent = hsplusHtml();
    } else {
      tabContent = manko.length
        ? `<button class="manko-copy-all manko-copy-all-rs" onclick="copyAllManko(this)" title="Kopiraj vse manjkajoče (SKU + količina)">⎘ Kopiraj vse</button>` + manko.map(mankoItemHtml).join('')
        : '<div class="manko-empty">Zaenkrat ni manjkajočih postavk 🎉</div>';
    }
    return `
      <div class="sidebar">
        ${statCard}
        <div class="side-card side-card-tabs">
          <div class="side-tabs">
            <button class="side-tab side-tab-manjko ${SIDEBAR_TAB!=='hsplus'?'active':''}" onclick="setSidebarTab('manjko')">⚠️ Manjko ${manko.length?`<span class="st-badge st-red">${manko.length}</span>`:''}</button>
            ${hsCount ? `<button class="side-tab side-tab-hsplus ${SIDEBAR_TAB==='hsplus'?'active':''}" onclick="setSidebarTab('hsplus')">📦 HS PLUS <span class="st-badge st-purple">${hsCount}</span></button>` : ''}
          </div>
          <div class="side-tab-body">${tabContent}</div>
        </div>
      </div>`;
  }

  // RS — tabi Manjko / Boxi / HS PLUS
  let tabContent;
  if (SIDEBAR_TAB === 'boxi') {
    tabContent = boxiHtml();
  } else if (SIDEBAR_TAB === 'hsplus') {
    tabContent = hsplusHtml();
  } else {
    // privzeto Manjko
    tabContent = manko.length
      ? `<button class="manko-copy-all manko-copy-all-rs" onclick="copyAllManko(this)" title="Kopiraj vse manjkajoče (SKU + količina)">⎘ Kopiraj vse</button>` + manko.map(mankoItemHtml).join('')
      : '<div class="manko-empty">Ni manjka 🎉</div>';
  }

  return `
    <div class="sidebar">
      ${statCard}
      <div class="side-card side-card-tabs">
        <div class="side-tabs">
          <button class="side-tab side-tab-manjko ${(SIDEBAR_TAB!=='boxi'&&SIDEBAR_TAB!=='hsplus')?'active':''}" onclick="setSidebarTab('manjko')">⚠️ Manjko ${manko.length?`<span class="st-badge st-red">${manko.length}</span>`:''}</button>
          <button class="side-tab side-tab-boxi ${SIDEBAR_TAB==='boxi'?'active':''}" onclick="setSidebarTab('boxi')">📦 Boxi</button>
          ${hsCount ? `<button class="side-tab side-tab-hsplus ${SIDEBAR_TAB==='hsplus'?'active':''}" onclick="setSidebarTab('hsplus')">📦 HS PLUS <span class="st-badge st-purple">${hsCount}</span></button>` : ''}
        </div>
        <div class="side-tab-body">${tabContent}</div>
      </div>
    </div>`;
}

function setSidebarTab(tab) {
  SIDEBAR_TAB = tab;
  refreshSidebarAndStats();
}

// ── Global stat (top bar) ──
function updateGlobalStat() {
  const stat = groupStat(ITEMS);
  // ČAKAJOČE (RS uvoz, kol>1): vsaka šteje kot 1 postavka v SKUPNI statistiki.
  // done:true (razdeljena v bokse) = nabrana (ok); sicer = še nabirajo (todo).
  const cak = getCakajoce();
  if (cak && cak.length) {
    let cOk = 0;
    cak.forEach(c => {
      const need = c.qty || 0;
      const assigned = Math.min(c.assigned || 0, need);
      const isFull = assigned >= need;
      const isClosed = !!c.done;
      if (isFull || isClosed) cOk++;
    });
    const cTodo = cak.length - cOk;
    stat.total += cak.length;
    stat.ok    += cOk;
    stat.todo  += cTodo;
    stat.done  += cOk;
    // preračun odstotkov po postavkah (vsota = 100)
    stat.pctOk   = stat.total ? Math.round(stat.ok / stat.total * 100) : 0;
    stat.pctNi   = stat.total ? Math.round(stat.ni / stat.total * 100) : 0;
    stat.pctTodo = stat.total ? (100 - stat.pctOk - stat.pctNi) : 0;
    stat.pct     = stat.total ? Math.round(stat.done / stat.total * 100) : 0;
    // bar po kosih: assigned = nabrano (zeleno). Preostanek → rdeče (manjko) le ob zaključku;
    // dokler ni zaključeno, preostanek ostane sivo (todo).
    cak.forEach(c => {
      const need = c.qty || 0;
      const assigned = Math.min(c.assigned || 0, need);
      const ostane = Math.max(0, need - assigned);
      stat.qNeed += need;
      stat.qOk   += assigned;
      if (c.done && ostane > 0) stat.qMiss += ostane;
      else stat.qTodo += ostane;
    });
    stat.qPctOk   = stat.qNeed ? Math.round(stat.qOk / stat.qNeed * 100) : 0;
    stat.qPctNi   = stat.qNeed ? Math.round(stat.qMiss / stat.qNeed * 100) : 0;
    stat.qPctTodo = stat.qNeed ? Math.max(0, 100 - stat.qPctOk - stat.qPctNi) : 0;
  }
  const bar = document.getElementById('globalBar');
  if (bar) bar.innerHTML = progBarSegments(stat);
  const mprog = document.getElementById('mobileProg');
  if (mprog) mprog.innerHTML = progBarSegments(stat);  // noga (mobile) — isti segmenti
  const pctEl = document.getElementById('globalPct');
  if (pctEl) {
    // 100% SAMO če je res vse obdelano; sicer zaokroži navzdol (99.6% → 99%, ne 100%)
    const allDone = stat.total > 0 && stat.done >= stat.total;
    const displayPct = allDone ? 100 : Math.min(99, Math.floor(stat.total ? stat.ok / stat.total * 100 : 0));
    pctEl.textContent = displayPct + '%';
    pctEl.style.color = displayPct === 100 ? 'var(--ok)' : 'var(--text)';
  }
  const doneEl = document.getElementById('globalDone');
  if (doneEl) doneEl.textContent = `${stat.done} / ${stat.total}`;
  const breakEl = document.getElementById('globalBreak');
  if (breakEl) breakEl.textContent = statBreakdownText(stat) || 'skupna uspešnost';
  updatePickTimer();
  updateStickyOffset();  // višina headerja se lahko spremeni (global-stat se prikaže)
}

// ═══ ČASOVNICA NABIRANJA (desktop) ═══
// Bere SESSION.pick_started_at / pick_finished_at (server-side). Teče živo do 100%.
let _pickTimerInt = null;

function _parseServerTs(s) {
  // Strežnik pošlje ISO žig. Če nima oznake cone (Z ali +HH:MM), ga razumi kot UTC
  // (Render teče v UTC). Brez tega bi brskalnik žig brez cone bral kot lokalni čas → +2h.
  if (!s) return NaN;
  const hasTz = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(s);
  return new Date(hasTz ? s : s + 'Z').getTime();
}

function _fmtDur(secs) {
  secs = Math.max(0, Math.floor(secs));
  const h = Math.floor(secs / 3600);
  const m = Math.floor((secs % 3600) / 60);
  const s = secs % 60;
  const pad = n => String(n).padStart(2, '0');
  return `${h}:${pad(m)}:${pad(s)}`;   // vedno H:MM:SS (npr. 0:00:00)
}

function updatePickTimer() {
  const wrap = document.getElementById('globalTimer');
  const timeEl = document.getElementById('gsTimerTime');
  const lblEl = document.getElementById('gsTimerLbl');
  if (!wrap || !timeEl || !lblEl) return;
  const sess = SESSION || {};
  const startStr = sess.pick_started_at;
  const finishStr = sess.pick_finished_at;
  const pausedStr = sess.pick_paused_at;
  const offset = (sess.pick_pause_offset_s || 0);

  // ustavi obstoječi tick (ponovno nastavimo po potrebi)
  if (_pickTimerInt) { clearInterval(_pickTimerInt); _pickTimerInt = null; }

  if (!startStr) {
    // še ni začetka
    wrap.classList.remove('running', 'done');
    timeEl.textContent = '00:00';
    lblEl.textContent = 'čaka prvo postavko';
    return;
  }
  const startMs = _parseServerTs(startStr);

  if (finishStr) {
    // končano — fiksen čas (z offsetom)
    const finMs = _parseServerTs(finishStr);
    wrap.classList.remove('running');
    wrap.classList.add('done');
    timeEl.textContent = '🏁 ' + _fmtDur((finMs - startMs) / 1000 - offset);
    lblEl.textContent = 'končni čas';
    return;
  }

  if (pausedStr) {
    // PAVZA — zamrznjen čas (offset že upoštevan)
    const pausedMs = _parseServerTs(pausedStr);
    wrap.classList.remove('running');
    wrap.classList.add('done');
    timeEl.textContent = '⏸ ' + _fmtDur((pausedMs - startMs) / 1000 - offset);
    lblEl.textContent = 'pavza';
    return;
  }

  // teče — živ tick (odštej offset prej pavziranih sekund)
  wrap.classList.remove('done');
  wrap.classList.add('running');
  lblEl.textContent = 'čas nabiranja';
  const tick = () => { timeEl.textContent = _fmtDur((Date.now() - startMs) / 1000 - offset); };
  tick();
  _pickTimerInt = setInterval(tick, 1000);
}

// Izmeri višino lepljivega vrha (header) → CSS var --sticky-h, da glava police lahko
// nalepi točno pod njim (višina ni fiksna: global-stat se prikaže/skrije, gumbi se ovijejo).
function updateStickyOffset() {
  const hdr = document.querySelector('.sticky-header');
  if (!hdr) return;
  // Na mobile je header FIKSNA NOGA (dno) — vrh je prazen, zato se glava police lepi na top:0.
  if (isMobile()) {
    document.documentElement.style.setProperty('--sticky-h', '0px');
    // izmeri višino noge → RS box-bar in spodnji odmik seznamov se prilagodita
    const fh = Math.round(hdr.getBoundingClientRect().height);
    document.documentElement.style.setProperty('--footer-h', fh + 'px');
    return;
  }
  const h = Math.round(hdr.getBoundingClientRect().height);
  document.documentElement.style.setProperty('--sticky-h', h + 'px');
}

// ── Toggle zavihek (persist per naprava) ──
function toggleShelf(g) {
  const expanded = getExpanded();
  const willOpen = !expanded[g];
  // Na mobile: samo 1 polica naenkrat (accordion) — zapri ostale ob odpiranju nove
  if (willOpen && isMobile()) {
    Object.keys(expanded).forEach(k => { if (k !== g) delete expanded[k]; });
    document.querySelectorAll('.shelf.open').forEach(el => {
      if (el.id !== 'shelf-' + cssId(g)) el.classList.remove('open');
    });
  }
  expanded[g] = willOpen;
  if (!expanded[g]) delete expanded[g];
  setExpanded(expanded);
  const el = document.getElementById('shelf-' + cssId(g));
  if (el) el.classList.toggle('open');
  // osveži spodnji sticky box-bar (sam poskrbi za skritje na SLO/desktop)
  updateMobileBoxBar();

  // UX mobile: ob ODPIRANJU police skoči na njen vrh (ker se stara zapre, layout se
  // skrči in scroll bi sicer pristal na napačnem mestu — pogosto vrglo na dno).
  if (willOpen && isMobile() && el) {
    // počakaj na skrčenje stare police (layout se posodobi), nato izmeri in scrollaj
    requestAnimationFrame(() => { requestAnimationFrame(() => {
      const boxbarH = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--boxbar-h')) || 0;
      const r = el.getBoundingClientRect();
      const y = window.scrollY + r.top - boxbarH - 8;   // glava police tik pod box-barom
      window.scrollTo({ top: Math.max(0, y), behavior: 'smooth' });
    }); });
    return;
  }

  // UX: ob ZAPIRANJU police — če je njena glava ušla nad vrh zaslona (ker se je
  // vsebina nad scrollom skrčila), jo prikaži nazaj, da ni treba ročno skrolati gor.
  if (!willOpen && el) {
    const head = el.querySelector('.shelf-head');
    const r = (head || el).getBoundingClientRect();
    // koliko prostora je zgoraj zasedeno (na desktopu lepljiv header; na mobile noga je spodaj → 0)
    const topOffset = isMobile() ? 0 : (parseInt(getComputedStyle(document.documentElement).getPropertyValue('--sticky-h')) || 0);
    if (r.top < topOffset) {
      const y = window.scrollY + r.top - topOffset - 8;  // 8px zraka nad glavo
      window.scrollTo({ top: Math.max(0, y), behavior: 'smooth' });
    }
  }
}

// Skoči na postavko: odpri njeno polico (če zaprta) in scrollaj+osvetli kartico.
function jumpToItem(idx) {
  const it = (ITEMS || []).find(x => x.idx === idx);
  if (!it) return;
  const g = it.group;
  // Zagotovi, da je polica ODPRTA — tudi če je s filtrom "samo odprto" skrita
  // (dokončana polica). Nastavi expanded in PONOVNO renderiraj, da pride v DOM.
  const expanded = getExpanded();
  const wasHiddenOrClosed = !expanded[g] || !document.getElementById('shelf-' + cssId(g));
  if (!expanded[g]) {
    if (isMobile()) Object.keys(expanded).forEach(k => { if (k !== g) delete expanded[k]; });
    expanded[g] = true;
    setExpanded(expanded);
  }
  if (wasHiddenOrClosed) {
    render();             // skrita polica (filter ON) pride v DOM
    updateMobileBoxBar();
  }
  // po renderju scrollaj do postavke + osvetli
  setTimeout(() => {
    const card = document.getElementById('item-' + idx);
    if (!card) return;
    const topOffset = isMobile() ? (parseInt(getComputedStyle(document.documentElement).getPropertyValue('--boxbar-h')) || 70) : (parseInt(getComputedStyle(document.documentElement).getPropertyValue('--sticky-h')) || 0);
    const r = card.getBoundingClientRect();
    const y = window.scrollY + r.top - topOffset - 16;
    window.scrollTo({ top: Math.max(0, y), behavior: 'smooth' });
    card.classList.add('item-jump-flash');
    setTimeout(() => card.classList.remove('item-jump-flash'), 1600);
  }, 120);
}

// Ali smo na mobilnem (ozek zaslon) — usklajeno z @media (max-width: 768px)
function isMobile() {
  return window.matchMedia('(max-width: 768px)').matches;
}

// RS mobile: posodobi spodnji sticky box-bar glede na trenutno odprto polico
function updateMobileBoxBar() {
  const host = document.getElementById('mobileBoxBar');
  if (!host) return;
  const hide = () => { host.innerHTML = ''; host.style.display = 'none'; document.body.classList.remove('has-boxbar'); };
  if (!isRS() || !isMobile()) { hide(); return; }
  const expanded = getExpanded();
  const openGroups = Object.keys(expanded).filter(k => expanded[k]);
  if (!openGroups.length) { hide(); return; }
  const group = openGroups[0];  // na mobile je odprta le ena
  const items = (ITEMS || []).filter(it => it.group === group);
  if (!items.length) { hide(); return; }
  host.innerHTML = shelfBoxBar(group, items, true);  // true = mobilna varianta (brez label)
  host.style.display = 'block';
  document.body.classList.add('has-boxbar');
  // izmeri višino box-bara → police se lepijo točno pod njim
  requestAnimationFrame(() => {
    const h = Math.round(host.getBoundingClientRect().height);
    if (h > 0) document.documentElement.style.setProperty('--boxbar-h', h + 'px');
  });
}

// ── Spremeni količino ──
function changeQty(idx, delta) {
  const it = ITEMS.find(x => x.idx === idx);
  if (!it) return;
  it.picked = Math.max(0, it.picked + delta);
  // posodobi samo to vrstico (brez polnega re-renderja, da ne zapre zavihka)
  refreshItem(it);
  refreshSidebarAndStats();
  saveItem(idx, { picked: it.picked });
  reorderShelf(it.group);   // delni manjko (npr. 5/6) → pripni na vrh
}

// ── Status OK/NI ──
function setStatus(idx, status) {
  const it = ITEMS.find(x => x.idx === idx);
  if (!it) return;
  // toggle: če že isti status, prekliči
  it.status = (it.status === status) ? '' : status;
  refreshItem(it);
  refreshShelfProgress(it.group);
  refreshSidebarAndStats();
  updateGlobalStat();
  syncFilterToggleLabel();  // osveži števec polic na gumbu filtra
  if (isRS()) refreshBoxCounters();  // posodobi globalni števec obkljukanih brez boxa
  saveItem(idx, { status: it.status });
  reorderShelf(it.group);   // pripni manjko na vrh police (takoj ob ✓/✗)
  // filter "Samo odprto": če polica ravno postane dokončana, jo samodejno skrij (brez osvežitve)
  maybeAutoHideShelf(it.group);
}

// Prerazporedi vrstice znotraj police: manjko (✗/delni ✓) na vrh, kot pripeto.
// Premakne DOM elemente brez polnega re-renderja (ohrani odprte police in box-bare).
function reorderShelf(group) {
  const shelf = document.getElementById('shelf-' + cssId(group));
  if (!shelf) return;
  const body = shelf.querySelector('.shelf-body');
  if (!body) return;
  const groups = groupItems();
  const items = _sortMankoTop(groups[group] || []);
  // prestavi item-vrstice v želeni vrstni red (appendChild premakne obstoječ element)
  items.forEach(it => {
    const row = document.getElementById('item-' + it.idx);
    if (row) body.appendChild(row);
  });
}

// Če je filter "Samo odprto" aktiven in je polica zdaj dokončana (vse postavke obdelane),
// jo z rahlo animacijo skrij — brez ročne osvežitve.
function maybeAutoHideShelf(group) {
  if (!getDoneFilter()) return;
  const groups = groupItems();
  const items = groups[group] || [];
  const stat = groupStat(items);
  const isDone = stat.total > 0 && stat.todo === 0;
  if (!isDone) return;
  const el = document.getElementById('shelf-' + cssId(group));
  if (!el || el.classList.contains('shelf-hiding')) return;
  el.classList.add('shelf-hiding');           // sproži fade/collapse animacijo (CSS)
  setTimeout(() => {
    // odstrani iz pogleda (zapri + render, da se odšteje iz seznama)
    const expanded = getExpanded();
    delete expanded[group];
    setExpanded(expanded);
    render();
  }, 420);  // ujema se s trajanjem CSS animacije
}

// RS: osveži globalni števec (✓ N) v vseh box-barih + spodnji mobilni bar
function refreshBoxCounters() {
  const n = globalPendingCount();
  document.querySelectorAll('.shelf-box-bar').forEach(bar => {
    if (bar.closest('#mobileBoxBar')) return;  // mobilni posodobimo posebej spodaj
    let badge = bar.querySelector('.sbb-count');
    if (n > 0) {
      const txt = `✓ ${n} čaka`;
      if (badge) badge.textContent = txt;
      else {
        badge = document.createElement('span');
        badge.className = 'sbb-count';
        badge.title = 'Obkljukanih brez boxa (čez vse police)';
        badge.textContent = txt;
        const sel = bar.querySelector('.sbb-select');
        if (sel) sel.insertAdjacentElement('afterend', badge);
      }
    } else if (badge) {
      badge.remove();
    }
  });
  updateMobileBoxBar();
}

// ── Osveži eno vrstico (in-place) ──
function refreshItem(it) {
  const el = document.getElementById('item-' + it.idx);
  if (!el) return;
  el.outerHTML = itemRow(it);
}

// ── Osveži progress bar zavihka ──
function refreshShelfProgress(group) {
  const groups = groupItems();
  const items = groups[group] || [];
  const stat = groupStat(items);
  const shelf = document.getElementById('shelf-' + cssId(group));
  if (!shelf) return;
  const isDone = stat.total > 0 && stat.todo === 0;
  shelf.classList.toggle('shelf-done', isDone);
  const bar = shelf.querySelector('.shelf-prog-bar');
  const pct = shelf.querySelector('.shelf-prog-pct');
  if (bar) bar.innerHTML = progBarSegments(stat);
  if (pct) { pct.textContent = (isDone ? '✓ ' : '') + stat.pctOk + '%'; pct.style.color = 'var(--text)'; }
  // mobilno obarvano ozadje glave (predlog 3) — posodobi sproti ob kliku ✓/✗ (po KOSIH)
  const fill = shelf.querySelector('.shelf-head-fill');
  if (fill) {
    fill.style.setProperty('--fill-ok', stat.qPctOk + '%');
    fill.style.setProperty('--fill-ni', (stat.qPctOk + stat.qPctNi) + '%');
  }
}

// ── Osveži sidebar ──
function refreshSidebarAndStats() {
  const sb = document.querySelector('.sidebar');
  if (sb) {
    const tmp = document.createElement('div');
    tmp.innerHTML = renderSidebar();
    sb.replaceWith(tmp.firstElementChild);
  }
}

// ── Live save na disk ──
async function saveItem(idx, patch) {
  try {
    const r = await fetch('/zaloga-update-item', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ idx, market: MARKET, ...patch })
    });
    const data = await r.json();
    if (data && data.ok && SESSION) {
      // osveži časovnico (server pove, kdaj se je začelo/končalo nabiranje)
      const prevStart = SESSION.pick_started_at, prevFin = SESSION.pick_finished_at, prevPause = SESSION.pick_paused_at;
      SESSION.pick_started_at = data.pick_started_at || null;
      SESSION.pick_finished_at = data.pick_finished_at || null;
      SESSION.pick_paused_at = data.pick_paused_at || null;
      SESSION.pick_pause_offset_s = data.pick_pause_offset_s || 0;
      if (prevStart !== SESSION.pick_started_at || prevFin !== SESSION.pick_finished_at || prevPause !== SESSION.pick_paused_at) {
        updatePickTimer();
      }
    }
  } catch(e) { /* tiho — nabiralec ne sme biti moten */ }
}

// ── Arhiviraj ──
async function archiveSession(force) {
  if (!force && !confirm('Arhiviram trenutno nabiranje?\n\nSeznam se zaključi in shrani v zgodovino. Nov CSV lahko naložiš za novo nabiranje.')) return;
  try {
    const r = await fetch('/zaloga-archive', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ market: MARKET, force: !!force })
    });
    const data = await r.json();
    if (data.ok) {
      toast('✓ Arhivirano');
      setExpanded({});  // počisti odprte zavihke
      showEmpty();
    } else if (data.warn_no_box) {
      // RS opozorilo: nabrane postavke brez boxa
      if (confirm(`⚠️ ${data.warn_no_box} nabranih postavk NIMA dodeljenega boxa!\n\nZa carinski pregled mora biti vsaka postavka v boxu.\n\nVseeno arhiviram?`)) {
        archiveSession(true);
      }
    } else {
      toast('✗ ' + (data.error || 'napaka'));
    }
  } catch(e) { toast('✗ ' + e.message); }
}

// ── Pomožne ──
function esc(s) { return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
// Pozicijski stolpec: primarna značka + druga vrstica (sekundarna lokacija ALI ＋ gumb).
// Vedno 2 etaži → enaka višina ne glede na to ali ima dodatno ali ne (in ali je nabrana).
// ── Sekundarne (backup) lokacije — modal ──
let _extraSku = null;
function openExtraPos(sku, naziv) {
  _extraSku = sku;
  document.getElementById('extraPosSku').textContent = sku;
  document.getElementById('extraPosNaziv').textContent = naziv || '';
  document.getElementById('extraPosInput').value = '';
  document.getElementById('extraPosStatus').innerHTML = '';
  extraPosRenderList();
  document.getElementById('extraPosModal').style.display = 'flex';
  setTimeout(() => { const i = document.getElementById('extraPosInput'); if (i) i.focus(); }, 60);
}
function closeExtraPos() { document.getElementById('extraPosModal').style.display = 'none'; _extraSku = null; }
function extraPosRenderList() {
  const wrap = document.getElementById('extraPosList');
  if (!wrap) return;
  const extras = EXTRA_POS[_extraSku] || [];
  const it = ITEMS.find(x => x.sku === _extraSku);
  const primary = it ? (it.poz || '—') : '—';
  let html = '<div class="ep-row ep-prim"><span class="ep-tag ep-tag-prim">PRIM</span><span class="ep-pos">' + esc(primary) + '</span><span class="ep-note">primarna</span></div>';
  if (extras.length) {
    html += extras.map(p =>
      '<div class="ep-row ep-sec"><span class="ep-tag ep-tag-sec">DOD</span><span class="ep-pos">' + esc(p) + '</span><span class="ep-del" onclick="removeExtraPos(\'' + jsStr(p) + '\')" title="Odstrani">🗑️</span></div>').join('');
  } else {
    html += '<div class="ep-empty">Ni dodatnih lokacij.</div>';
  }
  wrap.innerHTML = html;
}
async function addExtraPos() {
  if (!_extraSku) return;
  const pos = document.getElementById('extraPosInput').value.trim();
  const st = document.getElementById('extraPosStatus');
  if (!pos) { st.innerHTML = '<span style="color:var(--ni)">Vpiši pozicijo.</span>'; return; }
  st.innerHTML = '<span style="color:var(--text-dim)">⏳ dodajam...</span>';
  try {
    const r = await fetch('/zaloga-extra-position-add', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ sku: _extraSku, position: pos }) });
    const d = await r.json();
    if (d.ok) {
      EXTRA_POS[_extraSku] = d.positions;
      document.getElementById('extraPosInput').value = '';
      st.innerHTML = '<span style="color:var(--ok)">✓ Dodano</span>';
      extraPosRenderList();
      refreshItemsForSku(_extraSku);
    } else { st.innerHTML = '<span style="color:var(--ni)">✗ ' + esc(d.error||'napaka') + '</span>'; }
  } catch(e) { st.innerHTML = '<span style="color:var(--ni)">✗ napaka</span>'; }
}
async function removeExtraPos(pos) {
  if (!_extraSku) return;
  const st = document.getElementById('extraPosStatus');
  try {
    const r = await fetch('/zaloga-extra-position-remove', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ sku: _extraSku, position: pos }) });
    const d = await r.json();
    if (d.ok) {
      if (d.positions && d.positions.length) EXTRA_POS[_extraSku] = d.positions;
      else delete EXTRA_POS[_extraSku];
      st.innerHTML = '<span style="color:var(--ok)">✓ Odstranjeno</span>';
      extraPosRenderList();
      refreshItemsForSku(_extraSku);
    } else { st.innerHTML = '<span style="color:var(--ni)">✗ ' + esc(d.error||'napaka') + '</span>'; }
  } catch(e) { st.innerHTML = '<span style="color:var(--ni)">✗ napaka</span>'; }
}
// po spremembi sekundarne lokacije osveži vse postavke s tem SKU (lahko jih je več)
function refreshItemsForSku(sku) {
  ITEMS.filter(x => x.sku === sku).forEach(x => { if (typeof refreshItem === 'function') refreshItem(x); });
}
let _extraSuggestTimer = null;
function extraPosSuggest(q) {
  clearTimeout(_extraSuggestTimer);
  const box = document.getElementById('extraPosSuggestList');
  if (!box) return;
  if (!(q || '').trim()) { box.style.display = 'none'; return; }
  _extraSuggestTimer = setTimeout(async () => {
    try {
      const r = await fetch('/pozicije-pos-suggest?q=' + encodeURIComponent((q||'').trim()));
      const d = await r.json();
      if (!d.ok || !d.suggestions.length) { box.style.display = 'none'; return; }
      box.innerHTML = d.suggestions.map(s =>
        '<div class="ep-suggest-item" onclick="pickExtraPos(\'' + jsStr(s) + '\')">📍 ' + esc(s) + '</div>').join('');
      box.style.display = 'block';
    } catch (e) { box.style.display = 'none'; }
  }, 180);
}
function pickExtraPos(pos) {
  document.getElementById('extraPosInput').value = pos;
  document.getElementById('extraPosSuggestList').style.display = 'none';
}

function _pozCellHtml(it) {
  const sku = it.sku || '';
  const extras = EXTRA_POS[String(sku).trim()] || [];
  const primary = '<span class="poz poz-edit" onclick="event.stopPropagation();openPozEdit(\'' + jsStr(sku) + '\',\'' + jsStr(it.poz||'') + '\',\'' + jsStr(it.naziv||'') + '\')" title="Klikni za popravek pozicije">' + esc(it.poz) + '</span>';
  let second;
  if (extras.length) {
    const chips = extras.map(p =>
      '<span class="poz-extra-chip">↳ ' + esc(p) + '</span>').join('');
    second = '<span class="poz-extra-row" onclick="event.stopPropagation();openExtraPos(\'' + jsStr(sku) + '\',\'' + jsStr(it.naziv||'') + '\')" title="Uredi dodatne lokacije"><span class="poz-extra-edit">✎</span>' + chips + '</span>';
  } else {
    second = '<span class="poz-add-btn" onclick="event.stopPropagation();openExtraPos(\'' + jsStr(sku) + '\',\'' + jsStr(it.naziv||'') + '\')" title="Dodaj dodatno lokacijo">＋ lokacija</span>';
  }
  return '<span class="poz-cell">' + primary + second + '</span>';
}

function _skuFontStyle(sku) {
  const n = String(sku == null ? '' : sku).length;
  let fs;
  if (n <= 12) fs = '';            // privzeto (14px)
  else if (n <= 16) fs = '13px';
  else if (n <= 20) fs = '11px';
  else if (n <= 26) fs = '9.5px';
  else fs = '8px';
  return (fs ? 'font-size:' + fs + ';' : '') + 'overflow:visible;text-overflow:clip;white-space:normal;word-break:break-all;line-height:1.15;';
}

// ── ISKALNIK SKU / naziv / pozicija ──
function toggleSkuSearch() {
  const ov = document.getElementById('skuSearchOverlay');
  if (!ov) return;
  if (ov.style.display === 'none' || !ov.style.display) { openSkuSearch(); } else { closeSkuSearch(); }
}
function openSkuSearch() {
  const ov = document.getElementById('skuSearchOverlay');
  if (!ov) return;
  ov.style.display = 'block';
  const inp = document.getElementById('skuSearchInput');
  if (inp) { inp.value = ''; setTimeout(() => inp.focus(), 60); }
  const res = document.getElementById('skuSearchResults');
  if (res) res.innerHTML = '';
}
function closeSkuSearch() {
  const ov = document.getElementById('skuSearchOverlay');
  if (ov) ov.style.display = 'none';
}
function skuSearchRun(q) {
  const res = document.getElementById('skuSearchResults');
  if (!res) return;
  q = (q || '').trim().toLowerCase();
  if (!q) { res.innerHTML = ''; return; }
  const hits = (ITEMS || []).filter(it =>
    (it.sku || '').toLowerCase().includes(q) ||
    (it.naziv || '').toLowerCase().includes(q) ||
    (it.poz || '').toLowerCase().includes(q)
  ).slice(0, 30);
  if (!hits.length) {
    res.innerHTML = '<div style="padding:14px;text-align:center;color:var(--text-faint);font-size:13px">Ni zadetkov.</div>';
    return;
  }
  res.innerHTML = hits.map(it => {
    const st = it.status === 'ok' ? '✅' : (it.status === 'ni' ? '❌' : '⬜');
    return '<div onclick="skuSearchJump(' + it.idx + ')" style="display:flex;align-items:center;gap:10px;padding:10px 11px;border-bottom:1px solid var(--border);cursor:pointer" onmouseover="this.style.background=\'var(--panel2)\'" onmouseout="this.style.background=\'\'">' +
      '<span style="font-size:15px">' + st + '</span>' +
      '<div style="flex:1;min-width:0">' +
        '<div style="font-size:14px;font-weight:600;color:var(--text);word-break:break-all">' + esc(it.sku || '—') + '</div>' +
        '<div style="font-size:11px;color:var(--text-faint);white-space:nowrap;overflow:hidden;text-overflow:ellipsis">' + esc(it.naziv || '') + '</div>' +
      '</div>' +
      '<span style="flex-shrink:0;font-size:12px;font-weight:700;color:#fff;background:var(--poz-bg);padding:4px 9px;border-radius:7px">' + esc(it.poz || '—') + '</span>' +
    '</div>';
  }).join('');
}
function skuSearchJumpFirst() {
  const q = (document.getElementById('skuSearchInput').value || '').trim().toLowerCase();
  if (!q) return;
  const hit = (ITEMS || []).find(it =>
    (it.sku || '').toLowerCase().includes(q) ||
    (it.naziv || '').toLowerCase().includes(q) ||
    (it.poz || '').toLowerCase().includes(q)
  );
  if (hit) skuSearchJump(hit.idx);
}
function skuSearchJump(idx) {
  closeSkuSearch();
  const el = document.getElementById('item-' + idx);
  if (!el) return;
  // razširi polico, če je zložena (police uporabljajo razred 'open')
  const shelf = el.closest('.shelf');
  if (shelf && !shelf.classList.contains('open')) {
    const head = shelf.querySelector('.shelf-head');
    if (head) head.click();
  }
  setTimeout(() => {
    el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    // utripni poudarek
    el.style.transition = 'box-shadow 0.3s, background 0.3s';
    const prevBg = el.style.background;
    el.style.boxShadow = '0 0 0 3px var(--accent)';
    el.style.background = 'var(--accent-dim)';
    setTimeout(() => { el.style.boxShadow = ''; el.style.background = prevBg; }, 1800);
  }, 120);
}
function jsStr(s) { return String(s).replace(/\\/g,'\\\\').replace(/'/g,"\\'"); }
function cssId(s) { return String(s).replace(/[^a-zA-Z0-9]/g, '_'); }

// Barva boxa iz številke — konsistentno (BOX1 vedno ista barva, BOX2 druga...).
// Uporablja zlati kot (137.5°) za dobro razpršene, razločljive odtenke.
function boxColor(boxNum) {
  const n = parseInt(String(boxNum).replace(/\D/g, '')) || 0;
  const hue = (n * 137.508) % 360;       // zlati kot → enakomerno razpršene barve
  return {
    bg: `hsl(${hue}, 70%, 92%)`,
    border: `hsl(${hue}, 65%, 62%)`,
    text: `hsl(${hue}, 70%, 30%)`,
  };
}
function boxStyle(boxNum) {
  const c = boxColor(boxNum);
  return `background:${c.bg};border-color:${c.border};color:${c.text}`;
}

let toastTimer;
function toast(msg, dur) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), dur || 2200);
}

// ── Auto-refresh (sync med napravami) — vsakih 15s preberi disk ──
let lastUpdate = null;
async function pollSync() {
  if (!ITEMS.length) return;
  try {
    const r = await fetch(mq('/zaloga-current'));
    const data = await r.json();
    if (data.ok && data.updated_at && data.updated_at !== lastUpdate) {
      lastUpdate = data.updated_at;
      // VAROVALKA: osveži integriteto in opozori, če je seštevek padel
      if (SESSION) {
        SESSION.integrity = data.integrity;
        const ig = data.integrity;
        if (ig && ig.ok === false) {
          const sig = ig.dropped_items + ':' + ig.dropped_qty;
          if (sig !== _lastIntegritySig) {
            _lastIntegritySig = sig;
            const p = [];
            if (ig.dropped_items > 0) p.push(`${ig.dropped_items} postavk`);
            if (ig.dropped_qty > 0) p.push(`${ig.dropped_qty} kosov`);
            toast(`⚠️ Seštevek se je zmanjšal — manjka ${p.join(' in ')}! Preveri izbris.`, 6000);
            refreshSidebarAndStats();
          }
        } else if (ig && ig.ok) {
          if (_lastIntegritySig !== '') refreshSidebarAndStats();
          _lastIntegritySig = '';
        }
      }
      // osveži časovnico (drugi nabiralec je morda začel/končal/pavziral)
      if (SESSION) {
        const ps = SESSION.pick_started_at, pf = SESSION.pick_finished_at, pp = SESSION.pick_paused_at;
        SESSION.pick_started_at = data.pick_started_at || null;
        SESSION.pick_finished_at = data.pick_finished_at || null;
        if ('pick_paused_at' in data) SESSION.pick_paused_at = data.pick_paused_at || null;
        if ('pick_pause_offset_s' in data) SESSION.pick_pause_offset_s = data.pick_pause_offset_s || 0;
        if (ps !== SESSION.pick_started_at || pf !== SESSION.pick_finished_at || pp !== SESSION.pick_paused_at) updatePickTimer();
      }
      // posodobi samo statuse/picked (ne uniči odprtih zavihkov)
      let changed = false;
      data.items.forEach(srv => {
        const local = ITEMS.find(x => x.idx === srv.idx);
        if (local && (local.status !== srv.status || local.picked !== srv.picked)) {
          local.status = srv.status; local.picked = srv.picked;
          refreshItem(local); changed = true;
        }
      });
      if (changed) {
        // osveži vse progress bare + sidebar
        [...new Set(ITEMS.map(i=>i.group))].forEach(refreshShelfProgress);
        refreshSidebarAndStats();
        updateGlobalStat();
      }
    }
  } catch(e) {}
}

// ═══ ZGODOVINA ═══
async function openHistory() {
  const ov = document.getElementById('histOverlay');
  ov.classList.add('show');
  const body = document.getElementById('histBody');
  body.innerHTML = '<div class="hist-empty">⏳ Nalagam...</div>';
  try {
    const r = await fetch(mq('/zaloga-history'));
    const data = await r.json();
    if (!data.ok || !data.sessions || !data.sessions.length) {
      body.innerHTML = '<div class="hist-empty">Ni arhiviranih nabiranj.</div>';
      return;
    }
    body.innerHTML = data.sessions.map(histSessRow).join('');
  } catch(e) {
    body.innerHTML = '<div class="hist-empty">✗ Napaka pri nalaganju.</div>';
  }
}

function closeHistory() {
  document.getElementById('histOverlay').classList.remove('show');
}

function histDate(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleDateString('sl-SI', {day:'2-digit',month:'2-digit',year:'numeric'}) +
      ' · ' + d.toLocaleTimeString('sl-SI', {hour:'2-digit',minute:'2-digit'});
  } catch(e) { return iso; }
}

function histSessRow(s) {
  return `
    <div class="hist-sess" id="hsess-${cssId(s.filename)}">
      <div class="hist-sess-top">
        <span class="hist-sess-date">${histDate(s.archived_at)}</span>
        <div class="hist-sess-prog"><div style="width:${s.pct}%"></div></div>
        <span class="hist-sess-pct" style="color:${s.pct===100?'var(--ok)':'var(--text)'}">${s.pct}%</span>
      </div>
      <div class="hist-sess-meta">
        <span>Postavk: <b>${s.total}</b></span>
        <span class="ok">Nabrano: <b>${s.ok}</b></span>
        <span class="ni">Manjka: <b>${s.ni}</b></span>
        <span>Kosov: <b>${s.qty_picked} / ${s.qty_need}</b></span>
        ${s.pick_secs != null ? `<span title="Čas nabiranja (od prve do zadnje postavke)">⏱ <b>${_fmtDur(s.pick_secs)}</b></span>` : ''}
      </div>
      <div class="hist-sess-actions">
        <button class="open" onclick="histToggleDetail('${jsStr(s.filename)}')">📋 Podrobnosti</button>
        <button class="open" onclick="histPackingCsv('${jsStr(s.filename)}')" title="Packing lista CSV iz te arhivirane seje">📄 Packing CSV</button>
        <button class="open" onclick="histPackingXlsx('${jsStr(s.filename)}')" title="Packing lista XLS iz te arhivirane seje">📊 Packing XLS</button>
        <button class="del" onclick="histDelete('${jsStr(s.filename)}')">🗑 Izbriši</button>
      </div>
      <div class="hist-detail" id="hdet-${cssId(s.filename)}" style="display:none"></div>
    </div>`;
}

async function histToggleDetail(filename) {
  const det = document.getElementById('hdet-' + cssId(filename));
  if (!det) return;
  if (det.style.display !== 'none') { det.style.display = 'none'; det.innerHTML = ''; return; }
  det.style.display = 'block';
  det.innerHTML = '<div style="padding:10px 0;color:var(--text-dim);font-size:12px">⏳ Nalagam...</div>';
  try {
    const r = await fetch(mq('/zaloga-history/' + encodeURIComponent(filename)));
    const data = await r.json();
    if (!data.ok || !data.items) { det.innerHTML = '<div style="padding:8px 0;color:var(--text-dim)">Ni podatkov.</div>'; return; }
    det.innerHTML = data.items.map(it => {
      const st = it.status === 'ok' ? '<span class="hst-ok">✓ OK</span>'
        : it.status === 'ni' ? '<span class="hst-ni">✕ NI</span>' : '—';
      return `<div class="hist-detail-row">
        <span class="hsku">${esc(it.sku)}</span>
        <span class="hnaziv" title="${esc(it.naziv)}">${esc(it.naziv)}</span>
        <span class="hpoz">${esc(it.poz)}</span>
        <span class="hqty">${it.status==='ok'?it.picked:0} / ${it.qty}</span>
        <span>${st}</span>
      </div>`;
    }).join('');
  } catch(e) {
    det.innerHTML = '<div style="padding:8px 0;color:var(--ni)">✗ Napaka.</div>';
  }
}

function histPackingCsv(filename) {
  const url = '/zaloga-history-packing-csv/' + encodeURIComponent(filename) + '?market=' + MARKET;
  window.open(url, '_blank');
}
function histPackingXlsx(filename) {
  const url = '/zaloga-history-packing-xlsx/' + encodeURIComponent(filename) + '?market=' + MARKET;
  window.open(url, '_blank');
}

async function histDelete(filename) {
  if (!confirm('Izbrišem to arhivirano nabiranje?\n\nDejanje je nepovratno.')) return;
  try {
    const r = await fetch(mq('/zaloga-history/' + encodeURIComponent(filename)), { method: 'DELETE' });
    const data = await r.json();
    if (data.ok) {
      const el = document.getElementById('hsess-' + cssId(filename));
      if (el) el.remove();
      toast('✓ Izbrisano');
      const body = document.getElementById('histBody');
      if (body && !body.querySelector('.hist-sess')) {
        body.innerHTML = '<div class="hist-empty">Ni arhiviranih nabiranj.</div>';
      }
    } else {
      toast('✗ ' + (data.error || 'napaka'));
    }
  } catch(e) { toast('✗ ' + e.message); }
}

// ── Kopiraj SKU iz manjka ──
async function copySkuFromManko(el, sku) {
  try {
    await navigator.clipboard.writeText(sku);
    const orig = el.innerHTML;
    el.innerHTML = `✓ ${esc(sku)} — kopirano!`;
    el.style.background = 'var(--ok)';
    el.style.color = '#fff';
    el.style.borderColor = 'var(--ok)';
    setTimeout(() => {
      el.innerHTML = orig;
      el.style.background = '';
      el.style.color = '';
      el.style.borderColor = '';
    }, 1600);
  } catch(e) {
    // fallback za starejše brskalnike
    const ta = document.createElement('textarea');
    ta.value = sku; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    toast('✓ ' + sku + ' kopirano');
  }
}

// Kopiraj VSE manjkajoče postavke: vsaka v svojo vrstico "SKU količinx"
async function copyAllManko(btn) {
  const manko = ITEMS.filter(_isManko);
  if (!manko.length) { toast('Ni manjkajočih postavk'); return; }
  const text = manko.map(it => {
    const missingQty = it.status === 'ni' ? it.qty : (it.qty - it.picked);
    return `${it.sku} ${missingQty}x`;
  }).join('\n');
  const flash = (ok) => {
    if (!btn) { toast(ok ? '✓ Kopirano' : '✗ Napaka'); return; }
    const orig = btn.innerHTML;
    btn.innerHTML = ok ? '✓ Kopirano!' : '✗ Napaka';
    btn.classList.toggle('copied', ok);
    setTimeout(() => { btn.innerHTML = orig; btn.classList.remove('copied'); }, 1600);
  };
  try {
    await navigator.clipboard.writeText(text);
    flash(true);
  } catch(e) {
    const ta = document.createElement('textarea');
    ta.value = text; ta.style.position = 'fixed'; ta.style.opacity = '0';
    document.body.appendChild(ta); ta.select();
    try { document.execCommand('copy'); flash(true); } catch(_) { flash(false); }
    document.body.removeChild(ta);
  }
}

// ── Init ──
initMarketTab();
loadSession();
setInterval(pollSync, 15000);
// ob spremembi velikosti / rotaciji osveži mobilni box-bar (pojavi/skrije se po potrebi)
window.addEventListener('resize', () => { updateMobileBoxBar(); updateStickyOffset(); });

// ── IN-APP OBVESTILA (kaj je novega) ──
// Obvestila se vpisujejo prek /admin in nalagajo s strežnika (/notices).
// Vsako se pokaže ENKRAT na napravo (localStorage zabeleži videna).
async function showZalogaNews() {
  let notices = [];
  try {
    const r = await fetch('/notices?scope=zaloga');
    const d = await r.json();
    notices = (d && d.notices) || [];
  } catch(e) { return; }
  if (!notices.length) return;

  let seen = [];
  try { seen = JSON.parse(localStorage.getItem('zaloga_news_seen') || '[]'); } catch(e) { seen = []; }
  const pending = notices.filter(n => !seen.includes(n.id));
  if (!pending.length) return;
  const n = pending[pending.length - 1];  // najstarejši neprebrani najprej
  const html = `
    <div class="img-preview-overlay" id="newsOverlay" onclick="dismissNews('${n.id}')">
      <div class="news-box" onclick="event.stopPropagation()">
        <div class="news-icon">${esc(n.icon || '📢')}</div>
        <div class="news-title">${esc(n.title || '')}</div>
        <div class="news-body">${esc(n.body || '')}</div>
        <button class="news-ok" onclick="dismissNews('${n.id}')">Razumem 👍</button>
      </div>
    </div>`;
  document.body.insertAdjacentHTML('beforeend', html);
}

function dismissNews(id) {
  let seen = [];
  try { seen = JSON.parse(localStorage.getItem('zaloga_news_seen') || '[]'); } catch(e) { seen = []; }
  if (!seen.includes(id)) seen.push(id);
  try { localStorage.setItem('zaloga_news_seen', JSON.stringify(seen)); } catch(e) {}
  const o = document.getElementById('newsOverlay');
  if (o) o.remove();
  setTimeout(showZalogaNews, 250);  // pokaži naslednje neprebrano
}

// pokaži obvestila kmalu po odprtju
setTimeout(showZalogaNews, 800);
