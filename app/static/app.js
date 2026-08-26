const el = (id) => document.getElementById(id);
const sourcesEl = el("sources");
const resultPanel = el("result-panel");
const shotsEl = el("shots");
const stepEl = el("job-step");
const metaEl = el("job-meta");
const progressBar = el("progress-bar");
const summaryEl = el("summary");
const renderPanel = el("render-panel");
const renderBtn = el("render-btn");
const renderStep = el("render-step");
const renderProgressWrap = el("render-progress-wrap");
const renderProgress = el("render-progress");
const renderResult = el("render-result");

let currentJobId = null;

let pollTimer = null;

const sensitivity = () => el("sensitivity").value;

const LEVEL_LABEL = {
  coarse: "หยาบ",
  normal: "ปกติ",
  fine: "ละเอียด",
  finest: "ละเอียดมาก",
};

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
    const job = await api(
      `/api/jobs?name=${encodeURIComponent(name)}&sensitivity=${sensitivity()}`,
      { method: "POST" },
    );
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
    const job = await api(`/api/upload?sensitivity=${sensitivity()}`, { method: "POST", body: form });
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
  currentJobId = jobId;
  resultPanel.hidden = false;
  renderPanel.hidden = true;
  summaryEl.hidden = true;
  renderResult.textContent = "";
  renderStep.textContent = "";
  renderProgressWrap.hidden = true;
  shotsEl.innerHTML = "";
  metaEl.innerHTML = "";

  const tick = async () => {
    try {
      const job = await api(`/api/jobs/${jobId}`);
      render(job);
      if (["ready", "done", "error"].includes(job.status)) clearInterval(pollTimer);
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
    const level = LEVEL_LABEL[job.sensitivity] || job.sensitivity;
    metaEl.innerHTML =
      `<strong>${job.name}</strong> · ${i.aspect} (${ratio}:1) · ${fmt(i.duration)} · ${i.fps} fps` +
      ` · <span class="level">แบ่งแบบ${level}</span>`;
  }

  if (job.summary) {
    summaryEl.hidden = false;
    summaryEl.innerHTML =
      `<span class="pill pill-crop">crop ${job.summary.crop} ซีน</span>` +
      `<span class="pill pill-pad">ย่อ+เติมพื้นหลัง ${job.summary.pad} ซีน</span>`;
  }
  if (["ready", "done"].includes(job.status)) {
    renderPanel.hidden = false;
    renderBtn.disabled = false;
  }

  // วาดใหม่เฉพาะการ์ดที่เปลี่ยน เพื่อไม่ให้ภาพกระพริบตอน poll
  for (const shot of job.shots) {
    let card = shotsEl.querySelector(`[data-shot="${shot.index}"]`);
    if (!card) {
      card = document.createElement("figure");
      card.className = "shot";
      card.dataset.shot = shot.index;
      shotsEl.appendChild(card);
    }
    const p = shot.plan;
    const key = `${shot.thumbnail || ""}|${p ? p.mode : ""}`;
    if (card.dataset.key === key) continue;
    card.dataset.key = key;

    const img = shot.thumbnail
      ? `<img src="${shot.thumbnail}" alt="ซีน ${shot.index + 1}" loading="lazy" />`
      : `<div class="thumb-missing">ไม่มีภาพ</div>`;

    let decision = "";
    if (p) {
      const isCrop = p.mode === "crop";
      decision = `<div class="decision">
        <button type="button" class="mode ${isCrop ? "mode-crop" : "mode-pad"}"
                data-index="${shot.index}" data-mode="${isCrop ? "pad" : "crop"}"
                title="กดเพื่อสลับ">${isCrop ? "crop" : "ย่อ+เติมพื้นหลัง"}</button>
        <span class="reason">${p.reason}</span>
      </div>`;
    }

    card.innerHTML = `${img}<figcaption>
      <span class="shot-no">ซีน ${shot.index + 1}</span>
      <span class="shot-time">${fmt(shot.start)} → ${fmt(shot.end)}</span>
      <span class="shot-dur">${shot.duration.toFixed(1)} วิ</span>
    </figcaption>${decision}`;
  }
}

shotsEl.addEventListener("click", async (e) => {
  const btn = e.target.closest(".mode");
  if (!btn || !currentJobId) return;
  btn.disabled = true;
  try {
    const job = await api(
      `/api/jobs/${currentJobId}/shots/${btn.dataset.index}/mode?mode=${btn.dataset.mode}`,
      { method: "POST" },
    );
    render(job);
  } catch (err) {
    showError(err.message);
  }
});

renderBtn.onclick = async () => {
  if (!currentJobId) return;
  renderBtn.disabled = true;
  renderResult.textContent = "";
  renderProgressWrap.hidden = false;
  try {
    await api(`/api/jobs/${currentJobId}/render`, { method: "POST" });
  } catch (err) {
    showError(err.message);
    return;
  }
  clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    const job = await api(`/api/jobs/${currentJobId}`);
    renderProgress.style.width = `${job.progress * 100}%`;
    renderStep.textContent = job.step;
    if (job.status === "done") {
      clearInterval(pollTimer);
      renderBtn.disabled = false;
      renderResult.innerHTML =
        `เสร็จแล้ว — <a href="/api/jobs/${job.id}/output">ดาวน์โหลดไฟล์</a>` +
        `<br /><span class="path">${job.output}</span>`;
    } else if (job.status === "error") {
      clearInterval(pollTimer);
      renderBtn.disabled = false;
      renderResult.innerHTML = `<span class="error">${job.error}</span>`;
    }
  }, 700);
};

el("sensitivity").onchange = () => {
  // ถ้าเพิ่งวิเคราะห์ไฟล์ไหนไป ให้ลองระดับใหม่กับไฟล์เดิมเลย
  const current = document.querySelector(".meta strong");
  if (current) startJob(current.textContent);
};

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
