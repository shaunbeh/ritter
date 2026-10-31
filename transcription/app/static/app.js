(() => {
  const KEY_STORAGE = "transcription.apiKey";
  const form = document.getElementById("upload-form");
  const apiKeyInput = document.getElementById("api-key");
  const fileInput = document.getElementById("file");
  const languageInput = document.getElementById("language");
  const summarizeInput = document.getElementById("summarize");
  const diarizeInput = document.getElementById("diarize");
  const submitBtn = document.getElementById("submit");
  const copyBtn = document.getElementById("copy");
  const statusEl = document.getElementById("status");
  const errorEl = document.getElementById("error");
  const resultsEl = document.getElementById("results");
  const summaryBlock = document.getElementById("summary-block");
  const summaryText = document.getElementById("summary-text");
  const segmentsEl = document.getElementById("segments");

  let pollTimer = null;
  let lastPlainTranscript = "";

  apiKeyInput.value = localStorage.getItem(KEY_STORAGE) || "";

  function showError(message) {
    errorEl.hidden = !message;
    errorEl.textContent = message || "";
  }

  function showStatus(message) {
    statusEl.hidden = !message;
    statusEl.textContent = message || "";
  }

  function formatTime(seconds) {
    if (typeof seconds !== "number" || Number.isNaN(seconds)) return "--:--";
    const total = Math.max(0, Math.floor(seconds));
    const m = Math.floor(total / 60);
    const s = String(total % 60).padStart(2, "0");
    return `${m}:${s}`;
  }

  function authHeaders(apiKey) {
    return { Authorization: `Bearer ${apiKey}` };
  }

  async function readError(response) {
    try {
      const data = await response.json();
      if (typeof data.detail === "string") return data.detail;
      if (Array.isArray(data.detail)) {
        return data.detail.map((item) => item.msg || JSON.stringify(item)).join("; ");
      }
      return JSON.stringify(data);
    } catch (_) {
      return response.statusText || `HTTP ${response.status}`;
    }
  }

  function renderResult(job) {
    resultsEl.hidden = false;
    const segments = Array.isArray(job.segments) ? job.segments : [];
    const lines = [];

    if (job.summary) {
      summaryBlock.hidden = false;
      summaryText.textContent = job.summary;
    } else {
      summaryBlock.hidden = true;
      summaryText.textContent = "";
    }

    segmentsEl.replaceChildren();
    for (const segment of segments) {
      const li = document.createElement("li");
      const meta = document.createElement("div");
      meta.className = "meta";
      const speaker = segment.speaker_id || "SPEAKER";
      meta.textContent = `${speaker} · ${formatTime(segment.start)} – ${formatTime(segment.end)}`;
      const text = document.createElement("div");
      text.className = "seg-text";
      text.textContent = segment.text || "";
      li.append(meta, text);
      segmentsEl.append(li);
      lines.push(`${speaker}: ${segment.text || ""}`);
    }

    lastPlainTranscript = lines.join("\n");
    copyBtn.hidden = !lastPlainTranscript;
  }

  function stopPolling() {
    if (pollTimer) {
      clearTimeout(pollTimer);
      pollTimer = null;
    }
  }

  async function pollJob(apiKey, jobId) {
    const response = await fetch(`/v1/transcriptions/${jobId}`, {
      headers: authHeaders(apiKey),
    });
    if (!response.ok) {
      throw new Error(await readError(response));
    }
    const job = await response.json();
    const language = job.language ? ` · ${job.language}` : "";
    showStatus(`Job ${job.id}: ${job.status}${language}`);

    if (job.status === "queued" || job.status === "processing") {
      pollTimer = setTimeout(() => {
        pollJob(apiKey, jobId).catch((err) => {
          submitBtn.disabled = false;
          showError(err.message || String(err));
        });
      }, 2000);
      return;
    }

    submitBtn.disabled = false;
    if (job.status === "failed") {
      showError(job.error || "Transcription failed");
      return;
    }

    if (job.diarization_error || job.summary_error) {
      const notes = [job.diarization_error, job.summary_error].filter(Boolean).join(" · ");
      showStatus(`Job ${job.id}: completed (${notes})`);
    }
    renderResult(job);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    stopPolling();
    showError("");
    resultsEl.hidden = true;
    copyBtn.hidden = true;
    lastPlainTranscript = "";

    const apiKey = apiKeyInput.value.trim();
    if (!apiKey) {
      showError("API key is required");
      return;
    }
    if (!fileInput.files || !fileInput.files[0]) {
      showError("Choose an audio or video file");
      return;
    }

    localStorage.setItem(KEY_STORAGE, apiKey);
    const body = new FormData();
    body.append("file", fileInput.files[0]);
    body.append("summarize", summarizeInput.checked ? "true" : "false");
    body.append("diarize", diarizeInput.checked ? "true" : "false");
    const language = languageInput.value.trim();
    if (language) body.append("language", language);

    submitBtn.disabled = true;
    showStatus("Uploading…");

    try {
      const response = await fetch("/v1/transcriptions", {
        method: "POST",
        headers: authHeaders(apiKey),
        body,
      });
      if (!response.ok) {
        throw new Error(await readError(response));
      }
      const created = await response.json();
      showStatus(`Job ${created.id}: ${created.status}`);
      await pollJob(apiKey, created.id);
    } catch (err) {
      submitBtn.disabled = false;
      showStatus("");
      showError(err.message || String(err));
    }
  });

  copyBtn.addEventListener("click", async () => {
    if (!lastPlainTranscript) return;
    try {
      await navigator.clipboard.writeText(lastPlainTranscript);
      showStatus("Transcript copied");
    } catch (_) {
      showError("Could not copy to clipboard");
    }
  });
})();
