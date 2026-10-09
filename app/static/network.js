/* Shared browser request handling; CommonJS export keeps unit tests dependency-free. */
const ChartCourtNetwork = (() => {
  class RequestError extends Error {
    constructor(message, {code = 'request', status = 0, retryAfter = 0} = {}) {
      super(message);
      this.name = 'RequestError';
      this.code = code;
      this.status = status;
      this.retryAfter = retryAfter;
    }
  }

  async function fetchJSON(url, {timeoutMs = 10000, signal, ...options} = {}) {
    const controller = new AbortController();
    let timedOut = false;
    const cancel = () => controller.abort();
    if (signal?.aborted) cancel();
    else signal?.addEventListener('abort', cancel, {once:true});
    const timer = setTimeout(() => { timedOut = true; cancel(); }, timeoutMs);
    try {
      controller.signal.throwIfAborted();
      const response = await fetch(url, {...options, signal:controller.signal});
      let result;
      try { result = await response.json(); }
      catch (error) {
        if (controller.signal.aborted) throw error;
        result = null;
      }
      if (!response.ok) {
        const retrySeconds = Number(response.headers.get('Retry-After'));
        throw new RequestError(typeof result?.detail === 'string' ? result.detail : `The service returned an error (${response.status}). Please retry.`, {
          code:'http', status:response.status,
          retryAfter:Number.isFinite(retrySeconds) ? Math.max(0, Math.min(60, retrySeconds)) : 0,
        });
      }
      if (result === null || typeof result !== 'object') {
        throw new RequestError('The service returned an unreadable response. Please retry.', {code:'response'});
      }
      return result;
    } catch (error) {
      if (controller.signal.aborted) {
        throw new RequestError(timedOut ? 'The request took too long. Please retry or use a smaller image.' : 'Stopped waiting. The server may still finish this inspection.', {code:timedOut ? 'timeout' : 'cancelled'});
      }
      if (error instanceof RequestError) throw error;
      throw new RequestError('Could not connect to ChartCourt. Check that the service is running, then retry.', {code:'network'});
    } finally {
      clearTimeout(timer);
      signal?.removeEventListener('abort', cancel);
    }
  }

  return {fetchJSON, RequestError};
})();
if (typeof module !== 'undefined' && module.exports) module.exports = ChartCourtNetwork;
