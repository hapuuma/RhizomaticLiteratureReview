/* ─── Configuration ─────────────────────────────────────────── */
const API_BASE = '/api';

/* ─── State ──────────────────────────────────────────────────── */
let isRunning = false;
let currentEventSource = null;
let pipelineData = {};
let blastRadiusActive = false;
let blastRadiusNode = null;
let _lenses = [];        // current editable lens list
let _lensGenQuery = '';  // query used for the last AI generation

/* ─── Boot ───────────────────────────────────────────────────── */
document.addEventListener('DOMContentLoaded', () => {
  loadHealth();
  loadDefaultLenses();
  document.getElementById('queryInput').addEventListener('keydown', e => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) startTraversal();
  });
});

async function loadDefaultLenses() {
  try {
    const r = await fetch(`${API_BASE}/lenses/defaults`);
    const d = await r.json();
    _lenses = d.lenses || [];
    _renderLensCards();
  } catch {
    // Silently ignore — user can still generate or add lenses manually
  }
}

async function loadHealth() {
  try {
    const r = await fetch(`${API_BASE}/health`);
    const d = await r.json();
    document.getElementById('modelChip').textContent = d.model || 'model unknown';
  } catch {
    document.getElementById('modelChip').textContent = 'backend offline';
  }
}

/* ─── Tab Switching ──────────────────────────────────────────── */
function switchTab(name) {
  if (typeof ttsStop === 'function') ttsStop();
  document.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.toggle('active', b.id === `btn-${name}`);
    b.setAttribute('aria-selected', b.id === `btn-${name}`);
  });
  document.querySelectorAll('.tab-panel').forEach(p => {
    p.classList.toggle('active', p.id === `tab-${name}`);
  });

  // Re-render graph if switching to it and we have data
  if (name === 'graph' && pipelineData.graph) {
    setTimeout(() => initRhizomeGraph(pipelineData.graph), 50);
  }

  // Auto-load history when switching to history tab
  if (name === 'history') {
    const content = document.getElementById('history-content');
    if (!content || !content.innerHTML.trim()) loadHistory();
  }
}

/* ─── Pipeline meta bar ──────────────────────────────────────── */
function updateMetaBar(meta) {
  if (!meta) return;
  const chip = document.getElementById('sourceCountChip');
  if (chip) {
    const parts = [];
    if (meta.abs_approved != null) parts.push(`${meta.abs_approved} approved`);
    if (meta.abs_quarantined) parts.push(`${meta.abs_quarantined} quarantined`);
    if (meta.dedup_removed) parts.push(`${meta.dedup_removed} deduped`);
    if (parts.length) chip.textContent = parts.join(' · ');
  }
}

/* ─── Pipeline Progress ──────────────────────────────────────── */
function setStage(stage, status) {
  // Handle stage IDs that have underscores (abs_check → abs_check)
  const node = document.getElementById(`stage-${stage}`);
  if (!node) return;
  node.className = `stage-node ${status}`;
}

function setStatus(label, type = '') {
  document.getElementById('statusLabel').textContent = label;
  const dot = document.getElementById('statusDot');
  dot.className = `status-dot ${type}`;
}

/* ─── Traversal ──────────────────────────────────────────────── */
async function startTraversal() {
  const query = document.getElementById('queryInput').value.trim();
  if (!query) return;
  if (isRunning) return;

  // Auto mode: generate AI lenses for this query first, then traverse
  const isAuto = document.getElementById('lensAutoGenerate')?.checked;
  if (isAuto) {
    await generateLenses();   // updates _lenses in place; errors are handled inside
  }

  try {
    isRunning = true;
    pipelineData = {};
    const btn = document.getElementById('traverseBtn');
    btn.disabled = true;
    btn.classList.add('running');
    document.getElementById('sourceCountChip').textContent = '— sources';
    setStatus('Running…', 'running');
    dismissError();
    resetPipelineBar();
    resetTabs();

    if (currentEventSource) currentEventSource.close();

    // Always send current lenses — user may have edited them
    const customLenses = _lenses.length > 0 ? _collectLenses() : null;

    const response = await fetch(`${API_BASE}/traverse`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query,
        max_sources: 15,
        custom_lenses: customLenses,
        run_mode:       document.getElementById('runMode')?.value || 'controlled',
        domain:         document.getElementById('runDomain')?.value || 'other',
        corpus_profile: document.getElementById('corpusProfile')?.value || 'natural',
      }),
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop(); // keep incomplete line
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const event = JSON.parse(line.slice(6));
            handleEvent(event);
          } catch (e) {
            console.warn('SSE parse error', e);
          }
        }
      }
    }
  } catch (err) {
    console.error('Traversal failed:', err);
    showError(err.message || 'Traversal failed. Is the backend running?');
    setStatus('Error', 'error');
  } finally {
    isRunning = false;
    const traverseBtn = document.getElementById('traverseBtn');
    traverseBtn.disabled = false;
    traverseBtn.classList.remove('running');
    if (!document.getElementById('statusDot').classList.contains('error')) {
      setStatus('Complete', 'done');
    }
  }
}

/* ─── Event Dispatcher ───────────────────────────────────────── */
function handleEvent(event) {
  const { stage, status, data, error } = event;

  if (error) { showError(error); return; }

  switch (stage) {
    // V3: Phase 1 — Epistemology Agent
    case 'epistemology':
      if (status === 'running') setStage('epistemology', 'running');
      if (status === 'complete') {
        setStage('epistemology', 'complete');
        pipelineData.epistemology = data;
        // Show lens names in modules placeholder
        if (data.lenses && data.lenses.length) {
          const lensNames = data.lenses.map(l => l.name).join(' · ');
          const placeholder = document.getElementById('modules-placeholder');
          if (placeholder) {
            placeholder.querySelector('p').textContent =
              `Active lenses: ${lensNames}`;
          }
        }
      }
      break;

    case 'search':
      if (status === 'running') setStage('search', 'running');
      if (status === 'complete') {
        setStage('search', 'complete');
        const chip = document.getElementById('sourceCountChip');
        if (chip) {
          const parts = [`${data.source_count} raw`];
          if (data.after_dedup != null) parts.push(`→ ${data.after_dedup} unique`);
          if (data.sources_by_api) {
            const apis = Object.entries(data.sources_by_api)
              .map(([k, v]) => `${v} ${k}`).join(', ');
            parts.push(`[${apis}]`);
          }
          chip.textContent = parts.join(' ');
        }
      }
      break;

    // V3: ABS screening
    case 'abs_check':
      if (status === 'running') setStage('abs_check', 'running');
      if (status === 'complete') {
        setStage('abs_check', 'complete');
        pipelineData.abs_check = data;
      }
      break;

    // V3: Citation mapping
    case 'citations':
      if (status === 'complete') pipelineData.citation_map = data;
      break;

    case 'entry':
      if (status === 'running') setStage('entry', 'running');
      if (status === 'complete') {
        setStage('entry', 'complete');
        renderEntryTab(data);
        markTabHasData('entry');
      }
      break;

    case 'modules':
      if (status === 'running') setStage('modules', 'running');
      if (status === 'complete') {
        setStage('modules', 'complete');
        renderModulesTab(data);
        markTabHasData('modules');
      }
      break;

    case 'resonance':
      if (status === 'running') setStage('resonance', 'running');
      if (status === 'complete') {
        setStage('resonance', 'complete');
        pipelineData.resonance = data;
      }
      break;

    case 'rupture':
      if (status === 'complete') pipelineData.rupture = data;
      break;

    // V3: Rupture search additional sources
    case 'rupture_search':
      if (status === 'complete' && data && data.new_sources_added > 0) {
        const chip = document.getElementById('sourceCountChip');
        if (chip) chip.textContent += ` +${data.new_sources_added} rupture`;
      }
      break;

    case 'assemblage':
      if (status === 'running') setStage('assemblage', 'running');
      if (status === 'complete') {
        setStage('assemblage', 'complete');
        pipelineData.assemblage = data;
      }
      break;

    case 'graph':
      if (status === 'running') setStage('graph', 'running');
      if (status === 'complete') {
        setStage('graph', 'complete');
        // V3: persist metadata may be embedded in data
        const graphData = data.persist ? { nodes: data.nodes, edges: data.edges } : data;
        pipelineData.graph = graphData;
        pipelineData.persist = data.persist;
        renderGraphTab(graphData);
        markTabHasData('graph');
      }
      break;

    case 'cartography':
      if (status === 'complete') {
        setStage('topography', 'running'); // keep progress visible
        renderResonanceTab(data.tab_resonance);
        renderAssemblageTab(data.tab_assemblage);
        renderCartographyTab(data.tab_cartography);
        if (data.tab_graph) {
          pipelineData.graph = data.tab_graph;
          renderGraphTab(data.tab_graph);
          markTabHasData('graph');
        }
        if (data.pipeline_meta) {
          updateMetaBar(data.pipeline_meta);
          pipelineData.pipeline_meta = data.pipeline_meta;
        }
        markTabHasData('resonance');
        markTabHasData('assemblage');
        markTabHasData('cartography');
      }
      break;

    // V3: Semantic Topography
    case 'topography':
      if (status === 'running') setStage('topography', 'running');
      if (status === 'complete') {
        setStage('topography', 'complete');
        pipelineData.topography = data;
        renderTopographyTab(data);
        markTabHasData('topography');
      }
      break;

    case 'done':
      if (status === 'complete') {
        if (data.tab_topography && !pipelineData.topography) {
          pipelineData.topography = data.tab_topography;
          renderTopographyTab(data.tab_topography);
          markTabHasData('topography');
          setStage('topography', 'complete');
        }
        if (data.pipeline_meta) updateMetaBar(data.pipeline_meta);
        if (data.run_id) showRunReport(data.run_id, data.report_path);
        console.log('Pipeline complete:', data);
      }
      break;
  }
}

