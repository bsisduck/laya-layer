import {el, pairs} from './ui.js';
import {standardsEvidence} from './standards.js';
export const workflowLayers = [
  {id: 'identity', name: 'Identity / permissions', short: 'Who may act?', status: 'Partial', implemented: 'Hashed scoped API credentials; tenant/resource permissions; on-behalf delegation; model allowlist. Offline issuer assertion exchange uses pinned public trust.', gap: 'Full interactive OIDC/enterprise SSO is not implemented.', evidence: 'authority.py · issuer_trust.py · policy.py · model_config.py'},
  {id: 'input', name: 'Input', short: 'Bound the request', status: 'Partial', implemented: 'Bounded JSON/schema/size/deadline admission; active literal feed indicators. Optional Laya content-role inspection fails closed when required.', gap: 'No comprehensive PL/EN signature pack or Llama Guard / Granite integration. Semantic quality remains experimental.', evidence: 'app.py · control_plane.py · semantics.py'},
  {id: 'data', name: 'Data', short: 'Constrain exposure', status: 'Partial', implemented: 'Tenant/resource/classification checks; email masking; synthetic-secret pattern blocking; scoped memory filtering.', gap: 'PESEL, IBAN, payment-card and general secret detection are not implemented. Article 9 categories are not automatically identified.', evidence: 'policy.py · service.py · scoped_tools.py'},
  {id: 'actions', name: 'Actions', short: 'Check before dispatch', status: 'Partial', implemented: 'Canonical operation allowlist, strict argument schemas, resource/destination rules; exact payload approval with server revalidation; MCP tool results pass gateway inspection.', gap: 'Arbitrary destructive tools are undeclared and denied. MCP description quarantine and descriptor hash pinning are not implemented.', evidence: 'scoped_tools.py · tool_routes.py · mcp_adapter.py · tool_catalog.py'},
  {id: 'output', name: 'Output', short: 'Inspect, then release', status: 'Partial', implemented: 'Bounded output, email redaction, synthetic-secret and feed filtering; optional required content-role inspection; minimized audit before permitted release.', gap: 'No general DLP, active-element removal, canary detector or Llama Guard / Granite output guard. The console renders text safely.', evidence: 'service.py · models.py · ui.js'},
  {id: 'consumption', name: 'Consumption', short: 'Across every step', status: 'Partial', implemented: 'Persistent SQLite tool/model/semantic reservations; token and simulated-cost limits; deadlines, freezes and retained uncertain work.', gap: 'Redis, generic loop detection and a general circuit breaker are not implemented. Cost evidence is local accounting, not an invoice guarantee.', evidence: 'budgets.py · model_budgets.py · semantic_quota.py'},
  {id: 'supply', name: 'Supply chain', short: 'Across every step', status: 'Partial', implemented: 'Validated data-only feed activation; last activated policy/feed survives invalid updates; pinned installation assets and hash checks; metadata-only artifact intake.', gap: 'No verified 17-feed exploit inventory. Metadata intake does not download or sandbox arbitrary artifacts.', evidence: 'control_plane.py · artifacts.py · lifecycle/install.py'},
];
export const actionPaths = {
  read: ['Scope + policy + data checks', 'Reserve + durable intent', 'Execute → inspect output → audit → release'],
  consequential: ['Evaluate hard policy restrictions', 'Hard deny → stop; no override', 'If permitted and review required → exact human review', 'Server approval + revalidation → explicit resume → dispatch → audit'],
  destructive: 'Blocked · no reviewed executor',
  undeclared: 'Undeclared write, destructive or irreversible operations → denied / unimplemented',
};
const officialLink = (label, href) => el('a', {href, target: '_blank', rel: 'noopener noreferrer'}, label);
function policyContext() {
  return el('section', {class: 'policy-associations'}, el('div', {}, el('p', {class: 'eyebrow'}, 'POLICY CONTEXT'), el('h2', {}, 'GDPR / RODO associations'), el('p', {class: 'hint'}, 'Control associations for review. Applicability and legal obligations require deployment-specific assessment; this is not a compliance certification.')),
    el('div', {class: 'policy-context-grid'},
      el('div', {}, el('h3', {}, 'Article 9 · sensitive data'), el('p', {}, 'Scoped resource access, classification restrictions and minimized outputs can support privacy controls. Sensitive-category detection and a lawful-processing assessment are not implemented.')),
      el('div', {}, el('h3', {}, 'Article 22 · automated decisions'), el('p', {}, 'Exact review and audit preserve human control over permitted tool actions. An invitation approval is not a complete safeguard for legally significant automated decisions.'))),
    el('div', {class: 'gdpr-cards'}, standardsEvidence.filter(row => /Article (20|30) ·/.test(row.framework)).map(row => el('article', {class: 'gdpr-card'},
      el('h3', {}, row.framework.replace('RODO / GDPR · ', '')), pairs({'Current support': row.control, 'Purpose and gap': row.gap}),
      officialLink('Official GDPR source ↗', row.source), row.context ? officialLink('EDPB portability guidance ↗', row.context) : null))),
    el('div', {class: 'source-links'}, officialLink('Official GDPR text ↗', 'https://eur-lex.europa.eu/eli/reg/2016/679/oj/eng/'), officialLink('EDPB: individual rights ↗', 'https://www.edpb.europa.eu/sme/be-compliant/respect-individuals-rights_en'), officialLink('Commission: individual rights ↗', 'https://commission.europa.eu/law/law-topic/data-protection/information-business-and-organisations/dealing-requests-individuals_en'), el('a', {href: '#overview?section=standards'}, 'AI Act / DORA / OWASP evidence →')));
}
export function workflowView() {
  const detail = el('section', {id: 'layer-detail', class: 'layer-detail', 'aria-live': 'polite', 'aria-label': 'Selected layer details'});
  const controls = [];
  function select(layer) {
    controls.forEach(({node, id}) => node.setAttribute('aria-pressed', String(id === layer.id)));
    detail.replaceChildren(el('p', {class: 'eyebrow'}, 'SELECTED LAYER / IMPLEMENTATION SCOPE'), el('h2', {}, layer.name), pairs({Coverage: layer.status, Implemented: layer.implemented, 'Remaining gaps': layer.gap, 'Source evidence': layer.evidence}));
  }
  function control(layer, index, rail = false) {
    const node = el('button', {type: 'button', class: rail ? 'pipeline-rail' : 'pipeline-step', 'aria-pressed': 'false', 'aria-controls': 'layer-detail', onclick: () => select(layer)},
      el('span', {class: 'step-number'}, `0${index + 1}`), el('span', {}, el('strong', {}, layer.name), el('small', {}, layer.short)), el('span', {class: 'step-mark', 'aria-hidden': 'true'}, rail ? '↔' : '→'));
    controls.push({node, id: layer.id}); return node;
  }
  const diagram = el('section', {class: 'workflow-diagram', 'aria-label': 'Seven-layer control pipeline'},
    el('div', {class: 'diagram-intro'}, el('p', {class: 'eyebrow'}, 'REQUEST PATH / FIVE CHECKPOINTS'), el('h2', {}, 'From intent to permitted output'), el('p', {class: 'hint'}, 'Select a layer to inspect current coverage. This is a conceptual map; actual checks depend on the tool or model path.')),
    control(workflowLayers[5], 5, true),
    el('div', {class: 'request-path'}, workflowLayers.slice(0, 5).map((layer, index) => control(layer, index))),
    el('section', {class: 'action-branches', 'aria-label': 'Action policy branches'},
      el('div', {class: 'branch read-branch'}, el('h3', {}, 'Non-destructive / read'), el('ol', {}, actionPaths.read.map(step => el('li', {}, step))), el('p', {class: 'hint'}, 'A read is never authorized solely by classification.')),
      el('div', {class: 'branch write-branch'}, el('h3', {}, 'Write / consequential'), el('p', {class: 'hint'}, 'Writes can affect a person without being destructive. Destructive / irreversible proposals require their own declared operation and policy.'), el('ol', {}, actionPaths.consequential.map(step => el('li', {}, step)))),
      el('div', {class: 'branch destructive-branch'}, el('h3', {}, 'Destructive / undeclared'), el('p', {class: 'blocked-node'}, actionPaths.destructive), el('p', {class: 'hint'}, 'The current catalog has no reviewed destructive or irreversible executor. Undeclared operations stop before effects. Approval cannot create tool authority.'))),
    el('p', {class: 'undeclared-note'}, actionPaths.undeclared),
    control(workflowLayers[6], 6, true));
  select(workflowLayers[3]);
  return el('div', {class: 'workflow-workspace'}, el('div', {class: 'workflow-layout'}, diagram, detail), policyContext());
}
