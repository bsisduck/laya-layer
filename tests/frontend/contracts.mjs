import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createClient} from '../../src/agentgate/web/api.js';
import {filterEvents} from '../../src/agentgate/web/observe.js';
import {parseEditor} from '../../src/agentgate/web/ui.js';
import {playgroundBody} from '../../src/agentgate/web/actions.js';
import {catalogState} from '../../src/agentgate/web/catalog.js';
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
  assert.equal(standardsEvidence.length, 9);
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
