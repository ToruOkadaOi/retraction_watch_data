import test from 'node:test';
import assert from 'node:assert/strict';
import { mergeNeighborhood, doiHref, displayDate, edgeId, shortText } from '../dashboard/logic.mjs';

test('merge keeps stable IDs, direction and graph limits without dangling edges', () => {
  const center={id:'Article:1',type:'Article',name:'Record'};
  const nodes=[center,...Array.from({length:10},(_,i)=>({id:`Author:${i}`,type:'Author',name:`Name ${i}`}))];
  const edges=nodes.slice(1).map(node=>({source:node.id,target:center.id,type:'Authored_By'}));
  const page={center,nodes,edges};
  const result=mergeNeighborhood({nodes:[],edges:[]},page,5,10);
  assert.equal(result.nodes.length,5);assert.equal(result.edges.length,4);assert.equal(result.capped,true);
  const ids=new Set(result.nodes.map(n=>n.id));
  assert.ok(result.edges.every(e=>ids.has(e.source)&&ids.has(e.target)));
  const again=mergeNeighborhood(result,page,5,10);
  assert.equal(again.nodes.length,5);assert.equal(again.edges.length,4);
  assert.equal(again.edges[0].target,'Article:1');
  assert.equal(mergeNeighborhood({nodes:[],edges:[]},page,100,2).edges.length,2);
});
test('isolated centers remain visible and inputs are not mutated',()=>{
  const current={nodes:[],edges:[]};const center={id:'Article:1',name:'One'};
  const result=mergeNeighborhood(current,{center,nodes:[center],edges:[]});
  assert.equal(result.nodes.length,1);assert.equal(current.nodes.length,0);
});
test('source links accept DOIs without allowing script or foreign URL schemes',()=>{
  assert.equal(doiHref('https://doi.org/10.1234/example'),'https://doi.org/10.1234/example');
  assert.equal(doiHref('javascript:alert(1)'),null);
  assert.equal(doiHref('https://evil.example'),null);
  assert.equal(doiHref('Unavailable'),null);
  assert.equal(doiHref('10.1234/x#y'),'https://doi.org/10.1234/x%23y');
});
test('dates use explicit US source parsing and preserve unknown or invalid values',()=>{
  assert.equal(displayDate('2/3/2024'),'3 Feb 2024');
  assert.equal(displayDate('2024-02-03T10:00:00Z'),'3 Feb 2024');
  assert.equal(displayDate('2/31/2024'),'2/31/2024');
  assert.equal(displayDate('Unknown'),'Unknown');
  assert.equal(displayDate(''),'Not recorded');
});
test('long labels are bounded and edge identities do not collide',()=>{
  assert.equal(shortText('abcdef',4),'abc…');
  assert.notEqual(edgeId({source:'a:b',target:'c',type:'x'}),edgeId({source:'a',target:'b:c',type:'x'}));
});
