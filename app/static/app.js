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
  ribbon: el("ribbon"),
  undoBtn: el("undo-btn"),
  cancelBtn: el("cancel-btn"),
  previewAt: el("preview-at"),
  previewAtOut: el("preview-at-out"),
  suggest: el("suggest"),
  suggestText: el("suggest-text"),
  suggestApply: el("suggest-apply"),
};

let jobId = null;
let poll = null;
let bandMode = "trim";
let previewTimer = null;
let lastShotKeys = new Map();
let view = "result";   // ปกติโชว์ผลลัพธ์ 9:16 · สลับเป็น source ชั่วคราวตอนลากกรอบ
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
  stopAudio();
  clearError();
  ui.empty.hidden = true;
  ui.results.hidden = true;
  ui.working.hidden = false;
  ui.actionbar.hidden = true;
  ui.bandGroup.hidden = true;
  ui.done.hidden = true;
  ui.renderTrack.hidden = true;
  ui.shots.innerHTML = "";
  ui.previewAt.max = "100";
  ui.previewImg.removeAttribute("src");
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

  drawSuggestion(job);
  if (job.bands) syncBandInputs(job.bands);
  if (ui.previewAt.max === "100" && job.info) {
    // ตั้งช่วงสไลเดอร์ตามความยาวคลิป แล้วเด้งไปเฟรมที่น่าจะเห็นซับ
    ui.previewAt.max = String(Math.max(1, Math.floor(job.info.duration)));
    ui.previewAt.value = String(job.subtitle_hint || 0);
    updatePreviewAtLabel();
  }
  if (!ui.previewImg.getAttribute("src")) refreshPreview();

  const i = job.info;
  ui.resultsMeta.textContent =
    `${job.name} · ${i.aspect} · ${tc(i.duration)} · ${i.fps} fps`;

  lastJob = job;
  ui.undoBtn.disabled = !job.can_undo;
  ui.cancelBtn.hidden = job.status !== "rendering";
  drawTally(job.summary);
  drawShots(job);
  drawRibbon(job);
  applyFilter();
}

/* แถบภาพรวมตามเวลา — กริดการ์ดทำให้ไม่เห็นจังหวะของคลิป
   ความกว้างแต่ละชิ้นแปรตามความยาวซีน คลิกแล้วกระโดดไปที่การ์ดนั้น */
function drawRibbon(job) {
  const total = job.shots.reduce((sum, s) => sum + s.duration, 0) || 1;
  const key = job.shots.map((s) => {
    const p = s.plan || {};
    return `${s.index}:${p.mode}:${p.included}`;
  }).join(",");
  if (ui.ribbon.dataset.key === key) return;
  ui.ribbon.dataset.key = key;

  ui.ribbon.innerHTML = job.shots.map((s) => {
    const p = s.plan || {};
    const on = p.included !== false;
    return `<button type="button" class="rib" data-jump="${s.index}"
      style="flex-grow:${Math.max(0.4, s.duration / total * 100)}"
      data-mode="${p.mode || ""}" data-on="${on}"
      title="ซีน ${s.index + 1} · ${s.duration.toFixed(1)} วิ · ${MODE_LABEL[p.mode] || ""}${on ? "" : " (ไม่ได้เลือก)"}"
    ><span class="rib-no">${s.index + 1}</span></button>`;
  }).join("");
}

ui.ribbon.addEventListener("click", (e) => {
  const btn = e.target.closest("[data-jump]");
  if (!btn) return;
  const card = ui.shots.querySelector(`[data-shot="${btn.dataset.jump}"]`);
  if (!card) return;
  if (card.hidden) {
    document.querySelector('[data-filter="all"]').click();
  }
  card.scrollIntoView({ block: "center", behavior: "smooth" });
  card.focus({ preventScroll: true });
  card.classList.add("is-flash");
  setTimeout(() => card.classList.remove("is-flash"), 900);
});

/* ข้อเสนอแถบซับที่ได้จากการอ่านข้อความจริงในคลิป — ไม่ใส่ให้เอง เพราะเดาพลาดได้
   (คลิปที่มีสกรีนช็อตเยอะเคยถูกแนะนำให้ตัดทิ้งครึ่งจอ) */
