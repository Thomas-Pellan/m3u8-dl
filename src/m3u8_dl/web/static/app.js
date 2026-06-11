const frm = document.getElementById('frm');
const btn = document.getElementById('btn');
const msg = document.getElementById('msg');

frm.addEventListener('submit', async e => {
  e.preventDefault();
  const data = new FormData(frm);
  btn.disabled = true;
  msg.style.color = '#555';
  msg.textContent = 'Submitting…';
  try {
    const r = await fetch('/capture', {method:'POST', body:data});
    const j = await r.json();
    if (!r.ok) { throw new Error(j.detail || r.statusText); }
    msg.style.color = '#00d7af';
    msg.textContent = 'Job ' + j.job_id + ' queued.';
    frm.reset();
  } catch(err) {
    msg.style.color = '#ff5555';
    msg.textContent = 'Error: ' + err.message;
  } finally {
    btn.disabled = false;
  }
});

function esc(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function badge(s) {
  const cls = {pending:'p', running:'r', done:'d', error:'e'}[s] || 'p';
  return '<span class="badge ' + cls + '">' + s + '</span>';
}

function colorLog(line) {
  const s = esc(line);
  let c;
  if (/error|failed/i.test(line))                          c = '#ff5555';
  else if (/rate.limited|warning|retry/i.test(line))       c = '#ffaa00';
  else if (/downloading\.\.\.|segment.*\(\d+%\)/i.test(line)) c = '#7ab8ff';
  else if (/captured\.|segments captured|complete/i.test(line)) c = '#00d7af';
  else if (/playlist|intercepted|variant|ready/i.test(line)) c = '#00cc66';
  else if (/waiting|auto mode|direct mode|intercept mode/i.test(line)) c = '#666';
  else                                                       c = '#484848';
  return '<span style="color:' + c + '">' + s + '</span>';
}

async function refresh() {
  try {
    const jobs = await fetch('/jobs').then(r => r.json());
    document.getElementById('tick').textContent = 'updated ' + new Date().toLocaleTimeString();
    const entries = Object.values(jobs).reverse();
    const el = document.getElementById('jobs');
    if (!entries.length) { el.innerHTML = '<p class="empty">No jobs yet.</p>'; return; }
    el.innerHTML = '<table><tr>' +
      '<th>ID</th><th>URL</th><th>Output file</th><th>Started</th><th>Status</th>' +
      '</tr>' +
      entries.map(j => '<tr>' +
        '<td class="c-id">' + j.id + '</td>' +
        '<td class="c-url" title="' + j.url + '">' + j.url + '</td>' +
        '<td class="c-name">' + (j.output_name || '') + '</td>' +
        '<td class="c-time">' + (j.started_at || '').replace('T',' ') + '</td>' +
        '<td class="c-st">' + badge(j.status) +
          (j.progress != null && j.status === 'running' ? '<span class="pct">' + j.progress + '%</span>' : '') +
          (j.error ? '<div class="err">' + esc(j.error) + '</div>' : '') +
          (j.status === 'error' ? '<div class="job-actions"><button class="act-btn retry-btn" data-id="' + j.id + '">Retry</button><button class="act-btn clear-btn" data-id="' + j.id + '">Clear</button></div>' : '') +
          (j.output ? '<div class="out">✓ ' + esc(j.output) + '</div>' : '') +
          (j.logs && j.logs.length ? '<div class="logs">' + j.logs.map(colorLog).join('\n') + '</div>' : '') +
        '</td>' +
      '</tr>').join('') +
      '</table>';
    document.querySelectorAll('.logs').forEach(el => { el.scrollTop = el.scrollHeight; });
  } catch {}
}

document.getElementById('jobs').addEventListener('click', async e => {
  const btn = e.target.closest('.act-btn');
  if (!btn) return;
  const id = btn.dataset.id;
  btn.disabled = true;
  try {
    if (btn.classList.contains('retry-btn')) {
      await fetch('/jobs/' + id + '/retry', {method: 'POST'});
    } else if (btn.classList.contains('clear-btn')) {
      await fetch('/jobs/' + id, {method: 'DELETE'});
    }
    await refresh();
  } finally {
    btn.disabled = false;
  }
});

refresh();
setInterval(refresh, 3000);