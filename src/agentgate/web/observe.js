import {eventContext, ladder, levels, layers} from './threats.js';
import {departmentUsage} from './departments.js';
import {standardsView} from './standards.js';
import {el, text, tag, panel, pairs, details, table, empty, field, timestamp} from './ui.js';
export function overviewSection(hash = '') {
  const section = new URLSearchParams(hash.split('?')[1] || '').get('section');
  return ['usage', 'standards', 'controls'].includes(section) ? section : 'all';
}
// Pending is a global DB count, unlike the bounded terminal-decision window.
export function pendingApprovals(data) {
  const value = data.coverage?.pending_approvals ?? (data.count_window?.pending_scope ? data.counts?.pending : null);
  return Number.isSafeInteger(value) && value >= 0 ? value : null;
}
export async function overview(api) {
  const section = overviewSection(globalThis.location?.hash);
  const root = el('div', {class: 'operations'});
  root.append(el('div', {class: 'overview-sections', role: 'group', 'aria-label': 'Overview sections'},
    [['all', 'Operations'], ['usage', 'Department usage'], ['standards', 'Standards evidence'], ['controls', 'Threat controls']].map(([key, label]) => el('a', {href: key === 'all' ? '#overview' : `#overview?section=${key}`, ...(section === key ? {'aria-current': 'page'} : {})}, label))));
  if (section === 'usage') { root.append(departmentUsage(api)); return root; }
  if (section === 'standards') { root.append(standardsView()); return root; }
  if (section === 'controls') { root.append(await ladder(api)); return root; }
  const [summary, activity] = await Promise.allSettled([api.request('/admin/overview'), api.request('/admin/events?limit=8')]);
  if (summary.status === 'fulfilled') {
    const data = summary.value;
    const counts = data.counts || {};
    root.append(el('div', {class: 'summary-strip'}, el('span', {}, 'Policy ', text(data.policy_version)), el('span', {}, 'Feed ', text(data.feed_version))));
    root.append(el('div', {class: 'stats'}, ['allow', 'redact', 'deny', 'pending'].map(key => el('div', {class: `stat ${key}`},
      el('p', {class: 'eyebrow'}, {allow: 'Allowed', redact: 'Redacted', deny: 'Denied', pending: 'Pending approvals'}[key]),
      el('strong', {}, (key === 'pending' ? pendingApprovals(data) : counts[key])?.toLocaleString() ?? '—'),
      el('p', {class: 'footnote'}, key === 'pending' ? 'Global · all unexpired records' : 'Bounded terminal decisions')))));
    root.append(el('p', {class: 'hint count-window'}, data.count_window ? `Decision window: ${text(data.count_window.scope)} · ${text(data.count_window.audit_rows)} / ${text(data.count_window.limit)} audit rows. — means unknown.` : 'Decision window not reported. — means unknown.'));
    const services = Object.entries(data.services || {});
    const service = panel('Service & controls', services.length ? services.map(([key, value]) => el('div', {class: 'service-row'}, el('span', {}, key.replaceAll('_', ' ')), tag(value))) : empty('No service state reported.'),
      el('div', {class: 'service-row'}, el('span', {}, 'Audit delivery'), tag(data.telemetry?.status ?? 'unknown')),
      details('Active controls', data.controls || {}),
      el('p', {class: 'hint'}, 'Reported state only. Configured services do not establish model efficacy.'));
    const activityPane = recentActivity(activity);
    root.append(el('div', {class: 'operations-grid'}, activityPane, service));
    root.append(el('div', {class: 'operation-links'}, el('a', {href: '#approvals'}, 'Review approvals · tenant-a →'), el('a', {href: '#hr'}, 'Open HR workbench →')));
    const evidence = panel('Operational evidence',
      details('Protection coverage', data.coverage || {status: 'unknown'}),
      details('Resource ledger', data.budgets || {status: 'unknown'}),
      details('Latency evidence', data.latency || {status: 'unknown'}),
      details('Local audit delivery', data.telemetry || {status: 'not_configured'}));
    evidence.classList.add('operations-evidence');
    root.append(evidence);
  } else {
    root.append(el('div', {class: 'panel'}, empty('Operations summary unavailable. Refresh to retry.'), el('p', {class: 'status error', role: 'status'}, summary.reason.message)), recentActivity(activity));
  }
  return root;
}
function recentActivity(result) {
  const root = panel('Recent audit activity'); root.classList.add('recent-activity');
  if (result.status === 'rejected' || !Array.isArray(result.value?.events)) {
    root.append(empty('Recent activity unavailable. Refresh to retry.')); return root;
  }
  const events = result.value.events;
  root.append(el('p', {class: 'hint'}, 'Latest 8 audit events · all tenants · includes lifecycle stages'));
  root.append(events.length ? table(['Time / operation', 'Decision', 'Execution', 'Trace'], events.map(event => [
    el('div', {}, text(event.operation), el('p', {class: 'footnote'}, text(event.event_type).replaceAll('_', ' ')), el('p', {class: 'footnote'}, timestamp(event.timestamp))), tag(event.decision),
    event.executed === true ? 'Executed' : event.executed === false ? 'Not executed' : 'Unknown',
    el('a', {href: `#timeline?trace=${encodeURIComponent(event.trace_id ?? '')}`}, text(event.trace_id)),
  ])) : empty('No audit activity recorded. Open HR to begin a governed workflow.'));
  root.append(el('a', {class: 'panel-link', href: '#timeline'}, 'Open security timeline →')); return root;
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
