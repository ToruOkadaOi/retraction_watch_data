export const MAX_NODES = 150;
export const MAX_EDGES = 300;
export const NOTICE_COLORS = { Retraction: '#d69579', 'Expression of concern': '#c9b167', Correction: '#91a8ca', Reinstatement: '#6e9f8a' };
export const NODE_COLORS = { Article: '#e5a184', Author: '#84b59e', Institution: '#d1b66d', Journal: '#9bafd1', Reason: '#c3a1c6' };
export const KIND_LABELS = { Article: 'Article record', Author: 'Author name', Institution: 'Institution name', Journal: 'Journal', Reason: 'Reason' };
export function shortText(value, maximum = 70) { const text = String(value ?? ''); return text.length > maximum ? text.slice(0, maximum - 1) + '…' : text; }
export function doiHref(value) {
  const doi = String(value || '').trim().replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, '');
  return /^10\.\d{4,9}\/\S+$/i.test(doi) ? 'https://doi.org/' + encodeURIComponent(doi).replace(/%2F/gi, '/') : null;
}
export function displayDate(value) {
  if (!value) return 'Not recorded';
  const text = String(value), match = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})(?:\s|$)/);
  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (!match && !iso) return text;
  const [year, month, day] = match ? [+match[3], +match[1], +match[2]] : [+iso[1], +iso[2], +iso[3]];
  const date = new Date(Date.UTC(year, month - 1, day));
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return text;
  return new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' }).format(date);
}
export function edgeId(edge) { return 'edge:' + JSON.stringify([edge.source, edge.target, edge.type]); }
export function mergeNeighborhood(current, page, maxNodes = MAX_NODES, maxEdges = MAX_EDGES) {
  const nodes = new Map(current.nodes.map(node => [node.id, { ...node }]));
  const edges = new Map(current.edges.map(edge => [edgeId(edge), { ...edge }]));
  const incoming = new Map(page.nodes.map(node => [node.id, node]));
  let dropped = 0;
  const center = page.center;
  if (center && (nodes.has(center.id) || nodes.size < maxNodes)) nodes.set(center.id, { ...nodes.get(center.id), ...center });
  for (const edge of page.edges) {
    const id = edgeId(edge);
    if (edges.has(id)) continue;
    const missing = [...new Set([edge.source, edge.target])].filter(id => !nodes.has(id));
    if (missing.some(id => !incoming.has(id)) || nodes.size + missing.length > maxNodes || edges.size >= maxEdges) { dropped++; continue; }
    for (const id of missing) nodes.set(id, { ...incoming.get(id) });
    edges.set(id, { ...edge });
  }
  return { nodes: [...nodes.values()], edges: [...edges.values()], dropped, capped: dropped > 0 || nodes.size >= maxNodes || edges.size >= maxEdges };
}
