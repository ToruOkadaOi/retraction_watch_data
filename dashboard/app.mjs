import { MAX_NODES, MAX_EDGES, NODE_COLORS, NOTICE_COLORS, KIND_LABELS, shortText, doiHref, displayDate, edgeId, mergeNeighborhood } from './logic.mjs';

const API = location.pathname.startsWith('/dashboard/') ? location.origin : 'https://retraction-watch-data.onrender.com';
const $ = id => document.getElementById(id);
const fmt = number => new Intl.NumberFormat('en').format(number || 0);
const state = { kind: 'Article', q: '', notice: '', journal: '', reason: '', skip: 0, hasMore: false, selected: null,
  graph: { nodes: [], edges: [] }, pages: new Map(), cap: false, busy: false, graphEpoch: 0, resultsEpoch: 0, detailEpoch: 0, overview: null };
let cy = null;
const detailsCache = new Map();

function el(tag, className, text) { const element = document.createElement(tag); if (className) element.className = className; if (text !== undefined) element.textContent = text; return element; }
function button(text, action, className = '') { const element = el('button', className, text); element.type = 'button'; element.addEventListener('click', action); return element; }
function noticeClass(notice) { return notice === 'Expression of concern' ? 'concern' : notice === 'Correction' ? 'correction' : notice === 'Reinstatement' ? 'reinstatement' : ''; }
function noticeBadge(notice) { return el('span', 'notice-badge ' + noticeClass(notice), notice || 'Notice type unavailable'); }
function message(text, retry) {
  const box = $('service-message'); box.replaceChildren(); box.hidden = !text;
  if (text) { box.append(el('span', '', text)); if (retry) box.append(button('Retry connection', () => loadApp(), 'error-retry')); }
}
async function get(path, parameters = {}) {
  const url = new URL(API + path); for (const [key, value] of Object.entries(parameters)) if (value !== '' && value !== null && value !== undefined) url.searchParams.set(key, value);
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 85000);
  try {
    const response = await fetch(url, { signal: controller.signal, credentials: 'omit', headers: { Accept: 'application/json' } });
    if (!response.ok) {
      let detail = '';
      try { const data = await response.json(); detail = typeof data.detail === 'string' ? data.detail : ''; } catch { /* Render may return a temporary HTML wake-up page. */ }
      if (response.status === 503 && detail.startsWith('Graph database unavailable')) throw new Error('The graph database is unavailable. It may be paused or reconnecting; please try again shortly.');
      const error = new Error(response.status === 503 ? (detail.includes('refresh') || detail.includes('Snapshot') ? 'The graph is being refreshed. Please try again after the import completes.' : 'The dataset service is waking up or temporarily unavailable. Please try again in a moment.') : response.status === 404 ? 'The requested graph data is not available. Please try another record or retry shortly.' : 'The dataset request could not be completed. Please retry.');
      error.status = response.status; throw error;
    }
    const payload = await response.json();
    const generation = payload.snapshot_generation || payload.snapshot?.generation;
    const known = state.overview?.snapshot?.generation;
    if (path !== '/api/dashboard/overview' && generation && known && generation !== known) {
      detailsCache.clear(); clearGraph(); message('The hosted snapshot changed. Reload the dataset to continue with one consistent snapshot.', true);
      throw new Error('The hosted snapshot changed. Use Retry connection above to reload the dataset.');
    }
    return payload;
  } catch (error) { if (error.name === 'AbortError') throw new Error('The service took too long to respond. It may be waking up; please retry.'); if (error instanceof TypeError) throw new Error('Could not connect to the dataset service. Please check your connection and retry.'); throw error;
  } finally { clearTimeout(timer); }
}
function filters() { return { notice: state.notice, journal: state.journal, reason: state.reason }; }
function renderFilters() {
  $('notice-filter').value = state.notice;
  $('filter-chips').replaceChildren();
  for (const kind of ['journal', 'reason']) if (state[kind]) {
    const chip = button('', () => { state[kind] = ''; applyFilters(); }, 'filter-chip');
    chip.append(el('span', '', (kind === 'journal' ? 'Journal: ' : 'Reason: ') + state[kind]), el('span', '', '×'));
    chip.setAttribute('aria-label', 'Remove ' + kind + ' filter: ' + state[kind]); chip.title = state[kind]; $('filter-chips').append(chip);
  }
  $('clear-filters').hidden = !(state.notice || state.journal || state.reason);
}
function applyFilters() { state.skip = 0; renderFilters(); clearGraph(); loadResults(true); }
function chartFilter(kind, value, notice = 'Retraction') {
  state.kind = 'Article'; state.q = ''; state.skip = 0; state[kind] = value; state.notice = notice;
  $('search-kind').value = 'Article'; $('search-input').value = ''; applyFilters(); $('workspace').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' });
}
function drawBars(container, rows, kind) {
  container.replaceChildren(); const maximum = Math.max(1, ...rows.map(row => row.count));
  if (!rows.length) { container.append(el('p', 'subtle', 'No retraction notices recorded for this view.')); return; }
  for (const row of rows) {
    const item = button('', () => chartFilter(kind, row.name), 'bar-row');
    item.setAttribute('aria-label', `${row.name}: ${fmt(row.count)} retraction notice records. Filter the explorer.`); item.title = row.name;
    const label = el('span', 'bar-label'); label.append(el('span', 'bar-name', row.name), el('span', 'bar-value', fmt(row.count)));
    const track = el('span', 'bar-track'), fill = el('span', 'bar-fill'); fill.style.width = 100 * row.count / maximum + '%'; track.append(fill); item.append(label, track); container.append(item);
  }
}
function renderOverview(data) {
  if (state.overview?.snapshot?.generation && state.overview.snapshot.generation !== data.snapshot?.generation) { detailsCache.clear(); clearGraph(); }
  state.overview = data;
  $('metric-records').textContent = fmt(data.nodes.Article);
  $('metric-retractions').textContent = fmt(data.notice_counts.Retraction);
  $('metric-nodes').textContent = fmt(data.total_nodes);
  $('metric-edges').textContent = fmt(data.total_relationships);
  $('connection-badge').classList.remove('error'); $('connection-badge').lastElementChild.textContent = data.source === 'neo4j' ? 'Connected · Neo4j Aura' : 'Connected · JSON snapshot';
  const snapshot = data.snapshot || {}, hash = snapshot.source_csv_sha256;
  $('snapshot-label').textContent = hash ? 'Snapshot ' + hash.slice(0, 12) : 'Snapshot fingerprint unavailable';
  $('snapshot-label').title = hash || '';
  $('provenance').replaceChildren(el('div', '', hash ? 'Source CSV SHA-256: ' + shortText(hash, 25) : 'Source CSV fingerprint not recorded.'));
  if (hash) $('provenance').firstChild.title = hash;
  $('provenance').append(el('div', '', snapshot.imported_at ? 'Imported ' + displayDate(snapshot.imported_at) : 'Import time not recorded for this snapshot.'));
  $('provenance').append(el('div', '', 'Hosted refreshes run separately from repository CSV updates.'));
  const total = Object.values(data.notice_counts).reduce((sum, value) => sum + value, 0);
  const breakdown = $('notice-breakdown'); breakdown.replaceChildren();
  for (const [name, count] of Object.entries(data.notice_counts)) {
    const item = button('', () => { state.kind = 'Article'; state.notice = name; state.journal = ''; state.reason = ''; state.q = ''; $('search-input').value = ''; $('search-kind').value = 'Article'; applyFilters(); $('workspace').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth' }); }, 'notice-item');
    item.setAttribute('aria-label', `${name}: ${fmt(count)} records. Filter the explorer.`);
    const value = el('span', 'notice-value', fmt(count)), track = el('span', 'notice-track'), fill = el('i');
    fill.style.width = (total ? count / total * 100 : 0) + '%'; fill.style.background = NOTICE_COLORS[name] || '#5d9181'; track.append(fill);
    const label = el('span', 'notice-label'); label.append(el('span', '', name), el('span', 'notice-percent', (total ? count / total * 100 : 0).toFixed(1) + '%'));
    item.append(value, track, label); breakdown.append(item);
  }
  drawBars($('journal-chart'), data.top_journals, 'journal'); drawBars($('reason-chart'), data.top_reasons, 'reason');
}
async function loadOverview() {
  try { const data = await get('/api/dashboard/overview'); renderOverview(data); message(''); return true; }
  catch (error) { $('connection-badge').classList.add('error'); $('connection-badge').lastElementChild.textContent = 'Connection interrupted'; $('snapshot-label').textContent = 'Snapshot could not be verified'; message(error.message, true); }
}
function resultView(node) {
  const item = button('', () => chooseSeed(node), 'result-button'); item.dataset.nodeId = node.id; item.setAttribute('aria-pressed', String(state.selected?.id === node.id));
  const line = el('div', 'result-topline'); line.append(el('span', 'record-id', node.type === 'Article' ? 'RECORD ' + node.record_id : KIND_LABELS[node.type].toUpperCase()));
  if (node.type === 'Article') line.append(noticeBadge(node.retraction_nature));
  item.append(line, el('h4', 'result-title', node.name));
  if (node.type === 'Article') item.append(el('div', 'result-bottom', node.retraction_date ? 'Notice date · ' + displayDate(node.retraction_date) : 'Notice date not recorded'));
  else if (node.record_count) item.append(el('div', 'result-bottom', fmt(+node.record_count) + ' records list this name'));
  else item.append(el('div', 'result-bottom', 'Select to explore connected records'));
  if (node.id === state.selected?.id) item.classList.add('selected'); return item;
}
async function loadResults(autoSelect = false) {
  const epoch = ++state.resultsEpoch, list = $('results-list'); list.replaceChildren();
  for (let index = 0; index < 4; index++) list.append(el('div', 'loading-row'));
  $('results-title').textContent = { Article: 'Article records', Author: 'Shared author names', Institution: 'Shared institution names', Journal: 'Journals' }[state.kind];
  $('results-meta').textContent = 'Loading…'; $('previous-results').disabled = true; $('next-results').disabled = true;
  $('results-context').textContent = state.kind === 'Article' ? 'Ordered by record ID, highest first.' : 'Only entities represented as connected graph nodes.';
  if (state.kind !== 'Article' && !state.q) {
    list.replaceChildren(el('div', 'empty-results', 'Enter a name above to search connected entities. Singleton names are searchable under Article records.'));
    $('results-meta').textContent = ''; $('results-page').textContent = ''; return;
  }
  try {
    const data = await get(state.kind === 'Article' ? '/api/dashboard/records' : '/api/dashboard/entities', state.kind === 'Article' ? { q: state.q, ...filters(), skip: state.skip, limit: 20 } : { q: state.q, kind: state.kind, limit: 20 });
    if (epoch !== state.resultsEpoch) return;
    const rows = data.records || data.nodes; list.replaceChildren(...rows.map(resultView));
    if (!rows.length) { const empty = el('div', 'empty-results'); empty.append(el('strong', '', 'No matches in this view.'), el('span', '', state.kind === 'Article' ? 'Try a different term or clear the active filters.' : 'Try Article records to include names that have no separate graph node.')); list.append(empty); }
    $('results-meta').textContent = rows.length ? `${rows.length} shown` : '0 matches';
    state.hasMore = data.has_more;
    $('previous-results').disabled = state.kind !== 'Article' || state.skip === 0;
    $('next-results').disabled = state.kind !== 'Article' || !data.has_more;
    $('results-page').textContent = state.kind === 'Article' && rows.length ? `${state.skip + 1}–${state.skip + rows.length}` : data.has_more ? 'First 20 matches' : '';
    if (autoSelect && rows.length) chooseSeed(rows[0]);
  } catch (error) {
    if (epoch !== state.resultsEpoch) return;
    const empty = el('div', 'empty-results'); empty.append(el('strong', '', 'Records could not be loaded.'), el('span', '', error.message), button('Try again', () => loadResults(autoSelect), 'error-retry'));
    list.replaceChildren(empty); $('results-meta').textContent = 'Unavailable'; $('results-page').textContent = '';
  }
}
function initGraph() {
  if (cy || !window.cytoscape) return;
  cy = window.cytoscape({ container: $('network'), elements: [], minZoom: .12, maxZoom: 3, wheelSensitivity: .25,
    style: [
      { selector: 'node', style: { 'background-color': element => NODE_COLORS[element.data('type')] || '#bf8cc0', width: element => element.data('type') === 'Article' ? 46 : 54, height: element => element.data('type') === 'Article' ? 46 : 54, shape: 'ellipse', label: element => shortText(element.data('name'), 30), color: '#162433', 'font-family': 'Arial, sans-serif', 'font-size': 8, 'text-valign': 'center', 'text-halign': 'center', 'text-wrap': 'wrap', 'text-overflow-wrap': 'anywhere', 'text-max-width': 40, 'border-width': 1.5, 'border-color': '#ffffff', 'overlay-color': '#006fd6', 'overlay-padding': 6, 'overlay-shape': 'ellipse' } },
      { selector: 'edge', style: { width: 1, 'line-color': '#aab2be', opacity: .85, 'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'target-arrow-color': '#aab2be', 'arrow-scale': .6, label: element => element.data('type').replaceAll('_', ' '), color: '#616b7a', 'font-size': 6, 'font-family': 'Arial, sans-serif', 'text-rotation': 'autorotate', 'text-background-color': '#f4f5f7', 'text-background-opacity': 1, 'text-background-padding': 2 } },
      { selector: '.quiet-edge', style: { label: '' } },
      { selector: 'node:selected', style: { 'border-width': 3, 'border-color': '#006fd6', 'overlay-opacity': .12, 'font-weight': 'bold' } },
    ], layout: { name: 'preset' } });
  cy.on('tap', 'node', event => { const node = state.graph.nodes.find(n => n.id === event.target.id()); if (node) selectNode(node); });
  cy.on('mouseover', 'node', event => {
    const tip = $('graph-tooltip'), position = event.target.renderedPosition(); tip.textContent = `${KIND_LABELS[event.target.data('type')]} · ${event.target.data('name')}`; tip.hidden = false;
    tip.style.left = Math.max(8, Math.min(position.x + 15, $('network').clientWidth - Math.min(240, $('network').clientWidth - 16))) + 'px'; tip.style.top = Math.max(8, Math.min(position.y + 15, $('network').clientHeight - 100)) + 'px';
  });
  cy.on('mouseout', 'node', () => { $('graph-tooltip').hidden = true; });
  new ResizeObserver(() => { cy.resize(); }).observe($('network'));
}
function renderGraph() {
  initGraph();
  if (!cy) { $('graph-status').textContent = 'The graph renderer could not load. Record search and details remain available.'; return; }
  const existing = new Set(cy.nodes().map(node => node.id()));
  cy.batch(() => {
    for (const node of state.graph.nodes) {
      if (!existing.has(node.id)) cy.add({ group: 'nodes', data: { ...node } });
      else cy.getElementById(node.id).data(node);
    }
    for (const edge of state.graph.edges) if (!cy.getElementById(edgeId(edge)).length) cy.add({ group: 'edges', data: { id: edgeId(edge), ...edge } });
    cy.nodes().unselect(); if (state.selected) cy.getElementById(state.selected.id).select();
    cy.edges().toggleClass('quiet-edge', state.graph.nodes.length > 45);
  });
  cy.layout({ name: 'cose', animate: false, fit: true, padding: 40, nodeRepulsion: () => 6500, idealEdgeLength: () => 90, numIter: state.graph.nodes.length > 70 ? 500 : 300, randomize: existing.size === 0, componentSpacing: 80 }).run();
  $('graph-placeholder').hidden = state.graph.nodes.length > 0;
  $('graph-count').textContent = `${fmt(state.graph.nodes.length)} nodes · ${fmt(state.graph.edges.length)} connections`;
  const select = $('visible-nodes'); select.replaceChildren(el('option', '', 'Select a node…')); select.firstChild.value = '';
  for (const node of state.graph.nodes) { const option = el('option', '', KIND_LABELS[node.type] + ': ' + shortText(node.name, 80)); option.value = node.id; select.append(option); }
  select.value = state.selected?.id || ''; updateGraphButtons();
}
function updateGraphButtons() {
  const page = state.selected && state.pages.get(state.selected.id), expand = $('expand-node');
  expand.disabled = !state.selected || state.busy || state.cap || page && !page.has_more;
  expand.textContent = state.busy ? 'Loading…' : page ? page.has_more ? 'Load next 30' : 'All connections loaded' : 'Expand selected';
  for (const name of ['fit-graph', 'clear-graph', 'export-graph']) $(name).disabled = !state.graph.nodes.length;
}
function clearGraph() {
  state.graphEpoch++; state.detailEpoch++; state.graph = { nodes: [], edges: [] }; state.pages.clear(); state.cap = false; state.selected = null; state.busy = false;
  if (cy) cy.elements().remove(); $('graph-loading').hidden = true; $('graph-placeholder').hidden = false; $('graph-tooltip').hidden = true;
  $('graph-title').textContent = 'Select a starting point'; $('graph-count').textContent = '0 nodes · 0 connections'; $('graph-status').textContent = 'Select a node to inspect it. Expand to reveal connected records.';
  $('detail-content').replaceChildren(el('p', 'detail-note', 'Select an article or a connected name to inspect its source details.')); $('visible-nodes').replaceChildren(el('option', '', 'Select a node…')); $('visible-nodes').firstChild.value = ''; updateGraphButtons();
}
async function chooseSeed(node) { clearGraph(); state.selected = node; $('graph-title').textContent = node.type === 'Article' ? `Record ${node.record_id}` : shortText(node.name, 50); selectNode(node); await expandNode(); }
function selectNode(node) {
  state.selected = node; if (cy) { cy.nodes().unselect(); cy.getElementById(node.id).select(); }
  $('visible-nodes').value = node.id; updateGraphButtons();
  for (const item of $('results-list').querySelectorAll('.result-button')) { const selected = item.dataset.nodeId === node.id; item.classList.toggle('selected', selected); item.setAttribute('aria-pressed', String(selected)); }
  if (node.type === 'Article') loadArticle(node); else renderEntity(node);
}
async function expandNode() {
  if (!state.selected || state.busy || state.cap) return;
  const node = state.selected, previous = state.pages.get(node.id); if (previous && !previous.has_more) return;
  const epoch = state.graphEpoch; state.busy = true; $('graph-loading').hidden = false; updateGraphButtons();
  try {
    const page = await get('/api/dashboard/neighborhood', { node_id: node.id, skip: previous?.next_skip || 0, limit: 30, ...filters() });
    if (epoch !== state.graphEpoch) return;
    const merged = mergeNeighborhood(state.graph, page); state.graph = { nodes: merged.nodes, edges: merged.edges }; state.cap = merged.capped; state.pages.set(node.id, page); renderGraph();
    const loaded = (page.skip || 0) + page.returned_neighbors;
    $('graph-status').textContent = state.cap ? `View limit reached (${MAX_NODES} nodes / ${MAX_EDGES} connections). Start from another record to explore a different neighborhood.` : `${KIND_LABELS[node.type]}: ${fmt(loaded)} of ${fmt(page.total_neighbors)} direct connections loaded${page.has_more ? '. Load more or select a neighboring node to expand.' : '. Select a neighboring node to continue.'}`;
    if (state.selected?.id === node.id && node.type !== 'Article') renderEntity(node);
  } catch (error) { if (epoch === state.graphEpoch) $('graph-status').textContent = error.message; }
  finally { if (epoch === state.graphEpoch) { state.busy = false; $('graph-loading').hidden = true; updateGraphButtons(); if (state.selected && state.selected.type !== 'Article') renderEntity(state.selected); } }
}
function sectionLabel(text) { return el('span', 'detail-label', text); }
function listSection(label, names, shared = [], type = '') {
  const fragment = document.createDocumentFragment(); fragment.append(sectionLabel(`${label} · ${names.length}`));
  if (!names.length) { fragment.append(el('p', 'detail-note', 'Not recorded')); return fragment; }
  const sharedNames = new Set(shared.map(item => item.name));
  function list(items) { const ul = el('ul', 'detail-list'); for (const name of items) { const li = el('li'); if (sharedNames.has(name)) { const link = button(name + ' ↗', () => chooseSeed({ id: type + ':' + name, type, name }), 'name-button'); link.title = 'Explore this shared name'; li.append(link); } else li.textContent = name; ul.append(li); } return ul; }
  fragment.append(list(names.slice(0, 10)));
  if (names.length > 10) { const details = el('details', 'detail-source'); details.append(el('summary', '', `Show ${names.length - 10} more listed names`), list(names.slice(10))); fragment.append(details); }
  return fragment;
}
async function loadArticle(node) {
  const epoch = ++state.detailEpoch, panel = $('detail-content'); panel.replaceChildren(el('p', 'detail-note', 'Loading the source record…'));
  try {
    const id = node.record_id || node.id.slice('Article:'.length);
    const data = detailsCache.get(id) || await get('/api/articles/' + encodeURIComponent(id));
    if (epoch !== state.detailEpoch) return;
    if (detailsCache.size > 30) detailsCache.delete(detailsCache.keys().next().value); detailsCache.set(id, data);
    const props = data.article; panel.replaceChildren(noticeBadge(props.retraction_nature), el('h4', 'detail-heading', props.name), el('span', 'record-id', 'RECORD ' + props.record_id));
    const dates = el('dl', 'detail-dates');
    for (const [label, date] of [['Original publication', props.original_paper_date], ['Notice date', props.retraction_date]]) { const group = el('div'); group.append(el('dt', '', label), el('dd', '', displayDate(date))); dates.append(group); }
    panel.append(dates);
    if (data.journal) { panel.append(sectionLabel('Journal')); const link = button(data.journal.name + ' ↗', () => chooseSeed({ id: 'Journal:' + data.journal.name, type: 'Journal', name: data.journal.name }), 'name-button detail-doi'); panel.append(link); }
    const doi = doiHref(props.original_paper_doi); if (doi) { const link = el('a', 'detail-doi', 'Original paper DOI ↗'); link.href = doi; link.target = '_blank'; link.rel = 'noopener'; panel.append(sectionLabel('Source link'), link); }
    panel.append(listSection('Listed author names', data.listed_authors || [], data.authors, 'Author'));
    panel.append(listSection('Listed institutions', data.listed_institutions || [], data.institutions, 'Institution'));
    panel.append(sectionLabel('Listed reasons'));
    const reasons = el('ul', 'detail-list'); for (const reason of [...new Set(data.listed_reasons || [])]) { const li = el('li'); li.append(button(reason, () => { chartFilter('reason', reason, ''); }, 'name-button')); reasons.append(li); } panel.append(reasons.childNodes.length ? reasons : el('p', 'detail-note', 'Not recorded'));
    if (props.notes) { panel.append(sectionLabel('Notes'), el('p', 'detail-note', props.notes)); }
    panel.append(el('p', 'detail-note', 'Linked names have shared graph nodes. Unlinked names remain complete source-list entries. Name matches do not establish a person’s identity.'));
    if (props.source_record) { const details = el('details', 'detail-source'); let source; try { source = JSON.stringify(JSON.parse(props.source_record), null, 2); } catch { source = props.source_record; } details.append(el('summary', '', 'View original source fields'), el('pre', '', source)); panel.append(details); }
  } catch (error) { if (epoch !== state.detailEpoch) return; panel.replaceChildren(el('p', 'detail-note', error.message), button('Retry record', () => loadArticle(node), 'error-retry')); }
}
function renderEntity(node) {
  state.detailEpoch++; const panel = $('detail-content'), page = state.pages.get(node.id); panel.replaceChildren(el('span', 'eyebrow', KIND_LABELS[node.type]), el('h4', 'detail-heading', node.name));
  if (node.type === 'Author') panel.append(el('p', 'detail-note', 'This node groups an exact author-name string. It is not a disambiguated person or an individual misconduct finding.'));
  else if (node.type === 'Institution') panel.append(el('p', 'detail-note', 'This node groups an exact institution-name string listed on multiple records. It does not map individual authors to that institution.'));
  else if (node.type === 'Reason') panel.append(el('p', 'detail-note', 'Explore notice records listing this source reason. A reason is counted once per record.'));
  else panel.append(el('p', 'detail-note', 'Explore the article records connected to this journal. Active notice, journal, and reason filters apply.'));
  if (node.record_count) panel.append(sectionLabel('Source records listing this name'), el('strong', '', fmt(+node.record_count)));
  panel.append(button(page ? page.has_more ? 'Load more connections →' : 'Connections loaded' : 'Explore connections →', () => expandNode(), 'primary-button detail-expand'));
  const action = panel.lastChild; action.disabled = state.busy || state.cap || !!page && !page.has_more;
  const neighbors = state.graph.edges.filter(edge => edge.source === node.id || edge.target === node.id).map(edge => state.graph.nodes.find(n => n.id === (edge.source === node.id ? edge.target : edge.source))).filter(n => n?.type === 'Article');
  if (neighbors.length) { panel.append(sectionLabel(`${neighbors.length} visible article records`)); const list = el('div', 'detail-neighbor-list'); for (const neighbor of neighbors.slice(0, 20)) list.append(button(shortText(neighbor.name, 100), () => selectNode(neighbor))); panel.append(list); }
}
async function loadApp() {
  message(''); const timer = setTimeout(() => { if (!state.overview && $('service-message').hidden) message('Connecting to the hosted dataset. The free API may take about a minute to wake up.'); }, 8000);
  try { if (await loadOverview()) await loadResults(!state.selected); } finally { clearTimeout(timer); }
}
$('search-form').addEventListener('submit', event => { event.preventDefault(); state.q = $('search-input').value.trim(); state.kind = $('search-kind').value; state.skip = 0; clearGraph(); loadResults(true); });
$('search-kind').addEventListener('change', () => { state.kind = $('search-kind').value; $('search-input').placeholder = state.kind === 'Article' ? 'Search titles, DOIs, author names, institutions…' : `Search ${state.kind === 'Author' ? 'shared author names' : state.kind === 'Institution' ? 'shared institution names' : 'journals'}…`; });
$('notice-filter').addEventListener('change', () => { state.notice = $('notice-filter').value; applyFilters(); });
$('clear-filters').addEventListener('click', () => { state.notice = ''; state.journal = ''; state.reason = ''; applyFilters(); });
$('previous-results').addEventListener('click', () => { state.skip = Math.max(0, state.skip - 20); loadResults(); $('results-list').scrollTop = 0; });
$('next-results').addEventListener('click', () => { if (state.hasMore) { state.skip += 20; loadResults(); $('results-list').scrollTop = 0; } });
$('expand-node').addEventListener('click', expandNode); $('clear-graph').addEventListener('click', clearGraph);
$('fit-graph').addEventListener('click', () => cy?.fit(undefined, 40));
$('visible-nodes').addEventListener('change', () => { const node = state.graph.nodes.find(n => n.id === $('visible-nodes').value); if (node) selectNode(node); });
$('export-graph').addEventListener('click', () => {
  const payload = { snapshot: state.overview?.snapshot || null, filters: filters(), ...state.graph, scope: 'visible neighborhood only', identity_note: 'Nodes group source name strings; author-name matches are not verified identities.' };
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })); const anchor = el('a'); anchor.href = url; anchor.download = 'retraction-watch-neighborhood.json'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$('identity-info').addEventListener('click', () => $('identity-dialog').showModal());
for (const link of document.querySelectorAll('a[href="https://retraction-watch-data.onrender.com/docs"]')) link.href = API + '/docs';
initGraph(); loadApp();
