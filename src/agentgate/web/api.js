// Cookies carry authentication. Only the CSRF nonce lives in this module's memory.
export class ApiError extends Error {
  constructor(status, message) { super(message); this.status = status; }
}
export function createClient(onUnauthorized = () => {}, transport = globalThis.fetch) {
  let csrf = null;
  let generation = 0;
  const pending = new Set();
  function clear() {
    csrf = null;
    generation++;
    for (const controller of pending) controller.abort();
    pending.clear();
  }
  async function request(path, { method = 'GET', body, decision = false, download = false } = {}) {
    if (!path.startsWith('/admin/') || path.includes('#') || path.includes('\\')) {
      throw new ApiError(0, 'Invalid operator endpoint.');
    }
    const write = method !== 'GET';
    if (write && path !== '/admin/session' && !csrf) throw new ApiError(401, 'Unlock the console first.');
    const epoch = generation;
    const controller = new AbortController();
    pending.add(controller);
    const timeout = setTimeout(() => controller.abort(), 30000);
    try {
      const headers = { Accept: download ? 'application/x-ndjson' : 'application/json' };
      if (write) {
        headers['Content-Type'] = 'application/json';
        if (csrf) headers['X-CSRF-Token'] = csrf;
      }
      const response = await transport(path, {
        method, headers, credentials: 'same-origin', cache: 'no-store', redirect: 'error',
        body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal,
      });
      if (generation !== epoch) throw new ApiError(0, 'Session changed.');
      if (response.ok && download) {
        const blob = await response.blob();
        if (generation !== epoch) throw new ApiError(0, 'Session changed.');
        return { blob, cursor: response.headers.get('X-AgentGate-Cursor') };
      }
      let data;
      try { data = await response.json(); }
      catch { throw new ApiError(response.status, 'The service returned an unreadable response.'); }
      if (generation !== epoch) throw new ApiError(0, 'Session changed.');
      if (response.status === 401) {
        // An expired scoped playground credential is an action denial. The
        // operator session remains valid and can explicitly renew that scope.
        if (decision && data?.decision === 'deny' && data?.executed === false &&
            Array.isArray(data.reason_codes) && typeof data.action_id === 'string') return data;
        clear(); onUnauthorized();
        throw new ApiError(401, 'Session expired or credential denied. Unlock to continue.');
      }
      if (!response.ok) {
        // Enforcement denial is evidence, not a transport success or an executed action.
        if (decision && response.status !== 503 && typeof data?.decision === 'string' && typeof data?.executed === 'boolean') return data;
        const detail = typeof data?.detail === 'string' ? data.detail : 'Request rejected.';
        const prefix = response.status === 503 ? 'Service unavailable. ' :
          response.status === 404 || response.status === 501 ? 'This capability is unavailable in this installation. ' :
          response.status === 409 ? 'Version conflict. Reload current state before retrying. ' : '';
        throw new ApiError(response.status, prefix + detail);
      }
      return data;
    } catch (error) {
      if (error instanceof ApiError) throw error;
      throw new ApiError(0, write ? 'Connection interrupted. Outcome is unknown; inspect the timeline before retrying.' : 'Cannot reach the operator service. Check the gateway and try again.');
    } finally { clearTimeout(timeout); pending.delete(controller); }
  }
  function acceptSession(data) {
    if (data?.authenticated !== true || typeof data.csrf_token !== 'string' || !Number.isFinite(data.expires_at)) {
      throw new ApiError(0, 'Invalid session response.');
    }
    csrf = data.csrf_token;
    return data;
  }
  return {
    request, clear,
    async restore() { return acceptSession(await request('/admin/session')); },
    async login(token) { return acceptSession(await request('/admin/session', {method: 'POST', body: {token}})); },
    async logout() { await request('/admin/session', {method: 'DELETE'}); clear(); },
  };
}
