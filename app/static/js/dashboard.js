(function () {
  let offlineShown = false;

  function renderDashboard(stats, metrics) {
    offlineShown = false;

    document.getElementById("stat-total").textContent = stats.total ?? "0";
    document.getElementById("stat-queue").textContent =
      (stats.queue?.queued || 0) + (stats.queue?.processing || 0);
    document.getElementById("stat-completed").textContent =
      stats.finished?.completed ?? "0";
    document.getElementById("stat-failed").textContent =
      stats.finished?.failed ?? "0";

    const celery = metrics.celery || {};
    const badge = document.getElementById("celery-status-badge");
    if (badge) {
      badge.innerHTML =
        celery.status === "ok" && celery.workers_online > 0
          ? UI.statusBadge("COMPLETED").replace("COMPLETED", "WORKERS OK")
          : UI.statusBadge("FAILED").replace("FAILED", "DEGRADED");
    }

    document.getElementById("ops-summary").innerHTML = `
      <p style="font-size:14px;margin:0 0 12px">
        <strong>${celery.workers_online || 0}</strong> workers online ·
        <strong>${celery.active_tasks || 0}</strong> active ·
        <strong>${celery.queue_depth_estimate || 0}</strong> queue depth (est.)
      </p>
      <p style="font-size:12px;color:var(--text-muted);margin:0">
        Broker: Memurai (Redis-compatible) · Queue: <code>reports</code>
      </p>`;

    const by = stats.by_status || {};
    const max = Math.max(...Object.values(by), 1);
    let bars = "";
    Object.entries(by).forEach(([k, v]) => {
      const pct = (v / max) * 100;
      bars += `
        <div style="margin-bottom:12px">
          <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:4px">
            <span>${k}</span><span>${v}</span>
          </div>
          <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
        </div>`;
    });
    document.getElementById("status-chart").innerHTML = bars || "<p>No data</p>";

    const recent = stats.recent || [];
    const container = document.getElementById("recent-activity");
    if (!recent.length) {
      UI.setEmpty(
        container,
        "No reports yet",
        "Create your first async export.",
        `<a href="/reports/new" class="btn btn-primary btn-sm" style="margin-top:12px">New Export</a>`
      );
      return;
    }

    container.innerHTML = `
      <div class="table-wrap">
        <table class="data-table">
          <thead><tr>
            <th>Report ID</th><th>Status</th><th>Progress</th><th>Created</th><th></th>
          </tr></thead>
          <tbody>${recent
            .map(
              (r) => `
            <tr>
              <td class="mono">${UI.shortId(r.report_id)}</td>
              <td>${UI.statusBadge(r.status)}</td>
              <td>${r.progress_pct ?? 0}%</td>
              <td>${UI.formatDate(r.created_at)}</td>
              <td><a href="/reports/${r.report_id}" class="btn btn-secondary btn-sm">View</a></td>
            </tr>`
            )
            .join("")}
          </tbody>
        </table>
      </div>`;
  }

  function showOfflineDashboard() {
    if (offlineShown) return;
    offlineShown = true;
    ["stat-total", "stat-queue", "stat-completed", "stat-failed"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.textContent = "—";
    });
    UI.offlineState(
      document.getElementById("recent-activity"),
      "Backend offline",
      "Dashboard polling paused. Start Flask + Celery worker, or click Check connection."
    );
    document.getElementById("ops-summary").innerHTML = `
      <p style="color:var(--text-muted);font-size:13px;margin:0">Worker health unavailable while backend is offline.</p>`;
    document.getElementById("status-chart").innerHTML = `
      <p style="color:var(--text-muted);font-size:13px;margin:0">Status distribution unavailable.</p>`;
  }

  const dashboardPoller = new PollingManager(
    "dashboard",
    async ({ signal }) => {
      const [stats, metrics] = await Promise.all([
        ReportAPI.getStats({ signal }),
        ReportAPI.getMetrics({ signal }),
      ]);
      renderDashboard(stats, metrics);
    },
    {
      intervalMs: 12000,
      maxConsecutiveFailures: 4,
      onError(err, { isOffline }) {
        if (isOffline) showOfflineDashboard();
      },
    }
  );

  Connectivity.onChange((state) => {
    if (state === "offline") showOfflineDashboard();
  });

  dashboardPoller.start();
})();