/* ═════════════════════════════════════════════════════════════════
   LENS MANAGEMENT
   ═════════════════════════════════════════════════════════════════ */

async function generateLenses() {
  const query = document.getElementById('queryInput').value.trim();
  if (!query || query.length < 5) return;

  const generating = document.getElementById('lensGenerating');
  const btn        = document.getElementById('genLensesBtn');

  if (generating) generating.hidden = false;
  if (btn) { btn.disabled = true; btn.textContent = '…'; }

  try {
    const resp = await fetch(`${API_BASE}/lenses`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    _lenses = data.lenses || [];
    _lensGenQuery = query;
    _renderLensCards();
  } catch (err) {
    console.warn('Lens generation failed:', err);
    // Don't block traversal — current lenses stay in place
    showError('Lens generation failed — using current lenses.');
  } finally {
    if (generating) generating.hidden = true;
    if (btn) { btn.disabled = false; btn.textContent = '◈ Propose Lenses'; }
  }
}

function _renderLensCards() {
  const grid = document.getElementById('lensCardsGrid');
  if (!grid) return;
  grid.innerHTML = '';
  _lenses.forEach((lens, idx) => {
    grid.appendChild(_makeLensCard(lens, idx));
  });
  _updateLensCountBadge();
}

function _makeLensCard(lens, idx) {
  const card = document.createElement('div');
  card.className = 'lens-card';
  card.dataset.idx = idx;

  const isRupture = lens.is_rupture_lens || false;
  const vocab = Array.isArray(lens.signal_vocabulary)
    ? lens.signal_vocabulary.join(', ')
    : (lens.signal_vocabulary || '');

  card.innerHTML = `
    <div class="lens-card-header">
      <input class="lens-input lens-name" type="text" value="${esc(lens.name)}" placeholder="Lens name…"
        oninput="_patchLens(${idx},'name',this.value)">
      <label class="lens-rupture-toggle" title="Mark as rupture lens">
        <input type="checkbox" ${isRupture ? 'checked' : ''}
          onchange="_patchLens(${idx},'is_rupture_lens',this.checked)">
        <span class="lens-rupture-label">Rupture</span>
      </label>
      <button class="lens-delete-btn" onclick="_deleteLens(${idx})" title="Remove lens">✕</button>
    </div>
    <input class="lens-input lens-tradition" type="text" value="${esc(lens.tradition || '')}"
      placeholder="Theoretical tradition…"
      oninput="_patchLens(${idx},'tradition',this.value)">
    <textarea class="lens-input lens-question" rows="2"
      placeholder="Core question this lens asks of every paper…"
      oninput="_patchLens(${idx},'core_question',this.value)">${esc(lens.core_question || '')}</textarea>
    <input class="lens-input lens-vocab" type="text" value="${esc(vocab)}"
      placeholder="Signal vocabulary (comma-separated)…"
      oninput="_patchLens(${idx},'signal_vocabulary',this.value.split(',').map(s=>s.trim()).filter(Boolean))">
    <input class="lens-input lens-axiom" type="text" value="${esc(lens.axiom_it_dismantles || '')}"
      placeholder="Dominant assumption this lens dismantles (optional)…"
      oninput="_patchLens(${idx},'axiom_it_dismantles',this.value||null)">
  `;
  return card;
}

function _patchLens(idx, key, value) {
  if (_lenses[idx]) _lenses[idx][key] = value;
}

function _deleteLens(idx) {
  _lenses.splice(idx, 1);
  _renderLensCards();
}

function addBlankLens() {
  _lenses.push({
    name: '',
    tradition: '',
    core_question: '',
    signal_vocabulary: [],
    axiom_it_dismantles: null,
    is_rupture_lens: false,
  });
  _renderLensCards();
  // Focus the new card's name input
  const cards = document.querySelectorAll('.lens-card');
  const last  = cards[cards.length - 1];
  if (last) last.querySelector('.lens-name')?.focus();
}

function _collectLenses() {
  // Read live DOM values into clean objects
  return _lenses.map((lens, idx) => {
    const card = document.querySelector(`.lens-card[data-idx="${idx}"]`);
    if (!card) return lens;
    return {
      name:               card.querySelector('.lens-name')?.value  || lens.name,
      tradition:          card.querySelector('.lens-tradition')?.value || lens.tradition,
      core_question:      card.querySelector('.lens-question')?.value || lens.core_question,
      signal_vocabulary:  (card.querySelector('.lens-vocab')?.value || '')
                            .split(',').map(s => s.trim()).filter(Boolean),
      axiom_it_dismantles: card.querySelector('.lens-axiom')?.value || null,
      is_rupture_lens:    card.querySelector('input[type=checkbox]')?.checked || false,
    };
  });
}

function _updateLensCountBadge() {
  const badge = document.getElementById('lensCountBadge');
  if (!badge) return;
  badge.textContent = _lenses.length
    ? `${_lenses.length} lens${_lenses.length !== 1 ? 'es' : ''}`
    : '';
}

/* ─── Run Report Notice ──────────────────────────────────────── */
function showRunReport(runId, reportPath) {
  const notice = document.getElementById('runReportNotice');
  const pathEl = document.getElementById('runReportPath');
  if (!notice) return;
  if (pathEl) {
    const display = reportPath
      ? reportPath.replace(/.*\/output\//, 'output/')
      : `output/runs/${runId}/run_report.json`;
    pathEl.textContent = display;
  }
  notice.hidden = false;
}

function dismissRunReport() {
  const notice = document.getElementById('runReportNotice');
  if (notice) notice.hidden = true;
}

/* ═════════════════════════════════════════════════════════════════
   TAB RENDERERS
   ═════════════════════════════════════════════════════════════════ */

/* ─── Tab 1: Entry ───────────────────────────────────────────── */
function renderEntryTab(data) {
  const el = document.getElementById('entry-content');
  const placeholder = document.getElementById('entry-placeholder');
  if (placeholder) {
    placeholder.hidden = true;
    placeholder.style.display = 'none';
  }
  el.hidden = false;
  el.style.display = 'block';

  const ruptureBadge = data.rupture_risk
    ? `<span class="chip chip-amber">⚠ Rupture Risk</span>`
    : `<span class="chip chip-green">✓ Stable Entry</span>`;

  el.innerHTML = `
    <div>
      <p class="section-heading">Active Entry Points</p>
      <div class="chip-list">
        ${data.active_entry_points.map(p => `<span class="chip chip-blue">${esc(p)}</span>`).join('')}
      </div>
    </div>
    <div>
      <p class="section-heading">Dominant Frameworks Detected</p>
      <div class="chip-list">
        ${data.dominant_frameworks_detected.map(f => `<span class="chip chip-violet">${esc(f)}</span>`).join('')}
        ${ruptureBadge}
      </div>
    </div>
    <div>
      <p class="section-heading">Entry Narrative</p>
      <div class="narrative-block">${esc(data.narrative)}</div>
    </div>
  `;
  animateIn(el);
}

/* ─── Tab 2: Modules ─────────────────────────────────────────── */
function renderModulesTab(modules) {
  const el = document.getElementById('modules-content');
  const placeholder = document.getElementById('modules-placeholder');
  if (placeholder) {
    placeholder.hidden = true;
    placeholder.style.display = 'none';
  }
  el.hidden = false;
  el.style.display = 'block';

  const moduleKeys = Object.keys(modules);
  const stripHtml = moduleKeys.map((k, i) =>
    `<button class="module-tab${i === 0 ? ' active' : ''}" onclick="switchModule('${escAttr(k)}')" id="mtab-${i}">${esc(k)}</button>`
  ).join('');

  const panelsHtml = moduleKeys.map((k, i) => {
    const mod = modules[k];
    return `
      <div class="module-panel${i === 0 ? ' active' : ''}" id="mpanel-${escAttr(k)}">
        <div>
          <p class="section-heading">Analyzed Sources (${mod.analyzed_sources.length})</p>
          <div class="card-grid">
            ${mod.analyzed_sources.map(s => `
              <div class="info-card">
                <div class="card-title">${esc(s.title)}</div>
                <div class="card-authors">${esc(s.authors)}</div>
                <div class="card-signal">${esc(s.relevance_signal)}</div>
              </div>
            `).join('')}
          </div>
        </div>
        <div>
          <p class="section-heading">Extracted Becomings</p>
          <div class="chip-list">
            ${mod.extracted_becomings.map(b => `<span class="chip chip-green">${esc(b)}</span>`).join('')}
          </div>
        </div>
        <div>
          <p class="section-heading">Tensions & Blockages</p>
          <div class="chip-list">
            ${mod.identified_tensions.map(t => `<span class="chip chip-amber">${esc(t)}</span>`).join('')}
          </div>
        </div>
        <div>
          <p class="section-heading">Cross-Disciplinary Entanglement</p>
          <div class="narrative-block">${esc(mod.conceptual_entanglement_nexus)}</div>
        </div>
      </div>
    `;
  }).join('');

  // ── ABS Screening Panel ────────────────────────────────────────
  const abs = pipelineData.abs_check;
  let absPanelHtml = '';
  if (abs) {
    const quarantined = (abs.verdicts || []).filter(v => v.verdict === 'quarantine');
    const hasDetail = abs.verdicts && abs.verdicts.length > 0;

    const verdictRows = hasDetail ? abs.verdicts.map(v => `
      <div class="abs-verdict-row">
        <span class="abs-verdict-badge ${escAttr(v.verdict)}">${esc(v.verdict)}</span>
        <div>
          <div class="abs-verdict-title">${esc(v.title)}</div>
          ${v.rationale ? `<div class="abs-verdict-rationale">${esc(v.rationale)}</div>` : ''}
        </div>
      </div>
    `).join('') : '<p style="color:var(--clr-text-dim);font-size:0.78rem;margin:10px 0">No verdict detail available.</p>';

    absPanelHtml = `
      <div class="abs-panel" id="abs-panel">
        <div class="abs-panel-header" onclick="toggleAbsPanel()">
          <span class="abs-panel-title">Journal Screening — ABS</span>
          <div class="abs-stats">
            <span class="abs-chip pass">✓ ${abs.approved ?? (abs.total_screened - abs.quarantined)} approved</span>
            ${abs.quarantined > 0 ? `<span class="abs-chip quarantine">⚠ ${abs.quarantined} quarantined</span>` : ''}
          </div>
          <span class="abs-chevron">▼</span>
        </div>
        <div class="abs-panel-body">${verdictRows}</div>
      </div>
    `;
  }

  el.innerHTML = `
    ${absPanelHtml}
    <div class="module-tab-strip">${stripHtml}</div>
    ${panelsHtml}
  `;
  animateIn(el);
}

function switchModule(key) {
  document.querySelectorAll('.module-tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.module-panel').forEach(p => p.classList.remove('active'));
  const panelId = `mpanel-${key}`;
  const panel = document.getElementById(panelId);
  if (panel) panel.classList.add('active');
  // Activate matching tab button
  document.querySelectorAll('.module-tab').forEach(t => {
    if (t.textContent === key) t.classList.add('active');
  });
}

function toggleAbsPanel() {
  const panel = document.getElementById('abs-panel');
  if (panel) panel.classList.toggle('open');
}

/* ─── Tab 3: Resonance ───────────────────────────────────────── */
function renderResonanceTab(data) {
  const el = document.getElementById('resonance-content');
  const placeholder = document.getElementById('resonance-placeholder');
  if (placeholder) {
    placeholder.hidden = true;
    placeholder.style.display = 'none';
  }
  el.hidden = false;
  el.style.display = 'block';

  const ruptureHtml = data.rupture_triggered
    ? `<div class="rupture-banner">
        <span class="rupture-icon">⚡</span>
        <p><strong>Rupture Protocol Activated.</strong> ${esc(data.rupture_rationale || '')}<br/>
        <em>Outside entry: ${esc((data.rupture_protocol?.outside_view_entry_points || []).join(' · '))}</em></p>
       </div>`
    : '';

  const anomaliesHtml = (data.convergent_anomalies || []).map(a => `
    <div class="anomaly-card">
      <div class="anomaly-title">⊕ ${esc(a.phenomenon)}</div>
      <div class="chip-list" style="margin-bottom:8px">
        ${(a.fields_involved || []).map(f => `<span class="chip chip-blue">${esc(f)}</span>`).join('')}
        ${(a.interfering_frameworks || []).map(f => `<span class="chip chip-violet">${esc(f)}</span>`).join('')}
      </div>
      <div class="anomaly-signal">${esc(a.amplification_signal)}</div>
    </div>
  `).join('');

  el.innerHTML = `
    ${ruptureHtml}
    <div>
      <p class="section-heading">Convergent Anomalies (${(data.convergent_anomalies || []).length})</p>
      ${anomaliesHtml}
    </div>
    <div>
      <p class="section-heading">Cross-Module Tensions</p>
      <div class="chip-list">
        ${(data.cross_module_tensions || []).map(t => `<span class="chip chip-amber">${esc(t)}</span>`).join('')}
      </div>
    </div>
    <div>
      <p class="section-heading">Synthesis Direction</p>
      <div class="narrative-block">${esc(data.synthesis_note)}</div>
    </div>
  `;
  animateIn(el);
}

/* ─── Tab 4: Assemblage ──────────────────────────────────────── */
function renderAssemblageTab(data) {
  const el = document.getElementById('assemblage-content');
  const placeholder = document.getElementById('assemblage-placeholder');
  if (placeholder) {
    placeholder.hidden = true;
    placeholder.style.display = 'none';
  }
  el.hidden = false;
  el.style.display = 'block';

  const assemblagesHtml = (data.provisional_assemblages || []).map(a => `
    <div class="assemblage-item">
      <div class="assemblage-label">◉ ${esc(a.label)}</div>
      <div class="assemblage-narrative">${esc(a.becoming_narrative)}</div>
      <div class="chip-list">
        ${(a.constituting_elements || []).map(e => `<span class="chip chip-violet">${esc(e)}</span>`).join('')}
      </div>
    </div>
  `).join('');

  el.innerHTML = `
    <div>
      <p class="section-heading">Dominant Narrative</p>
      <div class="narrative-block">${esc(data.dominant_narrative)}</div>
    </div>
    <div>
      <p class="section-heading">Provisional Assemblages</p>
      ${assemblagesHtml}
    </div>
    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <div>
        <p class="section-heading">Deterritorializing Forces</p>
        <div class="chip-list">
          ${(data.deterritorializing_forces || []).map(f => `<span class="chip chip-green">${esc(f)}</span>`).join('')}
        </div>
      </div>
      <div>
        <p class="section-heading">Reterritorializing Forces</p>
        <div class="chip-list">
          ${(data.reterritorializing_forces || []).map(f => `<span class="chip chip-red">${esc(f)}</span>`).join('')}
        </div>
      </div>
    </div>
  `;
  animateIn(el);
}

/* ─── Tab 5: Cartography ─────────────────────────────────────── */
function renderCartographyTab(data) {
  const el = document.getElementById('cartography-content');
  const placeholder = document.getElementById('cartography-placeholder');
  if (placeholder) {
    placeholder.hidden = true;
    placeholder.style.display = 'none';
  }
  el.hidden = false;
  el.style.display = 'block';

  const moduleBadgeColor = {
    'Innovation Commons': 'chip-green',
    'Complexity & Assemblage': 'chip-blue',
    'Material & Infrastructural Flows': 'chip-violet',
  };

  const sourcesHtml = (data.source_map || []).map(s => `
    <tr>
      <td>${esc(s.title)}</td>
      <td class="td-module"><span class="chip ${moduleBadgeColor[s.module] || 'chip-blue'}"
          style="font-size:0.66rem">${esc(s.module)}</span></td>
      <td>${esc(s.signal)}</td>
    </tr>
  `).join('');

  const convergenceHtml = (data.convergence_nodes || []).map(n =>
    `<span class="chip chip-amber">⊕ ${esc(n)}</span>`
  ).join('');

  el.innerHTML = `
    <div>
      <p class="section-heading">Research Trajectory</p>
      <div class="narrative-block">${esc(data.research_trajectory)}</div>
    </div>
    <div>
      <p class="section-heading">Convergence Nodes</p>
      <div class="chip-list">${convergenceHtml}</div>
    </div>
    <div>
      <p class="section-heading">Lines of Flight</p>
      <div class="chip-list">
        ${(data.lines_of_flight || []).map(f => `<span class="chip chip-green">→ ${esc(f)}</span>`).join('')}
      </div>
    </div>
    <div>
      <p class="section-heading">Source Map (${(data.source_map || []).length} unique sources)</p>
      <div style="overflow-x:auto">
        <table class="source-table">
          <thead><tr><th>Title</th><th>Module</th><th>Signal</th></tr></thead>
          <tbody>${sourcesHtml}</tbody>
        </table>
      </div>
    </div>
  `;
  animateIn(el);
}

/* ─── Tab 6: Graph ───────────────────────────────────────────── */
let simulation = null;

function renderGraphTab(data) {
  const el = document.getElementById('graph-content');
  const panel = document.getElementById('tab-graph');
  const placeholder = document.getElementById('graph-placeholder');
  
  if (placeholder) {
    placeholder.hidden = true;
    placeholder.style.display = 'none';
  }
  
  if (el) {
    // If resetTabs cleared the innerHTML, we must restore the viewport structure
    if (!document.getElementById('graph-viewport')) {
      el.innerHTML = `
        <div class="graph-header">
          <h2 style="color:var(--clr-accent-1); margin:0 0 5px 0; font-size:1.2rem">Rhizomatic Relationship Topology</h2>
          <p style="color:var(--clr-text-muted); font-size:0.85rem; margin:0">
            Explore connections between actors, concepts, and tensions.
            <span style="color:#ff6b9d">◆ Angular nodes = Rupture papers.</span>
            Click a rupture node to activate Blast Radius. Click any edge for detail.
          </p>
        </div>
        <div class="graph-legend" style="display:flex;gap:16px;margin:10px 0;flex-wrap:wrap">
          <span style="font-size:0.7rem;color:var(--clr-text-dim)"><span style="color:#63b3ed">●</span> Actor</span>
          <span style="font-size:0.7rem;color:var(--clr-text-dim)"><span style="color:#b794f4">●</span> Concept</span>
          <span style="font-size:0.7rem;color:var(--clr-text-dim)"><span style="color:#68d391">●</span> Technology</span>
          <span style="font-size:0.7rem;color:var(--clr-text-dim)"><span style="color:#f6ad55">●</span> Tension</span>
          <span style="font-size:0.7rem;color:var(--clr-text-dim)"><span style="color:#ff6b9d">◆</span> Rupture</span>
          <span style="font-size:0.7rem;color:var(--clr-text-dim)">— Constructive</span>
          <span style="font-size:0.7rem;color:var(--clr-text-dim);text-decoration:line-through">- - Critical</span>
          <span style="font-size:0.7rem;color:#ff6b9d">· · Rhizomatic</span>
        </div>
        <div id="graph-viewport" style="width:100%; height:520px; background:rgba(0,0,0,0.2); border-radius:var(--radius-md); margin-top:10px; position:relative">
          <svg id="rhizome-svg" style="width:100%; height:100%"></svg>
        </div>
        <div id="node-info-overlay" class="glass-card hidden" style="position:absolute; top:80px; right:20px; width:280px; z-index:100; border:1px solid rgba(255,255,255,0.1); padding:20px">
          <button class="close-overlay" onclick="closeNodeInfo()" style="position:absolute; top:10px; right:10px; background:none; border:none; color:var(--clr-text-dim); cursor:pointer">✕</button>
          <div class="overlay-body">
            <h3 id="overlay-title" style="margin:0 0 8px 0; color:var(--clr-accent-1); font-size:1rem">Node Title</h3>
            <div class="overlay-tag" id="overlay-type" style="display:inline-block; padding:2px 8px; background:rgba(255,255,255,0.08); border-radius:4px; font-size:0.65rem; text-transform:uppercase; margin-bottom:8px">Type</div>
            <div id="overlay-axiom" style="display:none; font-size:0.72rem; color:#ff6b9d; margin-bottom:8px; font-style:italic"></div>
            <p id="overlay-desc" style="font-size:0.82rem; line-height:1.6; color:var(--clr-text-muted); margin-bottom:0">Description</p>
            <div class="overlay-meta" style="font-size:0.7rem; color:var(--clr-text-dim); margin-top:15px; border-top:1px solid rgba(255,255,255,0.05); padding-top:12px">
              Intensity: <span id="overlay-intensity">0.0</span>
            </div>
          </div>
        </div>
        <div id="edge-detail-panel" class="glass-card hidden" style="position:absolute; bottom:20px; right:20px; width:300px; z-index:100; border:1px solid rgba(255,255,255,0.1); padding:20px; font-size:0.82rem"></div>
      `;
    }
    el.hidden = false;
    el.style.display = 'block';
  }

  // Ensure the parent panel is active so D3 can measure dimensions
  if (panel && !panel.classList.contains('active')) {
      console.log("Graph panel not active, deferring D3 init until tab switch");
  } else {
      setTimeout(() => initRhizomeGraph(data), 50);
  }
  
  if (el) animateIn(el);
}

/* ─── V3: Node color & shape helpers ─────────────────────────── */
function nodeColor(d) {
  if (d.is_rupture_node || d.type === 'rupture') return '#ff6b9d'; // neon pink — rupture
  if (d.type === 'actor')      return '#63b3ed'; // cyan
  if (d.type === 'concept')    return '#b794f4'; // violet
  if (d.type === 'technology') return '#68d391'; // emerald
  return '#f6ad55';                              // amber — tension
}

function nodeGlow(d) {
  if (d.is_rupture_node || d.type === 'rupture') return 'url(#rupture-glow)';
  return null;
}

/* ─── V3: Edge style per type ────────────────────────────────── */
function edgeStroke(d) {
  if (d.edge_type === 'rhizomatic') return '#ff6b9d';
  if (d.edge_type === 'critical')   return '#f6ad55';
  return 'rgba(255,255,255,0.25)'; // constructive (default)
}

function edgeDash(d) {
  if (d.edge_type === 'critical')   return '6,3';
  if (d.edge_type === 'rhizomatic') return '2,2';
  return null; // solid
}

function edgeWidth(d) {
  if (d.edge_type === 'rhizomatic') return Math.sqrt(d.intensity || 0.5) * 4;
  if (d.edge_type === 'critical')   return Math.sqrt(d.intensity || 0.5) * 3;
  return Math.sqrt(d.intensity || 0.5) * 2;
}

function initRhizomeGraph(data) {
  if (typeof d3 === 'undefined') {
    const container = document.getElementById('graph-viewport');
    if (container) container.innerHTML = '<div style="color:var(--clr-accent-err); padding:20px; text-align:center">D3 library failed to load.</div>';
    return;
  }
  const container = document.getElementById('graph-viewport');
  if (!container) return;
  const width = container.clientWidth || 800;
  const height = container.clientHeight || 500;

  if (!data || !data.nodes || data.nodes.length === 0) return;

  try {
    d3.select('#rhizome-svg').selectAll('*').remove();

    const svg = d3.select('#rhizome-svg')
      .attr('viewBox', [0, 0, width, height])
      .call(d3.zoom().on('zoom', (event) => {
        g.attr('transform', event.transform);
      }));

    // V3: SVG defs for rupture glow filter
    const defs = svg.append('defs');
    const ruptureGlow = defs.append('filter').attr('id', 'rupture-glow');
    ruptureGlow.append('feGaussianBlur').attr('stdDeviation', '4').attr('result', 'blur');
    const feMerge = ruptureGlow.append('feMerge');
    feMerge.append('feMergeNode').attr('in', 'blur');
    feMerge.append('feMergeNode').attr('in', 'SourceGraphic');

    const g = svg.append('g');

    const nodes = data.nodes.map(d => ({ ...d }));
    const nodeIds = new Set(nodes.map(n => n.id));
    const links = (data.edges || [])
      .filter(e => nodeIds.has(e.source) && nodeIds.has(e.target))
      .map(d => ({ ...d }));

    // V3: Rupture nodes get high repulsive force — orbit the periphery
    simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(d => {
        const sourceRupture = d.source.is_rupture_node || d.source.type === 'rupture';
        const targetRupture = d.target.is_rupture_node || d.target.type === 'rupture';
        return (sourceRupture || targetRupture) ? 220 : 100; // rupture links high tension
      }))
      .force('charge', d3.forceManyBody().strength(d =>
        (d.is_rupture_node || d.type === 'rupture') ? -800 : -300  // rupture nodes highly repulsive
      ))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(d =>
        (d.is_rupture_node || d.type === 'rupture') ? 55 : 40
      ));

    // V3: Draw edges with type-specific styling
    const link = g.append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('class', d => `link link-${d.edge_type || 'constructive'}`)
      .attr('stroke', d => edgeStroke(d))
      .attr('stroke-width', d => edgeWidth(d))
      .attr('stroke-dasharray', d => edgeDash(d))
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        event.stopPropagation();
        showEdgeDetail(d);
      });

    // V3: Rupture nodes as angular polygon (diamond), others as circle
    const nodeGroup = g.append('g').selectAll('g.node-g').data(nodes).join('g')
      .attr('class', 'node-g')
      .call(drag(simulation))
      .on('click', (event, d) => {
        event.stopPropagation();
        if (d.is_rupture_node || d.type === 'rupture') {
          toggleBlastRadius(d, node, link);
        } else {
          if (blastRadiusActive) clearBlastRadius(node, link);
          showNodeInfo(d);
        }
      });

    // Circles for standard nodes, polygon for rupture
    nodeGroup.each(function(d) {
      const el = d3.select(this);
      const r = 8 + (d.importance * 12);
      if (d.is_rupture_node || d.type === 'rupture') {
        // Angular diamond geometry — V3 spec
        const s = r * 1.4;
        el.append('polygon')
          .attr('points', `0,${-s} ${s},0 0,${s} ${-s},0`)
          .attr('fill', nodeColor(d))
          .attr('filter', 'url(#rupture-glow)')
          .attr('class', 'node rupture-node')
          .style('stroke', '#ff6b9d')
          .style('stroke-width', '1.5px');
      } else {
        el.append('circle')
          .attr('r', r)
          .attr('fill', nodeColor(d))
          .attr('class', 'node');
      }
    });

    const node = nodeGroup; // alias for blast radius

    const label = g.append('g')
      .selectAll('text')
      .data(nodes)
      .join('text')
      .attr('class', 'node-label')
      .attr('fill', '#ffffff')
      .attr('dy', d => 18 + (d.importance * 12))
      .attr('text-anchor', 'middle')
      .style('font-size', '11px')
      .style('font-weight', d => (d.is_rupture_node || d.type === 'rupture') ? '700' : '500')
      .style('pointer-events', 'none')
      .text(d => d.label);

    // Dismiss blast radius on svg click
    svg.on('click', () => {
      if (blastRadiusActive) clearBlastRadius(node, link);
    });

    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);

      nodeGroup.attr('transform', d => `translate(${d.x},${d.y})`);

      label
        .attr('x', d => d.x)
        .attr('y', d => d.y);
    });

  } catch (err) {
    console.error("D3 Graph rendering error:", err);
  }
}

