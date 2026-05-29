(function () {
  const root = document.getElementById("downloads-root");

  async function load() {
    UI.setLoading(root, "Loading completed exports…");
    try {
      const data = await ReportAPI.listReports({
        status: "COMPLETED",
        page_size: 50,
        sort: "completed_at",
        order: "desc",
      });
      const items = data.items || [];

      if (!items.length) {
        UI.setEmpty(
          root,
          "No exports ready",
          "Completed jobs with CSV files appear here.",
          `<a href="/reports/new" class="btn btn-primary">New export</a>`
        );
        return;
      }

      root.innerHTML = `
        <div class="table-wrap">
          <table class="data-table">
            <thead>
              <tr>
                <th>Job ID</th>
                <th>Rows</th>
                <th>Completed</th>
                <th>Duration</th>
                <th>File</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${items
                .map((r) => {
                  const canDl = r.download_available !== false;
                  return `
                <tr>
                  <td class="mono"><a href="/reports/${r.report_id}">${UI.shortId(r.report_id)}</a></td>
                  <td>${r.rows_processed || 0}</td>
                  <td>${UI.formatDate(r.completed_at)}</td>
                  <td>${UI.formatDuration(r.duration_seconds)}</td>
                  <td>${canDl ? '<span class="badge badge-completed">Ready</span>' : '<span class="badge badge-failed">Missing</span>'}</td>
                  <td class="table-actions">
                    <button type="button" class="btn btn-primary btn-sm btn-dl" data-id="${r.report_id}" data-available="${canDl}">Download</button>
                    <a href="/reports/${r.report_id}" class="btn btn-ghost btn-sm">Open</a>
                  </td>
                </tr>`;
                })
                .join("")}
            </tbody>
          </table>
        </div>
        <p class="page-hint">Legacy jobs marked <strong>Missing</strong> have no CSV on disk — run a new export.</p>`;

      root.querySelectorAll(".btn-dl").forEach((btn) => {
        const id = btn.dataset.id;
        const available = btn.dataset.available === "true";
        UI.bindDownloadButton(btn, id, { disabled: !available });
      });
    } catch (err) {
      if (err.offline || err.status >= 500) {
        UI.offlineState(root, "Backend offline", "Cannot load exports until Flask is running.");
        return;
      }
      UI.setError(root, err.message);
    }
  }

  load();
})();
