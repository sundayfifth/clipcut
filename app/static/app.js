/* clipcut — หน้าเว็บสำหรับน้องตัดต่อ
   สถานะเดินเป็น: ว่าง -> วิเคราะห์ -> ตรวจ/แก้ -> render -> เสร็จ
   poll ฝั่ง server เพราะงานรันใน thread แยกและกินเวลาเป็นนาที */

const el = (id) => document.getElementById(id);

const ui = {
  dropzone: el("dropzone"),
  fileInput: el("file-input"),
  browse: el("browse"),
  urlForm: el("url-form"),
  urlInput: el("url-input"),
  urlBtn: el("url-btn"),
  sensitivity: el("sensitivity"),
  sources: el("sources"),

  bandGroup: el("band-group"),
  bandTop: el("band-top"),
  bandBottom: el("band-bottom"),
  bandTopOut: el("band-top-out"),
  bandBottomOut: el("band-bottom-out"),
  bandApply: el("band-apply"),
  previewImg: el("preview-img"),
  preview: document.querySelector(".preview"),
  previewCaption: el("preview-caption"),

  empty: el("empty"),
  working: el("working"),
  jobStep: el("job-step"),
  jobMeta: el("job-meta"),
  jobProgress: el("job-progress"),
  skeletons: el("skeletons"),

  results: el("results"),
  resultsMeta: el("results-meta"),
  shots: el("shots"),
  errorNote: el("error-note"),

  actionbar: el("actionbar"),
  tally: el("tally"),
  renderBtn: el("render-btn"),
  renderStep: el("render-step"),
  renderTrack: el("render-track"),
  renderProgress: el("render-progress"),
  done: el("done"),
};

let jobId = null;
let poll = null;
let bandMode = "trim";
let previewTimer = null;
let lastShotKeys = new Map();

/* ── helpers ─────────────────────────────────────────── */

const pct = (v) => `${Math.round(v * 100)}%`;

const tc = (s) => {
  const m = Math.floor(s / 60);
  return `${m}:${(s % 60).toFixed(1).padStart(4, "0")}`;
};

function setFill(node, value) {
  node.style.transform = `scaleX(${Math.max(0, Math.min(1, value))})`;
}

async function api(path, opts) {
  const res = await fetch(path, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `${res.status} ${res.statusText}`);
  }
  return res.json();
}

function showError(message) {
  ui.errorNote.hidden = false;
  ui.errorNote.textContent = message;
}

function clearError() {
  ui.errorNote.hidden = true;
  ui.errorNote.textContent = "";
}

function showSkeletons(n = 8) {
  ui.skeletons.innerHTML = "";
  for (let i = 0; i < n; i += 1) {
    const s = document.createElement("div");
    s.className = "skeleton";
    ui.skeletons.appendChild(s);
  }
}

/* ── รายการไฟล์ ──────────────────────────────────────── */

async function loadSources(activeName) {
  try {
    const { sources } = await api("/api/sources");
    ui.sources.innerHTML = "";
    if (!sources.length) {
      const p = document.createElement("p");
      p.className = "sources-empty";
      p.textContent = "ยังไม่มีไฟล์ใน media/input/";
      ui.sources.appendChild(p);
      return;
    }
    for (const s of sources) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "source";
      btn.setAttribute("role", "listitem");
      if (s.name === activeName) btn.setAttribute("aria-current", "true");
      btn.innerHTML =
        `<span class="source-name"></span><span class="source-size">${s.size_mb} MB</span>`;
      btn.querySelector(".source-name").textContent = s.name;
      btn.onclick = () => startJob(s.name);
      ui.sources.appendChild(btn);
    }
  } catch (err) {
    showError(`โหลดรายชื่อไฟล์ไม่ได้: ${err.message}`);
  }
}

/* ── เริ่มงาน ────────────────────────────────────────── */

function enterWorking() {
  clearError();
  ui.empty.hidden = true;
  ui.results.hidden = true;
  ui.working.hidden = false;
  ui.actionbar.hidden = true;
  ui.bandGroup.hidden = true;
  ui.done.hidden = true;
  ui.renderTrack.hidden = true;
  ui.shots.innerHTML = "";
  lastShotKeys = new Map();
  showSkeletons();
  setFill(ui.jobProgress, 0);
}

async function startJob(name) {
  enterWorking();
  ui.jobStep.textContent = "กำลังเริ่มวิเคราะห์";
  try {
    const job = await api(
      `/api/jobs?name=${encodeURIComponent(name)}&sensitivity=${ui.sensitivity.value}`,
      { method: "POST" },
    );
    loadSources(name);
    watch(job.id);
  } catch (err) {
    ui.working.hidden = true;
    ui.empty.hidden = false;
    showError(err.message);
  }
}

