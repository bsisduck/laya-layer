import {el, panel, pairs, details, field, tag, status, busy, timestamp, empty, button} from './ui.js';

export function hrResourceLabel(resource) {
  return ({'hr-candidate-001': 'Synthetic candidate record', 'hr-cv-injection-001': 'Untrusted CV', 'hr-private-notes': 'HR private notes', 'finance-record-001': 'Finance record'})[resource] || resource;
}

export function hrState(data) {
  return data?.version === 'hr-local-v1' && data?.data === 'synthetic' &&
    Array.isArray(data.effective_documents) && data.parent && data.identity && data.requester ? 'ready' : 'missing';
}
export function clearHR(state) { for (const key of Object.keys(state)) delete state[key]; }

export async function hrView(api, memory) {
  const data = await api.request('/admin/hr');
  if (hrState(data) !== 'ready') throw new Error('The HR workflow contract is unavailable.');
  const root = el('div', {class: 'hr-workspace'});
  const output = status();
  const result = el('div', {'aria-live': 'polite'});
  const bindingView = el('div');
  const actions = el('div');
  const approval = el('div');
  const controls = [];
  const running = new Set();
  let expiryTimer;
  const catalogue = await api.request('/admin/catalog');
  const mail = catalogue.tools?.find(item => item.operation === 'mail.send');
  const traceLink = trace => el('a', {href: `#timeline?trace=${encodeURIComponent(trace)}`}, 'Open this audit trace →');
  function evidence(data) {
    const evidence = data.completion?.agentgate || data;
    result.replaceChildren(panel(data.completion ? 'Provider summary' : 'Actual gateway decision',
      tag(evidence.decision || data.status),
      el('p', {}, data.completion ? data.completion.choices[0].message.content : (data.reason_codes || []).join(' · ')),
      data.result?.content ? el('p', {class: 'hr-source'}, data.result.content) : null,
      el('p', {class: 'hint'}, evidence.executed === true ? 'The gateway reports execution. Inspect the trace for release and accounting evidence.' : 'No execution confirmed. Review this actual response before continuing.'),
      evidence.trace_id ? traceLink(evidence.trace_id) : null,
      data.source ? traceLink(data.source.trace_id) : null,
      details('Inspect response', data)));
  }
  const write = async (path, body) => {
    try { return await api.request(`/admin/hr/${path}`, {method: 'POST', body, decision: true, evidence: true}); }
    catch (error) {
      if (error.status === 410) { clearHR(memory); approval.replaceChildren(); bindingStatus(); }
      throw error;
    }
  };
  function requireBinding() {
    if (!memory.binding || memory.binding.expires_at * 1000 <= Date.now()) throw new Error('HR binding expired or unavailable. Deliberately start a new binding; old proposals cannot transfer.');
    return memory.binding.handle;
  }
  function bindingStatus() {
    clearTimeout(expiryTimer);
    const active = memory.binding && memory.binding.expires_at * 1000 > Date.now();
    bindingView.replaceChildren(pairs({requester: 'Local HR business partner', provenance: 'Local operator-provisioned demo', agent: data.identity.agent_id, department: data.requester.department, accounting_owner: data.identity.principal_id, authority: active ? `Bound until ${timestamp(memory.binding.expires_at)}` : 'Start a bounded HR binding to act', preset_read_examples: data.effective_documents.map(hrResourceLabel)}));
    for (const control of controls) control.disabled = !active || running.has(control);
    if (active) expiryTimer = setTimeout(() => { if (root.isConnected) bindingStatus(); }, Math.max(0, memory.binding.expires_at * 1000 - Date.now()) + 50);
    if (memory.binding && !active) bindingView.append(el('p', {class: 'error', role: 'status'}, 'Binding expired. Old approvals cannot transfer. Start a new binding deliberately.'));
  }
  function controlled(label, action, kind = 'secondary') {
    const control = button(label, async () => {
      if (control.disabled) return;
      running.add(control);
      try { await busy(control, output, action); }
      finally { running.delete(control); bindingStatus(); }
    }, kind);
    controls.push(control); return control;
  }
  async function review() {
    approval.replaceChildren();
    if (!memory.proposal || !memory.binding) return;
    const rows = await api.request('/admin/approvals?tenant_id=tenant-a');
    const item = rows.approvals.find(row => row.action_id === memory.proposal.action_id);
    if (!item) { approval.append(empty('Proposal record unavailable. Inspect the audit timeline.')); return; }
    const payload = item.payload;
    const confirmation = el('input', {id: 'hr-consent', type: 'checkbox'});
    const consent = status();
    const card = panel('Review the exact proposed message', tag(item.state),
      pairs({recipient: payload.recipient, subject: payload.subject, requester: item.authority?.human_subject, agent: item.authority?.agent_id, accounting_owner: item.principal_id, approver: 'Current local-console operator (credential mode uses operator)', effect: 'One local fixture outbox record', risk: mail?.risk ? `${mail.risk.band} · ${mail.risk.score}/100 · reviewed policy heuristic` : 'See reviewed catalog', consent_expires: timestamp(item.expires_at)}),
      el('p', {class: 'hr-source'}, payload.body),
      el('p', {class: 'hint'}, 'Approval alone does not send. Exact resume rechecks current authority. Requester and approver are separate records; this local demo does not verify four-eyes IAM.'),
      details('Inspect immutable approval', item));
    if (item.state === 'pending') {
      const accept = controlled('Approve exact message', async () => {
        if (!confirmation.checked) throw new Error('Confirm the exact recipient and content first.');
        const decision = await api.request(`/admin/approvals/${encodeURIComponent(item.action_id)}/decision`, {method: 'POST', body: {tenant_id: 'tenant-a', fingerprint: item.fingerprint, approve: true}, decision: true, evidence: true});
        evidence(decision); output.textContent = 'Approval returned. No delivery occurs until you deliberately resume.';
        await review();
      }, 'primary');
      const reject = controlled('Reject message', async () => {
        evidence(await api.request(`/admin/approvals/${encodeURIComponent(item.action_id)}/decision`, {method: 'POST', body: {tenant_id: 'tenant-a', fingerprint: item.fingerprint, approve: false}, decision: true, evidence: true}));
        output.textContent = 'Rejection returned. Inspect the current record.'; await review();
      });
      card.append(field('I reviewed this exact recipient and content', confirmation), el('div', {class: 'hr-buttons'}, accept, reject), consent);
    }
    if (['approved', 'consumed'].includes(item.state)) {
      card.append(controlled(item.state === 'consumed' ? 'Replay exact resume' : 'Resume approved message', async () => {
        const response = await write('resume', {handle: requireBinding(), action_id: item.action_id});
        evidence(response); await review();
        const outbox = await api.request('/admin/outbox?tenant_id=tenant-a');
        const effects = outbox.messages.filter(row => row.action_id === item.action_id).length;
        output.textContent = `Observed local outbox records for this action: ${effects}.`;
      }, 'primary'));
    }
    card.append(el('a', {href: '#outbox'}, 'Open local outbox →'));
    approval.append(card); bindingStatus();
  }

  root.append(panel('Synthetic candidate workspace',
    el('p', {class: 'eyebrow'}, 'HR / LOCAL DEMO'),
    el('p', {}, 'Read a fictional candidate record, inspect an untrusted CV, then propose an exact follow-up message for human review.'),
    el('p', {class: 'hint'}, 'Local operator-provisioned employee records. No candidate ranking, hiring decision or real email.'),
    el('div', {class: 'hr-links'}, el('a', {href: '#catalog'}, 'Approved catalog →'), el('a', {href: '#overview'}, 'Measured usage →'), el('a', {href: '#timeline'}, 'Audit timeline →'))));

  if (!data.configured) {
    const setup = panel('Set up the reviewed HR preset',
      el('p', {}, data.incompatibility || 'HR authority is not configured. Preview the dedicated policy delta before activation.'),
      el('p', {class: 'hint'}, 'Current semantic, feed and budget controls are retained. Setup cannot restore revoked authority or enable a provider.'));
    const preview = el('div');
    const previewButton = button('Preview HR setup', () => busy(previewButton, output, async () => {
      const proposed = await api.request('/admin/hr/setup-preview');
      const activate = button('Activate reviewed HR setup', () => busy(activate, output, async () => {
        await write('setup', {expected_generation: proposed.expected_generation, preview_digest: proposed.preview_digest});
        clearHR(memory); root.replaceChildren(await hrView(api, memory));
      }), 'primary');
      preview.replaceChildren(pairs({current_policy: proposed.policy_version, changes: proposed.changes, retained: proposed.retained}), details('Inspect complete proposed policy', proposed.policy), activate);
      output.textContent = 'Review this delta. Activation checks the exact active generation.';
    }));
    setup.append(previewButton, preview); root.append(setup);
  } else {
    const start = button(memory.binding ? 'Start a new HR binding' : 'Start HR binding', () => busy(start, output, async () => {
      memory.binding = await write('bind', {}); delete memory.proposal; delete memory.key;
      approval.replaceChildren(); result.replaceChildren(); bindingStatus();
      start.textContent = 'Start a new HR binding';
      output.textContent = 'New short-lived HR binding issued. Earlier approvals cannot transfer.';
    }), 'primary');
    start.disabled = data.parent.state !== 'active';
    const end = controlled('End HR binding', async () => {
      await write('end', {handle: requireBinding()}); clearHR(memory); approval.replaceChildren(); bindingStatus(); output.textContent = 'HR binding revoked. Deliberately start again to act.';
    });
    const authority = panel('Employee and agent authority', bindingView,
      el('p', {class: 'hint'}, 'Active policy, binding and budgets are checked for each action. A new binding deliberately invalidates the previous binding and its pending approvals. Expiry, reload and session recovery never replay a mutation.'),
      el('div', {class: 'hr-buttons'}, start, end),
      details('Inspect human and agent grants', {human: data.permissions.profiles.find(p => p.role_id === 'HR-BP'), agent: data.permissions.profiles.find(p => p.role_id === 'hr-assistant'), requester: data.requester, identity: data.identity, parent: data.parent}));
    if (data.parent.state === 'expired') {
      const renew = button('Renew expired HR parent', () => busy(renew, output, async () => {
        await write('parent/renew', {expected_epoch: data.parent.epoch}); clearHR(memory); root.replaceChildren(await hrView(api, memory));
      }));
      authority.append(el('p', {class: 'error'}, 'Parent expired. Renewal is explicit and retains all accounting usage. Earlier approvals remain invalid.'), renew);
    }
    root.append(authority);
    const selection = el('select', {id: 'hr-resource'}, data.resources.map(value => el('option', {value}, ({'hr-candidate-001': 'Synthetic candidate record', 'hr-cv-injection-001': 'Untrusted CV / benign injection test', 'hr-private-notes': 'HR private notes / agent excludes', 'finance-record-001': 'Finance record / human excludes'})[value])));
    actions.append(panel('Read within the shared boundary', field('Synthetic source', selection),
      el('div', {class: 'hr-buttons'}, controlled('Read selected source', async () => { evidence(await write('read', {handle: requireBinding(), resource: selection.value})); output.textContent = 'Actual read decision returned.'; }, 'primary'),
      controlled('Request model summary', async () => { evidence(await write('summary', {handle: requireBinding(), resource: selection.value})); output.textContent = 'Actual summary request returned. A fresh authorized read is required each time.'; })),
      el('p', {class: 'hint'}, `${data.model_configured ? 'Model policy configured; availability is checked on invocation.' : 'Model policy unavailable; no substitute summary is produced.'} Semantic inspection: ${data.semantic_required ? 'required' : 'not required by active policy'} / ${data.semantic_mode}. CV decisions are actual pipeline results; real efficacy needs separately identified worker observation.`)));
    const recipient = el('input', {id: 'hr-recipient', type: 'email', required: true, maxlength: '254', value: 'candidate@demo.internal'});
    const subject = el('input', {id: 'hr-subject', required: true, maxlength: '200', value: 'Synthetic candidate follow-up'});
    const body = el('textarea', {id: 'hr-message', required: true, maxlength: '8192'}, 'Thank you for your interest. This is a synthetic follow-up for the local demonstration.');
    const propose = controlled('Propose exact message', async () => {
      const handle = requireBinding();
      memory.key ||= crypto.randomUUID();
      const response = await write('propose', {handle, proposal_key: memory.key, recipient: recipient.value, subject: subject.value, body: body.value});
      evidence(response); if (response.approval_id) { memory.proposal = response; await review(); }
      output.textContent = 'Proposal returned. Review the exact payload; no message has been sent.';
    }, 'primary');
    const fresh = controlled('Use a new proposal key', async () => { memory.key = crypto.randomUUID(); delete memory.proposal; approval.replaceChildren(); output.textContent = 'New proposal key selected. Submit the edited content for a new exact review.'; });
    actions.append(panel('Propose a synthetic follow-up', field('Message recipient', recipient), field('Message subject', subject), field('Message content', body),
      el('div', {class: 'hr-buttons'}, propose, fresh), el('p', {class: 'hint'}, 'Editing an existing proposal with the same key conflicts. A new key requires a fresh exact review. Local fixture outbox only.')));
    root.append(actions, approval);
    bindingStatus(); await review();
    if (memory.binding) {
      setTimeout(() => { if (root.isConnected) bindingStatus(); }, Math.max(0, memory.binding.expires_at * 1000 - Date.now()) + 50);
    }
  }
  root.append(output, result,
    panel('Future department adapters',
      el('p', {}, 'Dev: a reviewed merge would require an executable adapter; the current catalog example is unavailable.'),
      el('p', {}, 'Finance: payment policy and exact approval would require an executable adapter; the current catalog example is unavailable.'),
      el('a', {href: '#catalog'}, 'Inspect unavailable examples →')));
  return root;
}