function drag(simulation) {
  function dragstarted(event) {
    if (!event.active) simulation.alphaTarget(0.3).restart();
    event.subject.fx = event.subject.x;
    event.subject.fy = event.subject.y;
  }
  function dragged(event) {
    event.subject.fx = event.x;
    event.subject.fy = event.y;
  }
  function dragended(event) {
    if (!event.active) simulation.alphaTarget(0);
    event.subject.fx = null;
    event.subject.fy = null;
  }
  return d3.drag()
    .on('start', dragstarted)
    .on('drag', dragged)
    .on('end', dragended);
}

/* ─── V3: Blast Radius ───────────────────────────────────────── */
function toggleBlastRadius(ruptureNode, nodeSelection, linkSelection) {
  if (blastRadiusActive && blastRadiusNode && blastRadiusNode.id === ruptureNode.id) {
    clearBlastRadius(nodeSelection, linkSelection);
    return;
  }
  blastRadiusActive = true;
  blastRadiusNode = ruptureNode;

  // Find all edges connected to this rupture node
  const connectedNodeIds = new Set([ruptureNode.id]);
  linkSelection.each(d => {
    const srcId = d.source.id || d.source;
    const tgtId = d.target.id || d.target;
    if (srcId === ruptureNode.id || tgtId === ruptureNode.id) {
      connectedNodeIds.add(srcId);
      connectedNodeIds.add(tgtId);
    }
  });

  // Dim everything except connected nodes and rupture edges
  nodeSelection.style('opacity', d =>
    connectedNodeIds.has(d.id) ? 1.0 : 0.08
  );
  linkSelection.style('opacity', d => {
    const srcId = d.source.id || d.source;
    const tgtId = d.target.id || d.target;
    return (srcId === ruptureNode.id || tgtId === ruptureNode.id) ? 1.0 : 0.04;
  });

  // Show node info for the rupture node
  showNodeInfo(ruptureNode);
}