async function uploadFile(file) {
  enterWorking();
  ui.jobStep.textContent = `กำลังอัปโหลด ${file.name}`;
  const form = new FormData();
  form.append("file", file);
  try {
    const job = await api(`/api/upload?sensitivity=${ui.sensitivity.value}`, {
      method: "POST",
      body: form,
    });
    loadSources(job.name);
    watch(job.id);
  } catch (err) {
    ui.working.hidden = true;
    ui.empty.hidden = false;
    showError(err.message);
  }
}

async function loadUrl(url) {
  enterWorking();
  ui.jobStep.textContent = "กำลังโหลดคลิปจาก YouTube";
  ui.urlBtn.disabled = true;
  try {
    const job = await api(
      `/api/youtube?url=${encodeURIComponent(url)}&sensitivity=${ui.sensitivity.value}`,
      { method: "POST" },
    );
    ui.urlInput.value = "";
    watch(job.id);
  } catch (err) {
    ui.working.hidden = true;
    ui.empty.hidden = false;
    showError(err.message);
  } finally {
    ui.urlBtn.disabled = false;
  }
}

/* ── ติดตามสถานะ ─────────────────────────────────────── */

function watch(id) {
  clearInterval(poll);
  jobId = id;
  const tick = async () => {
    try {
      const job = await api(`/api/jobs/${id}`);
      draw(job);
      if (["ready", "done", "error"].includes(job.status)) {
        clearInterval(poll);
        if (job.status === "ready") loadSources(job.name);
      }
    } catch (err) {
      clearInterval(poll);
      showError(err.message);
    }
  };
  tick();
  poll = setInterval(tick, 700);
}

function draw(job) {
  setFill(ui.jobProgress, job.progress);
  ui.jobProgress.classList.toggle("is-error", job.status === "error");
  ui.jobStep.textContent = job.step;

  if (job.info) {
    const i = job.info;
    ui.jobMeta.textContent =
      `${job.name} · ${i.aspect} · ${tc(i.duration)} · ${i.fps} fps`;
  }

  if (job.status === "error") {
    ui.working.hidden = true;
    showError(job.error || "เกิดข้อผิดพลาด");
    return;
  }

  const reviewable = job.status === "ready" || job.status === "done" || job.status === "rendering";
  if (!reviewable) return;

  ui.working.hidden = true;
  ui.results.hidden = false;
  ui.actionbar.hidden = false;
  ui.bandGroup.hidden = false;

  if (job.bands) syncBandInputs(job.bands);
  if (!ui.previewImg.getAttribute("src")) refreshPreview();

  const i = job.info;
  ui.resultsMeta.textContent =
    `${job.name} · ${i.aspect} · ${tc(i.duration)} · ${i.fps} fps`;

  drawTally(job.summary);
  drawShots(job);
}

function drawTally(summary) {
  if (!summary) return;
  ui.tally.innerHTML =
    `<span class="chip">เลือก ${summary.included}/${summary.total} ซีน</span>` +
    `<span class="chip chip-crop">crop ${summary.crop}</span>` +
    `<span class="chip chip-pad">ย่อ+พื้นหลัง ${summary.pad}</span>` +
    `<span class="chip">${tc(summary.duration)}</span>`;
  ui.renderBtn.disabled = summary.included === 0;
}

function drawShots(job) {
  const src = job.info;
  for (const shot of job.shots) {
    const p = shot.plan;
    const key = [
      shot.thumbnail || "",
      p ? p.mode : "",
      p ? p.included : "",
      p && p.crop ? `${p.crop.x}:${p.crop.w}` : "",
      job.bands ? `${job.bands.top}:${job.bands.bottom}:${job.bands.mode}` : "",
    ].join("|");
    if (lastShotKeys.get(shot.index) === key) continue;
    lastShotKeys.set(shot.index, key);

    let card = ui.shots.querySelector(`[data-shot="${shot.index}"]`);
    if (!card) {
      card = document.createElement("figure");
      card.className = "shot";
      card.dataset.shot = shot.index;
      ui.shots.appendChild(card);
    }

    const included = !p || p.included !== false;
    card.dataset.included = String(included);

    const media = shot.thumbnail
      ? `<img src="${shot.thumbnail}" alt="ซีน ${shot.index + 1}" loading="lazy" />`
      : `<div class="thumb-missing">ไม่มีภาพ</div>`;

    card.innerHTML = `
      <label class="shot-pick">
        <input type="checkbox" data-index="${shot.index}" ${included ? "checked" : ""} />
        ${media}
        ${frameOverlay(p, src, job.bands)}
        <span class="tick" aria-hidden="true">✓</span>
      </label>
      <div class="shot-body">
        <div class="shot-line">
          <span class="shot-no">ซีน ${shot.index + 1}</span>
          <span>${tc(shot.start)} → ${tc(shot.end)}</span>
          <span class="shot-dur">${shot.duration.toFixed(1)} วิ</span>
        </div>
        ${modeButton(shot.index, p)}
        ${p ? `<p class="reason">${p.reason}</p>` : ""}
      </div>`;
  }
}

