<!DOCTYPE html>
<html lang="sl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Meta Ads Generator</title>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600&family=DM+Mono:wght@500&display=swap" rel="stylesheet">
<style>
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #f2f2f5;
  --surface: #ffffff;
  --surface2: #ebebf0;
  --border: rgba(0,0,0,0.07);
  --border-hover: rgba(0,0,0,0.14);
  --text: #111116;
  --text-secondary: #55555f;
  --text-tertiary: #9999a8;
  --accent: #3a6fff;
  --accent-dim: rgba(58,111,255,0.1);
  --accent-border: rgba(58,111,255,0.3);
  --green: #0a8c5a;
  --green-dim: rgba(10,140,90,0.1);
  --green-border: rgba(10,140,90,0.28);
  --red: #e03030;
  --chip-off: #dddde5;
  --chip-on: #3a6fff;
  --radius: 10px;
  --radius-lg: 14px;
}
body {
  font-family: 'DM Sans', sans-serif;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  display: flex;
  justify-content: center;
  padding: 2.5rem 1.5rem 5rem;
}
.layout { width: 100%; max-width: 900px; }

/* Logo */
.logo { display: flex; align-items: center; gap: 12px; margin-bottom: 2rem; }
.logo-icon { width: 42px; height: 42px; border-radius: 12px; background: #1877F2; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
.logo-icon svg { width: 20px; height: 20px; fill: white; }
.logo-name { font-size: 17px; font-weight: 600; letter-spacing: -0.3px; }
.logo-sub { font-size: 12px; color: var(--text-tertiary); margin-top: 2px; }

/* Card */
.card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: 1.5rem; margin-bottom: 12px; }
.section-label { font-size: 11px; font-weight: 600; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 10px; display: block; }

/* Mode toggle */
.mode-row { display: flex; gap: 6px; margin-bottom: 1.25rem; background: var(--surface2); padding: 4px; border-radius: var(--radius); }
.mode-btn { flex: 1; height: 34px; border-radius: 7px; border: none; background: transparent; color: var(--text-tertiary); font-size: 13px; font-family: 'DM Sans', sans-serif; font-weight: 500; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; transition: all 0.15s; }
.mode-btn:hover { color: var(--text-secondary); }
.mode-btn.on { background: var(--surface); color: var(--text); border: 1px solid var(--border-hover); }
.mode-btn svg { width: 13px; height: 13px; stroke: currentColor; fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }

/* Inputs */
.url-wrap { position: relative; display: flex; align-items: center; margin-bottom: 10px; }
.url-icon { position: absolute; left: 12px; pointer-events: none; }
.url-icon svg { width: 14px; height: 14px; stroke: var(--text-tertiary); fill: none; stroke-width: 1.5; stroke-linecap: round; stroke-linejoin: round; }
input[type="text"] { width: 100%; height: 44px; padding: 0 14px 0 36px; font-size: 14px; font-family: 'DM Sans', sans-serif; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface2); color: var(--text); transition: all 0.15s; }
input[type="text"]:focus { outline: none; border-color: var(--accent-border); background: var(--surface); box-shadow: 0 0 0 3px var(--accent-dim); }
input[type="text"]::placeholder { color: var(--text-tertiary); }
input[type="text"].error { border-color: var(--red) !important; }
textarea.input-area { width: 100%; min-height: 120px; padding: 12px 14px; font-size: 13.5px; font-family: 'DM Sans', sans-serif; line-height: 1.65; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface2); color: var(--text); resize: vertical; transition: all 0.15s; margin-bottom: 10px; }
textarea.input-area:focus { outline: none; border-color: var(--accent-border); background: var(--surface); box-shadow: 0 0 0 3px var(--accent-dim); }
textarea.input-area::placeholder { color: var(--text-tertiary); }
textarea.input-area.error { border-color: var(--red) !important; }

