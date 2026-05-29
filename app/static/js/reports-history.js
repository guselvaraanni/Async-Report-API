(function () {
  let page = 1;
  const pageSize = 15;
  let debounceTimer = null;
  let hasLoadedOnce = false;

  const wrap = document.getElementById("history-table-wrap");
  const pagination = document.getElementById("pagination");

  async function loadReports(options = {}) {
    const { signal, showSpinner = !hasLoadedOnce } = options;
    if (showSpinner) UI.setLoading(wrap, "Loading reports…");

    try {
      const params = {
        page,
        page_size: pageSize,
        sort: document.getElementById("sort-by").value,
        order: "desc",
      };
      const status = document.getElementById("filter-status").value;
      if (status) params.status = status;
      const q = document.getElementById("search-q").value.trim();
      if (q) params.q = q;

      const data = await ReportAPI.listReports(params, { signal });
      hasLoadedOnce = true;
      const items = data.items || [];

      if (!items.length) {
        UI.setEmpty(
          wrap,
          "No reports found",
          "Try adjusting filters or create a new export.",
          `<a href="/reports/new" class="btn btn-primary btn-sm" style="margin-top:12px">New Export</a>`
        );
        pagination.hidden = true;
        return;
      }

      wrap.innerHTML = `
        <div class="table-wrap">
          <table class="data-table">
            <thead><tr>
              <th>Report ID</th><th>Status</th><th>Progress</th><th>Rows</th>
              <th>Created</th><th>Duration</th><th>Actions</th>
            </tr></thead>
            <tbody>${items.map((r) => renderRow(r)).join("")}</tbody>
          </table>
        </div>`;

      bindActions(wrap);
      const totalPages = Math.ceil((data.total || 0) / pageSize) || 1;
      pagination.hidden = false;
      document.getElementById("page-info").textContent = `Page ${page} of ${totalPages} (${data.total} total)`;
      document.getElementById("prev-page").disabled = page <= 1;
      document.getElementById("next-page").disabled = page >= totalPages;
    } catch (err) {
      if (err.name === "AbortError") return;
      if (err.offline || err.status >= 500) {
        UI.offlineState(
          wrap,
          "Backend offline",
          "Report history paused. Reconnect or refresh when Flask is running."
        );
        pagination.hidden = true;
        return;
      }
      UI.setError(wrap, err.message);
    }
  }

  function renderRow(r) {
    const canCancel = !["COMPLETED", "FAILED", "CANCELED"].includes(r.status);
    const canRetry = r.status === "FAILED";
    const canDownload = r.status === "COMPLETED" && r.download_available !== false;
    return `
      <tr data-id="${r.report_id}">
        <td class="mono"><a href="/reports/${r.report_id}">${UI.shortId(r.report_id)}</a></td>
        <td>${UI.statusBadge(r.status)}</td>
        <td>${UI.progressBar(r.progress_pct, "")}</td>
        <td>${r.rows_processed || 0} / ${r.requested_rows || "—"}</td>
        <td>${UI.formatDate(r.created_at)}</td>
        <td>${UI.formatDuration(r.duration_seconds)}</td>
        <td class="table-actions">
          <a href="/reports/${r.report_id}" class="btn btn-ghost btn-sm">Open</a>
          ${r.status === "COMPLETED" ? `<button type="button" class="btn btn-primary btn-sm btn-dl" data-id="${r.report_id}" data-available="${canDownload}">DL</button>` : ""}
          ${canRetry ? `<button type="button" class="btn btn-secondary btn-sm act-retry">Retry</button>` : ""}
          ${canCancel ? `<button type="button" class="btn btn-danger btn-sm act-cancel">Cancel</button>` : ""}
          <button type="button" class="btn btn-secondary btn-sm act-delete">Delete</button>
        </td>
      </tr>`;
  }

  function bindActions(root) {
    root.querySelectorAll(".btn-dl").forEach((btn) => {
      UI.bindDownloadButton(btn, btn.dataset.id, {
        disabled: btn.dataset.available !== "true",
        label: "DL",
      });
    });
    root.querySelectorAll(".act-cancel").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const id = e.target.closest("tr").dataset.id;
        try {
          await ReportAPI.cancelReport(id);
          UI.toast("Cancel requested", "info");
          loadReports({ showSpinner: false });
        } catch (err) {
          UI.toast(err.message, "error");
        }
      });
    });
    root.querySelectorAll(".act-retry").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const id = e.target.closest("tr").dataset.id;
        try {
          await ReportAPI.retryReport(id);
          UI.toast("Job re-queued", "success");
          loadReports({ showSpinner: false });
        } catch (err) {
          UI.toast(err.message, "error");
        }
      });
    });
    root.querySelectorAll(".act-delete").forEach((btn) => {
      btn.addEventListener("click", async (e) => {
        const id = e.target.closest("tr").dataset.id;
        if (!confirm("Delete this report and its file?")) return;
        try {
          await ReportAPI.deleteReport(id);
          UI.toast("Report deleted", "success");
          loadReports({ showSpinner: false });
        } catch (err) {
          UI.toast(err.message, "error");
        }
      });
    });
  }

  document.getElementById("prev-page").addEventListener("click", () => {
    if (page > 1) {
      page--;
      loadReports({ showSpinner: true });
    }
  });
  document.getElementById("next-page").addEventListener("click", () => {
    page++;
    loadReports({ showSpinner: true });
  });
  document.getElementById("filter-status").addEventListener("change", () => {
    page = 1;
    loadReports({ showSpinner: true });
  });
  document.getElementById("sort-by").addEventListener("change", () => {
    page = 1;
    loadReports({ showSpinner: true });
  });
  document.getElementById("search-q").addEventListener("input", () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      page = 1;
      loadReports({ showSpinner: true });
    }, 350);
  });

  const historyPoller = new PollingManager(
    "reports-history",
    async ({ signal }) => loadReports({ signal, showSpinner: false }),
    { intervalMs: 12000, maxConsecutiveFailures: 4 }
  );

  loadReports({ showSpinner: true });
  historyPoller.start();
})();
