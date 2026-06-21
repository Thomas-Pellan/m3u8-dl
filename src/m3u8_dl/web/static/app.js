const frm          = document.getElementById('frm');
const btn          = document.getElementById('btn');
const msg          = document.getElementById('msg');
const urlInput     = document.getElementById('url-input');
const outputName   = document.getElementById('output-name');
const nameHints    = document.getElementById('name-hints');
const nameList     = document.getElementById('name-list');
const stepUrl      = document.getElementById('step-url');
const stepConfig   = document.getElementById('step-config');
const fetchBtn     = document.getElementById('fetch-btn');
const skipBtn      = document.getElementById('skip-btn');
const changeUrlBtn = document.getElementById('change-url-btn');
const clearUrlBtn  = document.getElementById('clear-url-btn');
const urlDisplay   = document.getElementById('url-display');
const fetchMsg     = document.getElementById('fetch-msg');
const TPL_JOB      = document.getElementById('tpl-job-row');
const TPL_SCHED    = document.getElementById('tpl-sched-row');
const TPL_CHIP     = document.getElementById('tpl-hint-chip');

// ── step navigation ───────────────────────────────────────────────────────────

function goToStep1() {
  stepConfig.hidden = false; // briefly un-hide so frm.reset() clears its inputs
  frm.reset();
  stepUrl.hidden    = false;
  stepConfig.hidden = true;
  clearHints();
  fetchMsg.textContent = '';
}

function goToStep2(candidates) {
  urlDisplay.textContent = urlInput.value.trim();
  clearHints();

  if (candidates?.length) {
    candidates.forEach(c => {
      const opt = document.createElement('option');
      opt.value = c;
      nameList.appendChild(opt);
    });
    outputName.value = candidates[0];
    candidates.forEach(c => nameHints.appendChild(renderChip(c, c === outputName.value)));
  }

  stepUrl.hidden    = true;
  stepConfig.hidden = false;
  outputName.focus();
}

// ── fetch names ───────────────────────────────────────────────────────────────

fetchBtn.addEventListener('click', async () => {
  if (!urlInput.checkValidity()) { urlInput.reportValidity(); return; }

  fetchBtn.disabled    = true;
  fetchBtn.textContent = 'Fetching…';
  fetchMsg.style.color = '#555';
  fetchMsg.textContent = 'Loading page and scraping title…';

  try {
    const r = await fetch('/suggest-names?' + new URLSearchParams({url: urlInput.value.trim()}));
    const j = await r.json();
    goToStep2(j.candidates);
  } catch (err) {
    fetchMsg.style.color = '#ff5555';
    fetchMsg.textContent  = 'Error: ' + err.message;
  } finally {
    fetchBtn.disabled    = false;
    fetchBtn.textContent = 'Fetch names →';
  }
});

skipBtn.addEventListener('click', () => {
  if (!urlInput.checkValidity()) { urlInput.reportValidity(); return; }
  goToStep2([]);
});

changeUrlBtn.addEventListener('click', goToStep1);
clearUrlBtn.addEventListener('click', goToStep1);

// ── hint chips ────────────────────────────────────────────────────────────────

function clearHints() {
  nameHints.innerHTML = '';
  nameList.innerHTML  = '';
}

function renderChip(name, active) {
  const chip = TPL_CHIP.content.firstElementChild.cloneNode(true);
  chip.textContent  = name;
  chip.dataset.name = name;
  if (active) chip.classList.add('hint-active');
  chip.addEventListener('click', () => {
    outputName.value = name;
    nameHints.querySelectorAll('.hint-chip').forEach(b => b.classList.remove('hint-active'));
    chip.classList.add('hint-active');
  });
  return chip;
}

// ── form submit ───────────────────────────────────────────────────────────────

frm.addEventListener('submit', async e => {
  e.preventDefault();
  btn.disabled = true;
  msg.style.color = '#555';
  msg.textContent = 'Submitting…';
  const isScheduled = !!document.getElementById('scheduled-at').value;
  try {
    const r = await fetch('/capture', {method: 'POST', body: new FormData(frm)});
    const j = await r.json();
    if (r.status === 429) throw new Error(j.detail || 'Scheduled job limit reached (max 10)');
    if (!r.ok) throw new Error(j.detail || r.statusText);
    msg.style.color = '#00d7af';
    msg.textContent = isScheduled ? 'Job ' + j.job_id + ' scheduled.' : 'Job ' + j.job_id + ' queued.';
    setTimeout(goToStep1, 1200);
  } catch (err) {
    msg.style.color = '#ff5555';
    msg.textContent = 'Error: ' + err.message;
  } finally {
    btn.disabled = false;
  }
});

// ── jobs table ────────────────────────────────────────────────────────────────

const LOG_COLORS = [
  [/error|failed/i,                                    '#ff5555'],
  [/rate.limited|warning|retry/i,                      '#ffaa00'],
  [/downloading\.\.\.|segment.*\(\d+%\)/i,             '#7ab8ff'],
  [/captured\.|segments captured|complete/i,           '#00d7af'],
  [/playlist|intercepted|variant|ready/i,              '#00cc66'],
  [/waiting|auto mode|direct mode|intercept mode/i,    '#666'],
];

function makeLogLine(text) {
  const span = document.createElement('span');
  span.textContent = text;
  const match = LOG_COLORS.find(([re]) => re.test(text));
  span.style.color = match ? match[1] : '#484848';
  return span;
}

const BADGE_CLASS = {pending: 'p', running: 'r', done: 'd', error: 'e'};