/* Generate button */
.btn-gen { width: 100%; height: 46px; border-radius: var(--radius); border: none; background: var(--accent); color: white; font-size: 14px; font-family: 'DM Sans', sans-serif; font-weight: 600; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 7px; transition: all 0.15s; }
.btn-gen:hover { background: #2d5fee; }
.btn-gen:active { transform: scale(0.98); }
.btn-gen:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-gen svg { width: 14px; height: 14px; stroke: white; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

/* Sep */
.sep { border: none; border-top: 1px solid var(--border); margin: 1.25rem 0; }

/* Counters */
.counters { display: flex; gap: 1.5rem; }
.counter-group { flex: 1; }
.counter-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.cnt-btn { width: 28px; height: 28px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface2); color: var(--text-secondary); font-size: 16px; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all 0.12s; font-family: 'DM Mono', monospace; }
.cnt-btn:hover { border-color: var(--border-hover); color: var(--text); }
.cnt-btn:disabled { opacity: 0.25; cursor: not-allowed; }
.cnt-val { font-size: 16px; font-weight: 600; color: var(--text); min-width: 22px; text-align: center; font-family: 'DM Mono', monospace; }
.cnt-max { font-size: 11px; color: var(--text-tertiary); }
.chips { display: flex; gap: 3px; }
.chip { height: 4px; flex: 1; border-radius: 2px; background: var(--chip-off); transition: background 0.2s; }
.chip.on { background: var(--chip-on); }
.counters-divider { width: 1px; background: var(--border); align-self: stretch; }

/* Hint */
.hint { display: flex; align-items: flex-start; gap: 8px; padding: 10px 12px; background: var(--surface2); border-radius: 8px; margin-top: 1.25rem; }
.hint svg { width: 13px; height: 13px; stroke: var(--text-tertiary); fill: none; stroke-width: 1.5; flex-shrink: 0; margin-top: 1px; }
.hint-text { font-size: 12px; color: var(--text-tertiary); line-height: 1.6; }

/* Error / loading */
.error-msg { display: none; padding: 10px 14px; background: rgba(224,48,48,0.07); border: 1px solid rgba(224,48,48,0.2); border-radius: var(--radius); font-size: 13px; color: var(--red); margin-top: 10px; }
.error-msg.show { display: block; }
.loading { display: none; text-align: center; padding: 3rem 1rem; }
.loading.show { display: block; }
.spinner { width: 30px; height: 30px; border: 2px solid var(--border); border-top-color: var(--accent); border-radius: 50%; animation: spin 0.7s linear infinite; margin: 0 auto 1rem; }
@keyframes spin { to { transform: rotate(360deg); } }
.loading-text { font-size: 13px; color: var(--text-tertiary); }

/* Results */
.results { display: none; }
.results.show { display: block; }

/* Results header */
.results-hdr { display: flex; align-items: center; justify-content: space-between; margin-bottom: 1.5rem; }
.product-badge { display: inline-flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 500; color: var(--text-secondary); background: var(--surface); border: 1px solid var(--border); border-radius: 20px; padding: 6px 14px; }
.back-btn { height: 36px; padding: 0 16px; border-radius: var(--radius); border: 1px solid var(--border); background: var(--surface); color: var(--text-secondary); font-size: 13px; font-family: 'DM Sans', sans-serif; cursor: pointer; transition: all 0.12s; display: flex; align-items: center; gap: 6px; }
.back-btn:hover { border-color: var(--border-hover); color: var(--text); }
.back-btn svg { width: 13px; height: 13px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }

/* COUNTRY SECTIONS — opcija C */
.country-section {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  margin-bottom: 10px;
  overflow: hidden;
}
.country-hdr {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
}
.country-badge {
  font-size: 11px;
  font-weight: 700;
  padding: 3px 9px;
  border-radius: 5px;
  font-family: 'DM Mono', monospace;
  letter-spacing: 0.3px;
}
.country-name {
  font-size: 12px;
  color: var(--text-tertiary);
}
.country-body {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
}
.country-body .field-col {
  padding: 12px 16px;
}
.country-body .field-col:first-child {
  border-right: 1px solid var(--border);
}
.field-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.field-lbl {
  font-size: 10px;
  font-weight: 700;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.7px;
}
.cp-btn {
  height: 24px;
  padding: 0 10px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--text-secondary);
  font-size: 11px;
  font-weight: 500;
  cursor: pointer;
  font-family: 'DM Sans', sans-serif;
  transition: all 0.12s;
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}
.cp-btn:hover { border-color: var(--border-hover); color: var(--text); background: var(--surface); }
.cp-btn.ok { color: var(--green); border-color: var(--green-border); background: var(--green-dim); }
.cp-btn svg { width: 11px; height: 11px; stroke: currentColor; fill: none; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; flex-shrink: 0; }
.field-text {
  font-size: 13px;
  color: var(--text);
  line-height: 1.65;
  white-space: pre-wrap;
}
.field-text.is-hl {
  font-size: 14px;
  font-weight: 600;
}

