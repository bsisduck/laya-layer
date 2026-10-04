import {el, panel, pairs, details, field, tag, status, busy, timestamp, empty, button} from './ui.js';

export function hrResourceLabel(resource) {
  return ({'hr-candidate-001': 'Synthetic candidate record', 'hr-cv-injection-001': 'Untrusted CV', 'hr-private-notes': 'HR private notes', 'finance-record-001': 'Finance record'})[resource] || resource;
}

export function hrState(data) {
  return data?.version === 'hr-local-v1' && data?.data === 'synthetic' &&
    Array.isArray(data.effective_documents) && data.parent && data.identity && data.requester ? 'ready' : 'missing';
}
export function clearHR(state) { for (const key of Object.keys(state)) delete state[key]; }

// Presentation follows released evidence, never the HTTP status alone.
export function hrDecision(data, kind = 'read') {
  const evidence = data.completion?.agentgate || data;
  const summary = data.completion?.choices?.[0]?.message?.content;
  const content = data.result?.content;
  const released = ['allow', 'redact'].includes(evidence.decision) && evidence.executed === true;
  if (data.completion) return {title: typeof summary === 'string' && released ? 'Provider summary' : 'Summary unavailable', message: typeof summary === 'string' && released ? 'Model output released. Review it against the source; no hiring decision is made.' : 'No released model summary was supplied.', content: released && typeof summary === 'string' ? summary : null, released: released && typeof summary === 'string'};
  if (evidence.decision === 'deny') return {title: 'Request blocked', message: evidence.executed === true ? 'The protected operation ran, but its output was withheld. Completed work may still count toward usage.' : evidence.executed === false ? 'This operation was not dispatched. A summary request may have performed a separate protected source read; inspect the audit timeline.' : 'Execution is unknown. Inspect the audit before retrying.', released: false};
  return {title: kind === 'read' ? 'Source decision' : 'Action decision', message: released && typeof content === 'string' ? 'Protected source output released. Review the source before drafting.' : evidence.executed === true ? 'The gateway reports execution. Inspect the audit and local outbox for the actual effect.' : evidence.executed === false ? 'This operation was not dispatched. Approval alone creates no message.' : 'Execution is not confirmed. Inspect the audit before retrying.', content: released && typeof content === 'string' ? content : null, released: released && typeof content === 'string'};
}

export function hrProgress(memory, active) {
  return [active ? 'Active' : memory.binding ? 'Expired' : 'Not started',
    memory.read === 'released' ? 'Output released' : memory.read === 'blocked' ? 'Blocked · review evidence' : memory.read === 'unavailable' ? 'Unavailable · review evidence' : 'Read or summarize',
    memory.effects === 1 ? 'One local record observed' : ({pending: 'Awaiting exact review', approved: 'Approved · resume required', consumed: 'Consumed · inspect outbox', rejected: 'Rejected'})[memory.reviewState] || 'Draft a message'];
}

