/**
 * LectureAI - Frontend Application Controller
 * Handles media upload, YouTube ingestion, status polling, and interactive note presentation.
 */

// State Management
const state = {
  lectures: [],
  currentLecture: null,
  activeViewerTab: 'notes',
  pollingInterval: null,
  selectedFile: null,
};

// API Base Endpoints
const API = {
  LECTURES: '/api/v1/lectures',
  HEALTH: '/health',
};

// DOM Elements
const elements = {
  lectureList: document.getElementById('lecture-list'),
  lectureCount: document.getElementById('lecture-count'),
  searchInput: document.getElementById('search-input'),
  dropzone: document.getElementById('dropzone'),
  fileInput: document.getElementById('file-input'),
  fileBadge: document.getElementById('file-badge'),
  fileName: document.getElementById('file-name'),
  lectureTitleInput: document.getElementById('lecture-title-input'),
  uploadBtn: document.getElementById('upload-btn'),
  ytUrlInput: document.getElementById('yt-url-input'),
  ytTitleInput: document.getElementById('yt-title-input'),
  ytBtn: document.getElementById('yt-btn'),
  pipelineCard: document.getElementById('pipeline-progress-card'),
  pipelineTitle: document.getElementById('pipeline-title'),
  viewerCard: document.getElementById('viewer-card'),
  viewerTitle: document.getElementById('viewer-title'),
  viewerSource: document.getElementById('viewer-source'),
  viewerDate: document.getElementById('viewer-date'),
  viewerStatus: document.getElementById('viewer-status'),
  viewerBody: document.getElementById('viewer-body'),
  copyNotesBtn: document.getElementById('copy-notes-btn'),
  downloadNotesBtn: document.getElementById('download-notes-btn'),
  refineNotesBtn: document.getElementById('refine-notes-btn'),
  refineModal: document.getElementById('refine-modal'),
  refineFocusInput: document.getElementById('refine-focus-input'),
  refineStyleSelect: document.getElementById('refine-style-select'),
  submitRefineBtn: document.getElementById('submit-refine-btn'),
  closeRefineBtn: document.getElementById('close-refine-btn'),
  toastContainer: document.getElementById('toast-container'),
};

// ==========================================================================
// Initialization
// ==========================================================================
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  loadLectures();
});

function setupEventListeners() {
  // Tabs: Ingestion (Upload vs YouTube)
  document.querySelectorAll('.ingest-tabs .tab-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.ingest-tabs .tab-btn').forEach((b) => b.classList.remove('active'));
      e.currentTarget.classList.add('active');
      const target = e.currentTarget.dataset.tab;
      document.getElementById('tab-upload').style.display = target === 'upload' ? 'block' : 'none';
      document.getElementById('tab-youtube').style.display = target === 'youtube' ? 'block' : 'none';
    });
  });

  // Drag and Drop Zone
  if (elements.dropzone) {
    elements.dropzone.addEventListener('click', () => elements.fileInput.click());
    elements.dropzone.addEventListener('dragover', (e) => {
      e.preventDefault();
      elements.dropzone.classList.add('drag-over');
    });
    elements.dropzone.addEventListener('dragleave', () => elements.dropzone.classList.remove('drag-over'));
    elements.dropzone.addEventListener('drop', (e) => {
      e.preventDefault();
      elements.dropzone.classList.remove('drag-over');
      if (e.dataTransfer.files.length) {
        handleFileSelection(e.dataTransfer.files[0]);
      }
    });
  }

  // File Input Change
  if (elements.fileInput) {
    elements.fileInput.addEventListener('change', (e) => {
      if (e.target.files.length) {
        handleFileSelection(e.target.files[0]);
      }
    });
  }

  // Upload Button
  if (elements.uploadBtn) {
    elements.uploadBtn.addEventListener('click', handleUploadSubmit);
  }

  // YouTube Button
  if (elements.ytBtn) {
    elements.ytBtn.addEventListener('click', handleYouTubeSubmit);
  }

  // Search Filter
  if (elements.searchInput) {
    elements.searchInput.addEventListener('input', (e) => {
      renderLectureList(e.target.value.toLowerCase().trim());
    });
  }

  // Viewer Tabs
  document.querySelectorAll('.viewer-tab-btn').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      document.querySelectorAll('.viewer-tab-btn').forEach((b) => b.classList.remove('active'));
      e.currentTarget.classList.add('active');
      state.activeViewerTab = e.currentTarget.dataset.view;
      renderActiveViewerContent();
    });
  });

  // Copy & Download Notes
  if (elements.copyNotesBtn) {
    elements.copyNotesBtn.addEventListener('click', handleCopyNotes);
  }
  if (elements.downloadNotesBtn) {
    elements.downloadNotesBtn.addEventListener('click', () => {
      if (state.currentLecture) {
        window.location.href = `${API.LECTURES}/${state.currentLecture.id}/notes/markdown`;
      }
    });
  }

  // Refine Modal
  if (elements.refineNotesBtn) {
    elements.refineNotesBtn.addEventListener('click', () => {
      elements.refineModal.style.display = 'flex';
    });
  }
  if (elements.closeRefineBtn) {
    elements.closeRefineBtn.addEventListener('click', () => {
      elements.refineModal.style.display = 'none';
    });
  }
  if (elements.submitRefineBtn) {
    elements.submitRefineBtn.addEventListener('click', handleRefineSubmit);
  }
}

