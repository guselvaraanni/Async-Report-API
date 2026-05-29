(function () {
  const root = document.getElementById("detail-root");
  const reportId = root.dataset.reportId;
  let poller = null;

  function render(data) {
    const terminal = ["COMPLETED", "FAILED", "CANCELED"];
    const canCancel = !terminal.includes(data.status);
    const canRetry = data.status === "FAILED";
    const canDownload = data.status === "COMPLETED";
    const fileReady = data.download_available !== false;

    root.innerHTML = `
      <div class="panel">
        <div class="panel-head">
          <div>
            <p class="panel-eyebrow">Job</p>
            <p class="mono job-id">${data.report_id}</p>
          </div>
          ${UI.statusBadge(data.status)}
        </div>

        ${UI.lifecycleHtml(data.status)}
        ${UI.progressBar(data.progress_pct, `${data.rows_processed || 0} / ${data.requested_rows || "?"} rows`)}

        <dl class="meta-grid">
          <div><dt>Created</dt><dd>${UI.formatDate(data.created_at)}</dd></div>
          <div><dt>Started</dt><dd>${UI.formatDate(data.started_at)}</dd></div>
          <div><dt>Completed</dt><dd>${UI.formatDate(data.completed_at)}</dd></div>
          <div><dt>Duration</dt><dd>${UI.formatDuration(data.duration_seconds)}</dd></div>
          <div><dt>Celery</dt><dd class="mono">${data.celery?.state || "—"}${data.celery?.error ? ` — ${data.celery.error}` : ""}</dd></div>
          <div><dt>User</dt><dd>${data.user_id}</dd></div>
        </dl>

        ${data.error_message ? `<div class="alert alert-danger"><strong>Error</strong><pre>${data.error_message}</pre></div>` : ""}
        ${data.partial_export ? `<div class="alert alert-warning">${data.error_message || `Exported ${data.rows_processed} of ${data.requested_rows} requested rows — no more data in database for this user.`}</div>` : ""}
        ${data.celery?.state === "FAILURE" ? `<div class="alert alert-danger">Celery task failed. On Windows use <code>--pool=solo</code> when starting the worker, then enqueue a new job.</div>` : ""}
        ${canDownload && !fileReady ? `<div class="alert alert-warning">CSV not found on disk. Run a <a href="/reports/new">new export</a> to generate a downloadable file.</div>` : ""}

        <div class="action-row">
          ${canDownload ? `<button type="button" class="btn btn-primary" id="btn-download">Download CSV</button>` : ""}
          ${canRetry ? `<button type="button" class="btn btn-secondary" id="btn-retry">Retry job</button>` : ""}
          ${canCancel ? `<button type="button" class="btn btn-danger" id="btn-cancel">Cancel job</button>` : ""}
          <button type="button" class="btn btn-secondary" id="btn-delete">Delete</button>
          <a href="/reports" class="btn btn-ghost">← Jobs</a>
        </div>
      </div>`;

    const dlBtn = document.getElementById("btn-download");
    if (dlBtn) {
      UI.bindDownloadButton(dlBtn, reportId, { disabled: !fileReady });
    }

    document.getElementById("btn-cancel")?.addEventListener("click", async () => {
      try {
        await ReportAPI.cancelReport(reportId);
        UI.toast("Cancel requested", "info");
      } catch (err) {
        UI.toast(err.message, "error");
      }
    });
    document.getElementById("btn-retry")?.addEventListener("click", async () => {
      try {
        await ReportAPI.retryReport(reportId);
        UI.toast("Job re-queued", "success");
        if (poller) poller.stop();
        startPolling();
      } catch (err) {
        UI.toast(err.message, "error");
      }
    });
    document.getElementById("btn-delete")?.addEventListener("click", async () => {
      if (!confirm("Delete this report?")) return;
      try {
        await ReportAPI.deleteReport(reportId);
        UI.toast("Deleted", "success");
        window.location.href = "/reports";
      } catch (err) {
        UI.toast(err.message, "error");
      }
    });
  }

  function startPolling() {
    poller = new JobPoller(reportId, (data, err) => {
      if (err) {
        UI.setError(root, err.message);
        return;
      }
      render(data);
    }, { intervalMs: 1500 });
    poller.start();
  }

  ReportAPI.getStatus(reportId)
    .then((data) => {
      render(data);
      if (!["COMPLETED", "FAILED", "CANCELED"].includes(data.status)) {
        startPolling();
      }
    })
    .catch((err) => UI.setError(root, err.message));
})();