export async function hrView(api, memory) {
  // Read evidence is view-local; returning to HR resets the selection and its progress together.
  delete memory.read;
  const data = await api.request('/admin/hr');
  if (hrState(data) !== 'ready') throw new Error('The HR workflow contract is unavailable.');
  const root = el('div', {class: 'hr-workspace'});
  const lifecycle = status();
  const readStatus = status();
  const draftStatus = status();
  const readResult = el('div', {class: 'hr-feedback', 'aria-live': 'polite'});
  const draftResult = el('div', {class: 'hr-feedback', 'aria-live': 'polite'});
  const steps = el('ol', {class: 'hr-steps', 'aria-label': 'HR workflow progress'});
  const next = el('p', {class: 'hr-next', role: 'status'});
  const bindingView = el('div');
  const actions = el('div');
  const approval = el('div');
  const controls = [];
  const running = new Set();
  let expiryTimer;
  let sourceSelection;
  const catalogue = await api.request('/admin/catalog');
  const mail = catalogue.tools?.find(item => item.operation === 'mail.send');
  const traceLink = (trace, label) => el('a', {href: `#timeline?trace=${encodeURIComponent(trace)}`}, `Open ${label} audit trace →`);
  function evidence(response, target, kind = 'read') {
    const actual = response.completion?.agentgate || response;
    const display = hrDecision(response, kind);
    target.replaceChildren(el('div', {class: 'result'}, el('h3', {}, display.title), tag(actual.decision || response.status),
      el('p', {class: 'hint'}, display.message),
      el('p', {}, (actual.reason_codes || []).join(' · ')),
      display.content !== null && display.content !== undefined ? el('p', {class: 'hr-source'}, display.content) : null,
      el('div', {class: 'hr-links'}, actual.trace_id ? traceLink(actual.trace_id, response.completion ? 'model' : kind === 'summary' ? 'summary request' : kind === 'read' ? 'source' : 'action') : null,
        response.source?.trace_id && response.source.trace_id !== actual.trace_id ? traceLink(response.source.trace_id, 'source') : null),
      details('Inspect response', response)));
    if (kind !== 'action') memory.read = display.released ? 'released' : actual.decision === 'deny' ? 'blocked' : 'unavailable';
    bindingStatus();
  }
  const write = async (path, body) => {
    try { return await api.request(`/admin/hr/${path}`, {method: 'POST', body, decision: true, evidence: true}); }
    catch (error) {
      if (error.status === 410) { clearHR(memory); memory.inactive = 'The HR session expired or is no longer available. Start a new HR session deliberately; old approvals cannot transfer.'; approval.replaceChildren(); bindingStatus(); }
      throw error;
    }
  };
  function requireBinding() {
    if (!memory.binding || memory.binding.expires_at * 1000 <= Date.now()) throw new Error('HR session expired or unavailable. Start a new HR session; old approvals cannot transfer.');
    return memory.binding.handle;
  }
  function bindingStatus() {
    clearTimeout(expiryTimer);
    const active = data.parent.state === 'active' && !!memory.binding && memory.binding.expires_at * 1000 > Date.now();
    bindingView.replaceChildren(el('p', {class: 'hr-identity'}, 'Requester: Local HR business partner', el('span', {}, `Agent: ${data.identity.agent_id}`), el('span', {}, active ? `Expires: ${timestamp(memory.binding.expires_at)}` : 'No active HR session')));
    const progress = hrProgress(memory, active);
    if (data.configured && data.parent.state !== 'active') progress[0] = `Authority ${data.parent.state}`;
    steps.replaceChildren(...['Start HR session', 'Read / summarize', 'Draft / review'].map((label, i) => el('li', {}, el('strong', {}, label), el('span', {}, progress[i]))));
    next.textContent = !data.configured ? 'Next: preview the HR setup, then activate the reviewed changes.' : data.parent.state === 'expired' ? 'Next: renew the expired HR authority below, then deliberately start a new HR session.' : data.parent.state !== 'active' ? 'Next: inspect the inactive HR authority and current policy before continuing.' : !active ? 'Next: start a bounded HR session to enable the actions below.' : memory.effects === 1 ? 'One local message recorded. Inspect the outbox or deliberately start a new draft.' : memory.reviewState === 'approved' ? 'Next: resume the exact approved message to create one local outbox record.' : memory.reviewState === 'pending' ? 'Next: review the exact recipient and content below.' : memory.read === 'released' ? 'Next: draft a follow-up for exact human review.' : 'Next: select a source and read it or request a model summary.';
    for (const {control, needsBinding} of controls) control.disabled = running.size > 0 || (needsBinding ? !active : data.parent.state !== 'active');
    if (sourceSelection) sourceSelection.disabled = running.size > 0;
    if (startControl) startControl.textContent = memory.binding ? 'Start a new HR session' : 'Start HR session';
    const inactive = active ? '' : data.parent.state !== 'active' ? 'HR authority is inactive. Inspect the session controls above for renewal or policy reconciliation.' : memory.inactive || (memory.binding ? 'HR session expired. Old approvals cannot transfer. Start a new HR session deliberately.' : 'Start an HR session above to enable this action.');
    for (const hint of inactiveHints) { hint.textContent = inactive; hint.hidden = active; }
    if (active) expiryTimer = setTimeout(() => { if (root.isConnected) bindingStatus(); }, Math.max(0, memory.binding.expires_at * 1000 - Date.now()) + 50);
    if (memory.binding && !active) { approval.replaceChildren(); bindingView.append(el('p', {class: 'status error'}, inactive)); }
  }
  let startControl;
  const inactiveHints = [];
  function inactiveHint() { const hint = el('p', {class: 'hint'}); inactiveHints.push(hint); return hint; }
  function controlled(label, output, action, kind = 'secondary', needsBinding = true) {
    const control = button(label, async event => {
      event.preventDefault();
      if (control.disabled) return;
      running.add(control);
      bindingStatus(); control.disabled = false;
      try { await busy(control, output, action); }
      finally { running.delete(control); bindingStatus(); }
    }, kind);
    controls.push({control, needsBinding}); return control;
  }
  async function review() {
    // Retire controls with the previous immutable review, rather than retaining them.
    for (let i = controls.length - 1; i >= 0; i--) if (approval.contains(controls[i].control)) controls.splice(i, 1);
    approval.replaceChildren();
    if (!memory.proposal || !memory.binding) return;
    const rows = await api.request('/admin/approvals?tenant_id=tenant-a');
    const item = rows.approvals.find(row => row.action_id === memory.proposal.action_id);
    if (!item) { approval.append(empty('Proposal record unavailable. Inspect the audit timeline.')); return; }
    const payload = item.payload;
    memory.reviewState = item.state;
    const confirmation = el('input', {id: 'hr-consent', type: 'checkbox'});
    const card = panel('Review the exact proposed message', tag(item.state),
      pairs({recipient: payload.recipient, subject: payload.subject, requester: item.authority?.human_subject, agent: item.authority?.agent_id, accounting_owner: item.principal_id, approver: 'Current local-console operator (credential mode uses operator)', effect: 'One local fixture outbox record', risk: mail?.risk ? `${mail.risk.band} · ${mail.risk.score}/100 · reviewed policy heuristic` : 'See reviewed catalog', consent_expires: timestamp(item.expires_at)}),
      el('p', {class: 'hr-source'}, payload.body),
      el('p', {class: 'hint'}, 'Approval alone does not send. Exact resume rechecks current authority. Requester and approver are separate records; this local demo does not verify four-eyes IAM.'),
      details('Inspect immutable approval', item));
    if (item.state === 'pending') {
      const accept = controlled('Approve exact message', draftStatus, async () => {
        if (!confirmation.checked) throw new Error('Confirm the exact recipient and content first.');
        const decision = await api.request(`/admin/approvals/${encodeURIComponent(item.action_id)}/decision`, {method: 'POST', body: {tenant_id: 'tenant-a', fingerprint: item.fingerprint, approve: true}, decision: true, evidence: true});
        evidence(decision, draftResult, 'action'); draftStatus.textContent = 'Decision recorded. Approval alone creates no local message.';
        await review();
      }, 'primary');
      const reject = controlled('Reject message', draftStatus, async () => {
        evidence(await api.request(`/admin/approvals/${encodeURIComponent(item.action_id)}/decision`, {method: 'POST', body: {tenant_id: 'tenant-a', fingerprint: item.fingerprint, approve: false}, decision: true, evidence: true}), draftResult, 'action');
        draftStatus.textContent = 'Decision recorded. Inspect the current record.'; await review();
      });
      card.append(field('I reviewed this exact recipient and content', confirmation), el('div', {class: 'hr-buttons'}, accept, reject));
    }
    if (['approved', 'consumed'].includes(item.state)) {
      card.append(controlled(item.state === 'consumed' ? 'Replay exact resume' : 'Resume approved message', draftStatus, async () => {
        const response = await write('resume', {handle: requireBinding(), action_id: item.action_id});
        evidence(response, draftResult, 'action'); await review();
        const outbox = await api.request('/admin/outbox?tenant_id=tenant-a');
        const effects = outbox.messages.filter(row => row.action_id === item.action_id).length;
        memory.effects = effects;
        draftStatus.textContent = `Observed local outbox records for this action: ${effects}. ${item.state === 'consumed' ? 'Replay did not request an edited message.' : 'This is local fixture delivery.'}`;
      }, 'primary'));
    }
    card.append(el('a', {href: '#outbox'}, 'Open local outbox →'));
    approval.append(card); bindingStatus();
  }

  root.append(panel('Synthetic candidate workspace',
    el('p', {class: 'eyebrow'}, 'HR / LOCAL DEMO'),
    el('p', {}, 'Read a fictional candidate record, then draft a follow-up for exact review. Local outbox only; no hiring decision or real email.'), steps, next));

  if (!data.configured) {
    const setup = panel('Set up the reviewed HR preset',
      el('p', {}, data.incompatibility || 'HR authority is not configured. Preview the dedicated policy delta before activation.'),
      el('p', {class: 'hint'}, 'Current semantic, feed and budget controls are retained. Setup cannot restore revoked authority or enable a provider.'));
    const preview = el('div');
    const previewButton = button('Preview HR setup', () => busy(previewButton, lifecycle, async () => {
      const proposed = await api.request('/admin/hr/setup-preview');
      const activate = button('Activate reviewed HR setup', () => busy(activate, lifecycle, async () => {
        await write('setup', {expected_generation: proposed.expected_generation, preview_digest: proposed.preview_digest});
        clearHR(memory); root.replaceChildren(await hrView(api, memory));
      }), 'primary');
      preview.replaceChildren(pairs({current_policy: proposed.policy_version, changes: proposed.changes, retained: proposed.retained}), details('Inspect complete proposed policy', proposed.policy), activate);
      lifecycle.textContent = 'Review this delta. Activation checks the exact active generation.';
    }));
    setup.append(previewButton, preview, lifecycle); root.append(setup); bindingStatus();
  } else {
    startControl = controlled('Start HR session', lifecycle, async () => {
      const binding = await write('bind', {}); clearHR(memory); memory.binding = binding;
      approval.replaceChildren(); readResult.replaceChildren(); draftResult.replaceChildren(); readStatus.textContent = ''; draftStatus.textContent = '';
      lifecycle.textContent = 'Bounded HR session started. Earlier approvals cannot transfer.';
    }, 'primary', false);
    const end = controlled('End HR session', lifecycle, async () => {
      await write('end', {handle: requireBinding()}); clearHR(memory); memory.inactive = 'HR session ended and revoked. Start a new HR session deliberately to act.'; approval.replaceChildren(); lifecycle.textContent = memory.inactive;
    });
    const grants = details('Session boundary and complete grants', {human: data.permissions.profiles.find(p => p.role_id === 'HR-BP'), agent: data.permissions.profiles.find(p => p.role_id === 'hr-assistant'), requester: data.requester, identity: data.identity, parent: data.parent});
    grants.prepend(el('p', {class: 'hint'}, 'Local operator-provisioned demo. Active policy, human/agent grants and budgets are checked on each action. Starting another session invalidates previous proposals. Expiry, reload and recovery never replay a mutation.'), pairs({department: data.requester.department, accounting_owner: data.identity.principal_id, preset_read_examples: data.effective_documents.map(hrResourceLabel)}));
    // Keep the disclosure label first for native keyboard and screen-reader behavior.
    grants.prepend(grants.querySelector('summary'));
    const authority = panel('1. Bounded HR session', bindingView, el('div', {class: 'hr-buttons'}, startControl, end), lifecycle, grants);
    if (data.parent.state === 'expired') {
      const renew = button('Renew expired HR parent', () => busy(renew, lifecycle, async () => {
        await write('parent/renew', {expected_epoch: data.parent.epoch}); clearHR(memory); root.replaceChildren(await hrView(api, memory));
      }));
      authority.append(el('p', {class: 'error'}, 'Parent expired. Renewal is explicit and retains all accounting usage. Earlier approvals remain invalid.'), renew);
    }
    else if (data.parent.state !== 'active') authority.append(el('p', {class: 'status error'}, 'HR authority is inactive or revoked. Inspect current policy and grants; setup cannot restore revoked authority.'), el('a', {href: '#policy'}, 'Inspect current policy →'));
    root.append(authority);
    const selection = el('select', {id: 'hr-resource'}, data.resources.map(value => el('option', {value}, ({'hr-candidate-001': 'Synthetic candidate record', 'hr-cv-injection-001': 'Untrusted CV / benign injection test', 'hr-private-notes': 'HR private notes / agent excludes', 'finance-record-001': 'Finance record / human excludes'})[value])));
    sourceSelection = selection;
    selection.addEventListener('change', () => { delete memory.read; readStatus.textContent = ''; readResult.replaceChildren(); bindingStatus(); });
    async function read(path) {
      const resource = selection.value;
      delete memory.read; readResult.replaceChildren(); bindingStatus();
      const response = await write(path, {handle: requireBinding(), resource});
      if (!root.isConnected) return;
      evidence(response, readResult, path === 'summary' ? 'summary' : 'read');
      readStatus.textContent = `${path === 'summary' ? 'Summary request checked' : 'Read decision received'}: ${hrResourceLabel(resource)}.`;
    }
    actions.append(panel('2. Read / summarize', field('Synthetic source', selection),
      el('div', {class: 'hr-buttons'}, controlled('Read selected source', readStatus, () => read('read'), 'primary'),
      controlled('Request model summary', readStatus, () => read('summary'))), inactiveHint(), readStatus, readResult,
      details('Source and model availability', {model: data.model_configured ? 'Policy configured; provider availability is checked on invocation. No substitute summary.' : 'Model policy unavailable; no substitute summary.', semantic: `${data.semantic_required ? 'required' : 'not required by active policy'} / ${data.semantic_mode}`, limits: 'CV decisions are actual pipeline results. Classifier efficacy requires separate real-worker evidence.'})));
    const recipient = el('input', {id: 'hr-recipient', type: 'email', required: true, maxlength: '254', value: memory.draft?.recipient ?? 'candidate@demo.internal'});
    const subject = el('input', {id: 'hr-subject', required: true, maxlength: '200', value: memory.draft?.subject ?? 'Synthetic candidate follow-up'});
    const body = el('textarea', {id: 'hr-message', required: true, maxlength: '8192'}, memory.draft?.body ?? 'Thank you for your interest. This is a synthetic follow-up for the local demonstration.');
    const form = el('form', {novalidate: ''});
    const editHint = el('p', {class: 'hint'});
    for (const input of [recipient, subject, body]) input.addEventListener('input', () => {
      input.setCustomValidity('');
      memory.draft = {recipient: recipient.value, subject: subject.value, body: body.value};
      editHint.textContent = memory.key ? 'Edits do not change the stored message or its approval. Start a new draft to request a fresh exact review.' : '';
    });
    const propose = controlled('Propose exact message', draftStatus, async () => {
      for (const [input, message] of [[recipient, 'Enter a valid email recipient.'], [subject, 'Enter a message subject.'], [body, 'Enter message content.']]) {
        input.setCustomValidity(input.value.trim() ? '' : message);
        if (!input.checkValidity()) { input.reportValidity(); throw new Error(message); }
      }
      const handle = requireBinding();
      memory.key ||= crypto.randomUUID();
      const response = await write('propose', {handle, proposal_key: memory.key, recipient: recipient.value, subject: subject.value, body: body.value});
      evidence(response, draftResult, 'action'); if (response.approval_id) { memory.proposal = response; await review(); }
      draftStatus.textContent = response.approval_id ? 'Proposal checked. Inspect the exact review below; this submission creates no local message.' : 'No exact approval was returned. Inspect the action decision before continuing.';
    }, 'primary');
    propose.type = 'submit';
    form.addEventListener('submit', event => { event.preventDefault(); propose.click(); });
    const fresh = controlled('Start new draft', draftStatus, async () => { memory.key = crypto.randomUUID(); delete memory.proposal; delete memory.reviewState; delete memory.effects; approval.replaceChildren(); draftResult.replaceChildren(); editHint.textContent = ''; draftStatus.textContent = 'New draft started with your entered content. Submit it for a fresh exact review.'; recipient.focus(); });
    form.append(field('Message recipient', recipient), field('Message subject', subject), field('Message content', body), el('div', {class: 'hr-buttons'}, propose, fresh), inactiveHint(), editHint);
    actions.append(panel('3. Draft / review follow-up', form, el('p', {class: 'hint'}, 'Submit the exact recipient and content for review. To change a stored proposal, start a new draft. Delivery creates one local fixture outbox record.'), draftStatus, draftResult, approval));
    root.append(actions);
    bindingStatus(); await review();
  }
  root.append(el('div', {class: 'hr-links'}, el('a', {href: '#catalog'}, 'Approved catalog →'), el('a', {href: '#overview?section=usage'}, 'Measured usage →'), el('a', {href: '#timeline'}, 'Audit timeline →')),
    el('details', {}, el('summary', {}, 'Future department adapters · unavailable'),
      el('p', {}, 'Dev: a reviewed merge would require an executable adapter; the current catalog example is unavailable.'),
      el('p', {}, 'Finance: payment policy and exact approval would require an executable adapter; the current catalog example is unavailable.'),
      el('a', {href: '#catalog'}, 'Inspect unavailable examples →')));
  return root;
}