// ==========================================================================
// Ingestion Handlers
// ==========================================================================
function handleFileSelection(file) {
  state.selectedFile = file;
  elements.fileName.textContent = `${file.name} (${formatBytes(file.size)})`;
  elements.fileBadge.style.display = 'inline-flex';
  if (!elements.lectureTitleInput.value.trim()) {
    elements.lectureTitleInput.value = file.name.replace(/\.[^/.]+$/, '').replace(/_/g, ' ');
  }
  elements.uploadBtn.disabled = false;
}

async function handleUploadSubmit() {
  if (!state.selectedFile) return;

  const formData = new FormData();
  formData.append('file', state.selectedFile);
  const title = elements.lectureTitleInput.value.trim();
  if (title) formData.append('title', title);

  setLoading(elements.uploadBtn, true, 'Uploading & Ingesting...');

  try {
    const res = await fetch(`${API.LECTURES}/upload`, {
      method: 'POST',
      body: formData,
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Upload failed');
    }

    const lecture = await res.json();
    showToast('Lecture uploaded! Pipeline started.', 'success');

    // Reset Form
    state.selectedFile = null;
    elements.fileInput.value = '';
    elements.fileBadge.style.display = 'none';
    elements.lectureTitleInput.value = '';

    await loadLectures();
    selectLecture(lecture.id);
  } catch (error) {
    showToast(error.message, 'error');
  } finally {
    setLoading(elements.uploadBtn, false, 'Process Lecture');
  }
}

async function handleYouTubeSubmit() {
  const url = elements.ytUrlInput.value.trim();
  if (!url) {
    showToast('Please enter a valid YouTube URL', 'error');
    return;
  }

  setLoading(elements.ytBtn, true, 'Downloading audio...');

  try {
    const payload = {
      url: url,
      title: elements.ytTitleInput.value.trim() || null,
    };

    const res = await fetch(`${API.LECTURES}/youtube`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'YouTube ingest failed');
    }

    const lecture = await res.json();
    showToast('YouTube media fetched! Pipeline started.', 'success');

    elements.ytUrlInput.value = '';
    elements.ytTitleInput.value = '';

    await loadLectures();
    selectLecture(lecture.id);
  } catch (error) {
    showToast(error.message, 'error');
  } finally {
    setLoading(elements.ytBtn, false, 'Fetch & Process Video');
  }
}

// ==========================================================================
// Lectures API & Rendering
// ==========================================================================
async function loadLectures() {
  try {
    const res = await fetch(`${API.LECTURES}/`);
    if (res.ok) {
      state.lectures = await res.json();
      renderLectureList();
    }
  } catch (err) {
    console.error('Failed to load lectures:', err);
  }
}