function clearBlastRadius(nodeSelection, linkSelection) {
  blastRadiusActive = false;
  blastRadiusNode = null;
  nodeSelection.style('opacity', 1.0);
  linkSelection.style('opacity', 1.0);
}

/* ─── V3: Edge Detail Panel ──────────────────────────────────── */
function showEdgeDetail(edge) {
  const panel = document.getElementById('edge-detail-panel');
  if (!panel) return;

  const srcLabel = edge.source.label || edge.source;
  const tgtLabel = edge.target.label || edge.target;

  const edgeTypeLabel = {
    rhizomatic: 'Rhizomatic Edge — Paradigm Rupture',
    critical:   'Critical Edge — Methodological Friction',
    constructive: 'Constructive Edge — Evolutionary Link',
  }[edge.edge_type] || 'Relationship';

  const edgeTypeColor = {
    rhizomatic: '#ff6b9d',
    critical:   '#f6ad55',
    constructive: 'var(--clr-accent-1)',
  }[edge.edge_type] || 'var(--clr-accent-1)';

  let metaHtml = '';
  if (edge.edge_type === 'rhizomatic') {
    metaHtml = `
      <div class="edge-detail-meta">
        <div class="edge-meta-row">
          <span class="edge-meta-label">Axiom Target</span>
          <span class="edge-meta-value">${esc(edge.axiom_target || '—')}</span>
        </div>
        <div class="edge-meta-row">
          <span class="edge-meta-label">Counter-Axiom</span>
          <span class="edge-meta-value">${esc(edge.counter_axiom || '—')}</span>
        </div>
        <div class="edge-meta-row">
          <span class="edge-meta-label">Rupture Vector</span>
          <span class="edge-meta-value chip chip-violet">${esc(edge.rupture_vector || '—')}</span>
        </div>
      </div>
    `;
  }

  panel.innerHTML = `
    <button class="close-overlay" onclick="closeEdgeDetail()" style="position:absolute;top:10px;right:10px;background:none;border:none;color:var(--clr-text-dim);cursor:pointer;font-size:1rem">✕</button>
    <div style="font-size:0.65rem;text-transform:uppercase;letter-spacing:.08em;color:${edgeTypeColor};margin-bottom:10px;font-weight:600">${esc(edgeTypeLabel)}</div>
    <div style="font-size:0.85rem;color:var(--clr-text-primary);margin-bottom:6px">
      <strong>${esc(srcLabel)}</strong>
    </div>
    <div style="font-size:0.75rem;color:var(--clr-text-muted);margin-bottom:4px">
      <em>${esc(edge.relationship)}</em>
    </div>
    <div style="font-size:0.85rem;color:var(--clr-text-primary);margin-bottom:12px">
      <strong>${esc(tgtLabel)}</strong>
    </div>
    <div style="font-size:0.7rem;color:var(--clr-text-dim);margin-bottom:12px">
      Intensity: ${(edge.intensity || 0).toFixed(2)}
    </div>
    ${metaHtml}
  `;
  panel.classList.remove('hidden');
}