function renderJob(j) {
  const frag = TPL_JOB.content.cloneNode(true);
  const q    = sel => frag.querySelector(sel);

  q('.c-id').textContent       = j.id;
  q('.c-url').textContent      = j.url;
  q('.c-url').title            = j.url;
  q('.c-name').textContent     = j.output_name || '';
  q('.c-time').textContent     = (j.started_at || '').replace('T', ' ');

  const badge = q('.badge');
  badge.classList.add(BADGE_CLASS[j.status] || 'p');
  badge.textContent = j.status;

  const pct = q('.pct');
  if (j.progress != null && j.status === 'running') pct.textContent = j.progress + '%';
  else pct.remove();

  const err = q('.err');
  if (j.error) err.textContent = j.error;
  else err.remove();

  const actions = q('.job-actions');
  if (j.status === 'error') {
    actions.querySelector('.retry-btn').dataset.id = j.id;
    actions.querySelector('.clear-btn').dataset.id = j.id;
  } else {
    actions.remove();
  }

  const out = q('.out');
  if (j.output) out.textContent = '✓ ' + j.output;
  else out.remove();

  const logs = q('.logs');
  if (j.logs?.length) j.logs.forEach(line => logs.appendChild(makeLogLine(line)));
  else logs.remove();

  return frag;
}

function renderScheduledJob(j) {
  const frag = TPL_SCHED.content.cloneNode(true);
  const tr   = frag.querySelector('tr');
  const q    = sel => frag.querySelector(sel);

  tr.dataset.id            = j.id;
  q('.c-id').textContent   = j.id;
  q('.c-url').textContent  = j.url;
  q('.c-url').title        = j.url;
  q('.c-name').textContent = j.output_name || '';
  q('.c-sched-at').textContent = (j.scheduled_at || '').replace('T', ' ');

  const input = q('.reschedule-input');
  if (j.scheduled_at) input.value = j.scheduled_at;

  return frag;
}

function makeTable(headers) {
  const table  = document.createElement('table');
  const row    = table.createTHead().insertRow();
  headers.forEach(h => {
    const th = document.createElement('th');
    th.textContent = h;
    row.appendChild(th);
  });
  table.createTBody();
  return table;
}

async function refresh() {
  try {
    const jobs     = await fetch('/jobs').then(r => r.json());
    const entries  = Object.values(jobs).reverse();
    const now      = 'updated ' + new Date().toLocaleTimeString();
    document.getElementById('tick').textContent = now;

    const scheduled = entries.filter(j => j.status === 'scheduled');
    const regular   = entries.filter(j => j.status !== 'scheduled');

    // ── scheduled panel ───────────────────────────────────────────────────────
    const schedEl   = document.getElementById('sched-jobs');
    const schedTick = document.getElementById('sched-tick');
    schedTick.textContent = scheduled.length ? scheduled.length + ' / 10' : '';

    if (!scheduled.length) {
      schedEl.innerHTML = '<p class="empty">No scheduled jobs.</p>';
    } else {
      const table = makeTable(['ID', 'URL', 'Output file', 'Scheduled for', 'Actions']);
      scheduled.forEach(j => table.tBodies[0].appendChild(renderScheduledJob(j)));
      schedEl.replaceChildren(table);
    }

    // ── regular jobs panel ────────────────────────────────────────────────────
    const el = document.getElementById('jobs');
    if (!regular.length) {
      el.innerHTML = '<p class="empty">No jobs yet.</p>';
    } else {
      const table = makeTable(['ID', 'URL', 'Output file', 'Started', 'Status']);
      regular.forEach(j => table.tBodies[0].appendChild(renderJob(j)));
      el.replaceChildren(table);
      el.querySelectorAll('.logs').forEach(l => { l.scrollTop = l.scrollHeight; });
    }
  } catch {}
}

document.getElementById('jobs').addEventListener('click', async e => {
  const btn = e.target.closest('.act-btn');
  if (!btn) return;
  const id = btn.dataset.id;
  btn.disabled = true;
  try {
    if (btn.classList.contains('retry-btn')) await fetch('/jobs/' + id + '/retry', {method: 'POST'});
    else if (btn.classList.contains('clear-btn')) await fetch('/jobs/' + id, {method: 'DELETE'});
    await refresh();
  } finally {
    btn.disabled = false;
  }
});

document.getElementById('sched-jobs').addEventListener('click', async e => {
  const btn = e.target.closest('.act-btn');
  if (!btn) return;

  const tr = btn.closest('tr');
  const id = tr.dataset.id;

  if (btn.classList.contains('reschedule-btn')) {
    tr.querySelector('.sched-actions').hidden  = true;
    tr.querySelector('.reschedule-form').hidden = false;
  } else if (btn.classList.contains('abort-reschedule-btn')) {
    tr.querySelector('.reschedule-form').hidden = true;
    tr.querySelector('.sched-actions').hidden  = false;
  } else if (btn.classList.contains('cancel-sched-btn')) {
    btn.disabled = true;
    try {
      await fetch('/jobs/' + id, {method: 'DELETE'});
      await refresh();
    } finally { btn.disabled = false; }
  } else if (btn.classList.contains('confirm-reschedule-btn')) {
    const input = tr.querySelector('.reschedule-input');
    if (!input.value) { input.focus(); return; }
    btn.disabled = true;
    try {
      const fd = new FormData();
      fd.append('scheduled_at', input.value);
      const r = await fetch('/jobs/' + id + '/reschedule', {method: 'PATCH', body: fd});
      if (!r.ok) { const j = await r.json(); throw new Error(j.detail || r.statusText); }
      await refresh();
    } catch (err) {
      alert('Reschedule failed: ' + err.message);
    } finally { btn.disabled = false; }
  }
});

refresh();
setInterval(refresh, 3000);