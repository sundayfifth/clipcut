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
  filterEmpty: el("filter-empty"),
};

let jobId = null;
let poll = null;
let bandMode = "trim";
let previewTimer = null;
let lastShotKeys = new Map();
let view = "result";   // result = พรีวิว 9:16 · source = ภาพต้นฉบับพร้อมกรอบ
let filter = "all";
let lastJob = null;

const MODE_LABEL = { crop: "เต็มจอ", pad: "ย่อทั้งภาพ" };

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

  lastJob = job;
  drawTally(job.summary);
  drawShots(job);
  applyFilter();
}

function drawTally(summary) {
  if (!summary) return;
  ui.tally.innerHTML =
    `<span class="chip">เลือก ${summary.included}/${summary.total} ซีน</span>` +
    `<span class="chip chip-crop">เต็มจอ ${summary.crop}</span>` +
    `<span class="chip chip-pad">ย่อทั้งภาพ ${summary.pad}</span>` +
    `<span class="chip">${tc(summary.duration)}</span>`;
  ui.renderBtn.disabled = summary.included === 0;
}

function drawShots(job) {
  const src = job.info;
  for (const shot of job.shots) {
    const p = shot.plan;
    const key = [
      view, shot.thumbnail || "",
      p ? `${p.mode}|${p.included}` : "",
      p && p.crop ? `${p.crop.x}:${p.crop.y}:${p.crop.w}:${p.crop.h}` : "",
      p && p.adjust ? `${p.adjust.dx}:${p.adjust.dy}:${p.adjust.scale}` : "",
      job.bands ? `${job.bands.top}:${job.bands.bottom}:${job.bands.mode}` : "",
    ].join("|");
    if (lastShotKeys.get(shot.index) === key) continue;

    let card = ui.shots.querySelector(`[data-shot="${shot.index}"]`);
    // กำลังลากสไลเดอร์ในการ์ดนี้อยู่ อย่าเพิ่งวาดทับ ค่าจะกระตุก
    if (card && card.contains(document.activeElement) &&
        document.activeElement.tagName === "INPUT" &&
        document.activeElement.type === "range") continue;
    lastShotKeys.set(shot.index, key);
    if (!card) {
      card = document.createElement("figure");
      card.className = "shot";
      card.dataset.shot = shot.index;
      card.tabIndex = 0;
      ui.shots.appendChild(card);
    }

    const included = !p || p.included !== false;
    card.dataset.included = String(included);
    card.dataset.mode = p ? p.mode : "";
    card.setAttribute(
      "aria-label",
      `ซีน ${shot.index + 1} ${p ? MODE_LABEL[p.mode] : ""} ${included ? "เลือกอยู่" : "ไม่ได้เลือก"}`,
    );

    card.innerHTML = `
      <label class="shot-pick shot-media">
        <input type="checkbox" data-index="${shot.index}" ${included ? "checked" : ""} />
        ${mediaFor(shot, p, src, job.bands)}
        <span class="tick" aria-hidden="true">✓</span>
      </label>
      <div class="shot-body">
        <div class="shot-line">
          <span class="shot-no">ซีน ${shot.index + 1}</span>
          <span>${tc(shot.start)} → ${tc(shot.end)}</span>
          <span class="shot-dur">${shot.duration.toFixed(1)} วิ</span>
        </div>
        ${p ? modeSwitch(shot.index, p.mode) : ""}
        ${p ? tuneControls(shot.index, p) : ""}
        ${p ? `<p class="reason">${p.reason}</p>` : ""}
      </div>`;
  }
}

/* ภาพในการ์ด — สลับได้ระหว่างต้นฉบับ (เห็นว่าจะเสียอะไร) กับผลลัพธ์จริง 9:16 */
function mediaFor(shot, plan, src, bands) {
  if (!shot.thumbnail) return `<div class="thumb-missing">ไม่มีภาพ</div>`;
  if (view === "source" || !plan || !src) {
    return `<img src="${shot.thumbnail}" alt="ซีน ${shot.index + 1}" loading="lazy" />` +
      frameOverlay(plan, src, bands);
  }
  return plan.mode === "crop" ? cropPreview(shot, plan, src) : padPreview(shot, src, bands);
}

/* crop: ขยายภาพให้กรอบที่เลือกไว้เต็มกล่อง 9:16 พอดี */
function cropPreview(shot, plan, src) {
  const c = plan.crop;
  const style = [
    `width:${(src.width / c.w) * 100}%`,
    `height:${(src.height / c.h) * 100}%`,
    `left:${(-c.x / c.w) * 100}%`,
    `top:${(-c.y / c.h) * 100}%`,
  ].join(";");
  return `<div class="frame916 frame916-crop">
    <img src="${shot.thumbnail}" alt="ผลลัพธ์ซีน ${shot.index + 1}" loading="lazy" style="${style}" />
  </div>`;
}