function closeEdgeDetail() {
  const panel = document.getElementById('edge-detail-panel');
  if (panel) panel.classList.add('hidden');
}

function showNodeInfo(node) {
  const overlay = document.getElementById('node-info-overlay');
  if (!overlay) return;
  document.getElementById('overlay-title').textContent = node.label;
  document.getElementById('overlay-type').textContent = node.type + (node.is_rupture_node ? ' ⚡ RUPTURE' : '');
  document.getElementById('overlay-desc').textContent = node.description || '';
  document.getElementById('overlay-intensity').textContent = (node.importance || 0).toFixed(2);
  // V3: Show axiom dismantled if rupture node
  const axiomEl = document.getElementById('overlay-axiom');
  if (axiomEl) {
    if (node.axiom_dismantled) {
      axiomEl.textContent = `Dismantles: ${node.axiom_dismantled}`;
      axiomEl.style.display = 'block';
    } else {
      axiomEl.style.display = 'none';
    }
  }
  overlay.classList.remove('hidden');
}

function closeNodeInfo() {
  const overlay = document.getElementById('node-info-overlay');
  if (overlay) overlay.classList.add('hidden');
}

/* ─── Tab 7: Topography ──────────────────────────────────────── */
// ── Topology colour palette (matches Python script) ───────────────────────────
const TOPO_PALETTE = [
  '#4C72B0','#DD8452','#55A868','#C44E52','#8172B3',
  '#937860','#DA8BC3','#8C8C8C','#CCB974','#64B5CD',
  '#E377C2','#7F7F7F','#BCBD22','#17BECF','#AEC7E8','#FFBB78',
];
function topoColor(clusterId) {
  if (clusterId < 0) return '#555566';
  return TOPO_PALETTE[clusterId % TOPO_PALETTE.length];
}

