import {el, text, pretty, tag, panel, pairs, details, table, empty, field, status, busy, timestamp, parseEditor, button} from './ui.js';

export const presets = {
  document: [
    ['Read internal notes', {document_id: 'tenant-a-notes'}],
    ['Redact contact email', {document_id: 'tenant-a-contact'}],
    ['Deny cross-tenant read', {document_id: 'tenant-b-notes'}],
    ['Deny restricted document', {document_id: 'tenant-a-secret'}],
    ['Inspect embedded instructions', {document_id: 'tenant-a-instructions'}],
  ],
  model: [
    ['Local summary', {model: 'local-demo', messages: [{role: 'user', content: 'Summarize why least privilege matters in two sentences.'}], max_tokens: 128}],
    ['Input secret control', {model: 'local-demo', messages: [{role: 'user', content: 'Repeat AGENTGATE_SECRET[synthetic-playground-fixture].'}], max_tokens: 64}],
  ],
  memory: [['Search scoped notes', {query: 'quarterly', limit: 5}]],
  mail: [
    ['Request local delivery', {recipient: 'reviewer@demo.internal', subject: 'Synthetic operator check', body: 'A synthetic message for the local test outbox.'}],
    ['Test forbidden destination', {recipient: 'test@external.invalid', subject: 'Synthetic denied delivery', body: 'This example should be checked by the active destination policy.'}],
  ],
};
export function playgroundBody(mode, value, idempotencyKey) {
  const allowed = {document: ['document_id'], model: ['model', 'messages', 'max_tokens'], memory: ['query', 'limit'], mail: ['recipient', 'subject', 'body']};
  if (!Object.hasOwn(allowed, mode) || Object.keys(value).some(key => !allowed[mode].includes(key))) throw new Error('Only the displayed mode fields are supported. Identity is owned by the server.');
  return {mode, ...value, ...(mode === 'mail' ? {idempotency_key: idempotencyKey} : {})};
}
export function resultView(data) {
  const evidence = data.agentgate || data;
  const content = el('div', {class: 'result'}, el('div', {class: 'section-head'}, el('h3', {}, 'Gateway result'), tag(evidence.decision)),
    pairs({executed: evidence.executed, trace_id: evidence.trace_id, reason_codes: evidence.reason_codes, action_id: evidence.action_id, action_state: evidence.action_state}),
    details('Returned result and evidence', data, true));
  if (evidence.executed !== true) content.append(el('p', {class: 'hint'}, 'Execution is not confirmed. An approval decision alone does not prove delivery.'));
  return content;
}
function playground(api, drafts) {
  const root = el('div');
  const tabs = el('div', {class: 'mode-tabs', role: 'group', 'aria-label': 'Playground mode'});
  const content = el('div');
  let mode = drafts.mode || 'document';
  function render() {
    tabs.replaceChildren(...Object.keys(presets).map(name => el('button', {type: 'button', 'aria-pressed': String(mode === name), onclick: () => {mode = name; drafts.mode = mode; render();}}, name[0].toUpperCase() + name.slice(1))));
    const draft = drafts[mode] ||= {payload: pretty(presets[mode][0][1]), key: crypto.randomUUID(), preset: '0'};
    const choices = el('select', {id: 'preset'}, presets[mode].map(([name], index) => el('option', {value: index}, name)));
    const editor = el('textarea', {id: 'playground-json', spellcheck: 'false', value: draft.payload});
    const key = el('input', {id: 'idempotency-key', value: draft.key, maxlength: '96', required: true});
    choices.value = draft.preset;
    editor.addEventListener('input', () => {draft.payload = editor.value;});
    key.addEventListener('input', () => {draft.key = key.value;});
    choices.addEventListener('change', () => {editor.value = pretty(presets[mode][Number(choices.value)][1]); key.value = crypto.randomUUID(); draft.payload = editor.value; draft.key = key.value; draft.preset = choices.value;});
    const output = status(); const result = el('div');
    const submit = el('button', {type: 'submit', class: 'primary'}, 'Run governed action ↗');
    const scope = mode === 'model' ? 'model' : 'tools';
    const authority = el('div', {class: 'confirmation', 'aria-label': 'Playground credential'});
    async function refreshAuthority() {
      submit.disabled = true;
      authority.replaceChildren(el('p', {role: 'status'}, 'Checking scoped credential…'));
      try {
        const credential = await api.request(`/admin/playground/credential?scope=${scope}`);
        if (credential.scope !== scope || !Number.isInteger(credential.epoch) ||
            !['unissued', 'active', 'expired', 'revoked'].includes(credential.state)) throw new Error('Credential status unavailable.');
        authority.replaceChildren(el('div', {class: 'section-head'}, el('h3', {}, `${scope === 'model' ? 'Model' : 'Tool'} credential`), tag(credential.state)),
          el('p', {class: 'hint'}, credential.expires_at ? `Expires ${timestamp(credential.expires_at)} · epoch ${credential.epoch}` : 'Issued on the first governed action.'));
        submit.disabled = !['unissued', 'active'].includes(credential.state);
        if (credential.state === 'expired') {
          const renewalStatus = status();
          const renew = button('Renew expired credential', () => busy(renew, renewalStatus, async () => {
            await api.request('/admin/playground/credential/renew', {method: 'POST', body: {scope, expected_epoch: credential.epoch}});
            await refreshAuthority();
            output.textContent = 'Credential renewed. Budget usage is preserved. Prior approvals need a new action and review.';
          }), 'secondary');
          authority.append(el('p', {class: 'hint'}, 'Renewal preserves identity and spent budget. It does not revive earlier approvals.'), renew, renewalStatus);
        } else if (credential.state === 'revoked') authority.append(el('p', {class: 'hint'}, 'This authority was revoked and cannot be renewed. Contact the installation owner.'));
      } catch (error) {authority.replaceChildren(el('p', {role: 'status', class: 'error'}, error.message));}
    }
    const form = el('form', {}, field('Example preset', choices), field('Action payload · JSON', editor, 'Examples are inputs, not expected results. Active policy determines the outcome.'),
      mode === 'mail' ? field('Idempotency key', key, 'Keep this key when retrying the exact action. Use a new key for a new message.') : null,
      submit, output);
    form.addEventListener('submit', async event => {event.preventDefault(); if (submit.disabled) return; await busy(submit, output, async () => {
      const body = playgroundBody(mode, parseEditor(editor.value), key.value);
      result.replaceChildren();
      const data = await api.request('/admin/playground', {method: 'POST', body, decision: true});
      result.replaceChildren(resultView(data));
      if (data.action_state === 'pending' || data.action_state === 'approved') result.append(el('a', {href: '#approvals'}, 'Review approvals →'), el('p', {class: 'hint'}, 'After approval, return here and run this exact saved action and key.'));
      output.textContent = 'Gateway response received. Review the decision and execution evidence below.';
    }); await refreshAuthority();});
    content.replaceChildren(el('div', {class: 'grid'}, panel('Compose an action', form), panel('Execution boundary',
      el('p', {}, 'Actions run as a server-owned, scoped demo principal.'),
      el('p', {class: 'hint'}, 'Mail targets a local test outbox. Model and tool modes require their installed backend integrations. Unavailable services do not produce simulated results.'),
      authority,
      el('p', {class: 'eyebrow'}, 'RESPONSE / EVIDENCE'), result)));
    refreshAuthority();
  }
  root.append(tabs, content); render(); return root;
}
async function editorView(kind, api, setDirty) {
  let current = await api.request(`/admin/${kind}`);
  if (!current[kind] || typeof current.version !== 'string') throw new Error('The service did not return a versioned document.');
  const root = panel(kind === 'policy' ? 'Policy document' : 'Threat indicator feed');
  const version = el('p', {class: 'hint'});
  const editor = el('textarea', {id: `${kind}-json`, class: 'editor', spellcheck: 'false', value: pretty(current[kind])});
  const output = status(); const preview = el('div');
  const validation = status();
  const validate = button('Validate on server', () => busy(validate, validation, async () => {
    const submitted = editor.value;
    const policy = parseEditor(submitted);
    const result = await api.request('/admin/policy/validate', {method: 'POST', body: {policy}});
    if (editor.value !== submitted) {validation.textContent = 'Edits changed during validation. Validate the current document again.'; return;}
    validation.textContent = result.valid === true ? `Valid · ${text(result.version)}. Activation still requires current-version validation.` : 'Server did not confirm validity.';
  }));
  const review = button('Review activation →', () => {
    output.textContent = ''; output.classList.remove('error'); preview.replaceChildren();
    try {
      const candidate = parseEditor(editor.value);
      if (pretty(candidate) === pretty(current[kind])) throw new Error('No changes to activate.');
      const candidateText = editor.value;
      const expectedVersion = current.version;
      const check = el('input', {id: `confirm-${kind}`, type: 'checkbox'});
      const activate = button('Activate reviewed version', () => busy(activate, output, async () => {
        if (!check.checked || editor.value !== candidateText) throw new Error('Review the current edits before activating.');
        const path = kind === 'policy' ? '/admin/policy/activate' : '/admin/feed';
        editor.disabled = true;
        let data;
        try {data = await api.request(path, {method: 'POST', body: {[kind]: candidate, expected_version: expectedVersion}});}
        finally {editor.disabled = false;}
        if (!data[kind] || typeof data.version !== 'string') throw new Error('Activation response incomplete. Refresh to inspect current state.');
        current = data; editor.value = pretty(data[kind]); setDirty(false); updateVersion();
        preview.replaceChildren(); output.textContent = `Activated ${data.version}.`; validation.textContent = '';
      }), 'primary');
      activate.disabled = true; check.addEventListener('change', () => {activate.disabled = !check.checked;});
      preview.append(el('div', {class: 'confirmation'}, el('h3', {}, `Replace ${expectedVersion}`),
        el('p', {class: 'hint'}, 'The server checks the expected version atomically. Increase the document revision; concurrent changes reject this activation.'),
        details('Current document', current[kind]), details('Proposed document', candidate, true),
        el('label', {for: check.id}, check, 'I reviewed this exact document.'), activate));
    } catch (error) {output.classList.add('error'); output.textContent = error.message;}
  }, 'primary');
  function updateVersion() {version.textContent = `Active version: ${current.version} · edits stay in this tab until activated.`;}
  editor.addEventListener('input', () => {setDirty(editor.value !== pretty(current[kind])); preview.replaceChildren(); validation.textContent = ''; output.textContent = '';});
  root.append(version, field(kind === 'policy' ? 'Policy JSON' : 'Feed JSON', editor, kind === 'feed' ? 'Data-only indicators. The server validates schema, bounds and revision during atomic activation.' : 'Schema and worker readiness are checked by the gateway.'),
    el('div', {class: 'actions'}, kind === 'policy' ? validate : null, review), validation, preview, output);
  updateVersion(); return root;
}
function tenantSelector() {return el('input', {id: 'tenant-filter', value: 'tenant-a', required: true, pattern: '[a-zA-Z0-9][a-zA-Z0-9._-]{0,95}', maxlength: '96'});}
function scopedList(kind, api) {
  const root = panel(kind === 'approvals' ? 'Exact mail actions' : 'Local test outbox');
  const tenant = tenantSelector(); const output = status(); const rows = el('div');
  const load = el('button', {type: 'submit', class: 'secondary'}, 'Load tenant');
  const form = el('form', {class: 'filters'}, field('Tenant', tenant), load);
  async function refresh() {
    rows.replaceChildren();
    const scope = tenant.value;
    const data = await api.request(`/admin/${kind}?${new URLSearchParams({tenant_id: scope, limit: '100'})}`);
    const entries = data[kind === 'approvals' ? 'approvals' : 'messages'];
    if (!Array.isArray(entries)) throw new Error('The service returned no record list.');
    output.textContent = `${entries.length} records · ${scope} · bounded to 100`;
    if (kind === 'outbox') {
      rows.append(entries.length ? table(['Created', 'Action', 'Recipient', 'Delivery state'], entries.map(item => [timestamp(item.created_at), item.action_id, item.recipient, item.delivery_state])) : empty('No messages recorded for this tenant.'));
    } else {
      if (!entries.length) rows.append(empty('No approval records for this tenant.'));
      for (const item of entries) {
        const response = el('div'); const rowStatus = status();
        const card = el('article', {class: 'panel approval'}, el('div', {class: 'section-head'}, el('h3', {}, text(item.action_id)), tag(item.state)),
          pairs({tenant: item.tenant_id, principal: item.principal_id, root_run: item.root_run_id, operation: item.operation, policy: item.policy_version, created: timestamp(item.created_at), expires: timestamp(item.expires_at), fingerprint: item.fingerprint, payload_digest: item.payload_digest, policy_digest: item.policy_digest, registry_digest: item.registry_digest, reason: item.reason, decided_by: item.decided_by}),
          el('pre', {'aria-label': 'Exact immutable mail payload'}, pretty(item.payload)), response, rowStatus);
        if (item.state === 'pending' && typeof item.fingerprint === 'string' && typeof item.action_id === 'string') {
          const check = el('input', {id: `review-${rows.childElementCount}`, type: 'checkbox'});
          const controls = el('div', {class: 'actions'});
          for (const approve of [true, false]) {
            const control = button(approve ? 'Approve exact action' : 'Reject action', () => busy(control, rowStatus, async () => {
              if (!check.checked) throw new Error('Review this exact action first.');
              check.disabled = true;
              controls.querySelectorAll('button').forEach(b => {b.disabled = true;});
              try {
                const result = await api.request(`/admin/approvals/${encodeURIComponent(item.action_id)}/decision`, {method: 'POST', body: {tenant_id: scope, fingerprint: item.fingerprint, approve}, decision: true});
                response.replaceChildren(resultView(result));
                controls.remove(); check.disabled = true;
                rowStatus.textContent = 'Decision returned. Refresh to inspect current state; approval alone is not delivery.';
              } catch (error) {check.disabled = false; controls.querySelectorAll('button').forEach(b => {b.disabled = !check.checked;}); throw error;}
            }), approve ? 'primary' : 'secondary');
            control.disabled = true; controls.append(control);
          }
          check.addEventListener('change', () => controls.querySelectorAll('button').forEach(b => {b.disabled = !check.checked;}));
          card.append(el('label', {for: check.id}, check, 'I reviewed the exact payload, identity, expiry and fingerprint.'), controls);
        }
        rows.append(card);
      }
    }
  }
  form.addEventListener('submit', event => {event.preventDefault(); busy(load, output, refresh);});
  root.append(el('p', {class: 'hint'}, kind === 'approvals' ? 'Review immutable payloads. The gateway revalidates current permissions; approval cannot override a prohibition.' : 'Metadata only. These records describe local fixture delivery, never SMTP delivery.'), form, output, rows);
  busy(load, output, refresh); return root;
}
function exportView(api) {
  const root = panel('Export a bounded audit page');
  const tenant = tenantSelector();
  const scope = el('select', {id: 'export-scope'}, el('option', {value: 'tenant'}, 'One tenant'), el('option', {value: 'unattributed'}, 'Unattributed events'));
  scope.addEventListener('change', () => {tenant.disabled = scope.value === 'unattributed';});
  const format = el('select', {id: 'export-format'}, ['jsonl', 'ecs', 'splunk-hec'].map(value => el('option', {value}, value)));
  const after = el('input', {id: 'after-sequence', type: 'number', min: '0', max: '9007199254740991', step: '1', value: '0', required: true});
  const through = el('input', {id: 'through-sequence', type: 'number', min: '0', max: '9007199254740991', step: '1', placeholder: 'Server snapshot'});
  const limit = el('input', {id: 'export-limit', type: 'number', min: '1', max: '1000', value: '100', required: true});
  const output = status(); const metadata = el('div');
  const submit = el('button', {type: 'submit', class: 'primary'}, 'Download audit page ↓');
  const form = el('form', {}, el('div', {class: 'grid'}, field('Scope', scope), field('Tenant', tenant), field('Format', format), field('Page limit', limit), field('After sequence', after), field('Through sequence', through)), submit, output);
  form.addEventListener('submit', event => {event.preventDefault(); busy(submit, output, async () => {
    const params = new URLSearchParams({format: format.value, limit: limit.value, after_sequence: after.value});
    params.set(scope.value === 'tenant' ? 'tenant' : 'unattributed', scope.value === 'tenant' ? tenant.value : 'true');
    if (through.value) params.set('through_sequence', through.value);
    const {blob, cursor} = await api.request(`/admin/audit/export?${params}`, {download: true});
    const url = URL.createObjectURL(blob); const link = el('a', {href: url, download: `agentgate-${format.value}.jsonl`});
    document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
    output.textContent = 'Audit page downloaded. Check the cursor for more records; this is not a complete export unless has_more is false.';
    metadata.replaceChildren(details('Export cursor', cursor ? JSON.parse(cursor) : {status: 'not_reported'}, true));
  });});
  root.append(el('p', {class: 'hint'}, 'Security records use the gateway’s minimized export projection. Raw prompts and credentials are excluded. Cursor values preserve the selected snapshot across pages.'), form, metadata); return root;
}
export function actionView(route, api, setDirty, drafts = {}) {
  if (route === 'playground') return playground(api, drafts);
  if (route === 'policy' || route === 'feed') return editorView(route, api, setDirty);
  if (route === 'approvals' || route === 'outbox') return scopedList(route, api);
  return exportView(api);
}
