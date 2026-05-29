/**
 * API client for /api/v1 endpoints (same-origin, no CORS needed).
 * Supports AbortSignal and classifies network vs HTTP errors for connectivity handling.
 */
const ReportAPI = {
  base: "/api/v1",

  // Coalesce duplicate /ops/metrics calls (dashboard + topbar poll the same data)
  _metricsCache: { data: null, at: 0, inflight: null },
  _metricsCacheTtlMs: 4000,

  async request(method, path, body, options = {}) {
    const opts = {
      method,
      headers: { Accept: "application/json" },
      signal: options.signal,
    };
    if (body !== undefined) {
      opts.headers["Content-Type"] = "application/json";
      opts.body = JSON.stringify(body);
    }

    let res;
    try {
      res = await fetch(`${this.base}${path}`, opts);
    } catch (err) {
      if (err.name === "AbortError") throw err;
      const netErr = new Error("Backend unavailable — check Flask is running");
      netErr.code = "NETWORK_ERROR";
      netErr.offline = true;
      throw netErr;
    }

    let data = null;
    const ct = res.headers.get("content-type") || "";
    if (ct.includes("application/json")) {
      try {
        data = await res.json();
      } catch {
        data = null;
      }
    }

    if (!res.ok) {
      const msg =
        data?.error?.message || res.statusText || `Request failed (${res.status})`;
      const err = new Error(msg);
      err.status = res.status;
      err.code = data?.error?.code;
      err.payload = data;
      // 503 = Celery/workers unavailable but Flask is up — not "backend offline"
      err.offline = res.status === 0 || (res.status >= 500 && res.status !== 503);
      throw err;
    }

    if (!options.skipConnectivitySideEffects && window.Connectivity) {
      Connectivity.markOnline();
    }

    return data;
  },

  get(path, options) {
    return this.request("GET", path, undefined, options);
  },

  post(path, body, options) {
    return this.request("POST", path, body, options);
  },

  delete(path, options) {
    return this.request("DELETE", path, undefined, options);
  },

  createReport(payload, options) {
    return this.post("/reports/", payload, options);
  },

  getReport(id, options) {
    return this.get(`/reports/${id}`, options);
  },

  getStatus(id, options) {
    return this.get(`/reports/${id}/status`, options);
  },

  listReports(params = {}, options) {
    const qs = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") qs.set(k, v);
    });
    const q = qs.toString();
    return this.get(`/reports/${q ? "?" + q : ""}`, options);
  },

  getStats(options) {
    return this.get("/reports/stats", options);
  },

  cancelReport(id, options) {
    return this.post(`/reports/${id}/cancel`, undefined, options);
  },

  retryReport(id, options) {
    return this.post(`/reports/${id}/retry`, undefined, options);
  },

  deleteReport(id, options) {
    return this.delete(`/reports/${id}`, options);
  },

  downloadUrl(id) {
    return `${this.base}/reports/${id}/download`;
  },

  /**
   * Download CSV via fetch → blob (shows errors instead of saving download.htm).
   */
  async downloadReport(reportId) {
    const url = this.downloadUrl(reportId);
    let res;
    try {
      res = await fetch(url, { headers: { Accept: "text/csv, application/json" } });
    } catch {
      const err = new Error("Cannot reach server — is Flask running?");
      err.code = "NETWORK_ERROR";
      err.offline = true;
      throw err;
    }

    const ct = res.headers.get("content-type") || "";
    if (!res.ok) {
      let msg = `Download failed (${res.status})`;
      if (ct.includes("application/json")) {
        try {
          const data = await res.json();
          msg = data?.error?.message || msg;
        } catch {
          /* ignore */
        }
      }
      const err = new Error(msg);
      err.status = res.status;
      err.code = res.status === 404 ? "FILE_NOT_FOUND" : "DOWNLOAD_FAILED";
      throw err;
    }

    const blob = await res.blob();
    const filename =
      res.headers.get("content-disposition")?.match(/filename="?([^";]+)"?/)?.[1] ||
      `report_${reportId}.csv`;

    const objectUrl = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(objectUrl);
    return { filename };
  },

  getMetrics(options = {}) {
    const now = Date.now();
    const c = this._metricsCache;
    if (!options.signal && c.data && now - c.at < this._metricsCacheTtlMs) {
      return Promise.resolve(c.data);
    }
    if (!options.signal && c.inflight) {
      return c.inflight;
    }
    const p = this.get("/ops/metrics", options)
      .then((data) => {
        c.data = data;
        c.at = Date.now();
        return data;
      })
      .finally(() => {
        c.inflight = null;
      });
    if (!options.signal) c.inflight = p;
    return p;
  },

  getWorkers(options) {
    return this.get("/ops/workers", options);
  },

  getQueues(options) {
    return this.get("/ops/queues", options);
  },

  getFailedJobs(page = 1, options) {
    return this.get(`/ops/failed?page=${page}&page_size=20`, options);
  },

  getOpsHealth(options) {
    return this.get("/ops/health", options);
  },
};

window.ReportAPI = ReportAPI;