function renderTopographyTab(data) {
  const el = document.getElementById('topography-content');
  const placeholder = document.getElementById('topography-placeholder');
  if (placeholder) { placeholder.hidden = true; placeholder.style.display = 'none'; }
  el.hidden = false;
  el.style.display = 'block';

  if (!data.bert_enabled) {
    el.innerHTML = `
      <div class="narrative-block" style="text-align:center; color:var(--clr-text-muted)">
        <p style="font-size:1.3rem; margin-bottom:8px">⬟</p>
        <p>${esc(data.message)}</p>
        <p style="margin-top:12px; font-size:0.75rem">To activate: set <code>BERT_ENABLED=true</code> in <code>.env</code> and run:<br>
        <code>pip install sentence-transformers umap-learn hdbscan</code></p>
      </div>`;
    animateIn(el);
    return;
  }

  // ── Build sub-tab shell ───────────────────────────────────────────────────
  const has2D = (data.umap_points_2d || []).length > 0;
  const has3D = (data.umap_points_3d || []).length > 0;

  el.innerHTML = `
    <div style="margin-bottom:12px">
      <span class="chip chip-green" style="font-size:0.7rem">${esc(data.message)}</span>
    </div>
    <div style="display:flex; gap:6px; margin-bottom:16px; border-bottom:1px solid rgba(255,255,255,0.08); padding-bottom:10px">
      ${has2D ? `<button class="topo-subtab active" data-subtab="map2d" onclick="switchTopoSubtab(this,'map2d')">◎ 2D Map</button>` : ''}
      ${has3D ? `<button class="topo-subtab" data-subtab="map3d" onclick="switchTopoSubtab(this,'map3d')">⬡ 3D Map</button>` : ''}
      <button class="topo-subtab${!has2D && !has3D ? ' active' : ''}" data-subtab="analysis" onclick="switchTopoSubtab(this,'analysis')">⟁ Analysis</button>
    </div>
    ${has2D ? `<div id="topo-subtab-map2d" class="topo-subtab-pane" style="display:block">
      <div id="topo-plot-2d" style="width:100%;height:520px"></div>
    </div>` : ''}
    ${has3D ? `<div id="topo-subtab-map3d" class="topo-subtab-pane" style="display:none">
      <div id="topo-plot-3d" style="width:100%;height:560px"></div>
    </div>` : ''}
    <div id="topo-subtab-analysis" class="topo-subtab-pane" style="display:${!has2D && !has3D ? 'block' : 'none'}">
      <div id="topo-analysis-inner"></div>
    </div>`;

  // ── Render analysis cards ─────────────────────────────────────────────────
  const clustersHtml = (data.semantic_clusters || []).map(c => `
    <div class="anomaly-card">
      <div class="anomaly-title" style="display:flex;align-items:center;gap:8px">
        <span style="display:inline-block;width:10px;height:10px;border-radius:50%;background:${topoColor(c.cluster_id)};flex-shrink:0"></span>
        ◎ ${esc(c.label)} <span style="font-size:0.7rem;color:var(--clr-text-dim)">(${c.size} papers)</span>
      </div>
      <div class="chip-list" style="margin:6px 0">
        ${(c.centroid_terms || []).map(t => `<span class="chip chip-blue">${esc(t)}</span>`).join('')}
      </div>
      <div style="font-size:0.75rem;color:var(--clr-text-dim)">${(c.paper_titles || []).slice(0,3).map(t => `• ${esc(t)}`).join('<br>')}</div>
    </div>`).join('');

  const voidsHtml = (data.semantic_voids || []).map(v => `
    <div class="anomaly-card" style="border-color:rgba(246,173,85,0.3)">
      <div class="anomaly-title" style="color:var(--clr-accent-warn)">◌ Semantic Void — Gap distance: ${(v.quantified_gap || 0).toFixed(3)}</div>
      <div style="font-size:0.82rem;color:var(--clr-text-muted);margin:6px 0">${esc(v.description)}</div>
    </div>`).join('');

  const isolationsHtml = (data.orthogonal_isolations || []).map(oi => `
    <div class="anomaly-card" style="border-color:rgba(183,148,244,0.3)">
      <div class="anomaly-title" style="color:var(--clr-accent-2)">⊘ Orthogonal Isolation</div>
      <div style="font-size:0.75rem;color:var(--clr-text-muted);margin:4px 0">
        <strong>${esc(oi.cluster_a_label)}</strong> ↔ <strong>${esc(oi.cluster_b_label)}</strong>
      </div>
      <div class="chip-list" style="margin:4px 0">
        ${(oi.shared_vocabulary || []).map(w => `<span class="chip chip-violet">${esc(w)}</span>`).join('')}
      </div>
      <div style="font-size:0.75rem;color:var(--clr-text-dim)">${esc(oi.interpretation)}</div>
    </div>`).join('');

  const marginHtml = (data.marginalization_index || []).map(m => `
    <div style="font-size:0.78rem;color:var(--clr-text-muted);padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04)">
      <strong style="color:var(--clr-text-primary)">${esc(m.paper_title)}</strong><br>
      ${esc(m.marginalization_signal)}
    </div>`).join('');

  document.getElementById('topo-analysis-inner').innerHTML = `
    <div>
      <p class="section-heading">Semantic Clusters (${(data.semantic_clusters || []).length})</p>
      <div class="card-grid">${clustersHtml || '<p style="color:var(--clr-text-dim)">No clusters detected.</p>'}</div>
    </div>
    <div>
      <p class="section-heading">Semantic Voids — Structural Research Gaps (${(data.semantic_voids || []).length})</p>
      ${voidsHtml || '<p style="color:var(--clr-text-dim)">No voids detected.</p>'}
    </div>
    <div>
      <p class="section-heading">Orthogonal Isolations — Cross-Pollination Failures (${(data.orthogonal_isolations || []).length})</p>
      ${isolationsHtml || '<p style="color:var(--clr-text-dim)">No isolations detected.</p>'}
    </div>
    ${data.marginalization_index && data.marginalization_index.length ? `
    <div>
      <p class="section-heading">Marginalization Index (${data.marginalization_index.length} marginalized papers)</p>
      ${marginHtml}
    </div>` : ''}`;

  // ── Render 2D scatter ─────────────────────────────────────────────────────
  if (has2D && typeof Plotly !== 'undefined') {
    _renderTopo2D(data);
  }

  // ── Render 3D scatter (lazy: only when tab becomes visible) ───────────────
  if (has3D) {
    el._topo3dData = data;  // stash for lazy render
  }

  animateIn(el);
}

function _renderTopo2D(data) {
  const points = data.umap_points_2d || [];
  const clusters = data.semantic_clusters || [];
  const voids = data.semantic_voids || [];
  const isolations = data.orthogonal_isolations || [];

  // Group points by cluster
  const byCluster = {};
  points.forEach(p => {
    const key = p.cluster_id;
    if (!byCluster[key]) byCluster[key] = [];
    byCluster[key].push(p);
  });

  const traces = [];

  // One trace per cluster
  Object.entries(byCluster).forEach(([cidStr, pts]) => {
    const cid = parseInt(cidStr);
    const cluster = clusters.find(c => c.cluster_id === cid);
    const label = cluster ? cluster.label : (cid < 0 ? 'Noise' : `Cluster ${cid}`);
    const color = topoColor(cid);

    // Split marginalized vs normal
    const normal = pts.filter(p => !p.is_marginalized);
    const marg   = pts.filter(p => p.is_marginalized);

    if (normal.length) {
      traces.push({
        type: 'scatter', mode: 'markers',
        name: label,
        x: normal.map(p => p.x), y: normal.map(p => p.y),
        text: normal.map(p => `<b>${p.title}</b><br>${p.authors || ''} ${p.year ? '('+p.year+')' : ''}<br>Cluster: ${label}`),
        hovertemplate: '%{text}<extra></extra>',
        marker: { color, size: 9, opacity: 0.85, line: { width: 0.5, color: '#ffffff44' } },
        legendgroup: `c${cid}`,
      });
    }
    if (marg.length) {
      traces.push({
        type: 'scatter', mode: 'markers',
        name: `${label} (marginalised)`,
        x: marg.map(p => p.x), y: marg.map(p => p.y),
        text: marg.map(p => `<b>${p.title}</b><br>${p.authors || ''} ${p.year ? '('+p.year+')' : ''}<br>⚠ Marginalised — Cluster: ${label}`),
        hovertemplate: '%{text}<extra></extra>',
        marker: { color, size: 10, opacity: 0.9, symbol: 'diamond', line: { width: 1.5, color: '#ff6b6b' } },
        legendgroup: `c${cid}`, showlegend: false,
      });
    }
  });

  // Semantic void markers (midpoints between adjacent cluster centroids)
  if (voids.length) {
    // Compute cluster centroids from points
    const centroids = {};
    const clusters2 = data.semantic_clusters || [];
    clusters2.forEach(c => {
      const pts = (data.umap_points_2d || []).filter(p => p.cluster_id === c.cluster_id);
      if (pts.length) {
        centroids[c.label] = {
          x: pts.reduce((s,p) => s + p.x, 0) / pts.length,
          y: pts.reduce((s,p) => s + p.y, 0) / pts.length,
        };
      }
    });

    const voidX = [], voidY = [], voidText = [];
    voids.forEach(v => {
      const [la, lb] = v.adjacent_cluster_labels || [];
      const ca = centroids[la], cb = centroids[lb];
      if (ca && cb) {
        voidX.push((ca.x + cb.x) / 2);
        voidY.push((ca.y + cb.y) / 2);
        voidText.push(`<b>◌ Semantic Void</b><br>${esc(v.description)}<br>Gap distance: ${(v.quantified_gap||0).toFixed(3)}`);
      }
    });

    if (voidX.length) {
      traces.push({
        type: 'scatter', mode: 'markers+text',
        name: 'Semantic Void',
        x: voidX, y: voidY,
        text: voidText, hovertemplate: '%{text}<extra></extra>',
        marker: { symbol: 'circle-open', size: 22, color: '#f6ad55', opacity: 0.9, line: { width: 2, color: '#f6ad55' } },
        legendrank: 1000,
      });
    }
  }

  // Orthogonal isolation lines
  isolations.forEach((oi, idx) => {
    const clusters2 = data.semantic_clusters || [];
    const ca_pts = (data.umap_points_2d || []).filter(p => {
      const c = clusters2.find(c => c.cluster_id === p.cluster_id);
      return c && c.label === oi.cluster_a_label;
    });
    const cb_pts = (data.umap_points_2d || []).filter(p => {
      const c = clusters2.find(c => c.cluster_id === p.cluster_id);
      return c && c.label === oi.cluster_b_label;
    });
    if (!ca_pts.length || !cb_pts.length) return;

    const ax = ca_pts.reduce((s,p)=>s+p.x,0)/ca_pts.length;
    const ay = ca_pts.reduce((s,p)=>s+p.y,0)/ca_pts.length;
    const bx = cb_pts.reduce((s,p)=>s+p.x,0)/cb_pts.length;
    const by = cb_pts.reduce((s,p)=>s+p.y,0)/cb_pts.length;

    traces.push({
      type: 'scatter', mode: 'lines',
      name: idx === 0 ? 'Orthogonal Isolation' : undefined,
      showlegend: idx === 0,
      legendgroup: 'isolations',
      x: [ax, bx], y: [ay, by],
      line: { color: '#b794f4', width: 1.5, dash: 'dot' },
      hoverinfo: 'skip',
    });
  });

  const layout = {
    template: 'plotly_dark',
    paper_bgcolor: 'rgba(0,0,0,0)',
    plot_bgcolor: 'rgba(16,21,46,0.6)',
    xaxis: { title: 'UMAP 1', gridcolor: '#ffffff0d', zeroline: false },
    yaxis: { title: 'UMAP 2', gridcolor: '#ffffff0d', zeroline: false },
    legend: { font: { size: 11 }, bgcolor: 'rgba(0,0,0,0.4)', bordercolor: '#ffffff22', borderwidth: 1 },
    margin: { l: 50, r: 20, t: 30, b: 50 },
    hovermode: 'closest',
    font: { family: 'Inter, sans-serif', color: '#c8c8d4' },
  };

  Plotly.newPlot('topo-plot-2d', traces, layout, { responsive: true, displayModeBar: true, scrollZoom: true });
}