/* pad: ภาพเต็มกว้างวางกลาง พื้นหลังเบลอ ตรงกับที่ ffmpeg เรนเดอร์จริง */
function padPreview(shot, src, bands) {
  // โหมดตัดแถบทำให้ภาพที่เหลือเตี้ยลง กล่องที่วางกลางจึงเตี้ยตาม
  const top = bands && bands.mode === "trim" ? bands.top : 0;
  const bottom = bands && bands.mode === "trim" ? bands.bottom : 0;
  const keep = Math.max(0.05, 1 - top - bottom);
  const visibleRatio = src.width / (src.height * keep);
  const fgHeightPct = ((9 / 16) / visibleRatio) * 100;

  return `<div class="frame916 frame916-pad">
    <img class="bg" src="${shot.thumbnail}" alt="" aria-hidden="true" loading="lazy" />
    <span class="fg" style="top:${(100 - fgHeightPct) / 2}%;height:${fgHeightPct}%">
      <img src="${shot.thumbnail}" alt="ผลลัพธ์ซีน ${shot.index + 1}" loading="lazy"
           style="left:0;width:100%;height:${(1 / keep) * 100}%;top:${(-top / keep) * 100}%" />
    </span>
  </div>`;
}

/* กรอบที่จะถูกเก็บจริง วาดทับภาพต้นฉบับ */
function frameOverlay(plan, src, bands) {
  if (!plan || !src) return "";
  const pieces = [];
  if (bands && bands.top > 0) {
    pieces.push(`<span class="frame-band" style="top:0;height:${bands.top * 100}%"></span>`);
  }
  if (bands && bands.bottom > 0) {
    pieces.push(`<span class="frame-band" style="bottom:0;height:${bands.bottom * 100}%"></span>`);
  }
  if (plan.mode === "crop" && plan.crop) {
    pieces.push(
      `<span class="frame-keep" style="left:${(plan.crop.x / src.width) * 100}%;` +
      `width:${(plan.crop.w / src.width) * 100}%"></span>`,
    );
  }
  return pieces.length ? `<span class="frame">${pieces.join("")}</span>` : "";
}

const MIN_SCALE = 0.4;

/* ตรงกับ derive_crop ใน app/plan.py — ถ้าแก้ฝั่งใดต้องแก้ให้ตรงกัน */
function deriveCrop(base, adjust, src) {
  const a = { dx: 0, dy: 0, scale: 1, ...(adjust || {}) };
  const w = base.w * a.scale;
  const h = base.h * a.scale;
  const centerX = base.center_x + a.dx * base.w;
  const left = Math.max(0, Math.min(centerX - w / 2, src.width - w));
  const centerY = base.y + base.h / 2 + a.dy * base.h / 2;
  const top = Math.max(base.y, Math.min(centerY - h / 2, base.y + base.h - h));
  return { x: Math.round(left), y: Math.round(top), w: Math.round(w), h: Math.round(h) };
}

function tuneControls(index, plan) {
  if (plan.mode !== "crop" || !plan.crop_base) return "";
  const a = { dx: 0, dy: 0, scale: 1, ...(plan.adjust || {}) };
  const zoomed = a.scale < 0.999;
  const touched = a.dx !== 0 || a.dy !== 0 || zoomed;
  return `<div class="tune" data-index="${index}">
    <label class="tune-row"><span>เลื่อน</span>
      <input type="range" data-axis="dx" min="-100" max="100" step="1"
             value="${Math.round(a.dx * 100)}" aria-label="เลื่อนกรอบซ้ายขวา" /></label>
    <label class="tune-row"><span>ซูม</span>
      <input type="range" data-axis="scale" min="40" max="100" step="1"
             value="${Math.round(a.scale * 100)}" aria-label="ย่อขยายกรอบ" /></label>
    <label class="tune-row" ${zoomed ? "" : "hidden"}><span>ขึ้นลง</span>
      <input type="range" data-axis="dy" min="-100" max="100" step="1"
             value="${Math.round(a.dy * 100)}" aria-label="เลื่อนกรอบขึ้นลง" /></label>
    <button type="button" class="tune-reset" ${touched ? "" : "hidden"}>คืนค่าอัตโนมัติ</button>
  </div>`;
}

function readTune(node) {
  const get = (axis) => Number(node.querySelector(`[data-axis="${axis}"]`).value);
  return { dx: get("dx") / 100, dy: get("dy") / 100, scale: get("scale") / 100 };
}

function modeSwitch(index, mode) {
  return `<div class="switch" role="group" aria-label="วิธีแปลงซีนนี้">` +
    ["crop", "pad"].map((m) =>
      `<button type="button" data-index="${index}" data-mode="${m}" ` +
      `aria-pressed="${mode === m}">${MODE_LABEL[m]}</button>`).join("") +
    `</div>`;
}

