import {eventContext, ladder, levels, layers} from './threats.js';
import {departmentUsage} from './departments.js';
import {standardsView} from './standards.js';
import {el, text, tag, panel, pairs, details, table, empty, field, timestamp} from './ui.js';
export async function overview(api) {
  const data = await api.request('/admin/overview');
  const counts = data.counts || {};
  const root = el('div');
  root.append(el('div', {class: 'summary-strip'}, el('span', {}, 'POLICY / ', text(data.policy_version)), el('span', {}, 'FEED / ', text(data.feed_version))));
  root.append(el('div', {class: 'stats'}, ['allow', 'redact', 'deny', 'pending'].map(key => el('div', {class: `stat ${key}`},
    el('p', {class: 'eyebrow'}, {allow: 'Allowed', redact: 'Redacted', deny: 'Denied', pending: 'Pending'}[key]),
    el('strong', {}, typeof counts[key] === 'number' ? counts[key].toLocaleString() : '—')))));
  root.append(el('p', {class: 'hint'}, data.count_window ? `Count window: ${text(data.count_window.scope)} · ${text(data.count_window.audit_rows)} / ${text(data.count_window.limit)} audit rows. — means unknown.` : 'Count window not reported. — means unknown.'));
  const services = Object.entries(data.services || {});
  root.append(el('div', {class: 'grid'},
    panel('Service state', services.length ? services.map(([key, value]) => el('div', {class: 'service-row'}, el('span', {}, key.replaceAll('_', ' ')), tag(value))) : empty('No service state reported.'), details('Active controls', data.controls || {})),
    panel('Protection coverage', pairs(data.coverage), el('p', {class: 'hint'}, 'Coverage is reported by the gateway. A configured classifier is not a real-model evaluation.'), details('Latency evidence', data.latency || {status: 'unknown'}))));
  const counters = data.budgets?.tool_counters;
  root.append(panel('Resource ledger', el('p', {class: 'hint'}, 'Reserved and spent values use the units reported by each budget. Unreported model usage is unknown.'),
    Array.isArray(counters) && counters.length ? table(['Scope', 'Key', 'Reserved', 'Spent'], counters.map(row => [row.scope, row.scope_key, row.reserved, row.spent])) : empty(Array.isArray(counters) ? 'No tool budget reservations recorded.' : 'Budget counters unavailable.'),
    details('Full budget evidence', data.budgets || {status: 'unknown'})));
  const delivery = data.telemetry || {status: 'not_configured'};
  root.append(panel('Audit delivery', el('div', {class: 'section-head'}, tag(delivery.status)),
    el('p', {class: 'hint'}, 'Local collector contract lab. Acknowledgments confirm persisted minimized events; this is not a bank connection or vendor certification.'),
    pairs({sender_running: delivery.sender_running, acknowledged_events: delivery.acknowledged_events, backlog_sequences: delivery.source_lag_sequences, last_delivery_ms: delivery.last_delivery_ms}),
    details('Delivery evidence', delivery)));
  root.append(await ladder(api));
  root.append(departmentUsage(api), standardsView());
  return root;
}
export function filterEvents(events, decision, query, level = '', layer = '') {
  const search = query.toLowerCase();
  return events.filter(event => (!level || (level === 'unknown' ? eventContext(event).level_status === 'unknown' : eventContext(event).candidate_levels.includes(level))) &&
    (!layer || eventContext(event).layers.includes(layer)) && (!decision || event.decision === (decision === 'pending' ? 'require_approval' : decision)) &&
    [event.trace_id, event.operation, event.tenant_id, event.principal_id, ...(event.reason_codes || [])].some(value => text(value).toLowerCase().includes(search)));
}
export async function timeline(api) {
  const data = await api.request('/admin/events?limit=100');
  if (!Array.isArray(data.events)) throw new Error('The timeline response is missing its event list.');
  const root = panel('Security timeline');
  root.classList.add('timeline-panel');
  const decision = el('select', {id: 'event-decision'}, ['', 'allow', 'redact', 'deny', 'pending'].map(value => el('option', {value}, value || 'All decisions')));
  const trace = new URLSearchParams(globalThis.location?.hash.split('?')[1] || '').get('trace') || '';
  const query = el('input', {id: 'event-query', type: 'search', placeholder: 'Trace, operation, tenant or reason', 'aria-label': 'Filter loaded events', value: trace});
  const level = el('select', {id: 'event-level'}, ['', 'unknown', ...levels].map(value => el('option', {value}, value === 'unknown' ? 'Unknown live level' : value || 'All levels')));
  const layer = el('select', {id: 'event-layer'}, ['', ...layers].map(value => el('option', {value}, value.replaceAll('_', ' ') || 'All layers')));
  const content = el('div');
  const count = el('p', {class: 'hint', role: 'status'});
  function render() {
    const rows = filterEvents(data.events, decision.value, query.value, level.value, layer.value);
    count.textContent = `${rows.length} of ${data.events.length} loaded events · latest 100 · times shown locally`;
    content.replaceChildren(rows.length ? table(['Time / trace', 'Operation', 'Decision', 'Execution', 'Control associations', 'Evidence'], rows.map(event => [
      el('div', {}, timestamp(event.timestamp), el('p', {class: 'footnote'}, event.trace_id)),
      el('div', {}, text(event.operation), el('p', {class: 'footnote'}, event.event_type)), tag(event.decision),
      event.executed === true ? 'Executed' : event.executed === false ? 'Not executed' : 'Unknown',
      el('div', {}, 'Unknown live level', el('p', {class: 'footnote'}, eventContext(event).layers.join(' · ') || 'No mapped layer'), el('p', {class: 'footnote'}, eventContext(event).owasp.join(' · ') || 'No mapped OWASP family')), details('Inspect event', event),
    ])) : empty('No matching events. Run an action or change the filters.'));
  }
  level.addEventListener('change', render); layer.addEventListener('change', render);
  decision.addEventListener('change', render); query.addEventListener('input', render);
  root.append(el('div', {class: 'filters'}, field('Decision', decision), field('Live level', level), field('Control layer', layer), query), count, content);
  root.append(el('p', {class: 'hint'}, 'Scroll the records horizontally on narrow screens. Filters apply only to this loaded window. L0–L5 describes authored scenarios; current live levels are always unknown, so selecting L0–L5 returns no classified observations. Layers and OWASP are control associations only; intent is not assessed.'));
  if (Array.isArray(data.control_events)) root.append(details('Policy and feed activation events', data.control_events));
  render(); return root;
}
