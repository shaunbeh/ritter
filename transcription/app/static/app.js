(() => {
  const KEY_STORAGE = "transcription.apiKey";
  const JOB_STORAGE = "transcription.activeJobId";
  const form = document.getElementById("upload-form");
  const apiKeyInput = document.getElementById("api-key");
  const fileInput = document.getElementById("file");
  const languageInput = document.getElementById("language");
  const summarizeInput = document.getElementById("summarize");
  const diarizeInput = document.getElementById("diarize");
  const submitBtn = document.getElementById("submit");
  const copyBtn = document.getElementById("copy");
  const recordBtn = document.getElementById("record-btn");
  const clearRecordingBtn = document.getElementById("clear-recording");
  const recordStatus = document.getElementById("record-status");
  const preview = document.getElementById("preview");
  const progressPanel = document.getElementById("progress-panel");
  const statusEl = document.getElementById("status");
  const progressPct = document.getElementById("progress-pct");
  const progressBar = document.getElementById("progress-bar");
  const progressDetail = document.getElementById("progress-detail");
  const errorEl = document.getElementById("error");
  const resultsEl = document.getElementById("results");
  const summaryBlock = document.getElementById("summary-block");
  const summaryText = document.getElementById("summary-text");
  const segmentsEl = document.getElementById("segments");

  let pollTimer = null;
  let lastPlainTranscript = "";
  let mediaStream = null;
  let mediaRecorder = null;
  let recordedChunks = [];
  let recordedBlob = null;
  let recordedMime = "";
  let recordStartedAt = 0;
  let recordTick = null;
  let elapsedTimer = null;
  let jobStartedAt = 0;

  function readStoredKey() {
    return localStorage.getItem(KEY_STORAGE) || sessionStorage.getItem(KEY_STORAGE) || "";
  }

  function persistApiKey(value) {
    const key = (value || "").trim();
    if (!key) {
      localStorage.removeItem(KEY_STORAGE);
      sessionStorage.removeItem(KEY_STORAGE);
      return;
    }
    localStorage.setItem(KEY_STORAGE, key);
    sessionStorage.setItem(KEY_STORAGE, key);
  }

  apiKeyInput.value = readStoredKey();
  apiKeyInput.addEventListener("input", () => persistApiKey(apiKeyInput.value));
  apiKeyInput.addEventListener("change", () => persistApiKey(apiKeyInput.value));
  apiKeyInput.addEventListener("blur", () => persistApiKey(apiKeyInput.value));

  function showError(message) {
    errorEl.hidden = !message;
    errorEl.textContent = message || "";
  }

  function setProgress(progress, title, detail) {
    const value = Math.max(0, Math.min(100, Number(progress) || 0));
    progressPanel.hidden = false;
    statusEl.textContent = title || "Working…";
    progressPct.textContent = `${Math.round(value)}%`;
    progressBar.style.width = `${value}%`;
    progressDetail.textContent = detail || "";
  }

  function hideProgress() {
    progressPanel.hidden = true;
    if (elapsedTimer) {
      clearInterval(elapsedTimer);
      elapsedTimer = null;
    }
  }

  function formatElapsed(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const m = Math.floor(total / 60);
    const s = String(total % 60).padStart(2, "0");
    return m > 0 ? `${m}m ${s}s` : `${total}s`;
  }

  function startElapsedClock() {
    jobStartedAt = Date.now();
    if (elapsedTimer) clearInterval(elapsedTimer);
    elapsedTimer = setInterval(() => {
      if (!progressDetail.dataset.base) return;
      progressDetail.textContent = `${progressDetail.dataset.base} · elapsed ${formatElapsed(Date.now() - jobStartedAt)}`;
    }, 1000);
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

  function pickRecorderMime() {
    const candidates = [
      "audio/webm;codecs=opus",
      "audio/webm",
      "audio/mp4",
      "audio/ogg;codecs=opus",
    ];
    if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) {
      return "";
    }
    return candidates.find((type) => MediaRecorder.isTypeSupported(type)) || "";
  }

  function extensionForMime(mime) {
    if (mime.includes("mp4")) return "m4a";
    if (mime.includes("ogg")) return "ogg";
    return "webm";
  }

  function clearRecording({ keepStatus = false } = {}) {
    if (preview.src) {
      URL.revokeObjectURL(preview.src);
    }
    preview.removeAttribute("src");
    preview.hidden = true;
    recordedBlob = null;
    recordedMime = "";
    recordedChunks = [];
    clearRecordingBtn.hidden = true;
    if (!keepStatus) {
      recordStatus.textContent = "No recording yet";
      recordStatus.classList.remove("live");
    }
  }

  function stopMicTracks() {
    if (mediaStream) {
      for (const track of mediaStream.getTracks()) {
        track.stop();
      }
      mediaStream = null;
    }
  }

  function setRecordingUi(isRecording) {
    recordBtn.textContent = isRecording ? "Stop recording" : "Start recording";
    recordBtn.classList.toggle("recording", isRecording);
    fileInput.disabled = isRecording;
    submitBtn.disabled = isRecording;
    if (isRecording) {
      recordStatus.classList.add("live");
    } else {
      recordStatus.classList.remove("live");
    }
  }

  async function startRecording() {
    showError("");
    if (!window.isSecureContext) {
      throw new Error(
        "Microphone needs HTTPS or localhost. Use an SSH tunnel to http://127.0.0.1:3000/ or enable TLS."
      );
    }
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      throw new Error("This browser does not support microphone capture");
    }
    if (!window.MediaRecorder) {
      throw new Error("This browser does not support MediaRecorder");
    }

    clearRecording({ keepStatus: true });
    recordedMime = pickRecorderMime();
    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
      },
      video: false,
    });

    mediaRecorder = recordedMime
      ? new MediaRecorder(mediaStream, { mimeType: recordedMime })
      : new MediaRecorder(mediaStream);
    recordedMime = mediaRecorder.mimeType || recordedMime || "audio/webm";
    recordedChunks = [];
    recordStartedAt = Date.now();

    mediaRecorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) {
        recordedChunks.push(event.data);
      }
    };

    mediaRecorder.onerror = () => {
      showError("Recording failed");
      finishRecording(false);
    };

    mediaRecorder.onstop = () => {
      stopMicTracks();
      if (recordTick) {
        clearInterval(recordTick);
        recordTick = null;
      }
      if (!recordedChunks.length) {
        setRecordingUi(false);
        recordStatus.textContent = "Recording was empty";
        return;
      }
      recordedBlob = new Blob(recordedChunks, { type: recordedMime });
      const url = URL.createObjectURL(recordedBlob);
      preview.src = url;
      preview.hidden = false;
      clearRecordingBtn.hidden = false;
      fileInput.value = "";
      const seconds = Math.max(1, Math.round((Date.now() - recordStartedAt) / 1000));
      recordStatus.textContent = `Recorded ${seconds}s · ${(recordedBlob.size / 1024).toFixed(0)} KB`;
      setRecordingUi(false);
    };

    mediaRecorder.start(1000);
    setRecordingUi(true);
    recordStatus.textContent = "Recording… 0s";
    recordTick = setInterval(() => {
      const seconds = Math.floor((Date.now() - recordStartedAt) / 1000);
      recordStatus.textContent = `Recording… ${seconds}s`;
    }, 250);
  }

  function finishRecording(shouldStopRecorder) {
    if (recordTick) {
      clearInterval(recordTick);
      recordTick = null;
    }
    if (shouldStopRecorder && mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
      return;
    }
    stopMicTracks();
    setRecordingUi(false);
  }

  async function toggleRecording() {
    try {
      if (mediaRecorder && mediaRecorder.state === "recording") {
        finishRecording(true);
        return;
      }
      await startRecording();
    } catch (err) {
      stopMicTracks();
      setRecordingUi(false);
      const message = err && err.name === "NotAllowedError"
        ? "Microphone permission denied"
        : err.message || String(err);
      showError(message);
      recordStatus.textContent = "No recording yet";
    }
  }

  function selectedAudioFile() {
    if (recordedBlob) {
      const ext = extensionForMime(recordedMime);
      return new File([recordedBlob], `microphone.${ext}`, {
        type: recordedMime || "audio/webm",
      });
    }
    if (fileInput.files && fileInput.files[0]) {
      return fileInput.files[0];
    }
    return null;
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

  function rememberJob(jobId) {
    if (jobId) localStorage.setItem(JOB_STORAGE, jobId);
    else localStorage.removeItem(JOB_STORAGE);
  }

  function updateProgressFromJob(job) {
    const title = job.status === "queued"
      ? "Queued"
      : job.status === "processing"
        ? "Processing"
        : job.status === "completed"
          ? "Completed"
          : job.status;
    const base = job.progress_message || title;
    progressDetail.dataset.base = base;
    const elapsed = jobStartedAt ? ` · elapsed ${formatElapsed(Date.now() - jobStartedAt)}` : "";
    setProgress(job.progress ?? 0, `Job ${job.id}: ${title}`, `${base}${elapsed}`);
  }

  async function pollJob(apiKey, jobId) {
    const response = await fetch(`/v1/transcriptions/${jobId}`, {
      headers: authHeaders(apiKey),
    });
    if (!response.ok) {
      throw new Error(await readError(response));
    }
    const job = await response.json();
    updateProgressFromJob(job);

    if (job.status === "queued" || job.status === "processing") {
      pollTimer = setTimeout(() => {
        pollJob(apiKey, jobId).catch((err) => {
          submitBtn.disabled = false;
          rememberJob(null);
          showError(err.message || String(err));
        });
      }, 1500);
      return;
    }

    submitBtn.disabled = false;
    rememberJob(null);
    if (job.status === "failed") {
      showError(job.error || "Transcription failed");
      return;
    }

    setProgress(100, `Job ${job.id}: completed`, job.progress_message || "Done");
    if (job.diarization_error || job.summary_error) {
      const notes = [job.diarization_error, job.summary_error].filter(Boolean).join(" · ");
      progressDetail.dataset.base = notes;
      progressDetail.textContent = notes;
    }
    renderResult(job);
  }

  recordBtn.addEventListener("click", () => {
    toggleRecording();
  });

  clearRecordingBtn.addEventListener("click", () => {
    clearRecording();
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files[0]) {
      clearRecording();
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    stopPolling();
    showError("");
    resultsEl.hidden = true;
    copyBtn.hidden = true;
    lastPlainTranscript = "";

    if (mediaRecorder && mediaRecorder.state === "recording") {
      showError("Stop the recording before transcribing");
      return;
    }

    const apiKey = apiKeyInput.value.trim();
    if (!apiKey) {
      showError("API key is required");
      return;
    }
    const audioFile = selectedAudioFile();
    if (!audioFile) {
      showError("Choose a file or record from the microphone");
      return;
    }

    persistApiKey(apiKey);
    const body = new FormData();
    body.append("file", audioFile);
    body.append("summarize", summarizeInput.checked ? "true" : "false");
    body.append("diarize", diarizeInput.checked ? "true" : "false");
    const language = languageInput.value.trim();
    if (language) body.append("language", language);

    submitBtn.disabled = true;
    setProgress(2, "Uploading…", "Sending audio to the server");
    startElapsedClock();

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
      rememberJob(created.id);
      setProgress(5, `Job ${created.id}: queued`, "Waiting for the GPU worker");
      progressDetail.dataset.base = "Waiting for the GPU worker";
      await pollJob(apiKey, created.id);
    } catch (err) {
      submitBtn.disabled = false;
      rememberJob(null);
      hideProgress();
      showError(err.message || String(err));
    }
  });

  copyBtn.addEventListener("click", async () => {
    if (!lastPlainTranscript) return;
    try {
      await navigator.clipboard.writeText(lastPlainTranscript);
      progressDetail.textContent = "Transcript copied";
    } catch (_) {
      showError("Could not copy to clipboard");
    }
  });

  // Resume an in-flight job after refresh so progress is not lost.
  const existingJob = localStorage.getItem(JOB_STORAGE);
  const existingKey = readStoredKey();
  if (existingJob && existingKey) {
    submitBtn.disabled = true;
    startElapsedClock();
    setProgress(8, `Job ${existingJob}: resuming`, "Reconnecting to the running job");
    progressDetail.dataset.base = "Reconnecting to the running job";
    pollJob(existingKey, existingJob).catch((err) => {
      submitBtn.disabled = false;
      rememberJob(null);
      showError(err.message || String(err));
    });
  }
})();
