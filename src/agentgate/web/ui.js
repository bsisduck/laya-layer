export const text = value => value === null || value === undefined ? 'Unknown' :
  typeof value === 'object' ? JSON.stringify(value) : String(value);
export const pretty = value => JSON.stringify(value, null, 2);
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') node.className = value;
    else if (key.startsWith('on')) node.addEventListener(key.slice(2).toLowerCase(), value);
    else if (['value', 'checked', 'disabled', 'hidden'].includes(key)) node[key] = value;
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) if (child !== null && child !== undefined) node.append(child instanceof Node ? child : document.createTextNode(text(child)));
  return node;
}
export const button = (label, action, kind = 'secondary') => el('button', {type: 'button', class: kind, onclick: action}, label);
export function tag(value) {
  const kind = ['allow', 'deny', 'redact', 'pending', 'ready', 'unavailable', 'measured'].includes(value) ? value : '';
  return el('span', {class: `tag ${kind}`}, text(value).replaceAll('_', ' '));
}
export const empty = message => el('p', {class: 'empty'}, message);
export const panel = (title, ...children) => el('section', {class: 'panel'}, el('div', {class: 'section-head'}, el('h2', {}, title)), ...children);
export function pairs(data) {
  const dl = el('dl', {class: 'kv'});
  for (const [key, value] of Object.entries(data || {})) dl.append(el('dt', {}, key.replaceAll('_', ' ')), el('dd', {}, Array.isArray(value) ? value.map(text).join(' · ') || 'None reported' : text(value)));
  return dl;
}
export function details(title, data, open = false) {
  const node = el('details', {}, el('summary', {}, title), el('pre', {}, pretty(data)));
  node.open = open;
  return node;
}
export function table(headers, rows) {
  return el('div', {class: 'table-wrap', tabindex: '0', role: 'region', 'aria-label': 'Scrollable records'}, el('table', {},
    el('thead', {}, el('tr', {}, headers.map(h => el('th', {scope: 'col'}, h)))),
    el('tbody', {}, rows.map(row => el('tr', {}, row.map(cell => el('td', {}, cell)))))));
}
export function field(label, input, hint) {
  return el('div', {class: 'field'}, el('label', {for: input.id}, label), input, hint ? el('p', {class: 'hint'}, hint) : null);
}
export function status() { return el('p', {class: 'status', role: 'status', 'aria-live': 'polite'}); }
export async function busy(control, output, action) {
  if (control.disabled) return;
  control.disabled = true;
  output.classList.remove('error'); output.textContent = 'Working…';
  try { await action(); }
  catch (error) { output.classList.add('error'); output.textContent = error.message; }
  finally { control.disabled = false; }
}
export function timestamp(value) {
  if (value === null || value === undefined) return 'Unknown';
  const date = new Date(typeof value === 'number' ? value * 1000 : value);
  return Number.isNaN(date.getTime()) ? 'Unknown' : date.toLocaleString();
}
export function parseEditor(value) {
  if (new TextEncoder().encode(value).length > 65536) throw new Error('JSON must be at most 64 KiB.');
  let data;
  try { data = JSON.parse(value); } catch { throw new Error('Invalid JSON. Check punctuation and quoted keys.'); }
  if (!data || Array.isArray(data) || typeof data !== 'object') throw new Error('Enter a JSON object.');
  return data;
}
