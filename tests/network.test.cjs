const {test} = require('node:test');
const assert = require('node:assert/strict');
const {getEventListeners} = require('node:events');
const {fetchJSON, RequestError} = require('../app/static/network.js');

test('successful requests preserve options and release abort listeners', async t => {
  const parent = new AbortController();
  const body = new FormData();
  body.append('file', new Blob(['pixels']), 'chart.png');
  let request;
  t.mock.method(global, 'fetch', async (url, options) => {
    request = {url, options};
    return Response.json({status:'clear'});
  });
  assert.deepEqual(await fetchJSON('/api/analyze', {method:'POST', body, signal:parent.signal}), {status:'clear'});
  assert.equal(request.url, '/api/analyze');
  assert.equal(request.options.body, body);
  assert.equal(request.options.method, 'POST');
  assert.notEqual(request.options.signal, parent.signal);
  assert.equal(parent.signal.aborted, false);
  assert.equal(getEventListeners(parent.signal, 'abort').length, 0);
});

test('HTTP errors retain the safe server message and retry delay', async t => {
  t.mock.method(global, 'fetch', async () => Response.json({detail:'Two inspections are already running.'}, {status:429, headers:{'Retry-After':'2'}}));
  await assert.rejects(fetchJSON('/api/analyze'), error => {
    assert.ok(error instanceof RequestError);
    assert.equal(error.code, 'http');
    assert.equal(error.status, 429);
    assert.equal(error.retryAfter, 2);
    assert.equal(error.message, 'Two inspections are already running.');
    return true;
  });
});

for (const [header, expected] of [['3600',60], ['-10',0], ['invalid',0], ['Infinity',0], ['0.5',.5]]) {
  test(`retry delay is bounded for ${header}`, async t => {
    t.mock.method(global, 'fetch', async () => Response.json({}, {status:503, headers:{'Retry-After':header}}));
    await assert.rejects(fetchJSON('/api/analyze'), error => error.retryAfter === expected);
  });
}

test('non-JSON proxy errors do not expose HTML or confuse response handling', async t => {
  t.mock.method(global, 'fetch', async () => new Response('<html>private proxy diagnostics</html>', {status:502}));
  await assert.rejects(fetchJSON('/api/health'), {code:'http', status:502, message:'The service returned an error (502). Please retry.'});
});

test('structured validation details use a readable fallback', async t => {
  t.mock.method(global, 'fetch', async () => Response.json({detail:[{input:'private data'}]}, {status:422}));
  await assert.rejects(fetchJSON('/api/analyze'), {message:'The service returned an error (422). Please retry.'});
});

for (const body of ['not JSON', 'null', '"unexpected string"', '123']) {
  test(`invalid success body is rejected: ${body}`, async t => {
    t.mock.method(global, 'fetch', async () => new Response(body));
    await assert.rejects(fetchJSON('/api/health'), {code:'response'});
  });
}

test('network failures have an actionable message without raw exception details', async t => {
  t.mock.method(global, 'fetch', async () => { throw new TypeError('private connection diagnostics'); });
  await assert.rejects(fetchJSON('/api/health'), {code:'network', message:'Could not connect to ChartCourt. Check that the service is running, then retry.'});
});

function waitForAbort(signal) {
  return new Promise((resolve, reject) => {
    signal.addEventListener('abort', () => reject(new DOMException('Aborted', 'AbortError')), {once:true});
  });
}

test('request deadline aborts a stalled connection', async t => {
  let requestSignal;
  t.mock.method(global, 'fetch', (url, {signal}) => { requestSignal = signal; return waitForAbort(signal); });
  await assert.rejects(fetchJSON('/api/health', {timeoutMs:5}), {code:'timeout'});
  assert.equal(requestSignal.aborted, true);
});

test('request deadline also covers reading the JSON body', async t => {
  t.mock.method(global, 'fetch', async (url, {signal}) => ({ok:true, json:() => waitForAbort(signal)}));
  await assert.rejects(fetchJSON('/api/health', {timeoutMs:5}), {code:'timeout'});
});

test('user cancellation differs from timeout and removes the listener', async t => {
  t.mock.method(global, 'fetch', (url, {signal}) => waitForAbort(signal));
  const parent = new AbortController();
  const request = fetchJSON('/api/analyze', {signal:parent.signal});
  parent.abort();
  await assert.rejects(request, {code:'cancelled', message:'Stopped waiting. The server may still finish this inspection.'});
  assert.equal(getEventListeners(parent.signal, 'abort').length, 0);
});

test('pre-cancelled requests never send data', async t => {
  const mocked = t.mock.method(global, 'fetch', async () => Response.json({}));
  const parent = new AbortController();
  parent.abort();
  await assert.rejects(fetchJSON('/api/analyze', {signal:parent.signal}), {code:'cancelled'});
  assert.equal(mocked.mock.callCount(), 0);
});

test('failed uploads can be explicitly retried with the same FormData', async t => {
  const body = new FormData();
  body.append('file', new Blob(['pixels']), 'chart.png');
  let count = 0;
  t.mock.method(global, 'fetch', async (url, options) => {
    assert.equal(await options.body.get('file').text(), 'pixels');
    if (++count === 1) throw new TypeError('offline');
    return Response.json({status:'clear'});
  });
  await assert.rejects(fetchJSON('/api/analyze', {method:'POST', body}), {code:'network'});
  assert.equal(count, 1, 'failed requests are not automatically retried');
  assert.deepEqual(await fetchJSON('/api/analyze', {method:'POST', body}), {status:'clear'});
});
