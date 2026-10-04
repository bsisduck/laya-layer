import {el, empty, panel, pairs, tag} from './ui.js';

// Accept a known catalog contract only; partial/old metadata never implies authority.
export function catalogState(data) {
  if (data?.version !== 'approved-tools-v1' || !Array.isArray(data.tools) || data.tools.length > 3 ||
      !Array.isArray(data.examples) || data.examples.length > 2) return 'missing';
  const seen = new Set();
  for (const tool of data.tools) {
    if (typeof tool?.operation !== 'string' || tool.executable !== true ||
        !['documents.read', 'memory.query', 'mail.send'].includes(tool.operation) || seen.has(tool.operation) ||
        !['read', 'write', 'destructive'].includes(tool.effect) || typeof tool.data_scope !== 'string' ||
        typeof tool.adapter !== 'string' || typeof tool.reversibility !== 'string' || typeof tool.affects_person !== 'boolean' ||
        !['automatic_read', 'exact_approval'].includes(tool.policy?.disposition) ||
        tool.risk?.version !== 'tool-policy-heuristic-v1' || !Number.isInteger(tool.risk?.score) ||
        tool.risk.score < 0 || tool.risk.score > 100 || !['low', 'moderate', 'high'].includes(tool.risk.band) ||
        !tool.risk.components || typeof tool.risk.components !== 'object' || Array.isArray(tool.risk.components)) return 'missing';
    const components = ['effect', 'potential_data', 'exposure', 'reversibility', 'affects_person'].map(key => tool.risk.components[key]);
    if (components.some(value => !Number.isInteger(value) || value < 0 || value > 100) ||
        components.reduce((sum, value) => sum + value, 0) !== tool.risk.score ||
        tool.risk.band !== (tool.risk.score < 25 ? 'low' : tool.risk.score < 60 ? 'moderate' : 'high')) return 'missing';
    seen.add(tool.operation);
  }
  if (data.examples.some(row => row?.executable !== false || typeof row.operation !== 'string' || typeof row.description !== 'string')) return 'missing';
  return data.tools.length ? 'ready' : 'empty';
}

const approvalLabel = disposition => disposition === 'exact_approval' ? 'Exact human approval required' : 'Automatic after hard authorization';
export async function catalogView(api) {
  const data = await api.request('/admin/catalog');
  const state = catalogState(data);
  if (state === 'missing') return empty('Catalog metadata is unavailable or incompatible. Refresh after updating the gateway.');
  if (state === 'empty') return empty('No implemented tools reported by this catalog.');
  return el('div', {class: 'stack'},
    panel('Approved tool catalog',
      el('p', {class: 'hint'}, 'Risk describes potential operation exposure. Your credential and the active policy still determine access to each resource. Scores do not grant permission or remove approval.'),
      pairs({catalog_version: data.version, policy_version: data.policy_version, registry_digest: data.registry_digest}),
      el('p', {class: 'hint'}, 'Local policy heuristic · not probability, PII classification, semantic inference, OWASP level or AI Act legal classification.')),
    ...data.tools.map(tool => panel(tool.operation,
      el('p', {class: 'hint'}, tool.description),
      el('div', {class: 'actions'}, tag(tool.effect), tag(`${tool.risk.band} · ${tool.risk.score}/100`), tag('implemented')),
      el('p', {class: 'hint'}, approvalLabel(tool.policy.disposition)),
      pairs({adapter_scope: tool.adapter, potential_data: tool.potential_data, data_scope: tool.data_scope,
        reversibility: tool.reversibility, may_affect_person: tool.affects_person ? 'Yes · potential consequence' : 'No direct person effect declared'}),
      el('details', {}, el('summary', {}, `Risk components and policy · ${tool.operation}`),
        el('div', {class: 'stack'}, pairs(tool.risk.components), pairs(tool.policy), el('p', {class: 'hint'}, tool.risk.version))))),
    panel('Proposed examples · unavailable', el('p', {class: 'hint'}, 'These examples cannot execute through REST or MCP. No GitLab or bank connection is installed.'),
      ...data.examples.map(row => el('section', {class: 'catalog-example'}, el('h3', {}, `${row.category} · ${row.operation}`), tag('unavailable'), el('p', {class: 'hint'}, row.description)))));
}
