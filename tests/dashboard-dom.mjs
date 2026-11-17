// Functional DOM checks use the real app and API with a headless graph model.
// They verify interactions; they do not replace visual browser review.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { createRequire } from 'node:module';
import { parseHTML } from 'linkedom';
const require = createRequire(import.meta.url);
const cytoscape = require('../dashboard/vendor/cytoscape.min.js');
const base = process.env.DASHBOARD_TEST_URL || 'http://127.0.0.1:8765';
for (let attempt = 0; attempt < 40; attempt++) {
  try { const ready = await fetch(base + '/ready'); if (ready.ok) break; } catch {}
  if (attempt === 39) throw new Error('Preview API did not become ready');
  await new Promise(resolve => setTimeout(resolve, 500));
}
const { window, document } = parseHTML(fs.readFileSync(new URL('../dashboard/index.html', import.meta.url), 'utf8'));
Object.assign(globalThis, { window, document, location: new URL(base + '/dashboard/'), matchMedia: () => ({ matches: true }), ResizeObserver: class { observe() {} } });
window.HTMLElement.prototype.scrollIntoView = function () {};
const optionValue = option => option ? (option.hasAttribute('value') ? option.getAttribute('value') : option.textContent) : '';
Object.defineProperty(window.HTMLSelectElement.prototype, 'value', {
  get() { return optionValue(this.querySelector('option[selected]') || this.querySelector('option')); },
  set(value) { for (const option of this.querySelectorAll('option')) { if (optionValue(option) === value) option.setAttribute('selected', ''); else option.removeAttribute('selected'); } },
});
document.getElementById('identity-dialog').showModal = function () { this.setAttribute('open', ''); };
let graph;
window.cytoscape = options => { graph = cytoscape({ headless: true, elements: options.elements, minZoom: options.minZoom, maxZoom: options.maxZoom, layout: { name: 'preset' } }); return graph; };
const $ = id => document.getElementById(id);
async function wait(check, description) { for (let i=0;i<120;i++) { if (check()) return; await new Promise(resolve=>setTimeout(resolve,100)); } throw new Error('Timed out: '+description); }
function change(id,value) { $(id).value=value; $(id).dispatchEvent(new window.Event('change',{bubbles:true})); }
const graphSnapshot = (await (await fetch(base + '/api/dashboard/overview')).json()).snapshot.source_sha256;
const previewFetch = globalThis.fetch;
let apiSnapshot = graphSnapshot;
globalThis.fetch = (input, options) => {
  const url = new URL(input);
  if (url.href === 'https://retraction-api.onrender.com/dataset') {
    return Promise.resolve(Response.json({ source_sha256: apiSnapshot }));
  }
  if (url.pathname.endsWith('/citation-timeline')) {
    const before = url.searchParams.get('period') === 'interval-0';
    const recordId = url.pathname.split('/')[3];
    const skip = Number(url.searchParams.get('skip') || 0);
    const citations = Array.from({ length: 21 }, (_, i) => ({
      doi: `10.1000/example-${i}`, title: `Example citing review ${i + 1}`,
      oci: `${i + 1}-2`, publication_date: '2021', period: 'interval-1',
    }));
    return Promise.resolve(Response.json({
      identifier: 'doi:10.1000/original', skip, citation_source: 'OpenCitations',
      citation_retrieved_at: '2026-11-18T12:00:00Z', source_sha256: graphSnapshot,
      indexed_count: 21, filtered_count: before ? 0 : 21,
      periods: [{ id: 'interval-0', before: '2020-08-01', count: 0 }, { id: 'interval-1', after: '2020-08-01', count: 21 }],
      notices: [
        { record_id: recordId, name: 'Example original', timeline_date: '2020-08-01', retraction_nature: 'Retraction' },
        { record_id: '999999', name: 'Example original', timeline_date: '2020-09-01', retraction_nature: 'Reinstatement' },
      ],
      citations: before ? [] : citations.slice(skip, skip + 20),
    }));
  }
  return previewFetch(input, options);
};
await import('../dashboard/app.mjs');
await wait(()=>$('metric-records').textContent !== '—' && graph.nodes().length>0 && $('detail-content').querySelector('.detail-heading'),'initial dashboard');
assert.equal($('metric-records').textContent,'200');
assert.equal(document.querySelectorAll('.notice-item').length,4);
assert.ok(document.querySelectorAll('#journal-chart .bar-row').length>0);
assert.ok(document.querySelectorAll('#reason-chart .bar-row').length>0);
assert.ok($('detail-content').textContent.includes('Listed author names'));
const compare = $('provenance').querySelector('button');
compare.click();
await wait(() => $('provenance').textContent.includes('use the same source CSV'), 'matching API snapshot');
apiSnapshot = 'f'.repeat(64);
compare.click();
await wait(() => $('provenance').textContent.includes('use different source CSV snapshots'), 'different API snapshot');
const history = [...$('detail-content').querySelectorAll('button')].find(item => item.textContent === 'Load publication notices');
assert.ok(history);
history.click();
await wait(() => history.parentNode === null, 'publication notice history');
assert.ok($('detail-content').querySelector('.detail-source .detail-list button'));
const citationDetails = [...$('detail-content').querySelectorAll('details')].find(item => item.querySelector('summary').textContent === 'Citation timeline');
assert.ok(citationDetails);
citationDetails.open = true;
citationDetails.dispatchEvent(new window.Event('toggle'));
await wait(() => citationDetails.textContent.includes('Example citing review'), 'citation timeline');
assert.ok(citationDetails.querySelector('.timeline-notice').textContent.includes('Retraction'));
const citationPeriod = citationDetails.querySelector('select');
citationPeriod.value = 'interval-0';
citationPeriod.dispatchEvent(new window.Event('change'));
await wait(() => citationDetails.textContent.includes('No indexed citing works in this period.'), 'citation period filter');
const baseNodeIds = graph.nodes().map(node => node.id()).sort();
assert.equal(graph.nodes().filter(node => node.data('type') === 'Work').length, 0);
const showOnGraph = () => [...$('detail-content').querySelectorAll('button')].find(item => item.textContent === 'Show citing papers on graph');
showOnGraph().click();
await wait(() => !$('exit-citation-view').hidden && graph.nodes().length === 3, 'citation graph for empty filtered period');
assert.equal(graph.edges().filter(edge => edge.data('type') === 'Cites').length, 0);
assert.equal(graph.edges().filter(edge => edge.data('type') === 'Notice_for').length, 2);
assert.equal($('expand-node').disabled, true);
const activeFilter = citationDetails.querySelector('select');
activeFilter.value = 'interval-1';
activeFilter.dispatchEvent(new window.Event('change'));
await wait(() => graph.edges().filter(edge => edge.data('type') === 'Cites').length === 20, 'citation filter updates graph');
assert.ok(graph.edges().filter(edge => edge.data('type') === 'Cites').every(edge =>
  edge.source().data('type') === 'CitingWork' && edge.target().data('type') === 'Work'));
