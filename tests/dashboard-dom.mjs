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
await import('../dashboard/app.mjs');
await wait(()=>$('metric-records').textContent !== '—' && graph.nodes().length>0 && $('detail-content').querySelector('.detail-heading'),'initial dashboard');
assert.equal($('metric-records').textContent,'200');
assert.equal(document.querySelectorAll('.notice-item').length,4);
assert.ok(document.querySelectorAll('#journal-chart .bar-row').length>0);
assert.ok(document.querySelectorAll('#reason-chart .bar-row').length>0);
assert.ok($('detail-content').textContent.includes('Listed author names'));
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
console.log('Functional DOM checks passed: overview, source details, search, paging, chart filters, graph expansion/selection, identity dialog, and clear.');
graph.destroy();
process.exit(0);
