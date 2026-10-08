const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value).replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = (name) => `<svg aria-hidden="true"><use href="#i-${name}"/></svg>`;
let current = null;
let pending = false;
let selectedSample = 'truncated';
let objectURL = null;
let toastTimer;

function notify(message) {
  $('#toast').textContent = message;
  $('#toast').hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 3000);
}

function download(content, name, type) {
  const url = URL.createObjectURL(new Blob([content], {type}));
  const a = document.createElement('a');
  a.href = url; a.download = name; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function setBusy(value) {
  pending = value;
  $('#busy').hidden = !value;
  $('#workspace').setAttribute('aria-busy', String(value));
  $('#export-report').disabled = value || !current;
  $('#export-csv').disabled = value || !current?.bars.length;
  $('#export-svg').disabled = value || !current?.reconstruction;
  document.querySelectorAll('.sample, #upload-sidebar, #upload-main').forEach(el => { el.disabled = value; });
  if (value) {
    $('#verdict').className = 'verdict pending';
    $('#verdict').innerHTML = `<div class="verdict-icon">${icon('scan')}</div><h2>Looking at the evidence.</h2><p>The inspection is running on the image.</p>`;
    $('#findings').innerHTML = '';
    $('#measurement-summary').innerHTML = '';
    $('#finding-count').textContent = '—';
    $('#trace-meta').textContent = 'Inspection in progress';
    $('#trace-list').innerHTML = '<div class="trace-empty">Reading the image and choosing the next inspection step…</div>';
  }
}

function selectView(view) {
  document.querySelectorAll('[data-view]').forEach(button => button.setAttribute('aria-selected', String(button.dataset.view === view)));
  document.querySelectorAll('.view').forEach(el => { el.hidden = el.id !== `view-${view}`; });
}

async function inspect(url, options, name, example = false) {
  if (pending) return;
  current = null;
  $('#error').hidden = true;
  $('#case-name').textContent = name;
  $('#source-tag').textContent = example ? 'EXAMPLE' : 'UPLOAD';
  setBusy(true);
  selectView('comparison');
  $('#comparison-metrics').innerHTML = '';
  $('#evidence-image').innerHTML = '';
  $('#data-table').innerHTML = '<div class="trace-empty">No numeric estimates are available yet.</div>';
  $('#reconstruction').innerHTML = `<div class="placeholder">${icon('chart')}<p>Recovering the chart’s values…</p></div>`;
  $('#original-note').textContent = 'Inspecting the visible scale and bar geometry.';
  $('#reconstruction-note').textContent = 'Same recovered values. A zero baseline.';
  try {
    const response = await fetch(url, {method:'POST', ...options});
    const result = await response.json();
    if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : 'The inspection could not complete.');
    current = result;
    render(result);
  } catch (error) {
    $('#error').textContent = error.message || 'Could not connect to the inspection service.';
    $('#error').hidden = false;
    $('#verdict').className = 'verdict review';
    $('#verdict').innerHTML = `<div class="verdict-icon">${icon('info')}</div><h2>Inspection interrupted.</h2><p>Try another image or retry this example.</p>`;
    $('#reconstruction').innerHTML = `<div class="placeholder">${icon('info')}<p>No reconstruction is available.</p></div>`;
    $('#trace-meta').textContent = 'Inspection did not complete';
    $('#trace-list').innerHTML = '<div class="trace-empty">No result was produced.</div>';
  } finally { setBusy(false); }
}