function applyFilter() {
  let shown = 0;
  for (const card of ui.shots.querySelectorAll(".shot")) {
    const ok =
      filter === "all" ? true :
      filter === "off" ? card.dataset.included !== "true" :
      card.dataset.mode === filter;
    card.hidden = !ok;
    if (ok) shown += 1;
  }
  ui.filterEmpty.hidden = shown > 0;
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

async function setMode(index, mode) {
  if (!jobId) return;
  try {
    draw(await api(`/api/jobs/${jobId}/shots/${index}/mode?mode=${mode}`, { method: "POST" }));
  } catch (err) {
    showError(err.message);
  }
}

async function setIncluded(index, included) {
  if (!jobId) return;
  try {
    draw(await api(
      `/api/jobs/${jobId}/shots/${index}/included?included=${included}`,
      { method: "POST" },
    ));
  } catch (err) {
    showError(err.message);
  }
}

ui.shots.addEventListener("click", (e) => {
  const btn = e.target.closest(".switch button");
  if (!btn) return;
  e.preventDefault();
  if (btn.getAttribute("aria-pressed") !== "true") setMode(btn.dataset.index, btn.dataset.mode);
});

ui.shots.addEventListener("change", (e) => {
  const box = e.target.closest('input[type="checkbox"]');
  if (box) setIncluded(box.dataset.index, box.checked);
});

/* ลากสไลเดอร์ = พรีวิวขยับทันที (คำนวณฝั่ง client) ปล่อยเมื่อไหร่ค่อยส่งขึ้น server */
async function commitTune(tune) {
  const a = readTune(tune);
  try {
    draw(await api(
      `/api/jobs/${jobId}/shots/${tune.dataset.index}/crop` +
      `?dx=${a.dx}&dy=${a.dy}&scale=${a.scale}`,
      { method: "POST" },
    ));
  } catch (err) {
    showError(err.message);
  }
}

ui.shots.addEventListener("input", (e) => {
  const slider = e.target.closest('.tune input[type="range"]');
  if (!slider || !lastJob) return;
  const tune = slider.closest(".tune");
  const card = tune.closest(".shot");
  const index = Number(tune.dataset.index);
  const plan = (lastJob.shots.find((s) => s.index === index) || {}).plan;
  if (!plan || !plan.crop_base) return;

  const adjust = readTune(tune);
  // ซูมออกสุดแล้วไม่มีที่ให้ขยับขึ้นลง ซ่อนสไลเดอร์นั้นไว้
  tune.querySelectorAll(".tune-row")[2].hidden = adjust.scale >= 0.999;
  tune.querySelector(".tune-reset").hidden =
    adjust.dx === 0 && adjust.dy === 0 && adjust.scale >= 0.999;

  const crop = deriveCrop(plan.crop_base, adjust, lastJob.info);
  const img = card.querySelector(".frame916-crop img");
  if (img) {
    const src = lastJob.info;
    img.style.width = `${(src.width / crop.w) * 100}%`;
    img.style.height = `${(src.height / crop.h) * 100}%`;
    img.style.left = `${(-crop.x / crop.w) * 100}%`;
    img.style.top = `${(-crop.y / crop.h) * 100}%`;
  }
  const keep = card.querySelector(".frame-keep");
  if (keep) {
    keep.style.left = `${(crop.x / lastJob.info.width) * 100}%`;
    keep.style.width = `${(crop.w / lastJob.info.width) * 100}%`;
  }
});

ui.shots.addEventListener("change", (e) => {
  const slider = e.target.closest('.tune input[type="range"]');
  if (slider && jobId) commitTune(slider.closest(".tune"));
});

ui.shots.addEventListener("click", (e) => {
  const reset = e.target.closest(".tune-reset");
  if (!reset || !jobId) return;
  const tune = reset.closest(".tune");
  tune.querySelector('[data-axis="dx"]').value = "0";
  tune.querySelector('[data-axis="dy"]').value = "0";
  tune.querySelector('[data-axis="scale"]').value = "100";
  commitTune(tune);
});

/* คีย์ลัด — งานนี้ต้องไล่ตรวจ 40 กว่าซีนต่อคลิป การใช้เมาส์อย่างเดียวช้าเกินไป */
ui.shots.addEventListener("keydown", (e) => {
  const card = e.target.closest(".shot");
  if (!card || e.metaKey || e.ctrlKey || e.altKey) return;
  const index = card.dataset.shot;
  const key = e.key.toLowerCase();

  if (e.key === " ") {
    e.preventDefault();
    setIncluded(index, card.dataset.included !== "true");
  } else if (key === "c" || key === "p") {
    e.preventDefault();
    setMode(index, key === "c" ? "crop" : "pad");
  } else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    const cards = [...ui.shots.querySelectorAll(".shot:not([hidden])")];
    const next = cards[cards.indexOf(card) + (e.key === "ArrowRight" ? 1 : -1)];
    if (next) { e.preventDefault(); next.focus(); }
  }
});

for (const btn of document.querySelectorAll("[data-view]")) {
  btn.onclick = () => {
    view = btn.dataset.view;
    for (const other of document.querySelectorAll("[data-view]")) {
      other.classList.toggle("is-on", other === btn);
    }
    lastShotKeys = new Map();
    if (lastJob) draw(lastJob);
  };
}

for (const btn of document.querySelectorAll("[data-filter]")) {
  btn.onclick = () => {
    filter = btn.dataset.filter;
    for (const other of document.querySelectorAll("[data-filter]")) {
      other.classList.toggle("is-on", other === btn);
    }
    applyFilter();
  };
}

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