function renderLectureList(filterText = '') {
  elements.lectureList.innerHTML = '';

  const filtered = state.lectures.filter((l) =>
    l.title.toLowerCase().includes(filterText)
  );

  elements.lectureCount.textContent = state.lectures.length;

  if (filtered.length === 0) {
    elements.lectureList.innerHTML = `
      <div class="empty-state">
        <i class="fas fa-folder-open" style="font-size: 2rem; margin-bottom: 0.5rem; opacity: 0.4;"></i>
        <p>No lectures found.<br>Upload a file or YouTube link to get started.</p>
      </div>
    `;
    return;
  }

  filtered.forEach((lecture) => {
    const item = document.createElement('div');
    item.className = `lecture-item ${state.currentLecture && state.currentLecture.id === lecture.id ? 'active' : ''}`;
    item.dataset.id = lecture.id;

    const dateStr = new Date(lecture.created_at).toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });

    item.innerHTML = `
      <div class="lecture-item-title" title="${escapeHtml(lecture.title)}">${escapeHtml(lecture.title)}</div>
      <div class="lecture-item-meta">
        <span><i class="${lecture.source_type === 'youtube' ? 'fab fa-youtube' : 'fas fa-file-video'}"></i> ${dateStr}</span>
        <span class="status-pill status-${lecture.status}">
          ${getStatusIcon(lecture.status)} ${formatStatus(lecture.status)}
        </span>
      </div>
    `;

    item.addEventListener('click', () => selectLecture(lecture.id));
    elements.lectureList.appendChild(item);
  });
}

async function selectLecture(id) {
  try {
    const res = await fetch(`${API.LECTURES}/${id}`);
    if (!res.ok) return;

    state.currentLecture = await res.json();
    renderLectureList();
    updateViewerHeader();
    updatePipelineProgress();
    renderActiveViewerContent();

    // Check if lecture is still processing; if so, start live polling
    if (['pending', 'transcribing', 'filtering', 'generating_notes'].includes(state.currentLecture.status)) {
      startLivePolling(id);
    } else {
      stopLivePolling();
    }
  } catch (err) {
    console.error('Failed to select lecture:', err);
  }
}

// ==========================================================================
// Live Pipeline Progress Tracker
// ==========================================================================
function updatePipelineProgress() {
  if (!state.currentLecture) return;

  const s = state.currentLecture.status;
  const isProcessing = ['pending', 'transcribing', 'filtering', 'generating_notes'].includes(s);

  if (!isProcessing) {
    elements.pipelineCard.style.display = 'none';
    return;
  }

  elements.pipelineCard.style.display = 'block';
  elements.pipelineTitle.textContent = `Processing: ${state.currentLecture.title} (${formatStatus(s)})`;

  const steps = [
    { id: 'step-upload', key: 'pending', name: '1. Media Ingestion' },
    { id: 'step-transcribe', key: 'transcribing', name: '2. Speech-to-Text' },
    { id: 'step-filter', key: 'filtering', name: '3. Filter Verbal Clutter' },
    { id: 'step-notes', key: 'generating_notes', name: '4. Generate Notes' },
  ];

  const statusOrder = ['pending', 'transcribing', 'filtering', 'generating_notes', 'completed'];
  const currentIndex = statusOrder.indexOf(s);

  steps.forEach((step, idx) => {
    const el = document.getElementById(step.id);
    if (!el) return;
    el.className = 'step-item';

    if (idx < currentIndex) {
      el.classList.add('completed');
      el.querySelector('.step-indicator').innerHTML = '<i class="fas fa-check"></i>';
    } else if (idx === currentIndex) {
      el.classList.add('active');
      el.querySelector('.step-indicator').innerHTML = '';
    } else {
      el.querySelector('.step-indicator').innerHTML = idx + 1;
    }
  });
}

function startLivePolling(lectureId) {
  stopLivePolling();
  state.pollingInterval = setInterval(async () => {
    try {
      const res = await fetch(`${API.LECTURES}/${lectureId}`);
      if (!res.ok) return;

      const updated = await res.json();
      state.currentLecture = updated;
      updateViewerHeader();
      updatePipelineProgress();

      if (['completed', 'failed'].includes(updated.status)) {
        stopLivePolling();
        await loadLectures();
        renderActiveViewerContent();
        showToast(
          updated.status === 'completed'
            ? 'Lecture processing completed!'
            : `Pipeline failed: ${updated.error_message || 'Unknown error'}`,
          updated.status === 'completed' ? 'success' : 'error'
        );
      }
    } catch (err) {
      console.error('Polling error:', err);
    }
  }, 3000);
}

function stopLivePolling() {
  if (state.pollingInterval) {
    clearInterval(state.pollingInterval);
    state.pollingInterval = null;
  }
}