/* กรอบที่จะถูกเก็บจริง วาดทับ thumbnail — เห็นเลยว่าอะไรจะหาย */
function frameOverlay(plan, src, bands) {
  if (!plan || !src) return "";
  const pieces = [];

  if (bands && (bands.top > 0 || bands.bottom > 0)) {
    if (bands.top > 0) {
      pieces.push(`<span class="frame-band" style="top:0;height:${bands.top * 100}%"></span>`);
    }
    if (bands.bottom > 0) {
      pieces.push(`<span class="frame-band" style="bottom:0;height:${bands.bottom * 100}%"></span>`);
    }
  }

  if (plan.mode === "crop" && plan.crop) {
    const left = (plan.crop.x / src.width) * 100;
    const width = (plan.crop.w / src.width) * 100;
    pieces.push(
      `<span class="frame-keep" style="left:${left}%;width:${width}%"></span>`,
    );
  }

  return pieces.length ? `<span class="frame">${pieces.join("")}</span>` : "";
}

function modeButton(index, plan) {
  if (!plan) return "";
  const isCrop = plan.mode === "crop";
  return `<button type="button" class="mode ${isCrop ? "mode-crop" : "mode-pad"}"
      data-index="${index}" data-mode="${isCrop ? "pad" : "crop"}"
      title="กดเพื่อสลับเป็น${isCrop ? "ย่อ+เติมพื้นหลัง" : "crop"}"
    >${isCrop ? "crop" : "ย่อ+เติมพื้นหลัง"}</button>`;
}

/* ── แถบซับ ──────────────────────────────────────────── */

function syncBandInputs(bands) {
  if (document.activeElement !== ui.bandTop) {
    ui.bandTop.value = String(Math.round(bands.top * 100));
  }
  if (document.activeElement !== ui.bandBottom) {
    ui.bandBottom.value = String(Math.round(bands.bottom * 100));
  }
  bandMode = bands.mode;
  for (const btn of document.querySelectorAll("[data-band-mode]")) {
    btn.classList.toggle("is-on", btn.dataset.bandMode === bandMode);
  }
  updateBandOutputs();
}

function updateBandOutputs() {
  ui.bandTopOut.textContent = `${ui.bandTop.value}%`;
  ui.bandBottomOut.textContent = `${ui.bandBottom.value}%`;
}

function refreshPreview() {
  if (!jobId) return;
  const top = Number(ui.bandTop.value) / 100;
  const bottom = Number(ui.bandBottom.value) / 100;
  const at = 8; // เอาเฟรมช่วงต้นคลิป มักมีซับขึ้นแล้ว
  ui.previewImg.src =
    `/api/jobs/${jobId}/preview?at=${at}&top=${top}&bottom=${bottom}&mode=${bandMode}` +
    `&_=${Date.now()}`;
  ui.preview.dataset.state = "loaded";
  ui.previewCaption.textContent =
    top || bottom
      ? `${bandMode === "trim" ? "ตัดทิ้ง" : "เบลอทับ"} บน ${ui.bandTop.value}% ล่าง ${ui.bandBottom.value}%`
      : "ยังไม่ได้ตัดแถบ";
}

function schedulePreview() {
  updateBandOutputs();
  clearTimeout(previewTimer);
  previewTimer = setTimeout(refreshPreview, 220);
}

async function applyBands() {
  if (!jobId) return;
  ui.bandApply.disabled = true;
  ui.bandApply.textContent = "กำลังคำนวณใหม่";
  try {
    const job = await api(
      `/api/jobs/${jobId}/bands?top=${Number(ui.bandTop.value) / 100}` +
      `&bottom=${Number(ui.bandBottom.value) / 100}&mode=${bandMode}`,
      { method: "POST" },
    );
    lastShotKeys = new Map();
    draw(job);
  } catch (err) {
    showError(err.message);
  } finally {
    ui.bandApply.disabled = false;
    ui.bandApply.textContent = "ใช้ค่านี้แล้วคำนวณใหม่";
  }
}