function drawSuggestion(job) {
  const sug = job.suggested_bands;
  const bands = job.bands || {};
  if (!sug || (!sug.top && !sug.bottom)) {
    ui.suggest.hidden = true;
    return;
  }
  // สไลเดอร์ปัดเป็นจำนวนเต็ม % ค่าที่ใส่จริงจึงต่างจากที่แนะนำได้ถึง 1 จุด
  const same =
    Math.abs((bands.top || 0) - sug.top) <= 0.011 &&
    Math.abs((bands.bottom || 0) - sug.bottom) <= 0.011;
  ui.suggest.hidden = same;
  if (same) return;

  const parts = [];
  if (sug.top) parts.push(`บน ${Math.round(sug.top * 100)}%`);
  if (sug.bottom) parts.push(`ล่าง ${Math.round(sug.bottom * 100)}%`);
  ui.suggestText.textContent = `จากข้อความที่อ่านได้ในคลิป แนะนำตัด ${parts.join(" · ")}`;
  ui.suggestApply.dataset.top = String(sug.top);
  ui.suggestApply.dataset.bottom = String(sug.bottom);
}

ui.suggestApply.onclick = async () => {
  if (!jobId) return;
  ui.suggestApply.disabled = true;
  try {
    ui.bandTop.value = String(Math.round(Number(ui.suggestApply.dataset.top) * 100));
    ui.bandBottom.value = String(Math.round(Number(ui.suggestApply.dataset.bottom) * 100));
    updateBandOutputs();
    refreshPreview();
    await applyBands();
  } finally {
    ui.suggestApply.disabled = false;
  }
};

function drawTally(summary) {
  if (!summary) return;
  ui.tally.innerHTML =
    `<span class="chip">เลือก ${summary.included}/${summary.total} ซีน</span>` +
    `<span class="chip chip-crop">เต็มจอ ${summary.crop}</span>` +
    `<span class="chip chip-pad">ย่อทั้งภาพ ${summary.pad}</span>` +
    `<span class="chip">${tc(summary.duration)}</span>` +
    (summary.dropped_with_speech
      ? `<span class="chip chip-warn">ตัดซีนที่มีคนพูดออก ${summary.dropped_with_speech}</span>`
      : "");
  ui.renderBtn.disabled = summary.included === 0;
}

