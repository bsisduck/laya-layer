import {el, panel, pairs, details, table, empty, field} from './ui.js';

export function exactMoney(value) {
  return typeof value === 'string' && /^(0|[1-9][0-9]{0,31})$/.test(value) ? value : 'Unknown';
}
export function knownMeasure(value, known, attempts, money = false) {
  if (!Number.isSafeInteger(known) || !Number.isSafeInteger(attempts) || known < 0 || known > attempts) return 'Unknown';
  if (!known) return `Unknown · 0/${attempts} contributing attempts`;
  const amount = money ? exactMoney(value) : Number.isSafeInteger(value) && value >= 0 ? String(value) : 'Unknown';
  return `${amount} · ${known}/${attempts} contributing attempts`;
}
export function usageState(data) {
  if (data?.version !== 1 || data.source !== 'model-attempt-evidence-v1' || !Array.isArray(data.departments) || data.departments.length > 64 || !data.totals || !data.completeness || !data.window) return 'missing';
  if (!Number.isSafeInteger(data.totals.attempts) || data.totals.attempts < 0 || !['complete', 'partial_evidence', 'truncated'].includes(data.completeness.status)) return 'missing';
  return data.totals.attempts ? 'ready' : 'empty';
}
const utc = value => new Date(value * 1000).toISOString().slice(0, 19);
export function departmentUsage(api) {
  const root = panel('Department model usage');
  root.classList.add('department-usage-panel');
  const end = Math.floor(Date.now() / 1000);
  const tenant = el('input', {id: 'usage-tenant', value: 'tenant-a', required: true, maxlength: '96', pattern: '[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}'});
  const startField = el('input', {id: 'usage-start', type: 'datetime-local', step: '1', required: true, value: utc(end - 86400)});
  const endField = el('input', {id: 'usage-end', type: 'datetime-local', step: '1', required: true, value: utc(end)});
  const submit = el('button', {type: 'submit', class: 'secondary'}, 'Load usage');
  const status = el('p', {role: 'status', 'aria-live': 'polite', class: 'hint'});
  const content = el('div', {'aria-label': 'Measured department evidence'});
  const form = el('form', {class: 'filters'}, field('Department report tenant', tenant), field('UTC start', startField), field('UTC end', endField), submit);
  root.append(el('p', {class: 'hint'}, 'Model attempts selected by UTC reservation time [start, end), at most 31 days. Each attempt is counted once across all budget scopes. Provider work with withheld output still counts. Tool operation charges and semantic installation usage are separate.'), form, status, content);
  async function load() {
    submit.disabled = true; content.replaceChildren(); content.setAttribute('aria-busy', 'true'); status.textContent = 'Loading department usage…'; status.classList.remove('error');
    try {
      const start = Date.parse(`${startField.value}Z`) / 1000, finish = Date.parse(`${endField.value}Z`) / 1000;
      if (!Number.isSafeInteger(start) || !Number.isSafeInteger(finish) || finish <= start || finish - start > 31 * 86400) throw new Error('Select a UTC period of at most 31 days.');
      const params = new URLSearchParams({tenant_id: tenant.value, start: String(start), end: String(finish)});
      const data = await api.request(`/admin/department-usage?${params}`);
      const state = usageState(data);
      if (state === 'missing') throw new Error('Department evidence is unavailable or uses an unsupported version.');
      const t = data.totals;
      status.textContent = `${data.source} · ${data.completeness.status.replaceAll('_', ' ')} · ${utc(data.window.start)}Z to ${utc(data.window.end)}Z · UTC [start, end)`;
      const totals = pairs({selected_attempts: t.attempts, durable_dispatch_intent: t.dispatch_intent, uncertain: t.uncertain, settled: t.settled,
        attribution_known: t.attributed, explicitly_unassigned: t.unassigned, historical_attribution_unavailable: t.historical_attribution_unavailable,
        usage_known_attempts: t.known_usage_attempts, usage_unknown_attempts: t.unknown_usage_attempts, historical_usage_unavailable: t.historical_usage_unavailable,
        known_actual_input_tokens: knownMeasure(t.known_input_tokens, t.known_usage_attempts, t.attempts), known_actual_output_tokens: knownMeasure(t.known_output_tokens, t.known_usage_attempts, t.attempts),
        known_simulated_micro_USD: knownMeasure(t.known_simulated_micro_usd, t.known_usage_attempts, t.attempts, true),
        outstanding_reserved_calls: t.outstanding_calls, outstanding_reserved_input_tokens: t.outstanding_input_tokens, outstanding_reserved_output_tokens: t.outstanding_output_tokens,
        outstanding_reserved_simulated_micro_USD: exactMoney(t.outstanding_simulated_micro_usd), over_bound_attempts_frozen: t.over_bound_attempts, zero_simulated_tariff_attempts: t.zero_tariff_attempts});
      if (state === 'empty') content.append(empty('No model attempts in this tenant and reservation period.'),
        el('details', {}, el('summary', {}, 'Inspect zero/unknown totals'), totals, details('Inspect reported totals', t)));
      else content.append(totals);
      content.append(el('p', {class: 'hint'}, 'Dispatch intent is durable intent, not confirmation of provider receipt. Known amounts are partial sums when usage is unknown. A zero simulated tariff does not mean free enterprise AI or zero compute cost. Unknown reservations remain retained.'));
      if (data.completeness.status === 'truncated') content.append(el('p', {class: 'status error'}, 'Truncated report. Totals cover selected attempts; department rows may cover fewer. Choose a smaller period.'));
      if (state !== 'empty') content.append(el('p', {class: 'hint table-scroll-hint'}, 'Scroll horizontally to read all columns. Keyboard: focus the table, then use ← / →.'));
      if (state !== 'empty') content.append(table(['Department / provenance', 'Attempts / known / unknown', 'Known actual input / output tokens', 'Known simulated micro-USD', 'Outstanding reservations'], data.departments.map(row => {
        const b = row.totals;
        return [el('div', {}, row.department ?? 'Unknown / unassigned', ...(row.provenance || []).map(p => el('p', {class: 'footnote'}, `${p.source === 'local_demo' ? 'local_demo · trusted local demo subject' : p.source} · authority v${p.authority_version}${p.issuer_id ? ` · issuer ${p.issuer_id}` : ''}`))),
          `${b.attempts} / ${b.known_usage_attempts} / ${b.unknown_usage_attempts}`,
          el('div', {}, knownMeasure(b.known_input_tokens, b.known_usage_attempts, b.attempts), el('p', {class: 'footnote'}, knownMeasure(b.known_output_tokens, b.known_usage_attempts, b.attempts))),
          knownMeasure(b.known_simulated_micro_usd, b.known_usage_attempts, b.attempts, true),
          `${b.outstanding_calls} calls · ${b.outstanding_input_tokens} input / ${b.outstanding_output_tokens} output tokens · ${exactMoney(b.outstanding_simulated_micro_usd)} simulated micro-USD`];
      })));
      content.append(details('Completeness and bounds', data.completeness), el('p', {class: 'hint'}, (data.gaps || []).join(' ')));
    } catch (error) { status.classList.add('error'); status.textContent = error.message; content.append(empty('No current department data. Check the period and service, then load usage again.')); }
    finally { submit.disabled = false; content.removeAttribute('aria-busy'); }
  }
  form.addEventListener('submit', event => {event.preventDefault(); if (!submit.disabled) void load();});
  void load(); return root;
}