$('expand-node').click();
await wait(() => graph.edges().filter(edge => edge.data('type') === 'Cites').length === 21, 'incremental citation expansion');
assert.equal($('expand-node').disabled, true);
graph.getElementById('CitingWork:1-2').emit('tap');
assert.equal($('detail-content').querySelector('.detail-heading').textContent, 'Example citing review 1');
assert.ok([...$('detail-content').querySelectorAll('a')].some(link => link.href.includes('opencitations.net/oci/1-2')));
$('exit-citation-view').click();
await wait(() => $('exit-citation-view').hidden && $('detail-content').querySelector('.detail-heading'), 'restore notice neighborhood');
assert.deepEqual(graph.nodes().map(node => node.id()).sort(), baseNodeIds);


const initialId = graph.nodes().filter(node=>node.data('type')==='Article')[0].data('record_id');
$('search-input').value=initialId;
$('search-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
await wait(()=>$('results-meta').textContent==='1 shown' && $('detail-content').querySelector('.detail-heading'),'record ID search');
assert.equal($('results-list').querySelectorAll('.result-button').length,1);
$('clear-filters').click(); // No active filters; normal records are reset below.
$('search-input').value='';
$('search-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));
await wait(()=>$('results-page').textContent==='1–20','clear search');
$('next-results').click(); await wait(()=>$('results-page').textContent==='21–40','next page');
$('previous-results').click(); await wait(()=>$('results-page').textContent==='1–20','previous page');
document.querySelector('#journal-chart .bar-row').click();
await wait(()=>$('filter-chips').textContent.includes('Journal:') && $('notice-filter').value==='Retraction' && $('graph-loading').hidden,'chart filter');
await wait(()=>$('detail-content').querySelector('.detail-doi.name-button') && $('graph-loading').hidden,'selected filtered article');
$('detail-content').querySelector('.detail-doi.name-button').click();
await wait(()=>graph.nodes().filter(node=>node.data('type')==='Journal').length && $('detail-content').querySelector('.eyebrow')?.textContent==='Journal' && $('graph-loading').hidden,'journal seed');
const before=graph.nodes().length;
if (!$('expand-node').disabled) { $('expand-node').click(); await wait(()=>$('graph-loading').hidden,'graph pagination'); assert.ok(graph.nodes().length>=before); }
assert.ok(graph.nodes().length<=150);assert.ok(graph.edges().length<=300);
const article=graph.nodes().filter(node=>node.data('type')==='Article')[0];
assert.ok(article); article.emit('tap'); await wait(()=>$('detail-content').querySelector('.record-id'),'graph article inspection');
$('identity-info').click();assert.ok($('identity-dialog').hasAttribute('open'));
$('clear-graph').click();assert.equal(graph.nodes().length,0);
assert.equal($('export-graph').disabled,true);
assert.equal($('graph-placeholder').hidden,false);
console.log('Functional DOM checks passed: overview, snapshot comparison, publication notice history, citation timeline and graph expansion, source details, search, paging, chart filters, graph expansion/selection, identity dialog, and clear.');
graph.destroy();
process.exit(0);