function _renderTopo3D(data) {
  const points = data.umap_points_3d || [];
  const clusters = data.semantic_clusters || [];

  const byCluster = {};
  points.forEach(p => {
    const key = p.cluster_id;
    if (!byCluster[key]) byCluster[key] = [];
    byCluster[key].push(p);
  });

  const traces = [];
  Object.entries(byCluster).forEach(([cidStr, pts]) => {
    const cid = parseInt(cidStr);
    const cluster = clusters.find(c => c.cluster_id === cid);
    const label = cluster ? cluster.label : (cid < 0 ? 'Noise' : `Cluster ${cid}`);

    traces.push({
      type: 'scatter3d', mode: 'markers',
      name: label,
      x: pts.map(p => p.x), y: pts.map(p => p.y), z: pts.map(p => p.z),
      text: pts.map(p => `<b>${p.title}</b><br>${p.authors||''} ${p.year?'('+p.year+')':''}<br>${p.is_marginalized?'⚠ Marginalised — ':''}<i>${label}</i>`),
      hovertemplate: '%{text}<extra></extra>',
      marker: {
        color: topoColor(cid), size: pts.map(p => p.is_marginalized ? 7 : 5),
        opacity: 0.85, line: { width: 0.3, color: '#ffffff22' },
        symbol: pts.map(p => p.is_marginalized ? 'diamond' : 'circle'),
      },
    });
  });

  const layout = {
    template: 'plotly_dark',
    paper_bgcolor: 'rgba(0,0,0,0)',
    scene: {
      bgcolor: 'rgba(16,21,46,0.6)',
      xaxis: { title: 'UMAP 1', gridcolor: '#ffffff1a' },
      yaxis: { title: 'UMAP 2', gridcolor: '#ffffff1a' },
      zaxis: { title: 'UMAP 3', gridcolor: '#ffffff1a' },
    },
    legend: { font: { size: 11 }, bgcolor: 'rgba(0,0,0,0.4)', bordercolor: '#ffffff22', borderwidth: 1 },
    margin: { l: 0, r: 0, t: 20, b: 0 },
    font: { family: 'Inter, sans-serif', color: '#c8c8d4' },
  };

  Plotly.newPlot('topo-plot-3d', traces, layout, { responsive: true, displayModeBar: true });
}

function switchTopoSubtab(btn, subtab) {
  // Update button states
  document.querySelectorAll('.topo-subtab').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  // Show/hide panes
  document.querySelectorAll('.topo-subtab-pane').forEach(p => p.style.display = 'none');
  const pane = document.getElementById(`topo-subtab-${subtab}`);
  if (pane) pane.style.display = 'block';

  // Lazy-render 3D on first show (Plotly needs the container visible)
  if (subtab === 'map3d') {
    const el = document.getElementById('topography-content');
    if (el && el._topo3dData && typeof Plotly !== 'undefined' && !el._topo3dRendered) {
      _renderTopo3D(el._topo3dData);
      el._topo3dRendered = true;
    }
  }
}

/* ─── Helpers ────────────────────────────────────────────────── */
function resetTabs() {
  ['entry','modules','resonance','assemblage','cartography','graph','topography','history'].forEach(t => {
    const placeholder = document.getElementById(`${t}-placeholder`);
    const content = document.getElementById(`${t}-content`);
    const btn = document.getElementById(`btn-${t}`);
    if (placeholder) {
      placeholder.hidden = false;
      placeholder.style.display = 'flex';
    }
    if (content) {
      content.hidden = true;
      content.style.display = 'none';
      content.innerHTML = '';
    }
    if (btn) btn.classList.remove('has-data');
  });
  closeNodeInfo();
  closeEdgeDetail();
  blastRadiusActive = false;
  blastRadiusNode = null;
}

function resetPipelineBar() {
  ['epistemology','search','abs_check','entry','modules','resonance','assemblage','graph','topography'].forEach(s => {
    const n = document.getElementById(`stage-${s}`);
    if (n) n.className = 'stage-node';
  });
}

function markTabHasData(name) {
  document.getElementById(`btn-${name}`).classList.add('has-data');
  const bar = document.getElementById('ttsBar');
  if (bar) bar.hidden = false;
  if (typeof _ttsAnnounce === 'function') _ttsAnnounce(name);
}

function animateIn(el) {
  el.style.animation = 'none';
  el.offsetHeight; // reflow
  el.style.animation = 'panelIn 0.4s ease forwards';
}

function showError(msg) {
  document.getElementById('errorMessage').textContent = msg;
  document.getElementById('errorToast').hidden = false;
}

function dismissError() {
  document.getElementById('errorToast').hidden = true;
}

// Safe HTML escaping
function esc(str) {
  if (str == null) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// Safe attribute escaping (for IDs)
function escAttr(str) {
  return String(str).replace(/[^a-zA-Z0-9_-]/g, '_');
}

/* ═════════════════════════════════════════════════════════════════
   KOKORO TTS
   ═════════════════════════════════════════════════════════════════ */

let _ttsAudio = null;       // current Audio element
let _ttsObjectURL = null;   // blob URL to revoke on stop
let _ttsPaused = false;
let _ttsCurrentTab = null;  // which tab is loaded

function _ttsSetStatus(msg, cls = '') {
  const el = document.getElementById('ttsStatus');
  if (!el) return;
  el.textContent = msg;
  el.className = 'tts-status' + (cls ? ' ' + cls : '');
}

function _ttsSetBtns({ play, pause, stop }) {
  const p = document.getElementById('ttsPlayBtn');
  const pa = document.getElementById('ttsPauseBtn');
  const s = document.getElementById('ttsStopBtn');
  if (p)  p.disabled  = !play;
  if (pa) pa.disabled = !pause;
  if (s)  s.disabled  = !stop;
}

function _ttsRevoke() {
  if (_ttsObjectURL) { URL.revokeObjectURL(_ttsObjectURL); _ttsObjectURL = null; }
}

function _ttsExtractText(tabName) {
  const content = document.getElementById(`${tabName}-content`);
  if (!content || content.hidden) return '';
  // Grab visible text, skip buttons and select elements
  const clone = content.cloneNode(true);
  clone.querySelectorAll('button, select, input, svg, .tts-bar').forEach(el => el.remove());
  return clone.innerText.replace(/\s+/g, ' ').trim();
}

function _ttsActiveTab() {
  const active = document.querySelector('.tab-btn.active');
  if (!active) return null;
  return active.id.replace('btn-', '');
}

async function ttsPlay() {
  ttsStop();
  const tab = _ttsActiveTab();
  if (!tab) { _ttsSetStatus('No active tab', 'error'); return; }
  const text = _ttsExtractText(tab);
  if (!text) { _ttsSetStatus('No text in tab', 'error'); return; }

  const voice = document.getElementById('ttsVoiceSelect')?.value || 'af_bella';
  _ttsCurrentTab = tab;
  _ttsSetStatus('Loading Kokoro…', 'loading');
  _ttsSetBtns({ play: false, pause: false, stop: true });

  try {
    const resp = await fetch(`${API_BASE}/tts/speak`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, voice, speed: 1.0 }),
    });

    if (!resp.ok) {
      let errMsg = `Backend ${resp.status}`;
      try { const j = await resp.json(); errMsg = j.detail || errMsg; } catch {}
      _ttsSetStatus(`${errMsg} — using browser`, 'error');
      console.warn('Kokoro TTS error:', errMsg);
      _ttsBrowserSpeak(text);
      return;
    }

    const arrayBuf = await resp.arrayBuffer();
    const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    const decoded = await audioCtx.decodeAudioData(arrayBuf);
    const source = audioCtx.createBufferSource();
    source.buffer = decoded;
    source.connect(audioCtx.destination);

    // Store refs for pause/stop
    _ttsAudio = { source, audioCtx, startTime: audioCtx.currentTime, pauseOffset: 0 };
    source.onended = () => {
      _ttsSetStatus('Kokoro TTS');
      _ttsSetBtns({ play: true, pause: false, stop: false });
      document.getElementById('ttsPauseBtn').textContent = '⏸';
      _ttsAudio = null;
    };
    source.start(0);
    _ttsPaused = false;
    _ttsSetStatus('Kokoro · Speaking…', 'speaking');
    _ttsSetBtns({ play: false, pause: true, stop: true });

  } catch (err) {
    console.error('TTS fetch error:', err);
    _ttsSetStatus(`Network error — using browser`, 'error');
    _ttsBrowserSpeak(text);
  }
}

function ttsPause() {
  // Browser TTS fallback
  if (window.speechSynthesis && window.speechSynthesis.speaking) {
    if (_ttsPaused) {
      window.speechSynthesis.resume();
      _ttsPaused = false;
      _ttsSetStatus('Speaking…', 'speaking');
      document.getElementById('ttsPauseBtn').textContent = '⏸';
    } else {
      window.speechSynthesis.pause();
      _ttsPaused = true;
      _ttsSetStatus('Paused');
      document.getElementById('ttsPauseBtn').textContent = '▶';
    }
    return;
  }
  // AudioContext — suspend/resume
  if (_ttsAudio && _ttsAudio.audioCtx) {
    if (_ttsPaused) {
      _ttsAudio.audioCtx.resume();
      _ttsPaused = false;
      _ttsSetStatus('Kokoro · Speaking…', 'speaking');
      document.getElementById('ttsPauseBtn').textContent = '⏸';
    } else {
      _ttsAudio.audioCtx.suspend();
      _ttsPaused = true;
      _ttsSetStatus('Paused');
      document.getElementById('ttsPauseBtn').textContent = '▶';
    }
  }
}

