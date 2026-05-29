/**
 * Global shell: theme, mobile nav, topbar worker/queue indicators.
 */
(function () {
  const THEME_KEY = "export-queue-theme";

  function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(THEME_KEY, theme);
  }

  applyTheme(localStorage.getItem(THEME_KEY) || "dark");

  document.getElementById("theme-toggle")?.addEventListener("click", () => {
    const current = document.documentElement.getAttribute("data-theme");
    applyTheme(current === "dark" ? "light" : "dark");
  });

  document.getElementById("mobile-nav-toggle")?.addEventListener("click", () => {
    document.querySelector(".site-nav")?.classList.toggle("open");
  });

  function renderTopbarFromMetrics(m) {
    const q = m.reports?.by_status || {};
    const queued =
      (q.QUEUED || 0) + (q.PROCESSING || 0) + (q.CANCEL_REQUESTED || 0);
    const el = document.getElementById("topbar-queue-count");
    if (el) el.textContent = String(queued);

    const celery = m.celery || {};
    const online = celery.workers_online || 0;
    const ok = celery.status === "ok" && online > 0;
    const dot = document.getElementById("topbar-worker-dot");
    const footerDot = document.getElementById("sidebar-worker-dot");
    const text = document.getElementById("topbar-worker-text");

    if (Connectivity.state !== "online") return;

    const dotCls = "dot " + (ok ? "dot-green" : "dot-red");
    if (dot) dot.className = dotCls;
    if (footerDot) footerDot.className = dotCls;
    if (text) {
      text.textContent = ok
        ? `${online} worker${online !== 1 ? "s" : ""}`
        : "offline";
    }
  }

  const topbarPoller = new PollingManager(
    "topbar",
    async ({ signal }) => {
      const m = await ReportAPI.getMetrics({ signal });
      renderTopbarFromMetrics(m);
    },
    { intervalMs: 15000, maxConsecutiveFailures: 4 }
  );

  topbarPoller.start();
})();
