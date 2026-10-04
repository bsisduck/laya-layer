// Coalesce concurrent expiry signals. One restore and, only on 401, one bootstrap.
// This helper receives no action callback and cannot replay a failed mutation.
export function createLocalRecovery(api) {
  let pending = null;
  return function recover() {
    if (pending) return pending;
    pending = (async () => {
      try { return await api.restore(); }
      catch (error) {
        if (error.status !== 401) throw error;
        return await api.bootstrap();
      }
    })().finally(() => { pending = null; });
    return pending;
  };
}
