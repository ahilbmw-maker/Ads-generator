// ═══ NABIRANJE ZALOGE — logika ═══
let ITEMS = [];           // vse postavke iz seje
let SESSION = null;       // celotna seja
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
  setExpanded({});  // počisti odprte zavihke ob preklopu
  lastUpdate = null;
  loadSession();
}

// ── Ob nalaganju: označi shranjeni trg ──
function initMarketTab() {
  const slo = document.getElementById('mtab-slo');
  const rs = document.getElementById('mtab-rs');
  if (slo) slo.classList.toggle('active', MARKET === 'slo');
  if (rs) rs.classList.toggle('active', MARKET === 'rs');
}

// ── Skupine ──
const GROUP_ORDER = (g) => {
  if (g.startsWith('Polica ')) return [0, g];
  if (/^P\d+$/.test(g)) return [1, parseInt(g.slice(1))];
  if (g === 'Paleta') return [2, 0];
  if (g === 'Pod Mizo') return [2, 1];
  if (g === 'Ikonka') return [2, 2];
  if (g === 'Amio') return [2, 3];
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

// ── Grupiraj postavke ──
function groupItems() {
  const groups = {};
  ITEMS.forEach(it => {
    (groups[it.group] = groups[it.group] || []).push(it);
  });
  // sortiraj postavke znotraj skupine po poziciji
  Object.values(groups).forEach(arr => arr.sort((a,b) => (a.poz||'').localeCompare(b.poz||'', 'sl', {numeric:true})));
  return groups;
}

// ── Render ──
function render() {
  const groups = groupItems();
  const expanded = getExpanded();
  const groupNames = Object.keys(groups).sort((a,b) => {
    const ga = GROUP_ORDER(a), gb = GROUP_ORDER(b);
    if (ga[0] !== gb[0]) return ga[0] - gb[0];
    if (typeof ga[1] === 'number' && typeof gb[1] === 'number') return ga[1] - gb[1];
    return String(ga[1]).localeCompare(String(gb[1]), 'sl', {numeric:true});
  });

  let html = '<div class="shelves">';
  groupNames.forEach(g => {
    const items = groups[g];
    const isOpen = !!expanded[g];
    const stat = groupStat(items);
    html += `
      <div class="shelf ${isOpen ? 'open' : ''}" id="shelf-${cssId(g)}">
        <div class="shelf-head" onclick="toggleShelf('${jsStr(g)}')">
          <span class="shelf-chevron">▶</span>
          <span class="shelf-name">${esc(g)}</span>
          <span class="shelf-count">${items.length} postavk</span>
          <div class="shelf-head-spacer"></div>
          <div class="shelf-prog">
            <div class="shelf-prog-bar prog-seg-wrap">${progBarSegments(stat)}</div>
            <span class="shelf-prog-pct" style="color:${stat.pctOk===100?'var(--ok)':'var(--text)'}">${stat.pctOk}%</span>
          </div>
        </div>
        <div class="shelf-body">
          ${isRS() ? shelfBoxBar(g, items) : ''}
          <div class="item-head">
            <span>ID naročila</span><span>Slika</span><span>SKU</span><span>Pozicija</span>
            <span>Naziv</span><span class="h-qty">Količina</span><span class="h-status">Status</span>
          </div>
          ${items.map(it => itemRow(it)).join('')}
        </div>
      </div>`;
  });
  // RS: sekcija dodatnih boxov (viški) — pod zadnjo polico
  if (isRS()) html += extraBoxesSection();
  html += '</div>';

  // Sidebar (manjko + skupna statistika)
  html += renderSidebar();

  document.getElementById('wrap').innerHTML = html;
  updateGlobalStat();
}

// ── RS: box vrstica pri polici ──
function shelfBoxBar(group, items) {
  // koliko obkljukanih (ok) IN še ne zaklenjenih
  const pending = items.filter(it => it.status === 'ok' && !it.locked).length;
  const lockedCount = items.filter(it => it.locked).length;
  return `
    <div class="shelf-box-bar" onclick="event.stopPropagation()">
      <span class="sbb-icon">📦</span>
      <span class="sbb-label">Št. Boxa:</span>
      <input type="number" class="sbb-input" id="boxinput-${cssId(group)}" placeholder="npr. 1" min="1"
        onclick="event.stopPropagation()">
      <button class="sbb-save" onclick="lockBox('${jsStr(group)}')">
        🔒 Shrani in zakleni${pending ? ` (${pending})` : ''}
      </button>
      ${lockedCount ? `<span class="sbb-locked">${lockedCount} zaklenjenih</span>` : ''}
    </div>`;
}

// ── RS: zakleni obkljukane v polici ──
async function lockBox(group) {
  const inp = document.getElementById('boxinput-' + cssId(group));
  const box = inp ? inp.value.trim() : '';
  if (!box) { toast('Vpiši št. boxa'); if (inp) inp.focus(); return; }
  try {
    const r = await fetch('/zaloga-lock-box', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ market: MARKET, group, box })
    });
    const data = await r.json();
    if (data.ok) {
      // posodobi lokalno
      ITEMS.forEach(it => {
        if (it.group === group && it.status === 'ok' && !it.locked) {
          it.box = box; it.locked = true;
        }
      });
      toast(`✓ ${data.locked} postavk → Box ${box}`);
      render();
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

async function addToExtraBox(idx, box, kos) {
  const it = ITEMS.find(x => x.idx === idx);
  if (!it) return;
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
        <span class="ebx-line-sku" onclick="copySkuFromManko(this,'${esc(e.sku)}')" title="Kopiraj SKU" style="cursor:pointer">${esc(e.sku)} <span class="mpoz-copy-icon">⎘</span></span>
        <span class="ebx-line-kos">× ${e.kos}</span>
        <button class="ebx-line-del" onclick="removeFromExtraBox('${jsStr(b)}','${jsStr(e.sku)}')" title="Odstrani">✕</button>
      </div>`).join('');
    return `
      <div class="ebx-card">
        <div class="ebx-head">
          <span class="ebx-name">📦 Box ${esc(b)}</span>
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

function itemRow(it) {
  const cls = it.status === 'ok' ? 'ok' : it.status === 'ni' ? 'ni' : '';
  const mismatch = it.picked !== it.qty ? 'qty-mismatch' : '';
  const rs = isRS();
  const locked = rs && it.locked;

  // RS: box značka ali odkleni gumb
  const boxBadge = locked
    ? `<span class="item-box-badge">📦 BOX ${esc(it.box)}</span>
       <button class="item-unlock" onclick="unlockItem(${it.idx})" title="Odkleni">🔓</button>`
    : '';

  // RS: opomba polje (dodatni box) — vgrajen label + gumb "V box"
  const opombaRow = rs ? `
      <div class="item-opomba">
        <div class="iop-prefix">📝 Dodatni box</div>
        <input type="text" class="iop-input" value="${esc(it.opomba || '')}" placeholder="npr. 2 kos"
          onclick="event.stopPropagation()" onblur="commitOpomba(${it.idx}, this.value, this)"
          onkeydown="if(event.key==='Enter')openBoxDialog(${it.idx})">
        <button class="iop-tobox" onclick="event.stopPropagation();openBoxDialog(${it.idx})" title="Dodaj v dodatni box">⤓ V box</button>
      </div>` : '';

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
        <span class="sku">${esc(it.sku)}</span>
        <span class="poz">${esc(it.poz)} ${boxBadge}</span>
      </div>
      <span class="naziv" title="${esc(it.naziv)}">${esc(it.naziv)}${it.low ? '<span class="tag-low">Nizka zaloga</span>' : ''}</span>
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
  // odstotki (zaokroženi tako da vsota = 100)
  const pctOk = total ? Math.round(ok / total * 100) : 0;
  const pctNi = total ? Math.round(ni / total * 100) : 0;
  const pctTodo = total ? (100 - pctOk - pctNi) : 0;
  const pct = total ? Math.round(done / total * 100) : 0;  // skupno obdelano (compat)
  return { total, done, ok, ni, todo, pct, pctOk, pctNi, pctTodo };
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

// ── Segmentiran bar (zeleno / rdeče / sivo) ──
function progBarSegments(s) {
  return `
    <div class="prog-seg prog-seg-ok" style="width:${s.pctOk}%"></div>
    <div class="prog-seg prog-seg-ni" style="width:${s.pctNi}%"></div>
    <div class="prog-seg prog-seg-todo" style="width:${s.pctTodo}%"></div>`;
}

// ── Sidebar ──
let SIDEBAR_TAB = 'opombe';  // RS aktivni tab

function mankoItemHtml(it) {
  const missingQty = it.status === 'ni' ? it.qty : (it.qty - it.picked);
  return `
    <div class="manko-item">
      <div class="top">
        <span class="msku">${esc(it.sku)}</span>
        <span class="mqty">manjka ${missingQty}${it.status==='ni'?' (cela)':''}</span>
      </div>
      <div class="mnaziv" title="${esc(it.naziv)}">${esc(it.naziv)}</div>
      <div class="mpoz-badge" onclick="copySkuFromManko(this,'${esc(it.sku)}')" title="Klikni za kopiranje SKU" style="cursor:pointer;user-select:none">📍 ${esc(it.poz)} <span class="mpoz-copy-icon">⎘</span></div>
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
      <div class="box-group-head">📦 BOX ${esc(b)} <span class="box-group-count">${boxes[b].length}</span></div>
      ${boxes[b].map(it => `
        <div class="box-line">
          <span class="box-line-sku" onclick="copySkuFromManko(this,'${esc(it.sku)}')" title="Kopiraj SKU" style="cursor:pointer">${esc(it.sku)} <span class="mpoz-copy-icon">⎘</span></span>
          <span class="box-line-poz">${esc(it.poz)}</span>
        </div>`).join('')}
    </div>`).join('');
}

function renderSidebar() {
  const manko = ITEMS.filter(it => it.status === 'ni' || (it.status === 'ok' && it.picked < it.qty));
  const opombe = ITEMS.filter(it => it.opomba && it.opomba.trim());
  const totalOk = ITEMS.filter(it => it.status === 'ok').length;
  const totalNi = ITEMS.filter(it => it.status === 'ni').length;
  const totalDone = totalOk + totalNi;
  const totalQtyNeed = ITEMS.reduce((s,it) => s + it.qty, 0);
  const totalQtyPicked = ITEMS.filter(it=>it.status==='ok').reduce((s,it) => s + it.picked, 0);

  const statCard = `
    <div class="side-card">
      <h3>📊 Skupna statistika</h3>
      <div class="stat-rows">
        <div class="stat-row"><span class="lbl">Vseh postavk</span><span class="val">${ITEMS.length}</span></div>
        <div class="stat-row"><span class="lbl">Obdelanih</span><span class="val">${totalDone}</span></div>
        <div class="stat-row"><span class="lbl">Nabrano (OK)</span><span class="val ok">${totalOk}</span></div>
        <div class="stat-row"><span class="lbl">Manjka (NI)</span><span class="val ni">${totalNi}</span></div>
        <div class="stat-row" style="border-top:1px solid var(--border);padding-top:10px;margin-top:2px">
          <span class="lbl">Kosov nabrano</span><span class="val">${totalQtyPicked} / ${totalQtyNeed}</span></div>
      </div>
    </div>`;

  if (!isRS()) {
    // SLO — samo Manjko
    const mankoHtml = manko.length === 0
      ? '<div class="manko-empty">Zaenkrat ni manjkajočih postavk 🎉</div>'
      : manko.map(mankoItemHtml).join('');
    return `
      <div class="sidebar">
        ${statCard}
        <div class="side-card">
          <h3>⚠️ Manjko ${manko.length ? `<span class="badge">${manko.length}</span>` : ''}</h3>
          <div class="manko-list">${mankoHtml}</div>
        </div>
      </div>`;
  }

  // RS — tabi Opombe / Manjko / Boxi
  let tabContent;
  if (SIDEBAR_TAB === 'opombe') {
    tabContent = opombe.length ? opombe.map(opombaItemHtml).join('') : '<div class="manko-empty">Ni opomb.</div>';
  } else if (SIDEBAR_TAB === 'manjko') {
    tabContent = manko.length ? manko.map(mankoItemHtml).join('') : '<div class="manko-empty">Ni manjka 🎉</div>';
  } else {
    tabContent = boxiHtml();
  }

  return `
    <div class="sidebar">
      ${statCard}
      <div class="side-card side-card-tabs">
        <div class="side-tabs">
          <button class="side-tab side-tab-opombe ${SIDEBAR_TAB==='opombe'?'active':''}" onclick="setSidebarTab('opombe')">📝 Opombe ${opombe.length?`<span class="st-badge st-blue">${opombe.length}</span>`:''}</button>
          <button class="side-tab side-tab-manjko ${SIDEBAR_TAB==='manjko'?'active':''}" onclick="setSidebarTab('manjko')">⚠️ Manjko ${manko.length?`<span class="st-badge st-red">${manko.length}</span>`:''}</button>
          <button class="side-tab side-tab-boxi ${SIDEBAR_TAB==='boxi'?'active':''}" onclick="setSidebarTab('boxi')">📦 Boxi</button>
        </div>
        <div class="side-tab-body side-tab-${SIDEBAR_TAB}">${tabContent}</div>
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
  const bar = document.getElementById('globalBar');
  if (bar) bar.innerHTML = progBarSegments(stat);
  const pctEl = document.getElementById('globalPct');
  if (pctEl) {
    pctEl.textContent = stat.pctOk + '%';
    pctEl.style.color = stat.pctOk===100 ? 'var(--ok)' : 'var(--text)';
  }
  const doneEl = document.getElementById('globalDone');
  if (doneEl) doneEl.textContent = `${stat.done} / ${stat.total}`;
  const breakEl = document.getElementById('globalBreak');
  if (breakEl) breakEl.textContent = statBreakdownText(stat) || 'skupna uspešnost';
}

// ── Toggle zavihek (persist per naprava) ──
function toggleShelf(g) {
  const expanded = getExpanded();
  expanded[g] = !expanded[g];
  if (!expanded[g]) delete expanded[g];
  setExpanded(expanded);
  const el = document.getElementById('shelf-' + cssId(g));
  if (el) el.classList.toggle('open');
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
  saveItem(idx, { status: it.status });
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
  const bar = shelf.querySelector('.shelf-prog-bar');
  const pct = shelf.querySelector('.shelf-prog-pct');
  if (bar) bar.innerHTML = progBarSegments(stat);
  if (pct) { pct.textContent = stat.pctOk + '%'; pct.style.color = stat.pctOk===100 ? 'var(--ok)' : 'var(--text)'; }
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
    await fetch('/zaloga-update-item', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ idx, market: MARKET, ...patch })
    });
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
function jsStr(s) { return String(s).replace(/\\/g,'\\\\').replace(/'/g,"\\'"); }
function cssId(s) { return String(s).replace(/[^a-zA-Z0-9]/g, '_'); }

let toastTimer;
function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
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
      </div>
      <div class="hist-sess-actions">
        <button class="open" onclick="histToggleDetail('${jsStr(s.filename)}')">📋 Podrobnosti</button>
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

// ── Init ──
initMarketTab();
loadSession();
setInterval(pollSync, 15000);
