const API_URL = window.APP_CONFIG.backendBaseUrl;
const sources = new Map();
let conversationId = null;
const list = document.querySelector('#source-list');
const count = document.querySelector('#source-count');
const readiness = document.querySelector('#readiness');
const input = document.querySelector('#chat-input');
const ask = document.querySelector('#ask-button');

function render() {
  count.textContent = sources.size;
  list.innerHTML = [...sources.values()].map((source) => `<label class="source"><input type="checkbox" data-document-id="${source.documentId}" ${source.selected ? 'checked' : ''} ${source.ready ? '' : 'disabled'} /><div><strong>${source.name}</strong><small>${source.status}</small></div><span class="source-status">${source.status}</span></label>`).join('');
  list.querySelectorAll('input[data-document-id]').forEach((checkbox) => checkbox.addEventListener('change', (event) => {
    sources.get(event.target.dataset.documentId).selected = event.target.checked; conversationId = null; updateReadiness();
  }));
  updateReadiness();
}
function updateReadiness() {
  const selected = [...sources.values()].filter((source) => source.selected);
  const ready = selected.length > 0 && selected.every((source) => source.ready);
  input.disabled = !ready; ask.disabled = !ready;
  readiness.textContent = ready ? 'Ready to search the selected sources.' : 'Your document is still being processed. AI will be able to answer questions once processing is complete.';
}
function selectedDocumentIds() {
  return [...sources.values()].filter((source) => source.selected && source.ready && source.documentId).map((source) => source.documentId);
}
function track(jobId, name) {
  sources.set(jobId, { name, documentId: null, status: 'QUEUED', ready: false, selected: true }); render();
  let delay = 3000;
  const maxDelay = 30000;
  const poll = async () => {
    let response;
    try { response = await fetch(`${API_URL}/ingest/${jobId}`); } catch (_) { setTimeout(poll, delay); delay = Math.min(delay * 2, maxDelay); return; }
    if (!response.ok) { setTimeout(poll, delay); delay = Math.min(delay * 2, maxDelay); return; }
    const job = await response.json(); const source = sources.get(jobId);
    if (!source) return;
    source.documentId = job.document_id; source.status = job.document_status || job.status; source.ready = job.ready_for_ai === true || job.document_status === 'READY'; render();
    if (source.ready || job.status === 'FAILED') return;
    if (job.status === 'FAILED') { readiness.textContent = `Processing failed: ${job.error?.message || job.processing_error?.message || 'Unknown error'}`; return; }
    setTimeout(poll, delay); delay = Math.min(delay * 2, maxDelay);
  }; poll();
}
async function create(data, name) { const response = await fetch(`${API_URL}/ingest/create`, { method: 'POST', body: data }); if (!response.ok) { readiness.textContent = 'The source could not be accepted.'; return; } const result = await response.json(); track(result.job_id, name); }
document.querySelector('#upload-form').addEventListener('submit', (event) => { event.preventDefault(); const file = document.querySelector('#file-input').files[0]; if (!file) return; const data = new FormData(); data.append('source_type', 'file'); data.append('file', file); create(data, file.name); });
document.querySelector('#url-form').addEventListener('submit', (event) => { event.preventDefault(); const url = document.querySelector('#url-input').value; const data = new FormData(); data.append('source_type', 'url'); data.append('url', url); create(data, url); });
document.querySelector('#chat-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const documentIds = selectedDocumentIds();
  if (!documentIds.length) {
    readiness.textContent = 'Select at least one ready document before asking a question.';
    return;
  }
  if (!conversationId) {
    const created = await fetch(`${API_URL}/chat/conversations`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ document_ids: documentIds }) });
    if (!created.ok) { readiness.textContent = 'A conversation could not be created.'; return; }
    conversationId = (await created.json()).id;
  }
  const question = input.value.trim(); if (!question) return;
  input.disabled = true; ask.disabled = true;
  const response = await fetch(`${API_URL}/chat/conversations/${conversationId}/messages`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ content: question, document_ids: documentIds }) });
  const messageList = document.querySelector('#message-list');
  if (!response.ok) { const error = await response.json().catch(() => ({})); readiness.textContent = error.error?.message || 'The question could not be answered.'; updateReadiness(); return; }
  const result = await response.json();
  messageList.innerHTML += `<article class="message user"><strong>You</strong><p>${escapeHtml(question)}</p></article><article class="message assistant"><strong>Assistant</strong><p>${escapeHtml(result.answer)}</p>${result.citations?.length ? `<small>Sources</small><ol>${result.citations.map((citation) => `<li><button class="citation" title="${escapeHtml(citation.excerpt || '')}">${escapeHtml(citation.document_name || citation.document_id)}${citation.page_number ? `, p. ${citation.page_number}` : ''}</button></li>`).join('')}</ol>` : ''}</article>`;
  input.value = ''; updateReadiness();
});
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (character) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[character])); }
