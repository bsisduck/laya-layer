import {createClient} from './api.js';
import {createLocalRecovery} from './session.js';
import {hrView, clearHR} from './hr.js';
const hrMemory = {};
import {el, empty, timestamp} from './ui.js';
import {overview, overviewSection, timeline} from './observe.js';
const $ = selector => document.querySelector(selector);
const lockscreen = $('#lockscreen');
const serviceScreen = $('#service-screen');
let mode = null;
let recoveryRunning = false;
const shell = $('#console');
const view = $('#view');
const notice = $('#notice');
let authenticated = false;
let revision = 0;
let expiryTimer;
let dirty = false;
let drafts = {};
const api = createClient(expired);
const recoverLocal = createLocalRecovery(api);
const titles = {hr: ['GOVERNED EMPLOYEE WORKFLOW', 'HR workspace'], overview: ['LIVE OPERATIONS', 'Overview'], timeline: ['CORRELATED EVIDENCE', 'Security timeline'], catalog: ['REVIEWED TOOL AUTHORITY', 'Catalog'], playground: ['BOUNDED DEMO ACTIONS', 'Playground'], policy: ['VERSIONED CONTROLS', 'Policy studio'], feed: ['DATA-ONLY INDICATORS', 'Threat feed'], approvals: ['EXACT ACTION REVIEW', 'Approvals'], outbox: ['LOCAL DELIVERY EVIDENCE', 'Test outbox'], export: ['BOUNDED SECURITY RECORDS', 'Audit export']};
let currentRoute = 'overview';
const rail = $('#navigation-rail');
const menuButton = $('#open-menu');
const backdrop = $('#nav-backdrop');
const mobile = matchMedia('(max-width: 760px)');
let menuOpen = false;
function closeMenu(restoreFocus = true) {
  menuOpen = false; rail.classList.remove('menu-open');
  backdrop.hidden = true; menuButton.setAttribute('aria-expanded', 'false');
  rail.hidden = mobile.matches;
  rail.removeAttribute('role'); rail.removeAttribute('aria-modal'); rail.removeAttribute('aria-label');
  document.body.classList.remove('menu-open'); $('.main-shell').inert = false;
  if (restoreFocus && mobile.matches) menuButton.focus();
}
function openMenu() {
  menuOpen = true; rail.hidden = false; rail.classList.add('menu-open');
  rail.setAttribute('role', 'dialog'); rail.setAttribute('aria-modal', 'true'); rail.setAttribute('aria-label', 'Navigation menu');
  backdrop.hidden = false; menuButton.setAttribute('aria-expanded', 'true');
  document.body.classList.add('menu-open'); $('.main-shell').inert = true; $('#close-menu').focus();
}
menuButton.addEventListener('click', openMenu);
$('#close-menu').addEventListener('click', () => closeMenu());
backdrop.addEventListener('click', () => closeMenu());
mobile.addEventListener('change', () => {
  // A queued breakpoint event must not close a drawer opened at the new mobile width.
  if (mobile.matches && menuOpen) return;
  const wasInMenu = rail.contains(document.activeElement);
  closeMenu(false);
  if (wasInMenu && mobile.matches) $('#workspace').focus();
});
rail.addEventListener('click', event => { if (event.target.closest('a') && menuOpen) { closeMenu(false); $('#workspace').focus(); } });
document.addEventListener('keydown', event => {
  if (!menuOpen) return;
  if (event.key === 'Escape') { event.preventDefault(); closeMenu(); }
  else if (event.key === 'Tab') {
    const items = [...rail.querySelectorAll('a, button:not([disabled])')].filter(node => node.getClientRects().length);
    const first = items[0], last = items.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  }
});
closeMenu(false);
function lock(message = 'Console locked. Use your operator credential to continue.') {
  closeMenu(false);
  authenticated = false; dirty = false; drafts = {}; clearHR(hrMemory); revision++; clearTimeout(expiryTimer); api.clear();
  view.replaceChildren(); notice.textContent = ''; $('#session-expiry').textContent = '';
  serviceScreen.hidden = true; shell.hidden = true; lockscreen.hidden = false; $('#credential').value = '';
  $('#login-status').textContent = message; $('#credential').focus();
}
function unlock(session) {
  authenticated = true; serviceScreen.hidden = true; lockscreen.hidden = true; shell.hidden = false;
  $('#credential').value = ''; $('#login-status').textContent = '';
  $('#session-expiry').textContent = `SESSION UNTIL ${timestamp(session.expires_at)}`;
  clearTimeout(expiryTimer);
  expiryTimer = setTimeout(expired, Math.max(0, session.expires_at * 1000 - Date.now()));
  navigate();
}
async function navigate() {
  if (!authenticated) return;
  const next = location.hash.slice(1).split('?')[0] || 'overview';
  if (dirty && !window.confirm('Discard the unsaved editor changes?')) {
    history.replaceState(null, '', `#${currentRoute}`); $('#workspace').focus(); return;
  }
  closeMenu(false);
  dirty = false; currentRoute = Object.hasOwn(titles, next) ? next : 'overview';
  const ticket = ++revision;
  notice.textContent = ''; view.replaceChildren(empty('Loading operator state…'));
  view.setAttribute('aria-busy', 'true');
  $('#page-kicker').textContent = titles[currentRoute][0]; $('#page-title').textContent = titles[currentRoute][1];
  document.title = `${titles[currentRoute][1]} — Laya Sec Layer`;
  const section = overviewSection(location.hash);
  const activeHash = currentRoute === 'overview' && section !== 'all' ? `#overview?section=${section}` : `#${currentRoute}`;
  document.querySelectorAll('nav a').forEach(a => { if (a.hash === activeHash) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
  $('#workspace').focus();
  try {
    let node;
    if (currentRoute === 'hr') node = await hrView(api, hrMemory);
    else if (currentRoute === 'overview') node = await overview(api);
    else if (currentRoute === 'timeline') node = await timeline(api);
    else if (currentRoute === 'catalog') {
      const {catalogView} = await import('./catalog.js');
      node = await catalogView(api);
    }
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
function expired() {
  if (mode === 'local') {
    if (!recoveryRunning) restoreLocal('Session restored. Review the current state and deliberately retry any expired action.');
  } else lock('Session expired or credential denied. Unlock to continue.');
}
function serviceState(message, retry = false) {
  closeMenu(false);
  authenticated = false; dirty = false; drafts = {}; clearHR(hrMemory); revision++; clearTimeout(expiryTimer); api.clear();
  view.replaceChildren(); notice.textContent = ''; $('#session-expiry').textContent = '';
  shell.hidden = true; lockscreen.hidden = true; serviceScreen.hidden = false;
  $('#credential').value = '';
  $('#service-status').textContent = message; $('#retry-session').hidden = !retry;
  $('#retry-session').disabled = !retry;
  if (retry) $('#retry-session').focus();
}
async function restoreLocal(message = '') {
  if (recoveryRunning) return;
  recoveryRunning = true;
  serviceState('Opening a bounded local session…');
  try {
    const session = await recoverLocal();
    unlock(session);
    if (message) notice.textContent = message;
  } catch {
    // Fixed diagnostic: server/transport details never reach the startup screen.
    serviceState('Cannot open the local console. Check the gateway with ./laya status, then retry the connection or reload this page. No action has been retried.', true);
  } finally { recoveryRunning = false; }
}
async function restoreCredential() {
  lock('Checking session…');
  const submit = $('#login-form button'); submit.disabled = true;
  try { unlock(await api.restore()); }
  catch (error) { $('#login-status').textContent = error.status === 401 ? 'Enter your operator credential to continue.' : error.message; }
  finally {submit.disabled = false;}
}
async function startup() {
  if (recoveryRunning) return;
  serviceState('Checking the operator service…');
  try {
    mode = (await api.config()).mode;
    $('#logout').hidden = mode === 'local';
    $('#console-mode').textContent = mode === 'local' ? 'Local console / trusted computer' : 'OPERATOR WORKSPACE';
    $('#topbar-mode').textContent = mode === 'local' ? 'Local console / trusted computer' : 'ENFORCEMENT CONTROL ROOM';
    $('#service-mode').textContent = mode === 'local' ? 'Local console / trusted computer' : 'OPERATOR WORKSPACE';
    if (mode === 'local') await restoreLocal();
    else await restoreCredential();
  } catch {
    serviceState('Cannot reach the operator service. Check the gateway with ./laya status, then retry the connection or reload this page.', true);
  }
}
$('#retry-session').addEventListener('click', () => mode === 'local' ? restoreLocal() : startup());
window.addEventListener('pageshow', event => { if (event.persisted) startup(); });
startup();
