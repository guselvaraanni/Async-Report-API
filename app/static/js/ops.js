(function () {
  let metricsOffline = false;

  function renderMetrics(m) {
    metricsOffline = false;
    const c = m.celery || {};
    document.getElementById("ops-workers").textContent = c.workers_online ?? "0";
    document.getElementById("ops-active").textContent = c.active_tasks ?? "0";
    document.getElementById("ops-reserved").textContent = c.reserved_tasks ?? "0";
    document.getElementById("ops-depth").textContent = c.queue_depth_estimate ?? "0";

    const workers = c.workers || [];
    document.getElementById("worker-list").innerHTML = workers.length
      ? workers
          .map(
            (w) =>
              `<li><span class="mono">${w}</span><span class="dot dot-green"></span></li>`
          )
          .join("")
      : "<li>No workers detected — start Celery worker</li>";
  }

  function showMetricsOffline() {
    if (metricsOffline) return;
    metricsOffline = true;
    ["ops-workers", "ops-active", "ops-reserved", "ops-depth"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.textContent = "—";
    });
    document.getElementById("worker-list").innerHTML =
      "<li>Backend offline — worker list unavailable</li>";
  }

  async function loadQueues() {
    try {
      const q = await ReportAPI.getQueues();
      document.getElementById("queue-info").textContent = JSON.stringify(
        q.active_queues || {},
        null,
        2
      );
    } catch {
      document.getElementById("queue-info").textContent =
        "Queue inspect unavailable. Ensure Celery worker is running with Memurai.";
    }
  }

  async function loadFailed() {
    const el = document.getElementById("failed-jobs");
    UI.setLoading(el, "Loading failed jobs…");
    try {
      const data = await ReportAPI.getFailedJobs(1);
      const items = data.items || [];
      if (!items.length) {
        UI.setEmpty(el, "No failed jobs", "All exports completed successfully.");
        return;
      }
      el.innerHTML = `
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr><th>ID</th><th>Error</th><th>Completed</th><th>Actions</th></tr></thead>
            <tbody>${items
              .map(
                (r) => `
              <tr>
                <td class="mono">${UI.shortId(r.report_id)}</td>
                <td style="max-width:280px;overflow:hidden;text-overflow:ellipsis">${r.error_message || "—"}</td>
                <td>${UI.formatDate(r.completed_at)}</td>
                <td>
                  <button type="button" class="btn btn-secondary btn-sm retry-fail" data-id="${r.report_id}">Retry</button>
                  <a href="/reports/${r.report_id}" class="btn btn-secondary btn-sm">View</a>
                </td>
              </tr>`
              )
              .join("")}
            </tbody>
          </table>
        </div>`;
      el.querySelectorAll(".retry-fail").forEach((btn) => {
        btn.addEventListener("click", async () => {
          try {
            await ReportAPI.retryReport(btn.dataset.id);
            UI.toast("Job re-queued", "success");
            loadFailed();
          } catch (err) {
            UI.toast(err.message, "error");
          }
        });
      });
    } catch (err) {
      if (err.offline || err.status >= 500) {
        UI.offlineState(el, "Backend offline", "Failed jobs list paused until reconnect.");
        return;
      }
      UI.setError(el, err.message);
    }
  }

  document.getElementById("refresh-failed").addEventListener("click", loadFailed);

  document.getElementById("cleanup-dry").addEventListener("click", async () => {
    try {
      const res = await fetch("/api/v1/ops/cleanup?days=7&dry_run=true", {
        method: "POST",
      });
      const data = await res.json();
      const pre = document.getElementById("cleanup-result");
      pre.style.display = "block";
      pre.textContent = JSON.stringify(data, null, 2);
      UI.toast(`${data.candidates} reports eligible for cleanup (dry run)`, "info");
    } catch {
      UI.toast("Cleanup preview failed", "error");
    }
  });

  const metricsPoller = new PollingManager(
    "ops-metrics",
    async ({ signal }) => {
      const m = await ReportAPI.getMetrics({ signal });
      renderMetrics(m);
    },
    {
      intervalMs: 12000,
      maxConsecutiveFailures: 4,
      onError(err, { isOffline }) {
        if (isOffline) showMetricsOffline();
      },
    }
  );

  Connectivity.onChange((state) => {
    if (state === "online") loadQueues();
    if (state === "offline") showMetricsOffline();
  });

  loadQueues();
  loadFailed();
  metricsPoller.start();
})();