function render(r) {
  $('#original').src = r.image;
  $('#original').alt = `Uploaded chart: ${r.filename}`;
  const warningCount = r.findings.filter(f => f.severity === 'warning').length;
  $('#finding-count').textContent = r.status === 'flagged' ? String(warningCount).padStart(2,'0') : r.status === 'clear' ? '00' : '—';
  const title = r.status === 'flagged' ? 'There’s more to this story.' : r.status === 'clear' ? 'The axis checks out.' : 'Some context is missing.';
  const symbol = r.status === 'flagged' ? 'alert' : r.status === 'clear' ? 'check' : 'info';
  $('#verdict').className = `verdict ${r.status}`;
  $('#verdict').innerHTML = `<div class="verdict-icon">${icon(symbol)}</div><h2>${title}</h2><p>${esc(r.summary)}</p>`;
  $('#findings').innerHTML = r.findings.map(f => `<div class="finding ${esc(f.severity)}"><div class="finding-heading">${icon(f.severity === 'pass' ? 'check' : f.severity === 'review' ? 'info' : 'alert')}<strong>${esc(f.title)}</strong></div><p>${esc(f.detail)}</p></div>`).join('');
  $('#original-note').textContent = r.axis ? `Visible baseline ≈ ${r.axis.baseline.toFixed(1)} · ${r.axis.inverted ? 'Values increase downward' : 'Values increase upward'}` : 'The visible scale could not be calibrated reliably.';
  if (r.reconstruction) {
    // SVG is generated by our server from numeric geometry and escaped OCR labels.
    $('#reconstruction').innerHTML = r.reconstruction;
    $('#reconstruction-note').textContent = 'Estimated values preserved · Zero baseline · Upward axis';
  } else {
    $('#reconstruction').innerHTML = `<div class="placeholder">${icon('eye')}<p>We need a readable scale<br>before we can redraw this chart.</p></div>`;
    $('#reconstruction-note').textContent = 'Reconstruction withheld. Try a clearer, supported chart.';
  }
  if (r.comparison) {
    const c = r.comparison;
    $('#comparison-metrics').innerHTML = `<div class="metric-strip"><div><span class="metric-label">What the bar lengths suggest</span><strong class="metric-warm">${c.apparent_ratio.toFixed(1)}×</strong><span class="metric-detail">longest / shortest visible bar</span></div>${icon('arrow')}<div><span class="metric-label">What the recovered values show</span><strong class="metric-green">${c.value_ratio.toFixed(3)}×</strong><span class="metric-detail">≈ ${c.actual_change_pct.toFixed(1)}% increase in value</span></div></div><p class="metric-footnote">Comparing ${esc(c.first_label)} and ${esc(c.second_label)}. Ratios are calculated from measured pixels and the recovered scale.</p>`;
  } else {
    $('#comparison-metrics').innerHTML = `<div class="neutral-summary">${icon(r.status === 'clear' ? 'check' : 'info')}<span>${r.status === 'clear' ? 'The recovered baseline is zero. Bar-length proportions agree with the recovered values.' : r.status === 'flagged' ? 'The reconstructed view restores the conventional axis direction while preserving the recovered values.' : 'A missing scale is meaningful evidence. The inspection stops instead of inventing values.'}</span></div>`;
  }
  $('#measurement-summary').innerHTML = `<div class="measurement-summary"><div class="measure-row"><span>Values recovered</span><strong>${r.bars.length}</strong></div><div class="measure-row"><span>Axis ticks read</span><strong>${r.axis?.ticks.length ?? '—'}</strong></div><div class="measure-row"><span>Axis-fit error</span><strong>${r.axis ? (r.axis.fit_error * 100).toFixed(2) + '%' : '—'}</strong></div><div class="measure-row"><span>Analysis time</span><strong>${(r.processing_ms/1000).toFixed(2)}s</strong></div></div>`;
  $('#evidence-image').innerHTML = `<img src="${r.image}" alt="Chart with detected bars and numeric axis ticks highlighted"><svg viewBox="0 0 ${r.width} ${r.height}" aria-label="Detected evidence regions">${r.overlays.map(item => `<rect tabindex="0" role="img" class="region ${esc(item.kind)}" x="${item.box[0]}" y="${item.box[1]}" width="${item.box[2]}" height="${item.box[3]}" aria-label="${esc(item.label)}"><title>${esc(item.label)}</title></rect>`).join('')}</svg>`;
  $('#data-table').innerHTML = r.bars.length ? `<table><thead><tr><th>Category</th><th>Estimated value</th><th>Visible length</th></tr></thead><tbody>${r.bars.map(b => `<tr><td><span class="swatch" style="background:${b.color}"></span>${esc(b.label)}</td><td class="number">≈ ${b.value?.toFixed(2) ?? '—'}</td><td class="number">${b.pixel_length ?? b.box[3]} px</td></tr>`).join('')}</tbody></table>` : '<div class="trace-empty">No reliable numeric values were recovered.</div>';
  $('#trace-meta').textContent = `${r.trace.length} steps · ${(r.processing_ms/1000).toFixed(2)}s · OpenCV ${r.engine.opencv}`;
  $('#trace-list').innerHTML = r.trace.map(t => `<details class="trace-row ${t.tool === 'inspection_policy' ? 'branch' : ''}"><summary><span class="trace-num">${String(t.step).padStart(2,'0')}</span><span class="trace-action">${esc(t.action)}</span><span class="trace-tool">${esc(t.tool)}</span><span class="trace-time" title="Time since the preceding step">${t.duration_ms}ms</span><span class="trace-chevron">›</span></summary><div class="trace-detail"><p>${esc(t.detail)}</p>${Object.keys(t.metrics).length ? `<pre>${esc(JSON.stringify(t.metrics, null, 2))}</pre>` : ''}</div></details>`).join('');
}

async function openSample(sample) {
  if (pending) return;
  selectedSample = sample.id;
  document.querySelectorAll('.sample').forEach(b => { b.classList.toggle('active', b.dataset.sample === sample.id); b.setAttribute('aria-pressed', String(b.dataset.sample === sample.id)); });
  $('#original').src = `/static/samples/${sample.id}.png`;
  await inspect(`/api/samples/${sample.id}/analyze`, {}, sample.name, true);
}

