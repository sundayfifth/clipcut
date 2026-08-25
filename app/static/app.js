const statusEl = document.getElementById("status");

async function checkHealth() {
  try {
    const res = await fetch("/health");
    const data = await res.json();
    statusEl.textContent = `server ok — v${data.version} · media: ${data.media_dir}`;
    statusEl.classList.add("ok");
  } catch (err) {
    statusEl.textContent = `ต่อ server ไม่ได้: ${err.message}`;
    statusEl.classList.add("error");
  }
}

checkHealth();