function drawShots(job) {
  const src = job.info;
  for (const shot of job.shots) {
    const p = shot.plan;
    const key = [
      view, shot.thumbnail || "",
      p ? `${p.mode}|${p.included}|${p.has_speech}|${lostText(p).length}` : "",
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
        ${listenRow(shot.index, p)}
        ${p ? modeSwitch(shot.index, p.mode) : ""}
        ${p ? tuneControls(shot.index, p) : ""}
        ${!included && p && p.has_speech
          ? `<p class="warn">ซีนนี้มีคนพูดอยู่ ตัดออกแล้วประโยคจะขาดกลางคัน</p>`
          : p ? `<p class="reason">${p.reason}</p>` : ""}
        ${lostTextNote(p)}
      </div>`;
  }
}

/* ภาพในการ์ดเป็นแถบ sprite หลายเฟรม — เลื่อนเมาส์ผ่านเพื่อดูว่าซีนเคลื่อนไหวยังไง
   ตัดสินการจัดเฟรมจากเฟรมเดียวคือการเดา เพราะทั้งคนและกรอบขยับตลอดซีน

   ใช้ background-image ไม่ใช่ <img> ที่ยืดด้วย width% เพราะการยืด img ทำให้เบราว์เซอร์
   สร้าง layer เท่าขนาดที่ยืด (เคยพุ่งไป 6400px ต่อการ์ด) จนค้างทั้งหน้า
   background วาดแค่เท่าขนาดกล่องจริง */

function tileStyle(url, n, at, sizeW, sizeH, posX, posY) {
  return [
    // ต้องเป็น single quote — style="..." จะขาดถ้าใช้ double quote ข้างใน
    `background-image:url('${url}')`,
    `background-size:${sizeW}% ${sizeH}%`,
    `background-position:${posX}% ${posY}%`,
    "background-repeat:no-repeat",
  ].join(";");
}

/* background-position เป็น % คิดจาก (ขนาดภาพ - ขนาดกล่อง) จึงต้องแปลงจาก px เอง */
function posPct(offset, imageSize, boxSize) {
  const room = imageSize - boxSize;
  return room <= 0 ? 0 : (offset / room) * 100;
}

function mediaFor(shot, plan, src, bands) {
  if (!shot.thumbnail) return `<div class="thumb-missing">ไม่มีภาพ</div>`;
  const n = shot.frames || 1;
  const inner =
    view === "source" || !plan || !src
      ? sourceView(shot, n, plan, src, bands)
      : plan.mode === "crop"
        ? cropPreview(shot, plan, src, n)
        : padPreview(shot, src, bands, n);
  return `<div class="scrub" data-frames="${n}" data-at="0">${inner}
    <span class="scrub-bar" aria-hidden="true"><i style="transform:scaleX(${1 / n})"></i></span></div>`;
}

function sourceView(shot, n, plan, src, bands) {
  return `<span class="tilebox" data-role="frame" data-n="${n}"
      style="${tileStyle(shot.thumbnail, n, 0, n * 100, 100, 0, 0)}"
      role="img" aria-label="ซีน ${shot.index + 1}"></span>` +
    frameOverlay(plan, src, bands);
}

/* crop: ขยายภาพให้กรอบที่เลือกไว้เต็มกล่อง 9:16 พอดี */
function cropPreview(shot, plan, src, n) {
  const c = plan.crop;
  const sizeW = (n * src.width / c.w) * 100;
  const sizeH = (src.height / c.h) * 100;
  return `<div class="frame916 frame916-crop" data-role="crop" data-n="${n}"
      style="${tileStyle(shot.thumbnail, n, 0,
        sizeW, sizeH,
        posPct(c.x, n * src.width, c.w), posPct(c.y, src.height, c.h))}"
      role="img" aria-label="ผลลัพธ์ซีน ${shot.index + 1}"></div>`;
}

/* pad: ภาพเต็มกว้างวางกลาง พื้นหลังเบลอ ตรงกับที่ ffmpeg เรนเดอร์จริง */
function padPreview(shot, src, bands, n) {
  const top = bands && bands.mode === "trim" ? bands.top : 0;
  const bottom = bands && bands.mode === "trim" ? bands.bottom : 0;
  const keep = Math.max(0.05, 1 - top - bottom);
  const fgHeightPct = ((9 / 16) / (src.width / (src.height * keep))) * 100;
  const cover = ((src.width / src.height) / (9 / 16)) * 100;

  const fg = tileStyle(shot.thumbnail, n, 0, n * 100, (1 / keep) * 100,
    0, keep >= 1 ? 0 : (top / (1 - keep)) * 100);
  const bg = tileStyle(shot.thumbnail, n, 0, n * cover, 100, 50 / n, 50);

  return `<div class="frame916 frame916-pad">
    <span class="bgwrap" data-role="bg" data-n="${n}" data-cover="${cover}" style="${bg}"></span>
    <span class="fg" data-role="frame" data-n="${n}"
        style="top:${(100 - fgHeightPct) / 2}%;height:${fgHeightPct}%;${fg}"
        role="img" aria-label="ผลลัพธ์ซีน ${shot.index + 1}"></span>
  </div>`;
}

/* เลื่อนไปเฟรมที่ at ของ sprite — ขยับแค่ background-position-x */
function showFrame(scrub, i) {
  const n = Number(scrub.dataset.frames) || 1;
  const at = Math.max(0, Math.min(n - 1, i));
  if (scrub.dataset.at === String(at)) return;
  scrub.dataset.at = String(at);

  for (const node of scrub.querySelectorAll("[data-role]")) {
    const parts = node.style.backgroundPosition.split(" ");
    const y = parts[1] || "0%";
    node.style.backgroundPosition = `${frameX(node, at, n)}% ${y}`;
  }
  const bar = scrub.querySelector(".scrub-bar i");
  if (bar) bar.style.transform = `translateX(${at * 100}%) scaleX(${1 / n})`;
}

function frameX(node, at, n) {
  const role = node.dataset.role;
  if (role === "crop") {
    // ต้องรู้ตำแหน่ง crop ในหน่วยของภาพเต็ม เก็บไว้ตอนสร้าง
    const src = lastJob && lastJob.info;
    const plan = planOf(node.closest(".shot").dataset.shot);
    if (!src || !plan || !plan.crop) return 0;
    const c = plan.crop;
    return posPct(at * src.width + c.x, n * src.width, c.w);
  }
  if (role === "bg") {
    const cover = Number(node.dataset.cover) || 100;
    return posPct(at * cover + (cover - 100) / 2, n * cover, 100);
  }
  return n <= 1 ? 0 : (at / (n - 1)) * 100;
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
  for (const box of plan.text_boxes || []) {
    pieces.push(
      `<span class="frame-text${box.lost ? " is-lost" : ""}" style="` +
      `left:${box.x0 * 100}%;top:${box.y0 * 100}%;` +
      `width:${(box.x1 - box.x0) * 100}%;height:${(box.y1 - box.y0) * 100}%"></span>`,
    );
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
  const touched = a.dx !== 0 || a.dy !== 0 || a.scale < 0.999;
  return `<div class="tune" data-index="${index}">
    <label class="tune-row"><span>ซูม</span>
      <input type="range" data-axis="scale" min="40" max="100" step="1"
             value="${Math.round(a.scale * 100)}" aria-label="ย่อขยายกรอบ" /></label>
    <button type="button" class="tune-reset" ${touched ? "" : "hidden"}>คืนค่าอัตโนมัติ</button>
  </div>`;
}