async function upload(file) {
  if (!file || pending) return;
  if (!['image/png','image/jpeg','image/webp'].includes(file.type)) { notify('Choose a PNG, JPEG, or WebP chart.'); return; }
  if (file.size > 8*1024*1024) { notify('Choose an image under 8 MB.'); return; }
  selectedSample = null;
  document.querySelectorAll('.sample').forEach(b => { b.classList.remove('active'); b.setAttribute('aria-pressed','false'); });
  if (objectURL) URL.revokeObjectURL(objectURL);
  objectURL = URL.createObjectURL(file);
  $('#original').src = objectURL;
  const form = new FormData(); form.append('file', file);
  await inspect('/api/analyze', {body:form}, file.name || 'pasted-chart.png');
}

document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => selectView(button.dataset.view)));
$('.tabs').addEventListener('keydown', event => {
  if (!['ArrowLeft','ArrowRight'].includes(event.key)) return;
  const tabs = [...document.querySelectorAll('[data-view]')];
  const i = tabs.indexOf(document.activeElement);
  if (i < 0) return;
  event.preventDefault();
  const next = tabs[(i + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
  next.focus(); selectView(next.dataset.view);
});
$('#upload-main').onclick = $('#upload-sidebar').onclick = () => $('#file-input').click();
$('#file-input').onchange = event => { upload(event.target.files[0]); event.target.value = ''; };
$('#export-report').onclick = () => {
  if (!current) return;
  const {image, reconstruction, ...report} = current;
  download(JSON.stringify(report, null, 2), 'chartcourt-inspection.json', 'application/json');
};
$('#export-svg').onclick = () => { if (current?.reconstruction) download(current.reconstruction, 'chartcourt-reconstruction.svg', 'image/svg+xml'); };
$('#export-csv').onclick = () => {
  if (!current) return;
  // Prefix text cells that spreadsheet software could interpret as formulas.
  const cell = value => { let s = String(value); if (/^[=+@-]/.test(s)) s = "'" + s; return '"' + s.replace(/"/g,'""') + '"'; };
  download('category,estimated_value,pixel_length\n' + current.bars.map(b => [cell(b.label), b.value ?? '', b.pixel_length ?? ''].join(',')).join('\n'), 'chartcourt-estimates.csv', 'text/csv');
};
$('#methodology').onclick = () => $('#method-dialog').showModal();
$('.close-dialog').onclick = () => $('#method-dialog').close();
$('#method-dialog').addEventListener('click', event => { if (event.target === $('#method-dialog')) { const r = event.target.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) event.target.close(); } });
let dragDepth = 0;
document.addEventListener('dragenter', event => { if ([...event.dataTransfer.types].includes('Files')) { event.preventDefault(); dragDepth++; $('#drop-overlay').hidden = false; } });
document.addEventListener('dragover', event => event.preventDefault());
document.addEventListener('dragleave', () => { dragDepth--; if (dragDepth <= 0) $('#drop-overlay').hidden = true; });
document.addEventListener('drop', event => { event.preventDefault(); dragDepth=0; $('#drop-overlay').hidden=true; upload(event.dataTransfer.files[0]); });
document.addEventListener('paste', event => { const item = [...(event.clipboardData?.items || [])].find(i => i.type.startsWith('image/')); if (item) { event.preventDefault(); upload(item.getAsFile()); } });

async function init() {
  const results = await Promise.allSettled([fetch('/api/health').then(r => r.json()), fetch('/api/samples').then(r => r.json())]);
  const health = results[0].status === 'fulfilled' ? results[0].value : null;
  const deploymentLabel = {local:'LOCAL',container:'CONTAINER',aws:'AWS'}[health?.deployment] || 'CUSTOM';
  $('#engine-text').textContent = health ? `OpenCV ${health.opencv.split('.').slice(0,2).join('.')} · ${deploymentLabel}${health.ocr_available ? '' : ' · OCR MISSING'}` : 'Engine offline';
  if (results[1].status !== 'fulfilled') { setBusy(false); $('#error').textContent='Could not load examples. Check that the Python service is running.'; $('#error').hidden=false; return; }
  const samples = results[1].value;
  $('#sample-list').innerHTML = samples.map((sample, i) => `<button class="sample" data-sample="${esc(sample.id)}" aria-pressed="false" title="${esc(sample.subtitle)}"><img class="sample-thumbnail" src="/static/samples/${esc(sample.id)}.png" alt=""><span class="sample-copy"><strong>${esc(sample.name)}</strong><span>CASE ${String(i+1).padStart(2,'0')} · SAMPLE CHART</span></span></button>`).join('');
  document.querySelectorAll('.sample').forEach(button => button.onclick = () => openSample(samples.find(s => s.id === button.dataset.sample)));
  setBusy(false);
  await openSample(samples[0]);
}
init();
