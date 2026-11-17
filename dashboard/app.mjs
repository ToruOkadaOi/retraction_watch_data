import { MAX_NODES, MAX_EDGES, NODE_COLORS, NOTICE_COLORS, KIND_LABELS, shortText, doiHref, displayDate, edgeId, mergeNeighborhood, citationNeighborhood } from './logic.mjs';

const API = location.pathname.startsWith('/dashboard/') ? location.origin : 'https://retraction-watch-data.onrender.com';
const $ = id => document.getElementById(id);
const fmt = number => new Intl.NumberFormat('en').format(number || 0);
const state = { kind: 'Article', q: '', notice: '', journal: '', reason: '', skip: 0, hasMore: false, selected: null,
  graph: { nodes: [], edges: [] }, pages: new Map(), cap: false, busy: false, graphEpoch: 0, resultsEpoch: 0, detailEpoch: 0, overview: null, citationView: null };
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
async function compareApiSnapshot(graphHash, status, control) {
  control.disabled = true;
  status.textContent = 'Checking API snapshot…';
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch('https://retraction-api.onrender.com/dataset', {
      signal: controller.signal, credentials: 'omit',
    });
    if (!response.ok) throw new Error('API snapshot unavailable');
    const { source_sha256: apiHash } = await response.json();
    status.textContent = !apiHash || !graphHash ? 'Snapshot match could not be verified.'
      : apiHash === graphHash ? 'Graph and API use the same source CSV.'
      : 'Graph and API use different source CSV snapshots.';
    status.title = apiHash || '';
  } catch {
    status.textContent = 'API snapshot could not be verified. Try again later.';
  } finally {
    clearTimeout(timer);
    control.disabled = false;
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
  const snapshot = data.snapshot || {}, hash = snapshot.source_sha256 || snapshot.source_csv_sha256;
  $('snapshot-label').textContent = hash ? 'Snapshot ' + hash.slice(0, 12) : 'Snapshot fingerprint unavailable';
  $('snapshot-label').title = hash || '';
  $('provenance').replaceChildren(el('div', '', hash ? 'Source CSV SHA-256: ' + shortText(hash, 25) : 'Source CSV fingerprint not recorded.'));
  if (hash) $('provenance').firstChild.title = hash;
  $('provenance').append(el('div', '', snapshot.imported_at ? 'Imported ' + displayDate(snapshot.imported_at) : 'Import time not recorded for this snapshot.'));
  const comparison = el('div', '');
  comparison.setAttribute('role', 'status');
  const compare = button('Compare with API snapshot', () => compareApiSnapshot(hash, comparison, compare), 'name-button');
  $('provenance').append(compare, comparison);
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
  $('results-title').textContent = { Article: 'Notice records', Author: 'Shared author names', Institution: 'Shared institution names', Journal: 'Journals' }[state.kind];
  $('results-meta').textContent = 'Loading…'; $('previous-results').disabled = true; $('next-results').disabled = true;
  $('results-context').textContent = state.kind === 'Article' ? 'Ordered by record ID, highest first.' : 'Only entities represented as connected graph nodes.';
  if (state.kind !== 'Article' && !state.q) {
    list.replaceChildren(el('div', 'empty-results', 'Enter a name above to search connected entities. Singleton names are searchable under Notice records.'));
    $('results-meta').textContent = ''; $('results-page').textContent = ''; return;
  }
  try {
    const data = await get(state.kind === 'Article' ? '/api/dashboard/records' : '/api/dashboard/entities', state.kind === 'Article' ? { q: state.q, ...filters(), skip: state.skip, limit: 20 } : { q: state.q, kind: state.kind, limit: 20 });
    if (epoch !== state.resultsEpoch) return;
    const rows = data.records || data.nodes; list.replaceChildren(...rows.map(resultView));
    if (!rows.length) { const empty = el('div', 'empty-results'); empty.append(el('strong', '', 'No matches in this view.'), el('span', '', state.kind === 'Article' ? 'Try a different term or clear the active filters.' : 'Try Notice records to include names that have no separate graph node.')); list.append(empty); }
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
function visibleGraph() { return state.citationView?.graph || state.graph; }

function initGraph() {
  if (cy || !window.cytoscape) return;
  cy = window.cytoscape({ container: $('network'), elements: [], minZoom: .12, maxZoom: 3, wheelSensitivity: .25,
    style: [
      { selector: 'node', style: { 'background-color': element => NODE_COLORS[element.data('type')] || '#bf8cc0', width: element => element.data('type') === 'Article' ? 46 : 54, height: element => element.data('type') === 'Article' ? 46 : 54, shape: 'ellipse', label: element => shortText(element.data('name'), 30), color: '#162433', 'font-family': 'Arial, sans-serif', 'font-size': 8, 'text-valign': 'center', 'text-halign': 'center', 'text-wrap': 'wrap', 'text-overflow-wrap': 'anywhere', 'text-max-width': 40, 'border-width': 1.5, 'border-color': '#ffffff', 'overlay-color': '#006fd6', 'overlay-padding': 6, 'overlay-shape': 'ellipse' } },
      { selector: 'edge', style: { width: 1, 'line-color': '#aab2be', opacity: .85, 'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'target-arrow-color': '#aab2be', 'arrow-scale': .6, label: element => element.data('type') === 'Retracted_For' ? 'Lists reason' : element.data('type').replaceAll('_', ' '), color: '#616b7a', 'font-size': 6, 'font-family': 'Arial, sans-serif', 'text-rotation': 'autorotate', 'text-background-color': '#f4f5f7', 'text-background-opacity': 1, 'text-background-padding': 2 } },
      { selector: 'edge[type = "Cites"]', style: { 'line-color': '#21747c', 'target-arrow-color': '#21747c', width: 1.75 } },
      { selector: 'edge[type = "Notice_for"]', style: { 'line-style': 'dashed' } },
      { selector: '.quiet-edge', style: { label: '' } },
      { selector: 'node:selected', style: { 'border-width': 3, 'border-color': '#006fd6', 'overlay-opacity': .12, 'font-weight': 'bold' } },
    ], layout: { name: 'preset' } });
  cy.on('tap', 'node', event => { const node = visibleGraph().nodes.find(n => n.id === event.target.id()); if (node) selectNode(node); });
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
  const graph = visibleGraph();
  const visibleNodes = new Set(graph.nodes.map(node => node.id));
  const visibleEdges = new Set(graph.edges.map(edgeId));
  const existing = new Set(cy.nodes().map(node => node.id()));
  cy.batch(() => {
    cy.edges().filter(edge => !visibleEdges.has(edge.id())).remove();
    cy.nodes().filter(node => !visibleNodes.has(node.id())).remove();
    for (const node of graph.nodes) {
      if (!existing.has(node.id)) cy.add({ group: 'nodes', data: { ...node } });
      else cy.getElementById(node.id).data(node);
    }
    for (const edge of graph.edges) if (!cy.getElementById(edgeId(edge)).length) cy.add({ group: 'edges', data: { id: edgeId(edge), ...edge } });
    cy.nodes().unselect(); if (state.selected) cy.getElementById(state.selected.id).select();
    cy.edges().toggleClass('quiet-edge', graph.nodes.length > 45);
  });
  if (graph.nodes.length) {
    cy.layout({ name: 'cose', animate: false, fit: true, padding: 40, nodeRepulsion: () => 6500, idealEdgeLength: () => 90, numIter: graph.nodes.length > 70 ? 500 : 300, randomize: !graph.nodes.some(node => existing.has(node.id)), componentSpacing: 80 }).run();
  }
  $('graph-placeholder').hidden = graph.nodes.length > 0 || !!state.citationView;
  $('graph-count').textContent = `${fmt(graph.nodes.length)} nodes · ${fmt(graph.edges.length)} connections`;
  const select = $('visible-nodes'); select.replaceChildren(el('option', '', 'Select a node…')); select.firstChild.value = '';
  for (const node of graph.nodes) { const option = el('option', '', KIND_LABELS[node.type] + ': ' + shortText(node.name, 80)); option.value = node.id; select.append(option); }
  select.value = state.selected?.id || ''; updateGraphButtons();
}
function updateGraphButtons() {
  const view = state.citationView;
  const page = state.selected && state.pages.get(state.selected.id), expand = $('expand-node');
  expand.disabled = view ? view.loading || !view.hasMore || view.capped
    : !state.selected || state.busy || state.cap || page && !page.has_more;
  expand.textContent = view ? view.loading ? 'Loading citations…' : 'Show more citing papers'
    : state.busy ? 'Loading…' : page ? page.has_more ? 'Load next 30' : 'All connections loaded' : 'Expand selected';
  $('exit-citation-view').hidden = !view;
  $('citation-legend').hidden = !view;
  $('neighborhood-legend').hidden = !!view;
  for (const name of ['fit-graph', 'clear-graph', 'export-graph']) $(name).disabled = !visibleGraph().nodes.length;
}
function clearGraph() {
  state.graphEpoch++; state.detailEpoch++; state.graph = { nodes: [], edges: [] }; state.pages.clear(); state.cap = false; state.selected = null; state.busy = false; state.citationView = null;
  if (cy) cy.elements().remove(); $('graph-loading').hidden = true; $('graph-placeholder').hidden = false; $('graph-tooltip').hidden = true;
  $('graph-title').textContent = 'Select a starting point'; $('graph-count').textContent = '0 nodes · 0 connections'; $('graph-status').textContent = 'Select a node to inspect it. Expand to reveal connected records.';
  $('detail-content').replaceChildren(el('p', 'detail-note', 'Select an article or a connected name to inspect its source details.')); $('visible-nodes').replaceChildren(el('option', '', 'Select a node…')); $('visible-nodes').firstChild.value = ''; updateGraphButtons();
}
async function chooseSeed(node) { clearGraph(); state.selected = node; $('graph-title').textContent = node.type === 'Article' ? `Record ${node.record_id}` : shortText(node.name, 50); selectNode(node); await expandNode(); }
function selectNode(node) {
  state.selected = node; if (cy) { cy.nodes().unselect(); cy.getElementById(node.id).select(); }
  $('visible-nodes').value = node.id; updateGraphButtons();
  for (const item of $('results-list').querySelectorAll('.result-button')) { const selected = item.dataset.nodeId === node.id; item.classList.toggle('selected', selected); item.setAttribute('aria-pressed', String(selected)); }
  if (node.type === 'Article') loadArticle(node);
  else if (node.type === 'Work' || node.type === 'CitingWork') renderCitationNode(node);
  else renderEntity(node);
}
async function expandNode() {
  if (state.citationView || !state.selected || state.busy || state.cap) return;
  const node = state.selected, previous = state.pages.get(node.id); if (previous && !previous.has_more) return;
  const epoch = state.graphEpoch; state.busy = true; $('graph-loading').hidden = false; updateGraphButtons();
  try {
    const page = await get('/api/dashboard/neighborhood', { node_id: node.id, skip: previous?.next_skip || 0, limit: 30, ...filters() });
    if (epoch !== state.graphEpoch) return;
    const merged = mergeNeighborhood(state.graph, page); state.graph = { nodes: merged.nodes, edges: merged.edges }; state.cap = merged.capped; state.pages.set(node.id, page); renderGraph();
    const loaded = (page.skip || 0) + page.returned_neighbors;
    if (!state.citationView) $('graph-status').textContent = state.cap ? `View limit reached (${MAX_NODES} nodes / ${MAX_EDGES} connections). Start from another record to explore a different neighborhood.` : `${KIND_LABELS[node.type]}: ${fmt(loaded)} of ${fmt(page.total_neighbors)} direct connections loaded${page.has_more ? '. Load more or select a neighboring node to expand.' : '. Select a neighboring node to continue.'}`;
    if (!state.citationView && state.selected?.id === node.id && node.type !== 'Article') renderEntity(node);
  } catch (error) { if (epoch === state.graphEpoch && !state.citationView) $('graph-status').textContent = error.message; }
  finally { if (epoch === state.graphEpoch) { state.busy = false; $('graph-loading').hidden = true; updateGraphButtons(); if (!state.citationView && state.selected && state.selected.type !== 'Article') renderEntity(state.selected); } }
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
function openNotice(row) {
  const id = 'Article:' + row.record_id;
  const visible = state.citationView?.graph.nodes.find(node => node.id === id);
  if (visible) selectNode(visible);
  else chooseSeed({ id, type: 'Article', record_id: row.record_id, name: row.name });
}
async function showPublicationNotices(recordId, panel, epoch, skip = 0) {
  const path = '/api/articles/' + encodeURIComponent(recordId) + '/publication-notices';
  try {
    const data = await get(path, { skip, limit: 20 });
    if (epoch !== state.detailEpoch) return;
    const notices = el('ul', 'detail-list');
    for (const row of data.notices) {
      const item = el('li', '');
      const link = button(row.retraction_nature + ' · ' + displayDate(row.retraction_date) + ' · Record ' + row.record_id,
        () => openNotice(row),
        'name-button');
      item.append(link);
      notices.append(item);
    }
    panel.replaceChildren(notices);
    if (skip) panel.append(button('Previous notices', () => showPublicationNotices(recordId, panel, epoch, skip - 20), 'name-button'));
    if (data.has_more) panel.append(button('More notices', () => showPublicationNotices(recordId, panel, epoch, skip + 20), 'name-button'));
  } catch {
    if (epoch !== state.detailEpoch) return;
    panel.replaceChildren(el('p', 'detail-note', 'Publication notices could not be loaded.'),
      button('Retry', () => showPublicationNotices(recordId, panel, epoch, skip), 'name-button'));
  }
}
function citationPeriodLabel(period) {
  if (period.id === 'notice-date') return 'On a notice date';
  if (period.id === 'uncertain') return 'Date missing or period uncertain';
  if (!period.after) return 'Before ' + displayDate(period.before);
  if (!period.before) return 'After ' + displayDate(period.after);
  return 'Between ' + displayDate(period.after) + ' and ' + displayDate(period.before);
}

function timelineDate(value) {
  if (!value || value.length === 4) return value || 'Date unavailable';
  if (value.length === 7) {
    const [year, month] = value.split('-');
    return new Intl.DateTimeFormat('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' })
      .format(new Date(`${year}-${month}-01T00:00:00Z`));
  }
  return displayDate(value);
}

function workHref(doi, pmid) {
  return (doi && doiHref(doi)) || (pmid && 'https://pubmed.ncbi.nlm.nih.gov/' + encodeURIComponent(pmid) + '/');
}
function citationSourceHref(oci) {
  return 'https://opencitations.net/oci/' + encodeURIComponent(oci);
}
function externalLink(label, href) {
  const link = el('a', 'detail-doi', label);
  link.href = href;
  link.target = '_blank';
  link.rel = 'noopener';
  return link;
}

function addCitationPage(view, data) {
  const notices = view.seedNotice && !data.notices.some(row => row.record_id === view.recordId)
    ? [view.seedNotice, ...data.notices] : data.notices;
  const merged = mergeNeighborhood(view.graph, citationNeighborhood({ ...data, notices }, view.recordId));
  view.graph = { nodes: merged.nodes, edges: merged.edges };
  view.capped = merged.capped;
  view.total = data.filtered_count;
  view.nextSkip = data.skip + data.citations.length;
  view.hasMore = data.citations.length > 0 && view.nextSkip < view.total;
  view.provenance = {
    provider: data.citation_source,
    retrieved_at: data.citation_retrieved_at,
    source_sha256: data.source_sha256,
  };
  const period = data.periods.find(item => item.id === view.period);
  view.periodName = period ? citationPeriodLabel(period) : 'All periods';
}

function reportCitationView(view, extra = '') {
  const shown = view.graph.nodes.filter(node => node.type === 'CitingWork').length;
  $('graph-status').textContent = `${view.periodName} · ${fmt(shown)} of ${fmt(view.total)} indexed citing papers.${view.capped ? ' Canvas limit reached. The timeline still lists all indexed results.' : ''}${extra}`;
}

async function showCitationsOnGraph(recordId, period, page, epoch, scroll = true) {
  const previous = state.citationView;
  const title = $('graph-title').textContent;
  try {
    const data = !page.skip ? page : await get('/api/articles/' + encodeURIComponent(recordId) + '/citation-timeline', { period, limit: 20 });
    if (epoch !== state.detailEpoch) return;
    const view = {
      recordId, period, graph: { nodes: [], edges: [] },
      previousTitle: previous?.previousTitle || title,
      previousStatus: previous?.previousStatus || $('graph-status').textContent,
      previousSelection: previous ? previous.previousSelection : state.selected,
      loading: false,
    };
    const selectedNotice = state.selected?.record_id === recordId && state.selected.type === 'Article' ? state.selected : null;
    if (selectedNotice) {
      view.seedNotice = {
        record_id: recordId, name: selectedNotice.name, retraction_nature: selectedNotice.retraction_nature,
        retraction_date: selectedNotice.retraction_date,
      };
    }
    addCitationPage(view, data);
    state.citationView = view;
    $('graph-title').textContent = 'Citation graph';
    renderGraph();
    reportCitationView(view);
    if (scroll) $('network').scrollIntoView({ behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest' });
  } catch {
    if (epoch === state.detailEpoch) $('graph-status').textContent = 'Citation graph could not be loaded. Try again from the timeline.';
  }
}

async function loadMoreCitationsOnGraph() {
  const view = state.citationView;
  if (!view || view.loading || !view.hasMore || view.capped) return;
  view.loading = true;
  updateGraphButtons();
  try {
    const path = '/api/articles/' + encodeURIComponent(view.recordId) + '/citation-timeline';
    const data = await get(path, { period: view.period, skip: view.nextSkip, limit: 20 });
    if (state.citationView !== view) return;
    const refreshed = data.citation_retrieved_at !== view.provenance.retrieved_at
      || data.source_sha256 !== view.provenance.source_sha256;
    if (refreshed) {
      const first = await get(path, { period: view.period, limit: 20 });
      if (state.citationView !== view) return;
      view.graph = { nodes: [], edges: [] };
      addCitationPage(view, first);
      const selected = view.graph.nodes.find(node => node.id === state.selected?.id)
        || view.graph.nodes.find(node => node.type === 'Work');
      if (selected && selected.id !== state.selected?.id) selectNode(selected);
    } else addCitationPage(view, data);
    renderGraph();
    reportCitationView(view, refreshed ? ' Citation results refreshed. Showing the first page again.' : '');
  } catch {
    if (state.citationView === view) reportCitationView(view, ' More citations could not be loaded. Try again.');
  } finally {
    if (state.citationView === view) { view.loading = false; updateGraphButtons(); }
  }
}

function exitCitationView() {
  const view = state.citationView;
  if (!view) return;
  state.citationView = null;
  $('graph-title').textContent = view.previousTitle;
  $('graph-status').textContent = view.previousStatus;
  if (view.previousSelection) selectNode(view.previousSelection);
  renderGraph();
}

function renderCitationNode(node) {
  state.detailEpoch++;
  const panel = $('detail-content');
  panel.replaceChildren(el('span', 'eyebrow', KIND_LABELS[node.type]), el('h4', 'detail-heading', node.name));
  const view = state.citationView;
  if (node.type === 'Work') {
    const [kind, ...parts] = node.identifier.split(':');
    const identifier = parts.join(':');
    const href = workHref(kind === 'doi' ? identifier : null, kind === 'pmid' ? identifier : null);
    if (href) panel.append(externalLink('Open original paper', href));
    panel.append(button('Open citation timeline', () => {
      const notice = view.graph.nodes.find(row => row.record_id === view.recordId && row.type === 'Article');
      if (notice) selectNode(notice);
    }, 'name-button'));
    return;
  }
  panel.append(el('p', 'detail-note', 'Published ' + timelineDate(node.publication_date)));
  const href = workHref(node.doi, node.pmid);
  if (href) panel.append(externalLink('Open citing paper', href));
  panel.append(externalLink('OpenCitations evidence', citationSourceHref(node.oci)));
  const original = view.graph.nodes.find(row => row.id === node.original_work_id);
  if (original) panel.append(button('Inspect original paper', () => selectNode(original), 'name-button'));
}

async function showCitationTimeline(recordId, panel, epoch, period = 'all', skip = 0) {
  const path = '/api/articles/' + encodeURIComponent(recordId) + '/citation-timeline';
  const loading = el('p', 'detail-note', 'Loading indexed citations…');
  loading.setAttribute('role', 'status');
  panel.replaceChildren(loading);
  try {
    const data = await get(path, { period, skip, limit: 20 });
    if (epoch !== state.detailEpoch) return;

    const total = fmt(data.indexed_count);
    const summary = el('p', 'detail-note', `${total} citing works indexed by OpenCitations. Coverage can be incomplete.`);
    const filter = el('select', 'timeline-filter');
    filter.setAttribute('aria-label', 'Filter citing works by publication period');
    for (const option of [{ id: 'all', label: 'All periods', count: data.indexed_count }, ...data.periods]) {
      const item = el('option', '', `${option.label || citationPeriodLabel(option)} (${fmt(option.count)})`);
      item.value = option.id;
      item.selected = option.id === period;
      filter.append(item);
    }
    filter.addEventListener('change', () => showCitationTimeline(recordId, panel, epoch, filter.value));
    panel.replaceChildren(summary, filter,
      button('Show citing papers on graph', () => showCitationsOnGraph(recordId, period, data, epoch), 'name-button'));
    if (state.citationView?.recordId === recordId && state.citationView.period !== period) {
      showCitationsOnGraph(recordId, period, data, epoch, false);
    }

    if (data.notices_truncated) panel.append(el('p', 'detail-note', 'Only the first 100 related notices are shown. Publication periods are unavailable.'));
    const events = [
      ...data.notices.map(row => ({ date: row.timeline_date, notice: row })),
      ...data.citations.map(row => ({ date: row.publication_date, citation: row })),
    ].sort((a, b) => (a.date || '9999-99-99').localeCompare(b.date || '9999-99-99') || Number(Boolean(b.notice)) - Number(Boolean(a.notice)));
    const list = el('ol', 'detail-list citation-timeline');
    for (const event of events) {
      const item = el('li', event.notice ? 'timeline-notice' : 'timeline-citation');
      item.append(el('span', 'timeline-date', timelineDate(event.date)));
      if (event.notice) {
        const row = event.notice;
        item.append(noticeBadge(row.retraction_nature),
          button(`Open notice ${row.record_id}`, () => openNotice(row), 'name-button'));
      } else {
        const row = event.citation;
        const href = workHref(row.doi, row.pmid);
        const link = citationSourceHref(row.oci);
        item.append(externalLink(row.title || row.doi || (row.pmid ? `PMID ${row.pmid}` : 'Indexed citing work'), href || link));
        if (href) item.append(externalLink('Citation source', link));
      }
      list.append(item);
    }
    if (!data.filtered_count) panel.append(el('p', 'detail-note', 'No indexed citing works in this period.'));
    panel.append(list);
    if (data.filtered_count > 20) {
      const navigation = el('div', 'timeline-pagination');
      navigation.append(el('span', '', `${skip + 1}–${skip + data.citations.length} of ${fmt(data.filtered_count)} citing works`));
      if (skip) navigation.append(button('Previous citations', () => showCitationTimeline(recordId, panel, epoch, period, skip - 20), 'name-button'));
      if (skip + 20 < data.filtered_count) navigation.append(button('More citations', () => showCitationTimeline(recordId, panel, epoch, period, skip + 20), 'name-button'));
      panel.append(navigation);
    }
    panel.append(el('p', 'detail-note', 'Periods use recorded notice dates and the citing works’ publication dates. A citation alone does not show reliance on the findings.'));
  } catch {
    if (epoch !== state.detailEpoch) return;
    panel.replaceChildren(el('p', 'detail-note', 'Indexed citations could not be loaded.'),
      button('Retry citations', () => showCitationTimeline(recordId, panel, epoch, period, skip), 'name-button'));
  }
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
    const publication = el('details', 'detail-source');
    const publicationNotices = el('div', '');
    const loadNotices = button('Load publication notices', () => showPublicationNotices(props.record_id, publicationNotices, epoch), 'name-button');
    publicationNotices.append(loadNotices);
    publication.append(el('summary', '', 'Publication notice history'),
      el('p', 'detail-note', 'Groups records by original DOI or PMID when the available identifiers agree.'), publicationNotices);
    panel.append(publication);
    if (doi || /^doi:\s*10\.\d{4,9}\/\S+$/i.test((props.original_paper_doi || '').trim()) || /^[0-9]{1,18}$/.test(props.original_paper_pubmed_id || '') && Number(props.original_paper_pubmed_id) > 0) {
      const timeline = el('details', 'detail-source');
      const content = el('div', 'timeline-content');
      const summary = el('summary', '', 'Citation timeline');
      timeline.append(summary, content);
      const view = state.citationView;
      const period = view?.recordId === props.record_id ? view.period : 'all';
      timeline.addEventListener('toggle', () => {
        if (timeline.open && !content.hasChildNodes()) showCitationTimeline(props.record_id, content, epoch, period);
      });
      panel.append(timeline);
      if (view?.recordId === props.record_id) {
        timeline.open = true;
        showCitationTimeline(props.record_id, content, epoch, period);
      }
    }
    panel.append(listSection('Listed author names', data.listed_authors || [], data.authors, 'Author'));
    panel.append(listSection('Listed institutions', data.listed_institutions || [], data.institutions, 'Institution'));
    panel.append(sectionLabel('Listed reasons'));
    const reasons = el('ul', 'detail-list'); for (const reason of [...new Set(data.listed_reasons || [])]) { const li = el('li'); li.append(button(reason, () => { chartFilter('reason', reason, ''); }, 'name-button')); reasons.append(li); } panel.append(reasons.childNodes.length ? reasons : el('p', 'detail-note', 'Not recorded'));
    if (props.notes) { panel.append(sectionLabel('Notes'), el('p', 'detail-note', props.notes)); }
    panel.append(el('p', 'detail-note', data.connected_entities === 'shared_names_only'
      ? 'The compact graph connects shared names. It retains singleton names and reasons on each notice. Names are source mentions.'
      : 'Names are source mentions. The dataset does not verify identities or link individual authors to institutions.'));
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
$('expand-node').addEventListener('click', () => state.citationView ? loadMoreCitationsOnGraph() : expandNode());
$('exit-citation-view').addEventListener('click', exitCitationView); $('clear-graph').addEventListener('click', clearGraph);
$('fit-graph').addEventListener('click', () => cy?.fit(undefined, 40));
$('visible-nodes').addEventListener('change', () => { const node = visibleGraph().nodes.find(n => n.id === $('visible-nodes').value); if (node) selectNode(node); });
$('export-graph').addEventListener('click', () => {
  const view = state.citationView;
  const payload = {
    snapshot: state.overview?.snapshot || null,
    ...visibleGraph(),
    ...(view ? { scope: 'visible citation graph', citation: { ...view.provenance, period: view.period, record_id: view.recordId } }
      : { scope: 'visible neighborhood only', filters: filters(), identity_note: 'Nodes group source name strings; author-name matches are not verified identities.' }),
  };
  const url = URL.createObjectURL(new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json' })); const anchor = el('a'); anchor.href = url; anchor.download = 'retraction-watch-neighborhood.json'; anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});
$('identity-info').addEventListener('click', () => $('identity-dialog').showModal());
for (const link of document.querySelectorAll('a[href="https://retraction-watch-data.onrender.com/docs"]')) link.href = API + '/docs';
initGraph(); loadApp();
