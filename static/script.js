// ── Password eye toggle ──────────────────────────────
document.querySelectorAll(".eye-btn").forEach((btn) => {
  const input = document.getElementById(btn.dataset.target);
  if (!input) return;

  // Start with eye-closed visible, eye-open hidden
  btn.querySelector(".eye-open").style.display = "none";

  btn.addEventListener("click", () => {
    const isHidden = input.type === "password";
    input.type = isHidden ? "text" : "password";
    btn.querySelector(".eye-closed").style.display = isHidden ? "none" : "";
    btn.querySelector(".eye-open").style.display  = isHidden ? ""     : "none";
    btn.setAttribute("aria-label", isHidden ? "Ocultar senha" : "Mostrar senha");
  });
});

// ── User dropdown ────────────────────────────────────
const avatarBtn    = document.getElementById("avatarBtn");
const userDropdown = document.getElementById("userDropdown");
if (avatarBtn && userDropdown) {
  avatarBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    const open = userDropdown.classList.toggle("open");
    avatarBtn.setAttribute("aria-expanded", String(open));
  });
  document.addEventListener("click", () => {
    userDropdown.classList.remove("open");
    avatarBtn?.setAttribute("aria-expanded", "false");
  });
}

// ── Profile edit toggle ──────────────────────────────
const editToggle = document.getElementById("editToggle");
const editForm   = document.getElementById("editForm");
const editCancel = document.getElementById("editCancel");
if (editToggle && editForm) {
  editToggle.addEventListener("click", () => {
    const hidden = editForm.hidden;
    editForm.hidden = !hidden;
    editToggle.textContent = hidden ? "Cancelar" : "Editar perfil";
  });
  editCancel?.addEventListener("click", () => {
    editForm.hidden = true;
    editToggle.textContent = "Editar perfil";
  });
}

// ── File upload drag-and-drop ────────────────────────
const fileDropArea    = document.getElementById("fileDropArea");
const fileInput       = document.getElementById("fileInput");
const fileDropContent = document.getElementById("fileDropContent");
const filePreviewBox  = document.getElementById("filePreviewBox");
const filePreviewInner = document.getElementById("filePreviewInner");
const fileRemoveBtn   = document.getElementById("fileRemoveBtn");
const contentField    = document.getElementById("contentField");
const contentNote     = document.getElementById("contentNote");
const contentTextarea = document.getElementById("content");

function showFilePreview(file) {
  if (!filePreviewBox) return;

  const ext = file.name.split(".").pop().toLowerCase();
  const isPdf = ext === "pdf";
  const sizeMB = (file.size / 1024 / 1024).toFixed(1);

  if (isPdf) {
    filePreviewInner.innerHTML = `
      <div class="file-preview-pdf">
        <span class="file-preview-icon">📄</span>
        <div>
          <strong>${file.name}</strong>
          <span>${sizeMB} MB · PDF</span>
        </div>
      </div>`;
  } else {
    const url = URL.createObjectURL(file);
    filePreviewInner.innerHTML = `
      <img src="${url}" alt="Preview" class="file-preview-img">
      <div class="file-preview-name"><strong>${file.name}</strong> · ${sizeMB} MB</div>`;
  }

  fileDropContent.hidden = true;
  filePreviewBox.hidden  = false;

  // Content field becomes optional
  if (contentNote) contentNote.textContent = "(opcional se tiver arquivo)";
  if (contentTextarea) contentTextarea.removeAttribute("required");
}

function clearFile() {
  if (fileInput) fileInput.value = "";
  if (filePreviewInner) filePreviewInner.innerHTML = "";
  if (fileDropContent) fileDropContent.hidden = false;
  if (filePreviewBox)  filePreviewBox.hidden  = true;
  if (contentNote) contentNote.textContent = "(obrigatório se não houver arquivo)";
  if (contentTextarea) contentTextarea.setAttribute("required", "");
}

