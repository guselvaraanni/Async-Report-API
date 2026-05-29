/**
 * Shared UI helpers: toasts, formatting, status badges.
 */
const UI = {
  toast(message, type = "info", duration = 4000) {
    const stack = document.getElementById("toast-stack");
    if (!stack) return;
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = message;
    stack.appendChild(el);
    setTimeout(() => {
      el.style.opacity = "0";
      el.style.transition = "opacity 0.2s";
      setTimeout(() => el.remove(), 200);
    }, duration);
  },

  formatDate(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString();
    } catch {
      return iso;
    }
  },

  formatDuration(seconds) {
    if (seconds == null) return "—";
    if (seconds < 60) return `${Math.round(seconds)}s`;
    const m = Math.floor(seconds / 60);
    const s = Math.round(seconds % 60);
    return `${m}m ${s}s`;
  },

  shortId(id) {
    if (!id) return "—";
    return id.length > 12 ? id.slice(0, 8) + "…" : id;
  },

  statusBadge(status) {
    const s = (status || "UNKNOWN").toLowerCase().replace("_", "-");
    const cls = {
      queued: "badge-queued",
      processing: "badge-processing",
      completed: "badge-completed",
      failed: "badge-failed",
      canceled: "badge-canceled",
      "cancel-requested": "badge-cancel_requested",
    }[s] || "badge-queued";
    const label = (status || "UNKNOWN").replace("_", " ");
    const pulse = status === "PROCESSING" ? '<span class="badge-dot"></span>' : "";
    return `<span class="badge ${cls}">${pulse}${label}</span>`;
  },

  progressBar(pct, label) {
    const p = Math.min(100, Math.max(0, pct || 0));
    const fillCls = p >= 100 ? " success" : "";
    return `
      <div class="progress-wrap">
        <div class="progress-label">
          <span>${label || "Progress"}</span>
          <span>${p.toFixed(1)}%</span>
        </div>
        <div class="progress-bar">
          <div class="progress-fill${fillCls}" style="width:${p}%"></div>
        </div>
      </div>`;
  },

  lifecycleHtml(status) {
    const steps = [
      { key: "QUEUED", label: "Queued" },
      { key: "PROCESSING", label: "Processing" },
      { key: "COMPLETED", label: "Completed" },
    ];
    const order = ["QUEUED", "PROCESSING", "COMPLETED", "FAILED", "CANCELED", "CANCEL_REQUESTED"];
    const idx = order.indexOf(status);
    const isFailed = status === "FAILED";
    const isCanceled = status === "CANCELED" || status === "CANCEL_REQUESTED";

    let html = '<div class="lifecycle">';
    steps.forEach((step, i) => {
      let cls = "";
      if (isFailed && step.key === "PROCESSING") cls = "failed";
      else if (isCanceled && step.key === "PROCESSING") cls = "failed";
      else if (step.key === status) cls = "active";
      else if (idx > order.indexOf(step.key) && !isFailed && !isCanceled) cls = "done";
      else if (status === "COMPLETED" && step.key !== "COMPLETED") cls = "done";
      else if (status === "COMPLETED" && step.key === "COMPLETED") cls = "done";

      if (status === "PROCESSING" && step.key === "QUEUED") cls = "done";
      if (status === "PROCESSING" && step.key === "PROCESSING") cls = "active";

      html += `
        <div class="lifecycle-step ${cls}">
          <div class="step-icon">${i + 1}</div>
          <div class="step-label">${step.label}</div>
        </div>`;
      if (i < steps.length - 1) {
        const connDone = cls === "done" || (status === "COMPLETED");
        html += `<div class="lifecycle-connector ${connDone ? "done" : ""}"></div>`;
      }
    });
    html += "</div>";
    if (isFailed) html += `<p class="error-state" style="padding:12px;color:var(--danger)">Job failed — see error details below.</p>`;
    if (isCanceled) html += `<p class="error-state" style="padding:12px;color:var(--warning)">Job was canceled.</p>`;
    return html;
  },

  setLoading(container, message = "Loading…") {
    container.innerHTML = `
      <div class="loading-state">
        <div class="spinner"></div>
        <p>${message}</p>
      </div>`;
  },

  setEmpty(container, title, subtitle, actionHtml = "") {
    container.innerHTML = `
      <div class="empty-state">
        <h3>${title}</h3>
        <p>${subtitle}</p>
        ${actionHtml}
      </div>`;
  },

  setError(container, message) {
    container.innerHTML = `
      <div class="error-state">
        <h3>Something went wrong</h3>
        <p>${message}</p>
        <button type="button" class="btn btn-secondary btn-sm" onclick="location.reload()">Retry</button>
      </div>`;
  },

  bindDownloadButton(button, reportId, options = {}) {
    const { disabled = false, label = "Download CSV" } = options;
    if (disabled) {
      button.disabled = true;
      button.textContent = "File unavailable";
      button.title = "CSV not found on server — run a new export";
      return;
    }
    button.textContent = label;
    button.addEventListener("click", async () => {
      const prev = button.textContent;
      button.disabled = true;
      button.textContent = "Downloading…";
      try {
        await ReportAPI.downloadReport(reportId);
        UI.toast("Download started", "success");
      } catch (err) {
        UI.toast(err.message, "error", 7000);
      } finally {
        button.disabled = false;
        button.textContent = prev;
      }
    });
  },

  offlineState(container, title, subtitle) {
    container.innerHTML = `
      <div class="offline-state">
        <div class="offline-icon">⚡</div>
        <h3>${title || "Backend offline"}</h3>
        <p>${subtitle || "Live updates paused. Start Flask and Celery, then wait for reconnect or refresh."}</p>
        <button type="button" class="btn btn-secondary btn-sm" id="offline-retry-btn">Check connection</button>
      </div>`;
    container.querySelector("#offline-retry-btn")?.addEventListener("click", () => {
      if (window.Connectivity) Connectivity.retryConnection();
    });
  },
};

window.UI = UI;