function ttsStop() {
  if (window.speechSynthesis) window.speechSynthesis.cancel();
  if (_ttsAudio && _ttsAudio.source) {
    try { _ttsAudio.source.stop(); } catch {}
    try { _ttsAudio.audioCtx.close(); } catch {}
  }
  _ttsAudio = null;
  _ttsRevoke();
  _ttsPaused = false;
  document.getElementById('ttsPauseBtn').textContent = '⏸';
  _ttsSetStatus('Kokoro TTS');
  _ttsSetBtns({ play: true, pause: false, stop: false });
}

function _ttsBrowserSpeak(text) {
  if (!window.speechSynthesis) {
    _ttsSetStatus('TTS unavailable', 'error');
    _ttsSetBtns({ play: true, pause: false, stop: false });
    return;
  }
  window.speechSynthesis.cancel();
  const utt = new SpeechSynthesisUtterance(text);
  utt.rate = 1.0;
  utt.onstart = () => {
    _ttsSetStatus('Speaking (browser)…', 'speaking');
    _ttsSetBtns({ play: false, pause: true, stop: true });
  };
  utt.onend = () => {
    _ttsSetStatus('Kokoro TTS');
    _ttsSetBtns({ play: true, pause: false, stop: false });
    document.getElementById('ttsPauseBtn').textContent = '⏸';
  };
  utt.onerror = () => {
    _ttsSetStatus('Speech error', 'error');
    _ttsSetBtns({ play: true, pause: false, stop: false });
  };
  window.speechSynthesis.speak(utt);
}

// ── Tab-ready announcements (always on) + Auto-read toggle ───
let _ttsAutoEnabled = false;

function ttsToggleAuto() {
  _ttsAutoEnabled = !_ttsAutoEnabled;
  const btn = document.getElementById('ttsAutoBtn');
  if (btn) {
    btn.classList.toggle('active', _ttsAutoEnabled);
    btn.title = _ttsAutoEnabled ? 'Auto-read ON' : 'Auto-read OFF';
  }
}

const TAB_ANNOUNCEMENTS = {
  entry:       'Entry analysis ready',
  modules:     'Modules analysis ready',
  resonance:   'Resonance analysis ready',
  assemblage:  'Assemblage synthesis ready',
  cartography: 'Cartography ready',
  graph:       'Relationship graph ready',
  topography:  'Semantic topology ready',
  history:     'History loaded',
};

// ── Announcement queue — plays one at a time, in order ───────
const _announceQueue = [];
let _announceRunning = false;

async function _processAnnounceQueue() {
  if (_announceRunning) return;
  _announceRunning = true;
  while (_announceQueue.length > 0) {
    const phrase = _announceQueue.shift();
    const voice = document.getElementById('ttsVoiceSelect')?.value || 'af_nicole';
    await _playAnnouncement(phrase, voice);
  }
  _announceRunning = false;
}

async function _playAnnouncement(phrase, voice) {
  return new Promise(async (resolve) => {
    try {
      const resp = await fetch(`${API_BASE}/tts/speak`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: phrase, voice, speed: 1.0 }),
      });
      if (!resp.ok) throw new Error(`${resp.status}`);
      const arrayBuf = await resp.arrayBuffer();
      const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      const decoded = await audioCtx.decodeAudioData(arrayBuf);
      const source = audioCtx.createBufferSource();
      source.buffer = decoded;
      source.connect(audioCtx.destination);
      source.onended = resolve;
      source.start(0);
    } catch (err) {
      console.warn('Announcement TTS failed:', err);
      resolve();
    }
  });
}

function _ttsAnnounce(tabName) {
  const phrase = TAB_ANNOUNCEMENTS[tabName] || `${tabName} ready`;
  _announceQueue.push(phrase);
  _processAnnounceQueue();
}

// markTabHasData and switchTab are patched directly above (lines ~1120 and ~31)
// to avoid JS hoisting conflicts with function declaration overrides.


/* ═════════════════════════════════════════════════════════════════
   HISTORY TAB
   ═════════════════════════════════════════════════════════════════ */

async function loadHistory() {
  const placeholder = document.getElementById('history-placeholder');
  const content = document.getElementById('history-content');
  try {
    const r = await fetch(`${API_BASE}/runs`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const { runs } = await r.json();

    if (!runs || runs.length === 0) {
      if (placeholder) { placeholder.hidden = false; placeholder.style.display = 'flex'; }
      if (content) content.hidden = true;
      return;
    }

    if (placeholder) { placeholder.hidden = true; placeholder.style.display = 'none'; }
    content.hidden = false;
    content.style.display = 'block';
    content.innerHTML = renderHistoryList(runs);
    animateIn(content);
  } catch (err) {
    console.error('History load failed:', err);
    showError(`History unavailable: ${err.message}`);
  }
}

function renderHistoryList(runs) {
  const rows = runs.map(r => {
    const date = new Date(r.timestamp).toLocaleString();
    const tu = r.token_usage || {};
    const tokens = tu.total_tokens
      ? `${tu.total_tokens.toLocaleString()} tokens · ${tu.call_count || 0} LLM calls`
      : 'Token data unavailable';
    const promptTok = tu.prompt_tokens ? `${tu.prompt_tokens.toLocaleString()} prompt` : '';
    const compTok = tu.completion_tokens ? `${tu.completion_tokens.toLocaleString()} completion` : '';
    const tokenBreakdown = (promptTok && compTok) ? `${promptTok} / ${compTok}` : '';
    const lenses = (r.lens_names || []).join(' · ') || '—';
    const ruptureTag = r.rupture_triggered
      ? `<span style="color:var(--clr-accent-2);font-size:0.7rem;margin-left:6px;font-weight:600">⚡ RUPTURE</span>`
      : '';

    return `
      <div class="glass-card history-run-card" style="margin-bottom:12px;padding:16px 20px;cursor:pointer;border:1px solid rgba(255,255,255,0.06);transition:border-color 0.2s"
           onclick="viewRun('${esc(r.run_id)}')"
           onmouseenter="this.style.borderColor='rgba(255,255,255,0.15)'"
           onmouseleave="this.style.borderColor='rgba(255,255,255,0.06)'">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:16px">
          <div style="flex:1;min-width:0">
            <p style="margin:0 0 6px 0;font-size:0.9rem;font-weight:500;color:var(--clr-text);line-height:1.4">${esc(r.query)}${ruptureTag}</p>
            <p style="margin:0 0 4px 0;font-size:0.72rem;color:var(--clr-text-muted)">${esc(lenses)}</p>
            <p style="margin:0;font-size:0.7rem;color:var(--clr-text-dim)">${esc(tokens)}${tokenBreakdown ? ` &nbsp;·&nbsp; ${esc(tokenBreakdown)}` : ''}</p>
          </div>
          <div style="text-align:right;flex-shrink:0;font-size:0.72rem;color:var(--clr-text-dim);line-height:1.8">
            <div style="color:var(--clr-text-muted)">${esc(date)}</div>
            <div>${r.paper_count != null ? `${r.paper_count} papers` : '—'}</div>
            <div style="font-size:0.65rem;opacity:0.6">${esc(r.model || '—')}</div>
          </div>
        </div>
      </div>
    `;
  });

  const header = `
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
      <p class="section-heading" style="margin:0">${runs.length} past run${runs.length !== 1 ? 's' : ''}</p>
      <button class="traverse-btn" style="padding:6px 14px;font-size:0.75rem" onclick="loadHistory()">
        <span class="btn-text">Refresh</span>
      </button>
    </div>
  `;

  return `<div style="padding:4px 0">${header}${rows.join('')}</div>`;
}

async function viewRun(runId) {
  try {
    setStatus('Loading run…', 'running');
    const r = await fetch(`${API_BASE}/runs/${encodeURIComponent(runId)}`);
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const run = await r.json();

    resetTabs();
    resetPipelineBar();
    pipelineData = {};

    if (run.tab_entry && Object.keys(run.tab_entry).length) {
      renderEntryTab(run.tab_entry);
      markTabHasData('entry');
    }
    if (run.tab_modules && Object.keys(run.tab_modules).length) {
      renderModulesTab(run.tab_modules);
      markTabHasData('modules');
    }
    if (run.tab_resonance && Object.keys(run.tab_resonance).length) {
      renderResonanceTab(run.tab_resonance);
      markTabHasData('resonance');
    }
    if (run.tab_assemblage && Object.keys(run.tab_assemblage).length) {
      renderAssemblageTab(run.tab_assemblage);
      markTabHasData('assemblage');
    }
    if (run.tab_cartography && Object.keys(run.tab_cartography).length) {
      renderCartographyTab(run.tab_cartography);
      markTabHasData('cartography');
    }
    if (run.tab_graph && Object.keys(run.tab_graph).length) {
      pipelineData.graph = run.tab_graph;
      renderGraphTab(run.tab_graph);
      markTabHasData('graph');
    }
    if (run.tab_topography && Object.keys(run.tab_topography).length) {
      renderTopographyTab(run.tab_topography);
      markTabHasData('topography');
    }
    if (run.pipeline_meta) updateMetaBar(run.pipeline_meta);

    document.getElementById('queryInput').value = run.query || '';
    setStatus(`Viewing run from ${new Date(run.timestamp).toLocaleDateString()}`, 'done');
    switchTab('entry');
  } catch (err) {
    showError(`Failed to load run: ${err.message}`);
    setStatus('Error', 'error');
  }
}