// ==========================================================================
// Viewer Presentation (Notes, Transcripts, Glossaries, Flashcards)
// ==========================================================================
function updateViewerHeader() {
  if (!state.currentLecture) return;

  elements.viewerTitle.textContent = state.currentLecture.title;
  elements.viewerSource.innerHTML = `<i class="${state.currentLecture.source_type === 'youtube' ? 'fab fa-youtube' : 'fas fa-video'}"></i> ${state.currentLecture.source_type.toUpperCase()}`;
  elements.viewerDate.textContent = new Date(state.currentLecture.created_at).toLocaleString();

  elements.viewerStatus.className = `status-pill status-${state.currentLecture.status}`;
  elements.viewerStatus.innerHTML = `${getStatusIcon(state.currentLecture.status)} ${formatStatus(state.currentLecture.status)}`;
}

function renderActiveViewerContent() {
  if (!state.currentLecture) return;

  const tab = state.activeViewerTab;
  const lecture = state.currentLecture;

  if (lecture.status === 'failed') {
    elements.viewerBody.innerHTML = `
      <div style="text-align: center; padding: 4rem 2rem; color: #fb7185;">
        <i class="fas fa-exclamation-triangle" style="font-size: 3rem; margin-bottom: 1rem;"></i>
        <h3>Processing Encountered an Error</h3>
        <p style="margin-top: 0.5rem; color: #94a3b8; font-family: var(--font-mono); font-size: 0.85rem; max-width: 600px; margin-left: auto; margin-right: auto;">
          ${escapeHtml(lecture.error_message || 'An unknown error occurred during media conversion or AI generation.')}
        </p>
      </div>
    `;
    return;
  }

  if (lecture.status !== 'completed') {
    elements.viewerBody.innerHTML = `
      <div style="text-align: center; padding: 4rem 2rem; color: #94a3b8;">
        <i class="fas fa-circle-notch fa-spin" style="font-size: 2.5rem; color: var(--accent-primary); margin-bottom: 1rem;"></i>
        <h3>Lecture is Currently Being Processed</h3>
        <p style="margin-top: 0.5rem; font-size: 0.9rem;">
          Status: <strong>${formatStatus(lecture.status)}</strong>. The live view will automatically update once notes are ready.
        </p>
      </div>
    `;
    return;
  }

  // Completed Views
  switch (tab) {
    case 'notes':
      renderStudyNotes(lecture.notes);
      break;
    case 'filtered':
      renderTranscript(lecture.transcript?.filtered_transcript, true);
      break;
    case 'raw':
      renderTranscript(lecture.transcript?.raw_transcript, false);
      break;
    case 'concepts':
      renderConcepts(lecture.notes?.key_concepts);
      break;
    case 'flashcards':
      renderFlashcards(lecture.notes?.study_questions);
      break;
  }
}

function renderStudyNotes(notes) {
  if (!notes) {
    elements.viewerBody.innerHTML = '<p class="empty-state">No notes available.</p>';
    return;
  }

  let html = '';
  if (notes.summary) {
    html += `
      <div class="summary-box">
        <div class="summary-box-title">
          <i class="fas fa-feather-alt"></i> Executive Summary
        </div>
        <p>${escapeHtml(notes.summary)}</p>
      </div>
    `;
  }

  const renderedMarkdown = typeof marked !== 'undefined'
    ? marked.parse(notes.structured_notes || '')
    : `<pre>${escapeHtml(notes.structured_notes || '')}</pre>`;

  html += `<div class="markdown-body">${renderedMarkdown}</div>`;
  elements.viewerBody.innerHTML = html;
}

function renderTranscript(text, isFiltered) {
  if (!text) {
    elements.viewerBody.innerHTML = '<p class="empty-state">Transcript not available.</p>';
    return;
  }

  // Format paragraphs and timestamps nicely
  const lines = text.split('\n');
  let html = '<div class="transcript-container">';

  lines.forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) return;

    if (trimmed.startsWith('##') || trimmed.startsWith('#')) {
      html += `<h3 style="color: #a5b4fc; margin-top: 1rem;">${escapeHtml(trimmed.replace(/^#+\s*/, ''))}</h3>`;
      return;
    }

    const timestampMatch = trimmed.match(/^\[(\d{2}:\d{2})\]\s*(.*)/);
    if (timestampMatch) {
      html += `
        <div class="transcript-section">
          <div class="transcript-header">
            <span class="timestamp-badge"><i class="fas fa-clock"></i> ${timestampMatch[1]}</span>
          </div>
          <div class="transcript-text">${escapeHtml(timestampMatch[2])}</div>
        </div>
      `;
    } else {
      html += `
        <div class="transcript-section">
          <div class="transcript-text">${escapeHtml(trimmed)}</div>
        </div>
      `;
    }
  });

  html += '</div>';
  elements.viewerBody.innerHTML = html;
}

