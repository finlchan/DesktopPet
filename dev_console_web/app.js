(() => {
  "use strict";

  const STORAGE_KEY = "desktoppet.sync_board.packet";

  const els = {
    chatLog: document.getElementById("chat-log"),
    chatForm: document.getElementById("chat-form"),
    chatInput: document.getElementById("chat-input"),
    btnHelp: document.getElementById("btn-help"),
    presetSelect: document.getElementById("preset-select"),
    btnLoad: document.getElementById("btn-load"),
    strokeColor: document.getElementById("stroke-color"),
    strokeSize: document.getElementById("stroke-size"),
    btnUndo: document.getElementById("btn-undo"),
    btnClear: document.getElementById("btn-clear"),
    fileInput: document.getElementById("file-input"),
    canvas: document.getElementById("draw-canvas"),
    btnSync: document.getElementById("btn-sync"),
    downloadLink: document.getElementById("download-link"),
    syncPreview: document.getElementById("sync-preview"),
    packetJson: document.getElementById("packet-json"),
    statusPill: document.getElementById("status-pill"),
  };

  const ctx = els.canvas.getContext("2d");
  const state = {
    baseImage: null,
    strokes: [],
    drawing: false,
    current: null,
    preset: "./sample-hud.jpg",
    lastPacket: null,
    objectUrl: null,
  };

  function setStatus(text, kind) {
    els.statusPill.textContent = text;
    els.statusPill.classList.remove("ok", "warn");
    if (kind) els.statusPill.classList.add(kind);
  }

  function appendChat(role, content) {
    const bubble = document.createElement("div");
    bubble.className = `bubble ${role}`;
    bubble.textContent = content;
    els.chatLog.appendChild(bubble);
    els.chatLog.scrollTop = els.chatLog.scrollHeight;
  }

  function helpText() {
    return [
      "DesktopPet Sync Board 指令：",
      "/help — 顯示說明",
      "/hakoniwa | /proj — 載入 sample-hud.jpg（箱庭 HUD 預設）",
      "/align — 提示：在繪圖欄標註後按 Sync 產生 sync_packet",
      "Sync — 寫入 localStorage 封包 + 右側預覽 / JSON / 下載",
      "純中文文字 — 視為校正備註，會併入下次 Sync 的 request",
    ].join("\n");
  }

  function redraw() {
    const { canvas } = els;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    if (state.baseImage) {
      ctx.drawImage(state.baseImage, 0, 0, canvas.width, canvas.height);
    } else {
      ctx.fillStyle = "#0b1016";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.fillStyle = "#6b7c90";
      ctx.font = "16px IBM Plex Sans, sans-serif";
      ctx.fillText("Load a preset to begin", 24, 40);
    }
    for (const stroke of state.strokes) {
      if (!stroke.points.length) continue;
      ctx.strokeStyle = stroke.color;
      ctx.lineWidth = stroke.size;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.beginPath();
      stroke.points.forEach((pt, i) => {
        if (i === 0) ctx.moveTo(pt.x, pt.y);
        else ctx.lineTo(pt.x, pt.y);
      });
      ctx.stroke();
    }
  }

  function loadImage(src, label) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => {
        const maxW = 900;
        const maxH = 600;
        let w = img.naturalWidth || img.width;
        let h = img.naturalHeight || img.height;
        const scale = Math.min(1, maxW / w, maxH / h);
        w = Math.max(1, Math.round(w * scale));
        h = Math.max(1, Math.round(h * scale));
        els.canvas.width = w;
        els.canvas.height = h;
        state.baseImage = img;
        state.strokes = [];
        state.preset = label || src;
        redraw();
        setStatus(`loaded ${label || "image"}`, "ok");
        resolve(img);
      };
      img.onerror = () => reject(new Error(`failed to load ${src}`));
      img.src = src;
    });
  }

  function pointerPos(evt) {
    const rect = els.canvas.getBoundingClientRect();
    const scaleX = els.canvas.width / rect.width;
    const scaleY = els.canvas.height / rect.height;
    const src = evt.touches ? evt.touches[0] : evt;
    return {
      x: (src.clientX - rect.left) * scaleX,
      y: (src.clientY - rect.top) * scaleY,
    };
  }

  function startStroke(evt) {
    evt.preventDefault();
    state.drawing = true;
    state.current = {
      color: els.strokeColor.value,
      size: Number(els.strokeSize.value) || 6,
      points: [pointerPos(evt)],
    };
    state.strokes.push(state.current);
    redraw();
  }

  function moveStroke(evt) {
    if (!state.drawing || !state.current) return;
    evt.preventDefault();
    state.current.points.push(pointerPos(evt));
    redraw();
  }

  function endStroke() {
    state.drawing = false;
    state.current = null;
  }

  function handleCommand(raw) {
    const text = (raw || "").trim();
    if (!text) return;
    appendChat("user", text);
    const lower = text.toLowerCase();

    if (lower === "/help" || lower === "help" || lower === "?") {
      appendChat("assistant", helpText());
      return;
    }

    if (lower === "/hakoniwa" || lower === "/proj" || lower === "/projection") {
      els.presetSelect.value = "./sample-hud.jpg";
      loadImage("./sample-hud.jpg", "sample-hud.jpg")
        .then(() => appendChat("assistant", "已載入箱庭 HUD 預設：sample-hud.jpg"))
        .catch((err) => appendChat("assistant", String(err.message || err)));
      return;
    }

    if (lower.startsWith("/align")) {
      appendChat(
        "assistant",
        "Alignment helper：在中欄標註畫面後按右側 Sync。\n" +
          "封包 kind 會是 sync_packet，並寫入 localStorage。\n" +
          "（本靜態板不執行 Alignment(2) 工作簿；請用 Gradio Dev Console 跑 /align。）"
      );
      return;
    }

    appendChat("assistant", `已記下校正備註：${text}`);
    setStatus("note saved", "ok");
  }

  function buildPacket() {
    const dataUrl = els.canvas.toDataURL("image/png");
    const note = (els.chatInput.value || "").trim();
    const lastUser = [...els.chatLog.querySelectorAll(".bubble.user")].pop();
    const request =
      note ||
      (lastUser ? lastUser.textContent.trim() : "") ||
      "Sync from Sync Board";
    const now = new Date();
    const savedAt = now.toISOString().replace(/\.\d{3}Z$/, "Z").replace(/[-:]/g, "").replace("T", "T");
    return {
      kind: "sync_packet",
      saved_at: savedAt,
      source: "dev_console_web",
      preset: state.preset,
      note,
      request,
      size: [els.canvas.width, els.canvas.height],
      stroke_count: state.strokes.length,
      preview_data_url: dataUrl,
      exists: { preview: true, localStorage: true },
    };
  }

  function showPacket(packet) {
    state.lastPacket = packet;
    const pretty = JSON.stringify(
      {
        ...packet,
        preview_data_url: packet.preview_data_url
          ? `${packet.preview_data_url.slice(0, 64)}… (${packet.preview_data_url.length} chars)`
          : null,
      },
      null,
      2
    );
    els.packetJson.textContent = pretty;
    els.syncPreview.src = packet.preview_data_url;
    els.syncPreview.classList.remove("empty");

    if (state.objectUrl) URL.revokeObjectURL(state.objectUrl);
    const blob = new Blob([JSON.stringify(packet, null, 2)], {
      type: "application/json",
    });
    state.objectUrl = URL.createObjectURL(blob);
    els.downloadLink.href = state.objectUrl;
    els.downloadLink.classList.remove("disabled");
    els.downloadLink.setAttribute("aria-disabled", "false");
  }

  function doSync() {
    try {
      const packet = buildPacket();
      localStorage.setItem(STORAGE_KEY, JSON.stringify(packet));
      showPacket(packet);
      appendChat(
        "user",
        packet.note || "[Sync]"
      );
      appendChat(
        "assistant",
        `Synced → localStorage[${STORAGE_KEY}] (${packet.size[0]}×${packet.size[1]}, strokes=${packet.stroke_count})`
      );
      els.chatInput.value = "";
      setStatus("synced", "ok");
    } catch (err) {
      appendChat("assistant", `Sync failed: ${err.message || err}`);
      setStatus("sync error", "warn");
    }
  }

  // Events
  els.chatForm.addEventListener("submit", (evt) => {
    evt.preventDefault();
    const value = els.chatInput.value;
    handleCommand(value);
    if ((value || "").trim().startsWith("/")) {
      els.chatInput.value = "";
    }
  });

  els.btnHelp.addEventListener("click", () => {
    els.chatInput.value = "/help";
    handleCommand("/help");
    els.chatInput.value = "";
  });

  els.btnLoad.addEventListener("click", () => {
    const src = els.presetSelect.value;
    loadImage(src, src.replace("./", "")).catch((err) => {
      appendChat("assistant", String(err.message || err));
      setStatus("load error", "warn");
    });
  });

  els.btnUndo.addEventListener("click", () => {
    state.strokes.pop();
    redraw();
  });

  els.btnClear.addEventListener("click", () => {
    state.strokes = [];
    redraw();
  });

  els.fileInput.addEventListener("change", () => {
    const file = els.fileInput.files && els.fileInput.files[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    loadImage(url, file.name)
      .catch((err) => appendChat("assistant", String(err.message || err)))
      .finally(() => URL.revokeObjectURL(url));
  });

  els.canvas.addEventListener("mousedown", startStroke);
  els.canvas.addEventListener("mousemove", moveStroke);
  window.addEventListener("mouseup", endStroke);
  els.canvas.addEventListener("touchstart", startStroke, { passive: false });
  els.canvas.addEventListener("touchmove", moveStroke, { passive: false });
  window.addEventListener("touchend", endStroke);

  els.btnSync.addEventListener("click", doSync);

  // Boot
  appendChat("assistant", helpText());
  loadImage("./sample-hud.jpg", "sample-hud.jpg").catch((err) => {
    appendChat("assistant", String(err.message || err));
    setStatus("ready", "warn");
  });

  try {
    const cached = localStorage.getItem(STORAGE_KEY);
    if (cached) {
      const packet = JSON.parse(cached);
      if (packet && packet.kind === "sync_packet" && packet.preview_data_url) {
        showPacket(packet);
        setStatus("restored packet", "ok");
      }
    }
  } catch (_) {
    /* ignore corrupt cache */
  }
})();