if (fileInput) {
  fileInput.addEventListener("change", () => {
    const file = fileInput.files[0];
    if (file) showFilePreview(file);
    else clearFile();
  });
}

if (fileRemoveBtn) {
  fileRemoveBtn.addEventListener("click", clearFile);
}

if (fileDropArea) {
  ["dragenter", "dragover"].forEach((ev) => {
    fileDropArea.addEventListener(ev, (e) => {
      e.preventDefault();
      fileDropArea.classList.add("drag-over");
    });
  });
  ["dragleave", "drop"].forEach((ev) => {
    fileDropArea.addEventListener(ev, () => fileDropArea.classList.remove("drag-over"));
  });
  fileDropArea.addEventListener("drop", (e) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file && fileInput) {
      const dt = new DataTransfer();
      dt.items.add(file);
      fileInput.files = dt.files;
      showFilePreview(file);
    }
  });
}

// ── Access material ──────────────────────────────────
const accessBtn = document.getElementById("accessBtn");
if (accessBtn) {
  accessBtn.addEventListener("click", async () => {
    const matId = accessBtn.dataset.matId;
    accessBtn.disabled = true;
    accessBtn.textContent = "Desbloqueando…";
    try {
      const res  = await fetch(`/material/${matId}/access`, { method: "POST" });
      const data = await res.json();
      if (data.ok) location.reload();
      else {
        accessBtn.disabled = false;
        accessBtn.textContent = "Desbloquear material";
        showToast(data.message, "error");
      }
    } catch {
      accessBtn.disabled = false;
      accessBtn.textContent = "Desbloquear material";
      showToast("Erro ao conectar. Tente novamente.", "error");
    }
  });
}

// ── Star rating ──────────────────────────────────────
const starInput = document.getElementById("starInput");
if (starInput) {
  const ratingSection = starInput.closest("[data-mat-id]");
  const matId         = ratingSection?.dataset.matId;
  const ratingMsg     = document.getElementById("ratingMsg");
  const avgNum        = document.getElementById("avgNum");
  const ratingCnt     = document.getElementById("ratingCnt");
  const starsDisplay  = document.querySelector(".stars-display");
  const buttons       = [...starInput.querySelectorAll(".star-btn")];
  let selected        = parseInt(starInput.dataset.userRating, 10) || 0;

  const paint = (n) => buttons.forEach((b, i) => b.classList.toggle("active", i < n));
  paint(selected);

  buttons.forEach((btn, idx) => {
    btn.addEventListener("mouseenter", () => paint(idx + 1));
    btn.addEventListener("mouseleave", () => paint(selected));
    btn.addEventListener("click", async () => {
      const rating = idx + 1;
      btn.disabled = true;
      try {
        const res  = await fetch(`/material/${matId}/rate`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ rating }),
        });
        const data = await res.json();
        if (data.ok) {
          selected = rating;
          paint(selected);
          if (ratingMsg) ratingMsg.textContent = `Você avaliou com ${rating} estrela${rating > 1 ? "s" : ""}.`;
          if (avgNum) avgNum.textContent = data.avg;
          if (ratingCnt) ratingCnt.textContent = `(${data.count} avaliações)`;
          if (starsDisplay) starsDisplay.textContent = "★".repeat(Math.floor(data.avg)) + "☆".repeat(5 - Math.floor(data.avg));
        } else {
          showToast(data.message, "error");
        }
      } catch { showToast("Erro ao enviar avaliação.", "error"); }
      finally  { btn.disabled = false; }
    });
  });
}

// ── Toast ────────────────────────────────────────────
function showToast(message, type = "success") {
  const t = document.createElement("div");
  t.className = `alert alert-${type}`;
  t.style.cssText = "position:fixed;bottom:24px;right:24px;z-index:9999;max-width:360px;animation:fadeIn .2s";
  t.textContent = message;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

const s = document.createElement("style");
s.textContent = "@keyframes fadeIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}";
document.head.appendChild(s);