/* ── การกระทำบนการ์ด ─────────────────────────────────── */

ui.shots.addEventListener("click", async (e) => {
  const btn = e.target.closest(".mode");
  if (!btn || !jobId) return;
  e.preventDefault();
  btn.disabled = true;
  try {
    draw(await api(
      `/api/jobs/${jobId}/shots/${btn.dataset.index}/mode?mode=${btn.dataset.mode}`,
      { method: "POST" },
    ));
  } catch (err) {
    showError(err.message);
    btn.disabled = false;
  }
});

ui.shots.addEventListener("change", async (e) => {
  const box = e.target.closest('input[type="checkbox"]');
  if (!box || !jobId) return;
  try {
    draw(await api(
      `/api/jobs/${jobId}/shots/${box.dataset.index}/included?included=${box.checked}`,
      { method: "POST" },
    ));
  } catch (err) {
    showError(err.message);
    box.checked = !box.checked;
  }
});

for (const btn of document.querySelectorAll("[data-select]")) {
  btn.onclick = async () => {
    if (!jobId) return;
    const want = btn.dataset.select === "all";
    btn.disabled = true;
    try {
      const boxes = [...ui.shots.querySelectorAll('input[type="checkbox"]')];
      let job = null;
      for (const box of boxes) {
        if (box.checked === want) continue;
        job = await api(
          `/api/jobs/${jobId}/shots/${box.dataset.index}/included?included=${want}`,
          { method: "POST" },
        );
      }
      if (job) draw(job);
    } catch (err) {
      showError(err.message);
    } finally {
      btn.disabled = false;
    }
  };
}

/* ── render ──────────────────────────────────────────── */

ui.renderBtn.onclick = async () => {
  if (!jobId) return;
  clearError();
  ui.renderBtn.disabled = true;
  ui.done.hidden = true;
  ui.renderTrack.hidden = false;
  setFill(ui.renderProgress, 0);
  try {
    await api(`/api/jobs/${jobId}/render`, { method: "POST" });
  } catch (err) {
    showError(err.message);
    ui.renderBtn.disabled = false;
    return;
  }

  clearInterval(poll);
  poll = setInterval(async () => {
    let job;
    try {
      job = await api(`/api/jobs/${jobId}`);
    } catch (err) {
      clearInterval(poll);
      showError(err.message);
      ui.renderBtn.disabled = false;
      return;
    }
    setFill(ui.renderProgress, job.progress);
    ui.renderStep.textContent = job.step;

    if (job.status === "done") {
      clearInterval(poll);
      ui.renderBtn.disabled = false;
      ui.renderStep.textContent = "";
      ui.done.hidden = false;
      ui.done.innerHTML =
        `<a href="/api/jobs/${job.id}/output">ดาวน์โหลดไฟล์ 9:16</a>` +
        `<a href="/api/jobs/${job.id}/checklist">checklist กราฟฟิก</a>` +
        `<span class="path"></span>`;
      ui.done.querySelector(".path").textContent = job.output;
    } else if (job.status === "error") {
      clearInterval(poll);
      ui.renderBtn.disabled = false;
      ui.renderStep.textContent = "";
      showError(job.error || "render ไม่สำเร็จ");
    }
  }, 700);
};

/* ── ผูก event ───────────────────────────────────────── */

ui.browse.onclick = () => ui.fileInput.click();
ui.fileInput.onchange = (e) => e.target.files[0] && uploadFile(e.target.files[0]);

ui.urlForm.onsubmit = (e) => {
  e.preventDefault();
  const url = ui.urlInput.value.trim();
  if (url) loadUrl(url);
};

ui.dropzone.addEventListener("dragover", (e) => {
  e.preventDefault();
  ui.dropzone.classList.add("is-over");
});
ui.dropzone.addEventListener("dragleave", () => ui.dropzone.classList.remove("is-over"));
ui.dropzone.addEventListener("drop", (e) => {
  e.preventDefault();
  ui.dropzone.classList.remove("is-over");
  const file = e.dataTransfer.files[0];
  if (file) uploadFile(file);
});

ui.bandTop.addEventListener("input", schedulePreview);
ui.bandBottom.addEventListener("input", schedulePreview);
ui.bandApply.onclick = applyBands;

for (const btn of document.querySelectorAll("[data-band-mode]")) {
  btn.onclick = () => {
    bandMode = btn.dataset.bandMode;
    for (const other of document.querySelectorAll("[data-band-mode]")) {
      other.classList.toggle("is-on", other === btn);
    }
    refreshPreview();
  };
}

ui.preview.dataset.state = "empty";
loadSources();
