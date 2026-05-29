(function () {
  let poller = null;
  let currentId = null;
  const tracker = document.getElementById("job-tracker");

  function renderTracker(data) {
    const terminal = ["COMPLETED", "FAILED", "CANCELED"];
    const canCancel = !terminal.includes(data.status);
    const canDownload = data.status === "COMPLETED";
    const fileReady = data.download_available !== false;

    tracker.innerHTML = `
      <div class="panel-head" style="border:0;padding:0 0 12px">
        ${UI.statusBadge(data.status)}
        <span class="mono" style="font-size:11px">${UI.shortId(data.report_id)}</span>
      </div>
      ${UI.lifecycleHtml(data.status)}
      ${UI.progressBar(data.progress_pct, `${data.rows_processed || 0} / ${data.requested_rows || "?"} rows`)}
      <p class="muted" style="font-size:12px;margin:12px 0">
        Created ${UI.formatDate(data.created_at)} · Celery <span class="mono">${data.celery?.state || "—"}</span>
      </p>
      <div class="action-row">
        ${canDownload ? `<button type="button" class="btn btn-primary btn-sm" id="tracker-dl">Download</button>` : ""}
        ${canCancel ? `<button type="button" class="btn btn-danger btn-sm" id="tracker-cancel">Cancel</button>` : ""}
        <a href="/reports/${data.report_id}" class="btn btn-ghost btn-sm">Open job</a>
      </div>
      ${canDownload && !fileReady ? `<p class="alert alert-warning" style="margin-top:12px">CSV not on disk yet — wait for worker or check REPORTS_FOLDER.</p>` : ""}`;

    document.getElementById("tracker-cancel")?.addEventListener("click", async () => {
      try {
        await ReportAPI.cancelReport(currentId);
        UI.toast("Cancel requested", "info");
      } catch (err) {
        UI.toast(err.message, "error");
      }
    });

    const dl = document.getElementById("tracker-dl");
    if (dl) UI.bindDownloadButton(dl, data.report_id, { disabled: !fileReady, label: "Download" });
  }

  document.getElementById("create-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = document.getElementById("submit-btn");
    const form = e.target;
    btn.disabled = true;
    btn.textContent = "Enqueueing…";

    try {
      if (poller) poller.stop();

      const payload = {
        user_id: parseInt(form.user_id.value, 10),
        rows: parseInt(form.rows.value, 10),
      };

      const res = await ReportAPI.createReport(payload);
      currentId = res.report_id || res.task_id;
      UI.toast("Job queued on Memurai → Celery worker", "success");
      UI.setLoading(tracker, "Waiting for worker…");

      poller = new JobPoller(currentId, (data, err) => {
        if (err) {
          UI.toast(err.message, "error");
          return;
        }
        renderTracker(data);
        if (data.status === "COMPLETED") {
          if (data.partial_export) {
            UI.toast(
              `Exported ${data.rows_processed} rows (only that many exist for this user)`,
              "info",
              8000
            );
          } else {
            UI.toast("Export complete", "success");
          }
        }
        if (data.status === "FAILED") {
          UI.toast(data.error_message || "Export failed", "error", 6000);
        }
      });
      poller.start();
    } catch (err) {
      UI.toast(err.message, "error");
    } finally {
      btn.disabled = false;
      btn.textContent = "Enqueue job";
    }
  });
})();