function renderConcepts(concepts) {
  if (!concepts || concepts.length === 0) {
    elements.viewerBody.innerHTML = '<p class="empty-state">No key concepts generated.</p>';
    return;
  }

  let html = '<div class="concepts-grid">';
  concepts.forEach((item) => {
    html += `
      <div class="concept-card">
        <div class="concept-title">
          <i class="fas fa-lightbulb" style="color: var(--accent-amber);"></i>
          ${escapeHtml(item.concept || '')}
        </div>
        <div class="concept-desc">
          ${escapeHtml(item.explanation || '')}
        </div>
      </div>
    `;
  });
  html += '</div>';
  elements.viewerBody.innerHTML = html;
}

function renderFlashcards(questions) {
  if (!questions || questions.length === 0) {
    elements.viewerBody.innerHTML = '<p class="empty-state">No study flashcards available.</p>';
    return;
  }

  let html = `
    <div style="margin-bottom: 1.5rem; color: var(--text-secondary); font-size: 0.9rem;">
      <i class="fas fa-info-circle"></i> Click any card to flip and test your active recall.
    </div>
    <div class="flashcards-container">
  `;

  questions.forEach((q, idx) => {
    html += `
      <div class="flashcard" onclick="this.classList.toggle('flipped')">
        <div class="flashcard-inner">
          <div class="flashcard-front">
            <span class="flashcard-label">Question ${idx + 1}</span>
            <div class="flashcard-question">${escapeHtml(q.question || '')}</div>
            <div class="flashcard-hint"><i class="fas fa-redo"></i> Click to reveal answer</div>
          </div>
          <div class="flashcard-back">
            <span class="flashcard-label" style="color: #34d399;">Answer</span>
            <div class="flashcard-answer">${escapeHtml(q.answer || '')}</div>
          </div>
        </div>
      </div>
    `;
  });

  html += '</div>';
  elements.viewerBody.innerHTML = html;
}

// ==========================================================================
// Actions: Copy, Refine, Delete
// ==========================================================================
async function handleCopyNotes() {
  if (!state.currentLecture || !state.currentLecture.notes) return;

  const notes = state.currentLecture.notes;
  let fullText = `# ${notes.title}\n\n`;
  fullText += `## Executive Summary\n${notes.summary}\n\n`;
  fullText += notes.structured_notes;

  try {
    await navigator.clipboard.writeText(fullText);
    showToast('Notes copied to clipboard!', 'success');
  } catch {
    showToast('Failed to copy to clipboard', 'error');
  }
}

async function handleRefineSubmit() {
  if (!state.currentLecture) return;

  const customFocus = elements.refineFocusInput.value.trim() || null;
  const formatStyle = elements.refineStyleSelect.value;

  setLoading(elements.submitRefineBtn, true, 'Regenerating...');

  try {
    const res = await fetch(`${API.LECTURES}/${state.currentLecture.id}/generate-notes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ custom_focus: customFocus, format_style: formatStyle }),
    });

    if (!res.ok) throw new Error('Failed to regenerate notes');

    const updatedNotes = await res.json();
    state.currentLecture.notes = updatedNotes;
    elements.refineModal.style.display = 'none';
    renderActiveViewerContent();
    showToast('Notes refined successfully!', 'success');
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    setLoading(elements.submitRefineBtn, false, 'Regenerate Notes');
  }
}

// ==========================================================================
// Utilities
// ==========================================================================
function getStatusIcon(status) {
  switch (status) {
    case 'completed': return '<i class="fas fa-check-circle"></i>';
    case 'failed': return '<i class="fas fa-times-circle"></i>';
    default: return '<i class="fas fa-circle-notch fa-spin"></i>';
  }
}

function formatStatus(status) {
  if (!status) return 'Unknown';
  return status.replace(/_/g, ' ');
}

function formatBytes(bytes, decimals = 1) {
  if (bytes === 0) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}

function escapeHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function setLoading(button, isLoading, text) {
  button.disabled = isLoading;
  button.innerHTML = isLoading
    ? `<i class="fas fa-circle-notch fa-spin"></i> ${text}`
    : text;
}

function showToast(message, type = 'info') {
  if (!elements.toastContainer) return;

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    <i class="fas ${type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle'}"></i>
    <span>${escapeHtml(message)}</span>
  `;

  elements.toastContainer.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(100%)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}
