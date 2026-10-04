import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createClient} from '../../src/agentgate/web/api.js';
import {filterEvents} from '../../src/agentgate/web/observe.js';
import {parseEditor} from '../../src/agentgate/web/ui.js';
import {playgroundBody} from '../../src/agentgate/web/actions.js';
import {catalogState} from '../../src/agentgate/web/catalog.js';
import {hrResourceLabel, hrDecision, hrProgress} from '../../src/agentgate/web/hr.js';
import {overviewSection, pendingApprovals} from '../../src/agentgate/web/observe.js';
import {exactMoney, knownMeasure, usageState} from '../../src/agentgate/web/departments.js';
import {standardsEvidence} from '../../src/agentgate/web/standards.js';
test('department money stays exact past JS and SQLite integer bounds with contributing counts', () => {
  for (const value of ['0', '9007199254740993', '10000000000000000021']) {
    assert.equal(exactMoney(value), value);
    assert.equal(knownMeasure(value, 1, 2, true), `${value} · 1/2 contributing attempts`);
  }
  for (const value of [9007199254740993, '1e19', '-1', '01', null]) assert.equal(exactMoney(value), 'Unknown');
  assert.equal(knownMeasure('0', 0, 2, true), 'Unknown · 0/2 contributing attempts');
  assert.equal(knownMeasure('0', 3, 2, true), 'Unknown');
  assert.equal(usageState(null), 'missing');
  assert.equal(usageState({version: 1, source: 'model-attempt-evidence-v1', departments: [], totals: {attempts: 0}, window: {}, completeness: {status: 'complete'}}), 'empty');
});
test('standards bind explicit official editions to local evidence and remaining obligations', () => {
  assert.equal(standardsEvidence.length, 11);
  for (const row of standardsEvidence) {
    assert.ok(['eur-lex.europa.eu', 'ai-act-service-desk.ec.europa.eu', 'www.esma.europa.eu', 'genai.owasp.org'].includes(new URL(row.source).hostname));
    assert.ok(row.evidence.length && row.gap.length);
    for (const path of row.evidence) assert.match(path, /^(docs|tests)\//);
  }
  assert.ok(standardsEvidence.some(row => row.framework.includes('edition 2025')));
  assert.ok(standardsEvidence.some(row => row.framework.includes('edition 2026')));
});
const session = {authenticated: true, csrf_token: 'test-csrf', expires_at: 9999999999};
const response = (body, status = 200) => new Response(JSON.stringify(body), {status, headers: {'Content-Type': 'application/json'}});
test('HR readable resource examples map the supplied contract without inventing grants', () => {
  assert.deepEqual(['hr-candidate-001'].map(hrResourceLabel), ['Synthetic candidate record']);
  assert.deepEqual([].map(hrResourceLabel), []);
  assert.equal(hrResourceLabel('future-synthetic-resource'), 'future-synthetic-resource');
});
test('HR distinguishes withheld output, no dispatch and actual released summaries', () => {
  const denied = {decision: 'deny', executed: false, result: {content: 'must not display'}};
  assert.match(hrDecision(denied).message, /not dispatched/);
  assert.equal(hrDecision(denied).content, undefined);
  assert.match(hrDecision({...denied, executed: true}).message, /output was withheld/);
  assert.equal(hrDecision({...denied, executed: true}).released, false);
  assert.match(hrDecision({decision: 'deny'}).message, /Execution is unknown/);
  assert.match(hrDecision({decision: 'deny', executed: null}).message, /Execution is unknown/);
  const completion = {agentgate: {decision: 'allow', executed: true}, choices: [{message: {content: 'Actual provider output'}}]};
  assert.equal(hrDecision({completion}).content, 'Actual provider output');
  for (const bad of [{...completion, choices: []}, {...completion, agentgate: denied}]) {
    assert.equal(hrDecision({completion: bad}).released, false);
    assert.equal(hrDecision({completion: bad}).content, null);
  }
  assert.equal(hrDecision({decision: 'allow', executed: true}).released, false);
  assert.equal(hrDecision({decision: 'require_approval', executed: false}, 'action').released, false);
});
test('HR progress requires released content and observed outbox effects', () => {
  assert.deepEqual(hrProgress({}, false), ['Not started', 'Read or summarize', 'Draft a message']);
  assert.equal(hrProgress({binding: {}}, false)[0], 'Expired');
  assert.equal(hrProgress({read: 'blocked'}, true)[1], 'Blocked · review evidence');
  assert.equal(hrProgress({read: 'unavailable'}, true)[1], 'Unavailable · review evidence');
  assert.equal(hrProgress({read: 'released'}, true)[1], 'Output released');
  assert.equal(hrProgress({reviewState: 'approved'}, true)[2], 'Approved · resume required');
  assert.equal(hrProgress({reviewState: 'consumed'}, true)[2], 'Consumed · inspect outbox');
  assert.equal(hrProgress({effects: 1}, true)[2], 'One local record observed');
  assert.equal(hrProgress({effects: 0}, true)[2], 'Draft a message');
});
test('overview deep links select only known evidence sections', () => {
  for (const key of ['usage', 'standards', 'controls']) assert.equal(overviewSection(`#overview?section=${key}`), key);
  for (const hash of ['', '#overview', '#overview?section=missing', '#overview?section=<script>']) assert.equal(overviewSection(hash), 'all');
});
test('catalog consumer separates unsupported, missing, empty and trusted versioned metadata', () => {
  const tool = {operation: 'mail.send', executable: true, effect: 'write', data_scope: 'Unclassified submitted text', adapter: 'local_fixture_outbox', reversibility: 'local_record_retained', affects_person: true, policy: {disposition: 'exact_approval'}, risk: {version: 'tool-policy-heuristic-v1', score: 75, band: 'high', components: {effect: 25, potential_data: 25, exposure: 10, reversibility: 5, affects_person: 10}}};
  const data = {version: 'approved-tools-v1', tools: [tool], examples: []};
  assert.equal(catalogState(data), 'ready');
  assert.equal(catalogState({...data, tools: []}), 'empty');
  for (const invalid of [null, {}, {...data, version: 'old'}, {...data, tools: [null]}, {...data, tools: [tool, tool]}, {...data, tools: [tool, tool, tool, tool]}, {...data, tools: [{...tool, risk: null}]}, {...data, tools: [{...tool, risk: {...tool.risk, score: 0}}]}, {...data, tools: [{...tool, risk: {...tool.risk, band: 'low'}}]}, {...data, examples: [{operation: 'payments.transfer', executable: true}]}]) assert.equal(catalogState(invalid), 'missing');
});
test('session credential is posted once; writes use cookie and memory-only CSRF', async () => {
  const calls = [];
  const api = createClient(() => {}, async (url, options) => {calls.push({url, ...options}); return response(session);});
  await api.login('ephemeral-test-credential');
  await api.request('/admin/policy/activate', {method: 'POST', body: {policy: {}, expected_version: 'demo:1'}});
  assert.deepEqual(JSON.parse(calls[0].body), {token: 'ephemeral-test-credential'});
  assert.equal(calls[1].headers['X-CSRF-Token'], 'test-csrf');
  assert.equal(calls[1].credentials, 'same-origin');
  assert.equal(calls[1].redirect, 'error');
  assert.equal(calls[1].cache, 'no-store');
  assert.equal(calls[1].headers.Authorization, undefined);
  await api.logout();
  await assert.rejects(api.request('/admin/feed', {method: 'POST', body: {}}), /Unlock/);
});
test('401 clears session while denial evidence and 503 remain distinct', async () => {
  let status = 200; let locked = 0;
  const api = createClient(() => {locked++;}, async () => response(status === 200 ? session : {decision: 'deny', executed: false}, status));
  await api.restore(); status = 403;
  assert.equal((await api.request('/admin/playground', {decision: true})).executed, false);
  status = 503;
  await assert.rejects(api.request('/admin/playground', {decision: true}), /unavailable/i);
  status = 401;
  await assert.rejects(api.request('/admin/overview'), /Session expired/);
  assert.equal(locked, 1);
  await assert.rejects(api.request('/admin/feed', {method: 'POST'}), /Unlock/);
});
test('stale requests cannot resurrect a locked session', async () => {
  let resolve;
  const api = createClient(() => {}, () => new Promise(done => {resolve = done;}));
  const restore = api.restore(); api.clear(); resolve(response(session));
  await assert.rejects(restore, /Session changed/);
  await assert.rejects(api.request('/admin/feed', {method: 'POST'}), /Unlock/);
});
test('expired playground authority retains the separate operator session for explicit renewal', async () => {
  let mode = 'session'; let locked = 0;
  const calls = [];
  const denied = {decision: 'deny', executed: false, action_id: 'act-expired', reason_codes: ['INVALID_CREDENTIAL']};
  const api = createClient(() => {locked++;}, async (url, options) => {
    calls.push({url, ...options});
    return mode === 'denied' ? response(denied, 401) : response(session);
  });
  await api.restore(); mode = 'denied';
  assert.deepEqual(await api.request('/admin/playground', {method: 'POST', body: {}, decision: true}), denied);
  assert.equal(locked, 0);
  mode = 'session';
  await api.request('/admin/playground/credential/renew', {method: 'POST', body: {scope: 'tools', expected_epoch: 0}});
  assert.equal(calls.at(-1).headers['X-CSRF-Token'], 'test-csrf');
  mode = 'denied';
  await assert.rejects(api.request('/admin/overview'), /Session expired/);
  assert.equal(locked, 1);
});
test('conflicts/missing routes/network writes never become successes', async () => {
  for (const [status, message] of [[409, /Version conflict/], [404, /unavailable/], [501, /unavailable/]]) {
    const api = createClient(() => {}, async url => response(url === '/admin/session' ? session : {detail: 'safe detail'}, url === '/admin/session' ? 200 : status));
    await api.restore();
    await assert.rejects(api.request('/admin/policy'), message);
  }
  const api = createClient(() => {}, async () => {throw new Error('connection');});
  await assert.rejects(api.login('test'), /Outcome is unknown/);
  await assert.rejects(api.request('https://example.invalid/'), /Invalid operator endpoint/);
});
test('filters preserve actual events, editor errors and server-owned identity', () => {
  const events = [{decision: 'deny', trace_id: 'abc', reason_codes: ['TENANT_DENIED']}, {decision: 'allow', operation: 'documents.read'}];
  assert.deepEqual(filterEvents(events, 'deny', 'tenant'), [events[0]]);
  assert.deepEqual(filterEvents(events, 'allow', 'abc'), []);
  const pending = {decision: 'require_approval', operation: 'mail.send'};
  assert.deepEqual(filterEvents([pending], 'pending', ''), [pending]);
  assert.throws(() => parseEditor('[]'), /JSON object/);
  assert.throws(() => parseEditor('{'), /Invalid JSON/);
  assert.throws(() => parseEditor(' '.repeat(65537)), /64 KiB/);
  assert.throws(() => playgroundBody('document', {tenant_id: 'other'}, 'key'), /Identity/);
  assert.deepEqual(playgroundBody('document', {document_id: 'notes'}, 'key'), {mode: 'document', document_id: 'notes'});
  assert.equal(playgroundBody('mail', {recipient: 'a@demo.internal'}, 'retry-key').idempotency_key, 'retry-key');
});

test('live ladder filters preserve unknown and overlapping control associations', async () => {
  const {eventContext} = await import('../../src/agentgate/web/threats.js');
  const context = {schema_version: 1, taxonomy_version: 'laya-threat-v1', candidate_levels: [], level_status: 'unknown', layers: ['identity', 'data'], owasp: ['LLM06:2025', 'ASI03:2026']};
  const denied = {decision: 'deny', threat_context: context};
  const old = {decision: 'allow'};
  assert.deepEqual(filterEvents([denied, old], '', '', 'unknown'), [denied, old]);
  for (const level of ['L0','L1','L2','L3','L4','L5']) assert.deepEqual(filterEvents([denied,old], '', '', level), []);
  assert.deepEqual(filterEvents([denied,old], '', '', '', 'data'), [denied]);
  assert.deepEqual(filterEvents([denied,old], 'allow', '', '', 'identity'), []);
  assert.equal(eventContext({...denied, threat_context: {...context, candidate_levels: ['L5']}}).level_status, 'unknown');
  assert.deepEqual(eventContext({...denied, threat_context: {...context, schema_version: 99}}).layers, []);
  assert.deepEqual(eventContext({threat_context: {...context, layers: ['<script>', 'input']}}).layers, ['input']);
});

test('taxonomy consumers reject invented OWASP families and invalid ordered legends', async () => {
  const {eventContext, validTaxonomy, levels, layers} = await import('../../src/agentgate/web/threats.js');
  const data = {schema_version: 1, taxonomy_version: 'laya-threat-v1',
    levels: levels.map(id => ({id, name: id, assignment: 'Rule', controls: 'Controls', gaps: 'Limits', coverage: 'partial'})),
    layers: layers.map(id => ({id, name: id}))};
  assert.equal(validTaxonomy(data), true);
  for (const mutate of [
    value => {value.levels[1].id = 'L0';}, value => {value.levels.reverse();},
    value => {value.levels[2].id = 'L9';}, value => {value.layers[1].id = 'identity';},
    value => {value.layers.reverse();}, value => {value.layers.pop();},
    value => {delete value.levels[0].controls;}, value => {value.layers[0] = null;},
  ]) {const malformed = structuredClone(data); mutate(malformed); assert.equal(validTaxonomy(malformed), false);}
  const context = {schema_version: 1, taxonomy_version: 'laya-threat-v1', layers: ['data','data'],
    owasp: ['LLM99:2025','ASI00:2026','LLM00:2025','ASI11:2026','LLM01:2026','ASI01:2025',null,{},'LLM02:2025','LLM02:2025','ASI10:2026']};
  assert.deepEqual(eventContext({threat_context: context}).owasp, ['LLM02:2025','ASI10:2026']);
  assert.deepEqual(eventContext({threat_context: context}).layers, ['data']);
});

test('local bootstrap sends only empty JSON and preserves memory-only CSRF', async () => {
  const calls = [];
  const api = createClient(() => {}, async (url, options) => {
    calls.push({url, ...options});
    return response(url === '/admin/config' ? {mode: 'local'} : session);
  });
  assert.deepEqual(await api.config(), {mode: 'local'});
  await api.bootstrap();
  assert.equal(calls[1].url, '/admin/session/bootstrap');
  assert.equal(calls[1].body, '{}');
  assert.equal(calls[1].headers.Authorization, undefined);
  await api.request('/admin/policy/activate', {method: 'POST', body: {}});
  assert.equal(calls[2].headers['X-CSRF-Token'], session.csrf_token);
});

import {createLocalRecovery} from '../../src/agentgate/web/session.js';
test('local recovery is one attempt, coalesced and does not renew credentials or replay mutations', async () => {
  for (const path of ['/admin/playground', '/admin/approvals/act-one/decision', '/admin/policy/activate', '/admin/feed']) {
    const calls = []; let recoveries = 0; let recovery;
    const api = createClient(() => {recoveries++; recovery = recover();}, async (url, options) => {
      calls.push({url, ...options});
      if (url === '/admin/session/bootstrap') return response(session);
      return response({detail: 'Operator session required'}, 401);
    });
    const recover = createLocalRecovery(api);
    await api.bootstrap();
    await assert.rejects(api.request(path, {method: 'POST', body: {reviewed: true}}), /expired/);
    await recovery;
    assert.equal(recoveries, 1);
    assert.deepEqual(calls.map(x => x.url), ['/admin/session/bootstrap', path, '/admin/session', '/admin/session/bootstrap']);
    assert.equal(calls.filter(x => x.url === path).length, 1);
    assert.equal(calls.filter(x => /credential\/renew/.test(x.url)).length, 0);
  }
  let restoreCalls = 0; let bootstrapCalls = 0; let release;
  const recover = createLocalRecovery({
    restore: () => {restoreCalls++; return new Promise(done => {release = done;});},
    bootstrap: async () => {bootstrapCalls++; return session;},
  });
  const a = recover(); const b = recover(); assert.equal(a, b);
  release(session); await a;
  assert.equal(restoreCalls, 1); assert.equal(bootstrapCalls, 0);
});
test('local outage never loops or bootstraps after non-401 and bootstrap failure', async () => {
  for (const status of [0, 503, 401]) {
    let restores = 0; let bootstraps = 0;
    const recover = createLocalRecovery({
      restore: async () => {restores++; throw {status};},
      bootstrap: async () => {bootstraps++; throw {status: 503};},
    });
    await assert.rejects(recover());
    assert.equal(restores, 1);
    assert.equal(bootstraps, status === 401 ? 1 : 0);
  }
});

test('an expired action follow-up cannot interrupt session recovery', async () => {
  const calls = []; let bootstrapDone; let recovery;
  const api = createClient(() => {recovery = recover();}, async url => {
    calls.push(url);
    if (url === '/admin/session/bootstrap' && calls.length > 1) return new Promise(done => {bootstrapDone = () => done(response(session));});
    return response(url === '/admin/session/bootstrap' ? session : {detail: 'expired'}, url === '/admin/session/bootstrap' ? 200 : 401);
  });
  const recover = createLocalRecovery(api);
  await api.bootstrap();
  await assert.rejects(api.request('/admin/playground', {method: 'POST', body: {}, decision: true}));
  await new Promise(done => setImmediate(done));
  await assert.rejects(api.request('/admin/playground/credential?scope=tools'), /session unavailable/);
  bootstrapDone(); await recovery;
  assert.deepEqual(calls, ['/admin/session/bootstrap', '/admin/playground', '/admin/session', '/admin/session/bootstrap']);
});

const {hrState, clearHR} = await import('../../src/agentgate/web/hr.js');
test('HR rejects missing contracts and recovery drops handles/proposals', () => {
  for (const data of [null, {}, {version: 'hr-local-v2'}, {version: 'hr-local-v1', data: 'real'}]) assert.equal(hrState(data), 'missing');
  assert.equal(hrState({version: 'hr-local-v1', data: 'synthetic', effective_documents: [], parent: {}, identity: {}, requester: {}}), 'ready');
  const memory = {binding: {handle: 'not-authority'}, proposal: {action_id: 'old'}, key: 'old'};
  clearHR(memory); assert.deepEqual(memory, {});
});
test('HR can retain actual 503 evidence while ordinary unavailable behavior stays intact', async () => {
  let current = session;
  const api = createClient(() => {}, async () => response(current, current === session ? 200 : 503));
  await api.restore();
  current = {action_id: 'actual-denied', trace_id: 'actual-trace', decision: 'deny', executed: false, reason_codes: ['REQUIRED_SEMANTIC_UNAVAILABLE']};
  assert.deepEqual(await api.request('/admin/hr/summary', {method: 'POST', body: {}, decision: true, evidence: true}), current);
  await assert.rejects(api.request('/admin/playground', {decision: true}), /unavailable/i);
});

test('pending approvals use explicit global evidence, never a bounded decision count', () => {
  assert.equal(pendingApprovals({coverage: {pending_approvals: 17}, counts: {pending: 2}}), 17);
  assert.equal(pendingApprovals({count_window: {pending_scope: 'all unexpired pending approval records'}, counts: {pending: 4}}), 4);
  assert.equal(pendingApprovals({counts: {pending: 9}}), null);
  assert.equal(pendingApprovals({coverage: {pending_approvals: -1}}), null);
  assert.equal(pendingApprovals({coverage: {pending_approvals: '12'}}), null);
});

import {destinations, resolveRoute} from '../../src/agentgate/web/routes.js';
import {exampleConversations} from '../../src/agentgate/web/conversations.js';
import {workflowLayers, actionPaths} from '../../src/agentgate/web/workflow.js';
test('three primary workspaces preserve old hashes and normalize unknown routes', () => {
  assert.deepEqual(Object.keys(destinations), ['chat', 'logs', 'workflow']);
  for (const hash of ['', '#unknown', '#<script>']) assert.equal(resolveRoute(hash).name, 'chat');
  for (const [parent, links] of Object.entries(destinations)) for (const [hash] of links) assert.equal(resolveRoute(hash).parent, parent);
  assert.deepEqual(resolveRoute('#timeline?trace=trace-1'), {name: 'timeline', parent: 'logs', section: 'all', active: '#logs'});
  assert.equal(resolveRoute('#overview?section=unknown').parent, 'logs');
  assert.equal(resolveRoute('#overview?section=usage').active, '#overview?section=usage');
});
test('every authored conversation includes authority, explanation and zero-effect framing', () => {
  assert.equal(exampleConversations.length, 4);
  assert.equal(new Set(exampleConversations.map(item => item.id)).size, 4);
  assert.deepEqual(exampleConversations.map(item => item.outcome), ['Allowed', 'Blocked', 'Escalated', 'Blocked']);
  for (const item of exampleConversations) {
    for (const key of ['title','role','context','request','response','reason','operation','data','policy','effects','next']) assert.ok(item[key]?.length, `${item.id}.${key}`);
    assert.ok(item.layers.length); assert.match(item.effects, /Illustration only/);
  }
  assert.match(exampleConversations[1].reason, /cannot override/);
  assert.match(exampleConversations[2].response, /Approval alone would not dispatch/);
  assert.match(exampleConversations[3].effects, /read may already have executed/);
});
test('seven-layer map keeps reads checked, hard denials final and gaps explicit', () => {
  assert.deepEqual(workflowLayers.map(layer => layer.id), ['identity','input','data','actions','output','consumption','supply']);
  for (const layer of workflowLayers) {assert.equal(layer.status, 'Partial'); assert.ok(layer.implemented && layer.gap && layer.evidence);}
  assert.match(actionPaths.read[0], /Scope \+ policy \+ data checks/);
  assert.match(actionPaths.consequential.join(' '), /Hard deny → stop; no override/);
  assert.match(actionPaths.consequential.at(-1), /Server approval \+ revalidation → explicit resume → dispatch/);
  assert.match(actionPaths.undeclared, /denied \/ unimplemented/);
  assert.match(workflowLayers[3].gap, /descriptor hash pinning are not implemented/);
  assert.match(workflowLayers[5].gap, /Redis/);
  assert.match(workflowLayers[6].gap, /No verified 17-feed/);
});
test('GDPR portability and organizational records are distinct from technical exports', () => {
  const portability = standardsEvidence.find(row => row.framework.includes('Article 20 ·'));
  const ropa = standardsEvidence.find(row => row.framework.includes('Article 30 ·'));
  for (const row of [portability, ropa]) assert.ok(row && row.source.startsWith('https://eur-lex.europa.eu/'));
  for (const phrase of ['provided personal data', 'consent/contract', 'automated processing', 'machine-readable', 'others’ rights', 'Audit JSONL is not', 'not implemented']) assert.ok(portability.gap.includes(phrase));
  for (const phrase of ['organizational RoPA', 'purposes', 'data/subject categories', 'recipients', 'transfers', 'retention', 'safeguards', 'not a complete RoPA', 'not implemented']) assert.ok(ropa.gap.includes(phrase));
});
