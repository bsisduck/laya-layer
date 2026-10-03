import {createClient} from './api.js';
import {el, empty, timestamp} from './ui.js';
import {overview, timeline} from './observe.js';
const $ = selector => document.querySelector(selector);
const lockscreen = $('#lockscreen');
const shell = $('#console');
const view = $('#view');
const notice = $('#notice');
let authenticated = false;
let revision = 0;
let expiryTimer;
let dirty = false;
let drafts = {};
const api = createClient(() => lock('Session expired or credential denied. Unlock to continue.'));
const titles = {overview: ['LIVE OPERATIONS', 'Overview'], timeline: ['CORRELATED EVIDENCE', 'Security timeline'], playground: ['BOUNDED DEMO ACTIONS', 'Playground'], policy: ['VERSIONED CONTROLS', 'Policy studio'], feed: ['DATA-ONLY INDICATORS', 'Threat feed'], approvals: ['EXACT ACTION REVIEW', 'Approvals'], outbox: ['LOCAL DELIVERY EVIDENCE', 'Test outbox'], export: ['BOUNDED SECURITY RECORDS', 'Audit export']};
let currentRoute = 'overview';
function lock(message = 'Console locked. Use your operator credential to continue.') {
  authenticated = false; dirty = false; drafts = {}; revision++; clearTimeout(expiryTimer); api.clear();
  view.replaceChildren(); notice.textContent = ''; $('#session-expiry').textContent = '';
  shell.hidden = true; lockscreen.hidden = false; $('#credential').value = '';
  $('#login-status').textContent = message; $('#credential').focus();
}
function unlock(session) {
  authenticated = true; lockscreen.hidden = true; shell.hidden = false;
  $('#credential').value = ''; $('#login-status').textContent = '';
  $('#session-expiry').textContent = `SESSION UNTIL ${timestamp(session.expires_at)}`;
  clearTimeout(expiryTimer);
  expiryTimer = setTimeout(() => lock('Session expired. Unlock to continue.'), Math.max(0, session.expires_at * 1000 - Date.now()));
  navigate();
}
async function navigate() {
  if (!authenticated) return;
  const next = location.hash.slice(1) || 'overview';
  if (dirty && !window.confirm('Discard the unsaved editor changes?')) {
    history.replaceState(null, '', `#${currentRoute}`); return;
  }
  dirty = false; currentRoute = Object.hasOwn(titles, next) ? next : 'overview';
  const ticket = ++revision;
  notice.textContent = ''; view.replaceChildren(empty('Loading operator state…'));
  view.setAttribute('aria-busy', 'true');
  $('#page-kicker').textContent = titles[currentRoute][0]; $('#page-title').textContent = titles[currentRoute][1];
  document.title = `${titles[currentRoute][1]} — Laya Sec Layer`;
  document.querySelectorAll('nav a').forEach(a => { if (a.hash === `#${currentRoute}`) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  $('#workspace').focus();
  try {
    let node;
    if (currentRoute === 'overview') node = await overview(api);
    else if (currentRoute === 'timeline') node = await timeline(api);
    else {
      const {actionView} = await import('./actions.js');
      node = await actionView(currentRoute, api, value => { if (ticket === revision) dirty = value; }, drafts);
    }
    if (ticket === revision && authenticated) view.replaceChildren(node);
  } catch (error) {
    if (ticket === revision && authenticated) { notice.textContent = error.message; view.replaceChildren(empty('No current data to display. Check the service and refresh.')); }
  } finally { if (ticket === revision) view.removeAttribute('aria-busy'); }
}
$('#login-form').addEventListener('submit', async event => {
  event.preventDefault(); const control = event.submitter;
  if (control.disabled) return;
  control.disabled = true; $('#login-status').textContent = 'Opening operator session…';
  const token = $('#credential').value; $('#credential').value = '';
  try { unlock(await api.login(token)); }
  catch (error) { $('#login-status').textContent = error.message; }
  finally { control.disabled = false; }
});
$('#logout').addEventListener('click', async () => {
  if (dirty && !window.confirm('Discard edits and sign out?')) return;
  const control = $('#logout'); control.disabled = true;
  try { await api.logout(); lock(); }
  catch (error) { notice.textContent = `Sign-out could not be confirmed. ${error.message}`; }
  finally { control.disabled = false; }
});
$('#refresh').addEventListener('click', navigate);
window.addEventListener('hashchange', navigate);
window.addEventListener('beforeunload', event => { if (dirty) { event.preventDefault(); event.returnValue = ''; } });
window.addEventListener('pageshow', event => { if (event.persisted) { lock('Checking session…'); restore(); } });
async function restore() {
  const submit = $('#login-form button'); submit.disabled = true;
  try { unlock(await api.restore()); }
  catch (error) { $('#login-status').textContent = error.status === 401 ? 'Enter your operator credential to continue.' : error.message; }
  finally {submit.disabled = false;}
}
restore();
