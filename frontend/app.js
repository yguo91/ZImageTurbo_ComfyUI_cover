'use strict';

const App = (() => {
  // ── State ────────────────────────────────────────────────────────────
  let ws               = null;
  let wsReconnectDelay = 1000;
  let promptId         = null;
  let pendingImage     = null;   // { filename, subfolder, type } from SaveImage node
  let currentImage     = null;   // same object, kept after completion for download
  let generating       = false;

  // Human-readable labels for the "executing" WebSocket event
  const NODE_LABELS = {
    '39': 'Loading CLIP encoder…',
    '40': 'Loading VAE…',
    '41': 'Creating latent canvas…',
    '42': 'Building conditioning…',
    '43': 'Decoding image…',
    '44': 'Sampling…',
    '45': 'Encoding prompt…',
    '46': 'Loading diffusion model…',
    '47': 'Configuring sampler…',
    '48': 'Loading LoRA…',
    '9':  'Saving image…',
  };

  // ── DOM helpers ──────────────────────────────────────────────────────
  const $ = id => document.getElementById(id);

  // ── Initialisation ───────────────────────────────────────────────────
  function init() {
    rollSeed();
    $('filename-prefix').addEventListener('input', sanitizePrefix);
    connectWS();
    pollStatus();
  }

  function sanitizePrefix() {
    // Strip characters Windows/Linux disallow in filenames
    $('filename-prefix').value =
      $('filename-prefix').value.replace(/[\\/:*?"<>|]/g, '');
  }

  // ── View switching ───────────────────────────────────────────────────
  function showView(id) {
    ['view-loading', 'view-setup', 'view-main'].forEach(v =>
      $(v).classList.toggle('hidden', v !== id)
    );
  }

  // ── Status polling (used on startup to determine which view to show) ─
  async function pollStatus() {
    try {
      const res  = await fetch('/api/status');
      const data = await res.json();

      if (data.setup_required) {
        showView('view-setup');
        loadCandidates();
        return;
      }

      if (data.comfyui_running) {
        showView('view-main');
        setStatus('ready', 'Ready');
        return;
      }

      // ComfyUI is still starting — stay on loading screen and keep polling
      $('loading-text').textContent = 'Starting ComfyUI…';
      showView('view-loading');

      if (data.comfyui_logs && data.comfyui_logs.length) {
        const logEl = $('loading-log');
        logEl.classList.remove('hidden');
        logEl.textContent = data.comfyui_logs.slice(-15).join('\n');
      }

    } catch {
      // Network not ready yet — keep trying
    }
    setTimeout(pollStatus, 2000);
  }

  // ── Status indicator ─────────────────────────────────────────────────
  function setStatus(state, label) {
    $('status-dot').className = `status-dot ${state}`;
    $('status-text').textContent = label;
  }

  // ── WebSocket ────────────────────────────────────────────────────────
  function connectWS() {
    ws = new WebSocket(`ws://${location.host}/ws`);

    ws.onopen = () => { wsReconnectDelay = 1000; };

    ws.onmessage = e => {
      try { handleWSMessage(JSON.parse(e.data)); } catch { /* ignore */ }
    };

    ws.onclose = () => {
      setTimeout(connectWS, wsReconnectDelay);
      wsReconnectDelay = Math.min(wsReconnectDelay * 2, 16000);
    };
  }

  function handleWSMessage(msg) {
    const data = msg.data || {};

    switch (msg.type) {

      case 'execution_start':
        if (data.prompt_id === promptId) {
          showProgress(0, 1, 'Starting…');
        }
        break;

      case 'executing':
        if (data.prompt_id === promptId || !data.prompt_id) {
          const label = NODE_LABELS[data.node] || 'Processing…';
          $('progress-node-label').textContent = label;
        }
        break;

      case 'progress':
        if (data.prompt_id === promptId || !promptId) {
          showProgress(data.value, data.max, NODE_LABELS['44']);
        }
        break;

      case 'executed':
        // Node 9 = SaveImage — capture the output filename
        if (data.node === '9' && data.output?.images?.length) {
          pendingImage = data.output.images[0];
        }
        break;

      case 'execution_success':
        if (data.prompt_id === promptId && pendingImage) {
          displayImage(pendingImage);
        }
        break;

      case 'execution_error':
        if (data.prompt_id === promptId) {
          const msg = data.exception_message || 'Generation failed.';
          setError(msg.length > 300 ? msg.slice(0, 297) + '…' : msg);
          setGenerating(false);
        }
        break;

      case 'comfyui_disconnected':
        setStatus('error', 'Disconnected');
        break;
    }
  }

  // ── Generate ─────────────────────────────────────────────────────────
  async function generate() {
    const prompt = $('prompt').value.trim();
    if (!prompt) {
      $('prompt').focus();
      return;
    }

    setGenerating(true);
    hideError();
    pendingImage = null;
    promptId     = null;
    $('post-actions').classList.add('hidden');
    showProgress(0, 1, 'Queuing…');

    const body = {
      prompt,
      width:           parseInt($('width').value,  10),
      height:          parseInt($('height').value, 10),
      seed:            parseInt($('seed').value,   10) || 0,
      steps:           parseInt($('steps').value,  10) || 9,
      pixel_art:       $('pixel-art').checked,
      filename_prefix: $('filename-prefix').value.trim() || 'z-image',
    };

    try {
      const res = await fetch('/api/generate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${res.status}`);
      }

      const data = await res.json();
      promptId = data.prompt_id;

    } catch (err) {
      setError(err.message);
      setGenerating(false);
    }
  }

  // ── Image display ─────────────────────────────────────────────────────
  function displayImage(imageInfo) {
    currentImage = imageInfo;

    const params = new URLSearchParams({
      filename:  imageInfo.filename,
      subfolder: imageInfo.subfolder || '',
      type:      imageInfo.type      || 'output',
    });

    const img  = $('output-img');
    img.onload = () => {
      $('img-placeholder').style.display = 'none';
      img.classList.add('visible');
      hideProgress();
      setGenerating(false);
      $('post-actions').classList.remove('hidden');
      setStatus('ready', 'Ready');

      if ($('auto-randomize').checked) rollSeed();
    };
    img.onerror = () => {
      setError('Image loaded but could not be displayed.');
      setGenerating(false);
    };
    img.src = `/api/image?${params}`;
  }

  // ── Download ──────────────────────────────────────────────────────────
  async function downloadImage() {
    if (!currentImage) return;
    try {
      const params = new URLSearchParams({
        filename:  currentImage.filename,
        subfolder: currentImage.subfolder || '',
        type:      currentImage.type      || 'output',
      });
      const res  = await fetch(`/api/image?${params}`);
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement('a');
      a.href     = url;
      a.download = currentImage.filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setError('Download failed: ' + err.message);
    }
  }

  // ── Seed ──────────────────────────────────────────────────────────────
  function rollSeed() {
    $('seed').value = Math.floor(Math.random() * 4294967296);
  }

  // ── UI state helpers ──────────────────────────────────────────────────
  function setGenerating(on) {
    generating = on;
    const btn  = $('btn-generate');
    btn.disabled    = on;
    btn.textContent = on ? 'Generating…' : 'Generate Image';
    if (on) setStatus('loading', 'Generating');
  }

  function showProgress(value, max, nodeLabel) {
    $('progress-wrap').classList.remove('hidden');
    const pct = max > 0 ? (value / max) * 100 : 0;
    $('progress-bar').style.width = pct + '%';
    if (nodeLabel) $('progress-node-label').textContent = nodeLabel;
    $('progress-steps').textContent = max > 1 ? `${value} / ${max}` : '';
  }

  function hideProgress() {
    $('progress-wrap').classList.add('hidden');
    $('progress-bar').style.width = '0%';
  }

  function setError(message) {
    $('error-banner').textContent = message;
    $('error-banner').classList.remove('hidden');
    hideProgress();
    setStatus('error', 'Error');
  }

  function hideError() {
    $('error-banner').classList.add('hidden');
  }

  // ── Setup wizard ──────────────────────────────────────────────────────
  async function loadCandidates() {
    try {
      const res  = await fetch('/api/setup/check');
      const data = await res.json();
      const list = $('candidate-list');

      if (data.candidates.length === 0) {
        list.innerHTML =
          '<p style="color:var(--text-muted);font-size:13px">' +
          'No ComfyUI installations detected automatically.</p>';
      } else {
        list.innerHTML = data.candidates.map((path, i) => `
          <label class="candidate-item">
            <input type="radio" name="candidate" value="${escHtml(path)}"
                   ${i === 0 ? 'checked' : ''}>
            <label>${escHtml(path)}</label>
          </label>`).join('');

        // Add "Use Selected" button once (after the list)
        if (!$('btn-use-candidate')) {
          const btn    = document.createElement('button');
          btn.className = 'btn-setup';
          btn.id        = 'btn-use-candidate';
          btn.textContent = 'Use Selected';
          btn.style.marginTop = '10px';
          btn.onclick  = () => {
            const sel = document.querySelector('input[name=candidate]:checked');
            if (sel) configurePath(sel.value);
          };
          list.after(btn);
        }
      }

      if (data.current_path) $('manual-path').value = data.current_path;

    } catch (err) {
      $('candidate-list').innerHTML =
        `<p style="color:var(--error);font-size:13px">Failed to load: ${err.message}</p>`;
    }
  }

  async function configurePath(path) {
    const errEl = $('setup-error');
    errEl.classList.add('hidden');
    try {
      const res = await fetch('/api/setup/configure', {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ comfyui_path: path }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        errEl.textContent = err.detail || 'Invalid path.';
        errEl.classList.remove('hidden');
        return;
      }
      goToStep(2);
      loadModelList();
    } catch (err) {
      errEl.textContent = err.message;
      errEl.classList.remove('hidden');
    }
  }

  function useManualPath() {
    const path = $('manual-path').value.trim();
    if (path) configurePath(path);
  }

  function goToStep(n) {
    document.querySelectorAll('.setup-step').forEach(el =>
      el.classList.remove('active')
    );
    $(`setup-step-${n}`).classList.add('active');
  }

  async function loadModelList() {
    try {
      const res  = await fetch('/api/setup/models');
      const data = await res.json();
      const list = $('model-list');

      let allRequired = true;
      list.innerHTML  = data.models.map(m => {
        if (m.required && !m.present) allRequired = false;
        const statusHtml = m.present
          ? '<span class="badge-ok">✓ Present</span>'
          : `<a href="${escHtml(m.url)}" target="_blank" class="badge-missing">✗ Download</a>`;
        const optBadge = !m.required
          ? '<span class="badge-opt">optional</span> ' : '';
        return `
          <div class="model-item">
            <div class="model-info">
              <div class="model-name">${escHtml(m.name)}</div>
              <div class="model-dir">models/${escHtml(m.directory)}/</div>
            </div>
            <div class="model-status">${optBadge}${statusHtml}</div>
          </div>`;
      }).join('');

      $('models-note').textContent = allRequired
        ? 'All required models are present. You can start the app.'
        : 'Download missing required models, place them in the correct folders, then refresh this page.';

      $('btn-launch').disabled = !allRequired;

    } catch (err) {
      $('model-list').innerHTML =
        `<p style="color:var(--error);font-size:13px">Failed to check models: ${err.message}</p>`;
    }
  }

  async function launch() {
    $('btn-launch').disabled    = true;
    $('btn-launch').textContent = 'Starting…';
    try {
      const res  = await fetch('/api/setup/launch', { method: 'POST' });
      const data = await res.json();
      if (data.ok) {
        showView('view-main');
        setStatus('ready', 'Ready');
      } else {
        $('btn-launch').disabled    = false;
        $('btn-launch').textContent = 'Start App';
        $('models-note').textContent =
          'ComfyUI failed to start. Check the terminal for error details.';
      }
    } catch {
      $('btn-launch').disabled    = false;
      $('btn-launch').textContent = 'Start App';
    }
  }

  // ── Utility ───────────────────────────────────────────────────────────
  function escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  // ── Public API ────────────────────────────────────────────────────────
  return {
    init,
    generate,
    downloadImage,
    rollSeed,
    useManualPath,
    configurePath,
    goToStep,
    launch,
  };
})();

document.addEventListener('DOMContentLoaded', App.init);
