const el = (id) => document.getElementById(id);
const sourcesEl = el("sources");
const resultPanel = el("result-panel");
const shotsEl = el("shots");
const stepEl = el("job-step");
const metaEl = el("job-meta");
const progressBar = el("progress-bar");

let pollTimer = null;

const fmt = (s) => {
  const m = Math.floor(s / 60);
  const sec = (s % 60).toFixed(1).padStart(4, "0");
  return `${m}:${sec}`;
};

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

async function loadSources() {
  try {
    const { sources } = await api("/api/sources");
    if (!sources.length) {
      sourcesEl.innerHTML = `<p class="empty">ยังไม่มีไฟล์ใน media/input/</p>`;
      return;
    }
    sourcesEl.innerHTML = "";
    for (const s of sources) {
      const btn = document.createElement("button");
      btn.className = "source";
      btn.innerHTML = `<span class="source-name">${s.name}</span><span class="source-size">${s.size_mb} MB</span>`;
      btn.onclick = () => startJob(s.name);
      sourcesEl.appendChild(btn);
    }
  } catch (err) {
    sourcesEl.innerHTML = `<p class="error">โหลดรายชื่อไฟล์ไม่ได้: ${err.message}</p>`;
  }
}

async function startJob(name) {
  try {
    const job = await api(`/api/jobs?name=${encodeURIComponent(name)}`, { method: "POST" });
    watch(job.id);
  } catch (err) {
    showError(err.message);
  }
}

async function uploadFile(file) {
  const form = new FormData();
  form.append("file", file);
  stepEl.textContent = `กำลังอัปโหลด ${file.name}…`;
  resultPanel.hidden = false;
  try {
    const job = await api("/api/upload", { method: "POST", body: form });
    loadSources();
    watch(job.id);
  } catch (err) {
    showError(err.message);
  }
}

function showError(message) {
  resultPanel.hidden = false;
  stepEl.textContent = "";
  metaEl.innerHTML = `<p class="error">${message}</p>`;
  progressBar.style.width = "0%";
}

function watch(jobId) {
  clearInterval(pollTimer);
  resultPanel.hidden = false;
  shotsEl.innerHTML = "";
  metaEl.innerHTML = "";

  const tick = async () => {
    try {
      const job = await api(`/api/jobs/${jobId}`);
      render(job);
      if (job.status === "done" || job.status === "error") clearInterval(pollTimer);
    } catch (err) {
      clearInterval(pollTimer);
      showError(err.message);
    }
  };
  tick();
  pollTimer = setInterval(tick, 700);
}

function render(job) {
  progressBar.style.width = `${job.progress * 100}%`;
  progressBar.classList.toggle("error", job.status === "error");
  stepEl.textContent = job.step;

  if (job.error) {
    metaEl.innerHTML = `<p class="error">${job.error}</p>`;
    return;
  }
  if (job.info) {
    const i = job.info;
    const ratio = (i.width / i.height).toFixed(2);
    metaEl.innerHTML = `<strong>${job.name}</strong> · ${i.aspect} (${ratio}:1) · ${fmt(i.duration)} · ${i.fps} fps`;
  }

  // วาดใหม่เฉพาะการ์ดที่ยังไม่มี เพื่อไม่ให้ภาพกระพริบตอน poll
  for (const shot of job.shots) {
    let card = shotsEl.querySelector(`[data-shot="${shot.index}"]`);
    if (!card) {
      card = document.createElement("figure");
      card.className = "shot";
      card.dataset.shot = shot.index;
      shotsEl.appendChild(card);
    }
    const img = shot.thumbnail
      ? `<img src="${shot.thumbnail}" alt="ซีน ${shot.index + 1}" loading="lazy" />`
      : `<div class="thumb-missing">ไม่มีภาพ</div>`;
    const wanted = card.dataset.thumb || "";
    if (wanted !== (shot.thumbnail || "")) {
      card.dataset.thumb = shot.thumbnail || "";
      card.innerHTML = `${img}<figcaption>
        <span class="shot-no">ซีน ${shot.index + 1}</span>
        <span class="shot-time">${fmt(shot.start)} → ${fmt(shot.end)}</span>
        <span class="shot-dur">${shot.duration.toFixed(1)} วิ</span>
      </figcaption>`;
    }
  }
}

el("browse").onclick = () => el("file-input").click();
el("file-input").onchange = (e) => e.target.files[0] && uploadFile(e.target.files[0]);

const dz = el("dropzone");
dz.addEventListener("dragover", (e) => { e.preventDefault(); dz.classList.add("over"); });
dz.addEventListener("dragleave", () => dz.classList.remove("over"));
dz.addEventListener("drop", (e) => {
  e.preventDefault();
  dz.classList.remove("over");
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file);
});

loadSources();