/* ค่าที่กำลังปรับอยู่ของแต่ละซีน — เก็บแยกจาก DOM เพราะตอนนี้ลากบนภาพ ไม่ได้อ่านจากสไลเดอร์อย่างเดียว */
const pending = new Map();

function currentAdjust(index) {
  if (pending.has(index)) return { ...pending.get(index) };
  const plan = planOf(index);
  return { dx: 0, dy: 0, scale: 1, ...((plan && plan.adjust) || {}) };
}

function planOf(index) {
  if (!lastJob) return null;
  const shot = lastJob.shots.find((s) => s.index === Number(index));
  return shot ? shot.plan : null;
}

/* ฟังก่อนตัดสินใจ — "ซีนนี้" บอกว่าพูดอะไร · "รอยต่อ" บอกว่าตัดแล้วสะดุดมั้ย */
function listenRow(index, plan) {
  if (!plan) return "";
  return `<div class="listen">
    <button type="button" class="play" data-index="${index}" data-kind="shot">
      <span class="play-ico" aria-hidden="true"></span>ซีนนี้</button>
    <button type="button" class="play" data-index="${index}" data-kind="join"
      title="ฟังเสียงท้ายซีนก่อนหน้าต่อกับหัวซีนถัดไป — คือเสียงที่จะได้ยินถ้าตัดซีนนี้ทิ้ง">
      <span class="play-ico" aria-hidden="true"></span>ถ้าตัดออก</button>
  </div>
  <div class="joinbar" hidden>
    <div class="joinbar-track"><span class="joinbar-head"></span><span class="joinbar-seam"></span></div>
    <p class="joinbar-label"></p>
  </div>`;
}

/* ต้องตรงกับ JOIN_CONTEXT ใน app/preview_audio.py */
const JOIN_CONTEXT = 1.6;

/* คำนวณว่ารอยตัดอยู่วินาทีที่เท่าไหร่ของคลิปเสียงที่กำลังจะเล่น
   ใช้ตรรกะเดียวกับฝั่ง server — ถ้าแก้ฝั่งใดต้องแก้ให้ตรงกัน */
