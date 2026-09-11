const API_URL = window.APP_CONFIG.backendBaseUrl;
const sources = new Map();
const list = document.querySelector('#source-list');
const count = document.querySelector('#source-count');
const readiness = document.querySelector('#readiness');
const input = document.querySelector('#chat-input');
const ask = document.querySelector('#ask-button');

function render() {
  count.textContent = sources.size;
  list.innerHTML = [...sources.values()].map((source) => `<article class="source"><div><strong>${source.name}</strong><small>${source.status}</small></div><span class="source-status">${source.status}</span></article>`).join('');
}
function track(jobId, name) {
  sources.set(jobId, { name, status: 'QUEUED' }); render();
  const poll = async () => {
    const response = await fetch(`${API_URL}/ingest/${jobId}`);
    if (!response.ok) return;
    const job = await response.json(); const source = sources.get(jobId);
    if (!source) return;
    source.status = job.status; render();
    if (job.status === 'COMPLETED') { readiness.textContent = 'This document is ready for questions.'; input.disabled = false; ask.disabled = false; return; }
    if (job.status === 'FAILED') { readiness.textContent = `Processing failed: ${job.error?.message || 'Unknown error'}`; return; }
    readiness.textContent = 'Your document is still being processed. AI will be able to answer questions once processing is complete.';
    setTimeout(poll, 1200);
  }; poll();
}
async function create(data, name) { const response = await fetch(`${API_URL}/ingest/create`, { method: 'POST', body: data }); if (!response.ok) { readiness.textContent = 'The source could not be accepted.'; return; } const result = await response.json(); track(result.job_id, name); }
document.querySelector('#upload-form').addEventListener('submit', (event) => { event.preventDefault(); const file = document.querySelector('#file-input').files[0]; if (!file) return; const data = new FormData(); data.append('source_type', 'file'); data.append('file', file); create(data, file.name); });
document.querySelector('#url-form').addEventListener('submit', (event) => { event.preventDefault(); const url = document.querySelector('#url-input').value; const data = new FormData(); data.append('source_type', 'url'); data.append('url', url); create(data, url); });
document.querySelector('#chat-form').addEventListener('submit', (event) => event.preventDefault());
