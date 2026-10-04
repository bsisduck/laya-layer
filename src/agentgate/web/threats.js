import {el, panel, empty, tag} from './ui.js';
export const levels = ['L0', 'L1', 'L2', 'L3', 'L4', 'L5'];
export const layers = ['identity', 'input', 'data', 'actions', 'output', 'consumption', 'supply_chain'];
export function eventContext(event) {
  const context = event.threat_context;
  const valid = context?.schema_version === 1 && context?.taxonomy_version === 'laya-threat-v1';
  // No authenticated scenario attribution exists in this version. Never infer a level.
  return {level_status: 'unknown', candidate_levels: [],
    layers: valid && Array.isArray(context.layers) ? [...new Set(context.layers.filter(value => layers.includes(value)))] : [],
    owasp: valid && Array.isArray(context.owasp) ? [...new Set(context.owasp.filter(value => typeof value === 'string' && /^(LLM(0[1-9]|10):2025|ASI(0[1-9]|10):2026)$/.test(value)))] : []};
}
export function validTaxonomy(data) {
  return data?.schema_version === 1 && data?.taxonomy_version === 'laya-threat-v1' &&
    Array.isArray(data.levels) && data.levels.length === levels.length &&
    data.levels.every((level, index) => level?.id === levels[index] &&
      ['name', 'assignment', 'controls', 'gaps', 'coverage'].every(key => typeof level[key] === 'string' && level[key].length > 0)) &&
    Array.isArray(data.layers) && data.layers.length === layers.length &&
    data.layers.every((layer, index) => layer?.id === layers[index] && typeof layer.name === 'string' && layer.name.length > 0);
}
export async function ladder(api) {
  const root = panel('Authored scenario ladder · L0–L5');
  root.append(el('p', {class: 'hint'}, 'Scenario types, not a severity score. Live events have unknown levels: denials, budget exhaustion and semantic signals do not identify attacker sophistication.'));
  try {
    const data = await api.request('/admin/threat-taxonomy');
    if (!validTaxonomy(data)) throw new Error('Taxonomy metadata unavailable.');
    root.append(el('ol', {class: 'threat-ladder'}, data.levels.map(level => el('li', {},
      el('div', {class: 'section-head'}, el('h3', {}, `${level.id} · ${level.name}`), tag(level.coverage)),
      el('p', {}, level.assignment), el('p', {class: 'hint'}, `Current controls: ${level.controls}`),
      el('p', {class: 'hint'}, `Gaps: ${level.gaps}`)))));
    root.append(el('p', {class: 'hint'}, `Seven system layers: ${data.layers.map(layer => layer.name).join(' · ')}`),
      el('p', {class: 'hint'}, 'OWASP LLM 2025 / Agentic 2026 associations describe related control families, not confirmed vulnerabilities or certification. Classifier false positives and missed attacks remain.'));
  } catch (error) { root.append(empty(`Ladder unavailable: ${error.message}`)); }
  return root;
}