function joinShape(index) {
  if (!lastJob) return null;
  const shots = lastJob.shots;
  const at = shots.findIndex((s) => s.index === Number(index));
  if (at < 0) return null;
  const on = (s) => !s.plan || s.plan.included !== false;
  const before = [...shots.slice(0, at)].reverse().find(on);
  const after = shots.slice(at + 1).find(on);
  if (!before && !after) return null;

  const beforeLen = before ? Math.min(JOIN_CONTEXT, before.duration) : 0;
  const afterLen = after ? Math.min(JOIN_CONTEXT, after.duration) : 0;
  return {
    seam: beforeLen,
    total: beforeLen + afterLen,
    before: before ? before.index + 1 : null,
    after: after ? after.index + 1 : null,
  };
}

/* เล่นทีละอันเท่านั้น กดอันใหม่ให้หยุดอันเก่า */
let player = null;
let playingBtn = null;
let joinTicker = null;

function stopAudio() {
  cancelAnimationFrame(joinTicker);
  for (const bar of ui.shots.querySelectorAll(".joinbar")) bar.hidden = true;
  if (player) {
    // ถอด handler ก่อนล้าง src — การเซ็ต src="" ทำให้ onerror ทำงาน
    // แล้วจะขึ้นข้อความว่าเล่นไม่ได้ทุกครั้งที่เสียงเล่นจบปกติ
    player.onended = null;
    player.onerror = null;
    player.pause();
    player.removeAttribute("src");
    player.load();
    player = null;
  }
  if (playingBtn) { playingBtn.classList.remove("is-playing"); playingBtn = null; }
}

ui.shots.addEventListener("click", (e) => {
  const btn = e.target.closest(".play");
  if (!btn || !jobId) return;
  e.preventDefault();

  const wasPlaying = btn === playingBtn;
  stopAudio();
  if (wasPlaying) return;   // กดซ้ำที่ปุ่มเดิม = หยุด

  player = new Audio(
    `/api/jobs/${jobId}/shots/${btn.dataset.index}/audio` +
    `?kind=${btn.dataset.kind}&_=${Date.now()}`,
  );
  playingBtn = btn;
  btn.classList.add("is-playing");
  if (btn.dataset.kind === "join") showJoinBar(btn);
  player.onended = stopAudio;
  player.onerror = () => {
    stopAudio();
    showError("เล่นเสียงไม่ได้ — คลิปนี้อาจไม่มีเสียง");
  };
  player.play().catch(() => stopAudio());
});

/* แถบบอกว่ารอยตัดอยู่ตรงไหน — ฟังอย่างเดียวแยกไม่ออกว่าหัวหรือท้าย */
function showJoinBar(btn) {
  const card = btn.closest(".shot");
  const bar = card.querySelector(".joinbar");
  const shape = joinShape(btn.dataset.index);
  if (!bar || !shape || !shape.total) return;

  const seamPct = (shape.seam / shape.total) * 100;
  bar.hidden = false;
  bar.querySelector(".joinbar-seam").style.left = `${seamPct}%`;
  bar.querySelector(".joinbar-head").style.width = "0%";
  bar.querySelector(".joinbar-label").textContent =
    shape.before && shape.after
      ? `ท้ายซีน ${shape.before}  ⇢  หัวซีน ${shape.after}`
      : shape.before
        ? `ท้ายซีน ${shape.before} (ไม่มีซีนต่อจากนี้)`
        : `หัวซีน ${shape.after} (ไม่มีซีนก่อนหน้า)`;

  const head = bar.querySelector(".joinbar-head");
  const tick = () => {
    if (!player) return;
    const total = player.duration || shape.total;
    head.style.width = `${Math.min(100, (player.currentTime / total) * 100)}%`;
    joinTicker = requestAnimationFrame(tick);
  };
  tick();
}

/* ข้อความที่จะหายเพราะ crop ข้าง = กราฟฟิกที่คนต้องไปทำใหม่ */
function lostText(plan) {
  // ไม่นับโลโก้ประจำช่อง — มันโผล่ทุกซีน ถ้านับด้วยการ์ดจะเตือนกันหมดทั้งหน้า
  return (plan && plan.text_boxes || []).filter((b) => b.lost && b.cause === "crop");
}

function lostTextNote(plan) {
  const lost = lostText(plan);
  if (!lost.length) return "";
  const sample = lost[0].text.slice(0, 22);
  return `<p class="warn warn-text">ข้อความจะหาย ${lost.length} จุด — “${sample}${
    lost[0].text.length > 22 ? "…" : ""}”</p>`;
}