/* Multiple PT — separator inside col */
.pt-item { margin-bottom: 10px; padding-bottom: 10px; border-bottom: 1px solid var(--border); }
.pt-item:last-child { margin-bottom: 0; padding-bottom: 0; border-bottom: none; }

/* Lang color map */
.lang-sl { background: #dbeafe; color: #1e40af; }
.lang-hr { background: #ffedd5; color: #9a3412; }
.lang-rs { background: #fee2e2; color: #991b1b; }
.lang-hu { background: #dcfce7; color: #166534; }
.lang-cz { background: #f3e8ff; color: #6b21a8; }
.lang-sk { background: #e0f2fe; color: #075985; }
.lang-pl { background: #fef9c3; color: #854d0e; }
.lang-gr { background: #e0e7ff; color: #3730a3; }
.lang-ro { background: #fef3c7; color: #92400e; }
.lang-bg { background: #d1fae5; color: #065f46; }
</style>
</head>
<body>
<div class="layout">

  <div class="logo">
    <div class="logo-icon">
      <svg viewBox="0 0 24 24"><path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"/></svg>
    </div>
    <div>
      <div class="logo-name">Meta Ads Generator</div>
      <div class="logo-sub">FB / Instagram — 10 jezikov</div>
    </div>
  </div>

  <!-- FORM -->
  <div id="formSection">
    <div class="card">
      <span class="section-label">Način vnosa</span>
      <div class="mode-row">
        <button class="mode-btn on" id="mode-url" onclick="setMode('url')">
          <svg viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
          URL izdelka
        </button>
        <button class="mode-btn" id="mode-txt" onclick="setMode('txt')">
          <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          Opis izdelka
        </button>
      </div>

      <div id="input-url-wrap">
        <span class="section-label">URL izdelka</span>
        <div class="url-wrap">
          <span class="url-icon"><svg viewBox="0 0 24 24"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg></span>
          <input type="text" id="urlInput" placeholder="https://www.maaarket.si/izdelek/..." />
        </div>
      </div>

      <div id="input-txt-wrap" style="display:none">
        <span class="section-label">Opis izdelka</span>
        <textarea class="input-area" id="txtInput" placeholder="Prilepi sem naziv, opis, lastnosti — karkoli iz strani izdelka..."></textarea>
      </div>

      <button class="btn-gen" id="btnGen" onclick="generate()">
        <svg viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        Generiraj oglase
      </button>
      <div class="error-msg" id="errorMsg"></div>

      <div class="sep"></div>

      <div class="counters">
        <div class="counter-group">
          <span class="section-label">Primary Texts</span>
          <div class="counter-row">
            <button class="cnt-btn" id="pt-minus" onclick="change('pt',-1)">−</button>
            <span class="cnt-val" id="pt-val">1</span>
            <button class="cnt-btn" id="pt-plus" onclick="change('pt',1)">+</button>
            <span class="cnt-max">max 5</span>
          </div>
          <div class="chips" id="pt-chips"></div>
        </div>
        <div class="counters-divider"></div>
        <div class="counter-group">
          <span class="section-label">Headlines</span>
          <div class="counter-row">
            <button class="cnt-btn" id="hl-minus" onclick="change('hl',-1)">−</button>
            <span class="cnt-val" id="hl-val">1</span>
            <button class="cnt-btn" id="hl-plus" onclick="change('hl',1)">+</button>
            <span class="cnt-max">max 5</span>
          </div>
          <div class="chips" id="hl-chips"></div>
        </div>
      </div>

      <div class="hint">
        <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        <span class="hint-text" id="hintText">Generiram 1× Primary Text in 1× Headline v 10 jezikih.</span>
      </div>
    </div>

    <div class="loading" id="loading">
      <div class="spinner"></div>
      <div class="loading-text">Generiram oglase in prevode...</div>
    </div>
  </div>

  <!-- RESULTS -->
  <div class="results" id="results">
    <div class="results-hdr">
      <div class="product-badge" id="productBadge">Izdelek</div>
      <button class="back-btn" onclick="goBack()">
        <svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg>
        Nov izdelek
      </button>
    </div>
    <div id="countryList"></div>
  </div>

</div>

<script>
const state = { pt: 1, hl: 1, mode: 'url' };
const MAX = 5;

const LANGS = [
  { code: 'sl', label: 'SI SL', name: 'Slovenščina' },
  { code: 'hr', label: 'HR HR', name: 'Hrvaščina' },
  { code: 'rs', label: 'RS RS', name: 'Srbščina' },
  { code: 'hu', label: 'HU HU', name: 'Madžarščina' },
  { code: 'cz', label: 'CZ CZ', name: 'Češčina' },
  { code: 'sk', label: 'SK SK', name: 'Slovaščina' },
  { code: 'pl', label: 'PL PL', name: 'Poljščina' },
  { code: 'gr', label: 'GR GR', name: 'Grščina' },
  { code: 'ro', label: 'RO RO', name: 'Romunščina' },
  { code: 'bg', label: 'BG BG', name: 'Bolgarščina' },
];

function setMode(m) {
  state.mode = m;
  document.getElementById('mode-url').classList.toggle('on', m === 'url');
  document.getElementById('mode-txt').classList.toggle('on', m === 'txt');
  document.getElementById('input-url-wrap').style.display = m === 'url' ? 'block' : 'none';
  document.getElementById('input-txt-wrap').style.display = m === 'txt' ? 'block' : 'none';
}

function change(type, dir) {
  state[type] = Math.min(MAX, Math.max(1, state[type] + dir));
  update();
}

function update() {
  ['pt', 'hl'].forEach(t => {
    document.getElementById(t + '-val').textContent = state[t];
    document.getElementById(t + '-minus').disabled = state[t] <= 1;
    document.getElementById(t + '-plus').disabled = state[t] >= MAX;
    const chips = document.getElementById(t + '-chips');
    chips.innerHTML = '';
    for (let i = 0; i < MAX; i++) {
      const c = document.createElement('div');
      c.className = 'chip' + (i < state[t] ? ' on' : '');
      chips.appendChild(c);
    }
  });
  document.getElementById('hintText').textContent =
    `Generiram ${state.pt}× Primary Text in ${state.hl}× Headline v 10 jezikih.`;
}

async function generate() {
  let input = '';
  if (state.mode === 'url') {
    input = document.getElementById('urlInput').value.trim();
    if (!input) { flash('urlInput'); return; }
  } else {
    input = document.getElementById('txtInput').value.trim();
    if (!input) { flash('txtInput'); return; }
  }
  const btn = document.getElementById('btnGen');
  btn.disabled = true;
  document.getElementById('errorMsg').classList.remove('show');
  document.getElementById('loading').classList.add('show');

  try {
    const res = await fetch('/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ input, mode: state.mode, pt_count: state.pt, hl_count: state.hl })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    renderResults(data);
  } catch(e) {
    document.getElementById('loading').classList.remove('show');
    const err = document.getElementById('errorMsg');
    err.textContent = 'Napaka: ' + (e.message || 'Poskusi znova.');
    err.classList.add('show');
    btn.disabled = false;
  }
}

function copyIcon() {
  return `<svg viewBox="0 0 24 24"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
}
function checkIcon() {
  return `<svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg>`;
}

function renderResults(data) {
  document.getElementById('loading').classList.remove('show');
  document.getElementById('formSection').style.display = 'none';
  document.getElementById('results').classList.add('show');
  document.getElementById('productBadge').textContent = '🛍 ' + (data.product || 'Izdelek');

  const list = document.getElementById('countryList');
  list.innerHTML = '';

  LANGS.forEach(lang => {
    const d = data[lang.code];
    if (!d) return;

    const pts = Array.isArray(d.pt) ? d.pt : [d.pt];
    const hls = Array.isArray(d.hl) ? d.hl : [d.hl];

    const section = document.createElement('div');
    section.className = 'country-section';

    // Header
    const hdr = document.createElement('div');
    hdr.className = 'country-hdr';
    hdr.innerHTML = `<span class="country-badge lang-${lang.code}">${lang.label}</span><span class="country-name">${lang.name}</span>`;
    section.appendChild(hdr);

    // Body
    const body = document.createElement('div');
    body.className = 'country-body';

    // PT column
    const ptCol = document.createElement('div');
    ptCol.className = 'field-col';

    if (pts.length === 1) {
      const id = `f-pt-${lang.code}-0`;
      ptCol.innerHTML = `
        <div class="field-top">
          <span class="field-lbl">Primary Text</span>
          <button class="cp-btn" id="${id}" onclick="doCopy('${id}')">${copyIcon()}Kopiraj</button>
        </div>
        <div class="field-text" id="txt-${id}">${esc(pts[0])}</div>`;
    } else {
      ptCol.innerHTML = `<div class="field-lbl" style="margin-bottom:10px">Primary Texts</div>`;
      pts.forEach((pt, i) => {
        const id = `f-pt-${lang.code}-${i}`;
        ptCol.innerHTML += `
          <div class="pt-item">
            <div class="field-top">
              <span class="field-lbl" style="font-size:9px;opacity:0.7">#${i+1}</span>
              <button class="cp-btn" id="${id}" onclick="doCopy('${id}')">${copyIcon()}Kopiraj</button>
            </div>
            <div class="field-text" id="txt-${id}">${esc(pt)}</div>
          </div>`;
      });
    }

    // HL column
    const hlCol = document.createElement('div');
    hlCol.className = 'field-col';

    if (hls.length === 1) {
      const id = `f-hl-${lang.code}-0`;
      hlCol.innerHTML = `
        <div class="field-top">
          <span class="field-lbl">Headline</span>
          <button class="cp-btn" id="${id}" onclick="doCopy('${id}')">${copyIcon()}Kopiraj</button>
        </div>
        <div class="field-text is-hl" id="txt-${id}">${esc(hls[0])}</div>`;
    } else {
      hlCol.innerHTML = `<div class="field-lbl" style="margin-bottom:10px">Headlines</div>`;
      hls.forEach((hl, i) => {
        const id = `f-hl-${lang.code}-${i}`;
        hlCol.innerHTML += `
          <div class="pt-item">
            <div class="field-top">
              <span class="field-lbl" style="font-size:9px;opacity:0.7">#${i+1}</span>
              <button class="cp-btn" id="${id}" onclick="doCopy('${id}')">${copyIcon()}Kopiraj</button>
            </div>
            <div class="field-text is-hl" id="txt-${id}">${esc(hl)}</div>
          </div>`;
      });
    }

    body.appendChild(ptCol);
    body.appendChild(hlCol);
    section.appendChild(body);
    list.appendChild(section);
  });
}

function doCopy(id) {
  const el = document.getElementById('txt-' + id);
  const text = el ? el.innerText : '';
  const btn = document.getElementById(id);

  const tryClipboard = () => {
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(() => showOk(btn)).catch(() => fallback(text, btn));
    } else {
      fallback(text, btn);
    }
  };
  tryClipboard();
}

function fallback(text, btn) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0';
  document.body.appendChild(ta);
  ta.focus();
  ta.select();
  ta.setSelectionRange(0, 99999);
  try { document.execCommand('copy'); } catch(e) {}
  document.body.removeChild(ta);
  showOk(btn);
}

function showOk(btn) {
  btn.innerHTML = `<svg viewBox="0 0 24 24" style="width:11px;height:11px;stroke:currentColor;fill:none;stroke-width:2.5;stroke-linecap:round;stroke-linejoin:round"><polyline points="20 6 9 17 4 12"/></svg>Kopirano`;
  btn.classList.add('ok');
  setTimeout(() => {
    btn.innerHTML = `<svg viewBox="0 0 24 24" style="width:11px;height:11px;stroke:currentColor;fill:none;stroke-width:2;stroke-linecap:round;stroke-linejoin:round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>Kopiraj`;
    btn.classList.remove('ok');
  }, 2000);
}

function goBack() {
  document.getElementById('results').classList.remove('show');
  document.getElementById('countryList').innerHTML = '';
  document.getElementById('formSection').style.display = 'block';
  document.getElementById('btnGen').disabled = false;
  document.getElementById('errorMsg').classList.remove('show');
}

function flash(id) {
  const el = document.getElementById(id);
  el.classList.add('error');
  el.focus();
  setTimeout(() => el.classList.remove('error'), 1500);
}

function esc(s) {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

update();
</script>
</body>
</html>