function modeSwitch(index, mode) {
  return `<div class="switch" role="group" aria-label="วิธีแปลงซีนนี้">` +
    ["crop", "pad"].map((m) =>
      `<button type="button" data-index="${index}" data-mode="${m}" ` +
      `aria-pressed="${mode === m}">${MODE_LABEL[m]}</button>`).join("") +
    `</div>`;
}

function applyFilter() {
  const counts = { all: 0, crop: 0, pad: 0, off: 0 };
  const cards = [...ui.shots.querySelectorAll(".shot")];
  for (const card of cards) {
    counts.all += 1;
    if (card.dataset.included !== "true") counts.off += 1;
    if (card.dataset.mode === "crop") counts.crop += 1;
    if (card.dataset.mode === "pad") counts.pad += 1;
  }
  // โชว์จำนวนบนปุ่มไปเลย จะได้ไม่ต้องกดแล้วเจอหน้าว่าง
  for (const btn of document.querySelectorAll("[data-filter]")) {
    const n = counts[btn.dataset.filter] ?? 0;
    const label = btn.dataset.label ?? (btn.dataset.label = btn.textContent.trim());
    btn.textContent = `${label} ${n}`;
    btn.disabled = n === 0 && btn.dataset.filter !== "all";
    if (btn.disabled && filter === btn.dataset.filter) {
      filter = "all";
      for (const o of document.querySelectorAll("[data-filter]")) {
        o.classList.toggle("is-on", o.dataset.filter === "all");
      }
    }
  }

  let shown = 0;
  for (const card of cards) {
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
  const at = Number(ui.previewAt.value);
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

/* ── ปรับกรอบ: ลากบนภาพเป็นหลัก สไลเดอร์ซูมเป็นตัวช่วย ── */

function applyLive(index, adjust) {
  const plan = planOf(index);
  if (!plan || !plan.crop_base || !lastJob) return;
  pending.set(String(index), adjust);

  const card = ui.shots.querySelector(`[data-shot="${index}"]`);
  if (!card) return;
  const crop = deriveCrop(plan.crop_base, adjust, lastJob.info);
  const src = lastJob.info;
  const scrub = card.querySelector(".scrub");
  const n = Number(scrub && scrub.dataset.frames) || 1;
  const at = Number(scrub && scrub.dataset.at) || 0;

  const box = card.querySelector('[data-role="crop"]');
  if (box) {
    box.style.backgroundSize =
      `${(n * src.width / crop.w) * 100}% ${(src.height / crop.h) * 100}%`;
    box.style.backgroundPosition =
      `${posPct(at * src.width + crop.x, n * src.width, crop.w)}% ` +
      `${posPct(crop.y, src.height, crop.h)}%`;
  }
  const keep = card.querySelector(".frame-keep");
  if (keep) {
    keep.style.left = `${(crop.x / src.width) * 100}%`;
    keep.style.width = `${(crop.w / src.width) * 100}%`;
    keep.style.top = `${(crop.y / src.height) * 100}%`;
    keep.style.height = `${(crop.h / src.height) * 100}%`;
  }
  const reset = card.querySelector(".tune-reset");
  if (reset) {
    reset.hidden = adjust.dx === 0 && adjust.dy === 0 && adjust.scale >= 0.999;
  }
  const zoom = card.querySelector('[data-axis="scale"]');
  if (zoom && document.activeElement !== zoom) {
    zoom.value = String(Math.round(adjust.scale * 100));
  }
}

async function commitAdjust(index) {
  const a = pending.get(String(index));
  if (!a || !jobId) return;
  pending.delete(String(index));
  try {
    draw(await api(
      `/api/jobs/${jobId}/shots/${index}/crop?dx=${a.dx}&dy=${a.dy}&scale=${a.scale}`,
      { method: "POST" },
    ));
  } catch (err) {
    showError(err.message);
  }
}

/* ลากบนภาพ = ขยับกรอบ — สายตาอยู่ที่ภาพ ไม่ต้องไปมองสไลเดอร์ */
let drag = null;

ui.shots.addEventListener("pointerdown", (e) => {
  const scrub = e.target.closest(".scrub");
  if (!scrub || e.button !== 0) return;
  const card = scrub.closest(".shot");
  const index = card.dataset.shot;
  const plan = planOf(index);
  if (!plan || plan.mode !== "crop" || !plan.crop_base) return;

  const box = scrub.getBoundingClientRect();
  drag = {
    index, scrub, box, moved: false, card,
    startX: e.clientX, startY: e.clientY,
    from: currentAdjust(index),
    base: plan.crop_base,
  };
  try { scrub.setPointerCapture(e.pointerId); } catch { /* ไม่ critical */ }
});

ui.shots.addEventListener("pointermove", (e) => {
  if (!drag) {
    // ไม่ได้ลาก = เลื่อนดูเฟรมในซีน
    const scrub = e.target.closest(".scrub");
    if (!scrub) return;
    const box = scrub.getBoundingClientRect();
    const n = Number(scrub.dataset.frames) || 1;
    showFrame(scrub, Math.floor(((e.clientX - box.left) / box.width) * n));
    return;
  }

  const dxPx = e.clientX - drag.startX;
  const dyPx = e.clientY - drag.startY;
  if (!drag.moved && Math.abs(dxPx) + Math.abs(dyPx) < 3) return;

  if (!drag.moved) {
    drag.moved = true;
    drag.scrub.classList.add("is-dragging");
    // สลับให้เห็นภาพเต็มพร้อมกรอบ จะได้รู้ว่ากำลังดึงมาจากตรงไหนของเฟรม
    showContext(drag);
  }

  const src = lastJob.info;
  const crop = deriveCrop(drag.base, drag.from, src);
  const next = { ...drag.from };

  // ในภาพเต็ม สิ่งที่มือจับคือ "กรอบ" ลากซ้ายกรอบต้องไปซ้าย
  // ในผลลัพธ์ 9:16 สิ่งที่มือจับคือ "ภาพ" ลากซ้ายแล้วเห็นของทางขวา (แบบแผนที่)
  // ตอนนี้ลากทีไรก็เห็นภาพเต็ม จึงใช้ทิศของกรอบ
  const perPxX = src.width / drag.box.width;
  next.dx = drag.from.dx + (dxPx * perPxX) / drag.base.w;
  if (drag.from.scale < 0.999) {
    const perPxY = src.height / drag.box.height;
    next.dy = drag.from.dy + (dyPx * perPxY) / (drag.base.h / 2);
  }
  next.dx = Math.max(-1, Math.min(1, next.dx));
  next.dy = Math.max(-1, Math.min(1, next.dy));
  applyLive(drag.index, next);
});

/* ระหว่างลาก สลับการ์ดไปโชว์ภาพเต็ม + กรอบสีเขียว แล้วคืนค่าเมื่อปล่อย */
function showContext(d) {
  const shot = lastJob.shots.find((x) => x.index === Number(d.index));
  const plan = shot && shot.plan;
  if (!shot || !plan) return;
  const holder = d.scrub;
  holder.dataset.wasResult = "1";
  const n = shot.frames || 1;
  const at = Number(holder.dataset.at) || 0;
  holder.innerHTML =
    sourceView(shot, n, plan, lastJob.info, lastJob.bands) +
    `<span class="scrub-bar" aria-hidden="true"><i style="transform:scaleX(${1 / n})"></i></span>`;
  showFrame(holder, at);
  d.box = holder.getBoundingClientRect();
}

function endDrag(e) {
  if (!drag) return;
  const { index, moved, scrub } = drag;
  drag = null;
  scrub.classList.remove("is-dragging");
  // ปล่อย capture ต้องไม่บล็อกการบันทึก ไม่งั้นค่าที่ลากไว้หายเงียบๆ
  try { if (e) scrub.releasePointerCapture?.(e.pointerId); } catch { /* ไม่ critical */ }
  if (!moved) return;
  lastShotKeys.delete(Number(index));  // บังคับวาดใหม่ให้กลับไปเป็นผลลัพธ์ 9:16
  commitAdjust(index);
}
ui.shots.addEventListener("pointerup", endDrag);
ui.shots.addEventListener("pointercancel", endDrag);

/* หมุนล้อบนภาพ = ซูมกรอบ */
let wheelTimer = null;
ui.shots.addEventListener("wheel", (e) => {
  // ต้องกด Option/Alt ค้างถึงจะซูม — ไม่งั้นเลื่อนหน้าผ่านการ์ดแล้วกรอบเปลี่ยนโดยไม่ตั้งใจ
  if (!e.altKey) return;
  const scrub = e.target.closest(".scrub");
  if (!scrub) return;
  const index = scrub.closest(".shot").dataset.shot;
  const plan = planOf(index);
  if (!plan || plan.mode !== "crop" || !plan.crop_base) return;
  e.preventDefault();

  const a = currentAdjust(index);
  a.scale = Math.max(MIN_SCALE, Math.min(1, a.scale + (e.deltaY > 0 ? 0.03 : -0.03)));
  applyLive(index, a);
  clearTimeout(wheelTimer);
  wheelTimer = setTimeout(() => commitAdjust(index), 400);
}, { passive: false });

ui.shots.addEventListener("input", (e) => {
  const slider = e.target.closest('[data-axis="scale"]');
  if (!slider) return;
  const index = slider.closest(".shot").dataset.shot;
  const a = currentAdjust(index);
  a.scale = Number(slider.value) / 100;
  applyLive(index, a);
});

ui.shots.addEventListener("change", (e) => {
  const slider = e.target.closest('[data-axis="scale"]');
  if (slider) commitAdjust(slider.closest(".shot").dataset.shot);
});

ui.shots.addEventListener("click", (e) => {
  const reset = e.target.closest(".tune-reset");
  if (!reset || !jobId) return;
  const index = reset.closest(".shot").dataset.shot;
  pending.set(String(index), { dx: 0, dy: 0, scale: 1 });
  commitAdjust(index);
});

ui.shots.addEventListener("pointerleave", (e) => {
  const scrub = e.target.closest && e.target.closest(".scrub");
  if (scrub && !drag) showFrame(scrub, 0);
}, true);

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
        `<button type="button" class="btn btn-quiet btn-sm" id="reveal-btn">เปิดโฟลเดอร์</button>` +
        `<span class="path"></span>`;
      ui.done.querySelector(".path").textContent = job.output;
      el("reveal-btn").onclick = () =>
        api(`/api/jobs/${job.id}/reveal`, { method: "POST" }).catch((err) =>
          showError(err.message));
    } else if (job.status === "error") {
      clearInterval(poll);
      ui.renderBtn.disabled = false;
      ui.renderStep.textContent = "";
      showError(job.error || "สร้างไฟล์ไม่สำเร็จ");
    } else if (job.status === "ready") {
      // ยกเลิกกลางคัน
      clearInterval(poll);
      ui.renderBtn.disabled = false;
      ui.cancelBtn.hidden = true;
      ui.renderTrack.hidden = true;
      ui.renderStep.textContent = job.step;
      watch(jobId);
    }
  }, 700);
};

/* ── ผูก event ───────────────────────────────────────── */

async function doUndo() {
  if (!jobId || ui.undoBtn.disabled) return;
  try {
    draw(await api(`/api/jobs/${jobId}/undo`, { method: "POST" }));
  } catch (err) {
    showError(err.message);
  }
}

ui.undoBtn.onclick = doUndo;

document.addEventListener("keydown", (e) => {
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z" && !e.shiftKey) {
    e.preventDefault();
    doUndo();
  }
});

ui.cancelBtn.onclick = async () => {
  if (!jobId) return;
  ui.cancelBtn.disabled = true;
  try {
    await api(`/api/jobs/${jobId}/cancel`, { method: "POST" });
  } catch (err) {
    showError(err.message);
  } finally {
    ui.cancelBtn.disabled = false;
  }
};

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

function updatePreviewAtLabel() {
  ui.previewAtOut.textContent = tc(Number(ui.previewAt.value)).replace(/\.\d$/, "");
}

ui.previewAt.addEventListener("input", () => {
  updatePreviewAtLabel();
  schedulePreview();
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
