/**
 * Centralized polling + backend connectivity management.
 *
 * - Exponential backoff on failures
 * - Retry limits before pausing
 * - Pauses when tab is hidden
 * - Aborts in-flight fetch on stop/unload
 * - Slow reconnect probe when backend is down
 */
(function () {
  const DEFAULTS = {
    intervalMs: 10000,
    maxIntervalMs: 120000,
    maxConsecutiveFailures: 5,
    pauseWhenHidden: true,
    jitterMs: 500,
  };

  /** @type {Set<PollingManager>} */
  const registry = new Set();

  let reconnectTimer = null;
  let reconnectBackoffMs = 15000;
  let failureToastShown = false;

  const Connectivity = {
    state: "online", // online | offline | reconnecting
    listeners: new Set(),

    onChange(fn) {
      this.listeners.add(fn);
      fn(this.state);
      return () => this.listeners.delete(fn);
    },

    setState(next) {
      if (this.state === next) return;
      this.state = next;
      this.listeners.forEach((fn) => fn(next));
      this._updateBanner();
      this._updateTopbarConnectivity();
    },

    markOnline() {
      failureToastShown = false;
      reconnectBackoffMs = 15000;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      if (this.state !== "online") {
        this.setState("online");
        registry.forEach((p) => p.resumeFromConnectivity());
      }
    },

    markOffline(reason) {
      if (this.state === "online") {
        this.setState("offline");
        if (!failureToastShown && typeof UI !== "undefined") {
          failureToastShown = true;
          UI.toast(reason || "Backend offline — polling paused", "error", 6000);
        }
        registry.forEach((p) => p.pauseDueToFailure());
        this._scheduleReconnectProbe();
      }
    },

    markReconnecting() {
      if (this.state !== "reconnecting") {
        this.setState("reconnecting");
      }
    },

    _scheduleReconnectProbe() {
      if (reconnectTimer) return;
      this.markReconnecting();

      const probe = async () => {
        reconnectTimer = null;
        if (Connectivity.state === "online") return;

        try {
          await ReportAPI.request("GET", "/reports/health", undefined, {
            signal: AbortSignal.timeout ? AbortSignal.timeout(8000) : undefined,
            skipConnectivitySideEffects: true,
          });
          Connectivity.markOnline();
          return;
        } catch {
          reconnectBackoffMs = Math.min(reconnectBackoffMs * 1.5, 120000);
          reconnectTimer = setTimeout(probe, reconnectBackoffMs);
        }
      };

      reconnectTimer = setTimeout(probe, reconnectBackoffMs);
    },

    _updateBanner() {
      const el = document.getElementById("connectivity-banner");
      if (!el) return;

      const map = {
        online: { show: false },
        offline: {
          show: true,
          cls: "banner-offline",
          text: "Backend offline — live updates paused. Start Flask and Celery to reconnect.",
        },
        reconnecting: {
          show: true,
          cls: "banner-reconnecting",
          text: "Reconnecting to backend…",
        },
      };

      const cfg = map[this.state] || map.online;
      el.className = "connectivity-banner" + (cfg.show ? ` ${cfg.cls} visible` : "");
      el.textContent = cfg.text || "";
      el.setAttribute("aria-hidden", cfg.show ? "false" : "true");
    },

    _updateTopbarConnectivity() {
      const text = document.getElementById("topbar-worker-text");
      const dot = document.getElementById("topbar-worker-dot");
      if (!text) return;

      if (this.state === "offline") {
        text.textContent = "Backend offline";
        if (dot) dot.className = "dot dot-red";
      } else if (this.state === "reconnecting") {
        text.textContent = "Reconnecting…";
        if (dot) dot.className = "dot dot-muted";
      }
    },

    isOnline() {
      return this.state === "online";
    },

    /** Manually trigger a reconnect probe (e.g. user clicks "Check connection"). */
    retryConnection() {
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      reconnectBackoffMs = 5000;
      this._scheduleReconnectProbe();
    },
  };

  class PollingManager {
    /**
     * @param {string} name
     * @param {(ctx: { signal: AbortSignal }) => Promise<void>} tickFn
     * @param {object} options
     */
    constructor(name, tickFn, options = {}) {
      this.name = name;
      this.tickFn = tickFn;
      this.opts = { ...DEFAULTS, ...options };
      this.onSuccess = options.onSuccess || null;
      this.onError = options.onError || null;
      this.onPaused = options.onPaused || null;

      this.running = false;
      this.paused = false;
      this.pausedByVisibility = false;
      this.pausedByFailure = false;
      this.consecutiveFailures = 0;
      this.currentIntervalMs = this.opts.intervalMs;
      this.timerId = null;
      this.abortController = null;
      this.inFlight = false;
    }

    start() {
      if (this.running) return;
      this.running = true;
      this.paused = false;
      this.pausedByFailure = false;
      this.consecutiveFailures = 0;
      this.currentIntervalMs = this.opts.intervalMs;
      registry.add(this);
      this._schedule(0);
    }

    stop() {
      this.running = false;
      this.paused = false;
      registry.delete(this);
      this._clearTimer();
      this._abortInFlight();
    }

    pauseDueToFailure() {
      if (!this.running) return;
      this.pausedByFailure = true;
      this.paused = true;
      this._clearTimer();
      this._abortInFlight();
    }

    resumeFromConnectivity() {
      if (!this.running) return;
      this.pausedByFailure = false;
      this.paused = this.pausedByVisibility;
      this.consecutiveFailures = 0;
      this.currentIntervalMs = this.opts.intervalMs;
      if (!this.paused) {
        this._schedule(500);
      }
    }

    pauseForVisibility() {
      if (!this.running || !this.opts.pauseWhenHidden) return;
      this.pausedByVisibility = true;
      this.paused = true;
      this._clearTimer();
      this._abortInFlight();
    }

    resumeFromVisibility() {
      if (!this.running || !this.pausedByVisibility) return;
      this.pausedByVisibility = false;
      if (!this.pausedByFailure && Connectivity.isOnline()) {
        this.paused = false;
        this._schedule(300);
      }
    }

    _clearTimer() {
      if (this.timerId) {
        clearTimeout(this.timerId);
        this.timerId = null;
      }
    }

    _abortInFlight() {
      if (this.abortController) {
        this.abortController.abort();
        this.abortController = null;
      }
    }

    _schedule(delayMs) {
      this._clearTimer();
      if (!this.running || this.paused) return;

      const jitter = Math.random() * this.opts.jitterMs;
      this.timerId = setTimeout(() => this._tick(), delayMs + jitter);
    }

    async _tick() {
      if (!this.running || this.paused || this.inFlight) return;

      this.abortController = new AbortController();
      const signal = this.abortController.signal;
      this.inFlight = true;

      try {
        await this.tickFn({ signal });
        this.consecutiveFailures = 0;
        this.currentIntervalMs = this.opts.intervalMs;
        Connectivity.markOnline();
        if (this.onSuccess) this.onSuccess();
        this.inFlight = false;
        this.abortController = null;
        this._schedule(this.currentIntervalMs);
      } catch (err) {
        this.inFlight = false;
        this.abortController = null;

        if (err.name === "AbortError") return;

        this.consecutiveFailures += 1;

        const isOffline =
          err.offline ||
          err.code === "NETWORK_ERROR" ||
          err.status === 0 ||
          (err.status >= 500 && err.status !== 503);

        if (isOffline) {
          Connectivity.markOffline(err.message);
          this.currentIntervalMs = Math.min(
            this.currentIntervalMs * 2,
            this.opts.maxIntervalMs
          );
        }

        if (this.onError) this.onError(err, { isOffline, attempt: this.consecutiveFailures });

        if (this.consecutiveFailures >= this.opts.maxConsecutiveFailures) {
          this.pauseDueToFailure();
          if (this.onPaused) this.onPaused(err);
          return;
        }

        if (this.running && !this.paused) {
          this._schedule(this.currentIntervalMs);
        }
      }
    }
  }

  /**
   * Poll a single report job until terminal state.
   */
  class JobPoller {
    constructor(reportId, onUpdate, options = {}) {
      this.reportId = reportId;
      this.onUpdate = onUpdate;
      this.terminal = new Set(["COMPLETED", "FAILED", "CANCELED"]);

      this.manager = new PollingManager(
        `job-${reportId}`,
        async ({ signal }) => {
          const data = await ReportAPI.getStatus(this.reportId, { signal });
          this.onUpdate(data, null);

          if (this.terminal.has(data.status)) {
            this.stop();
            return;
          }
          if (data.status !== "CANCEL_REQUESTED") {
            // keep polling
          }
        },
        {
          intervalMs: options.intervalMs || 2000,
          maxIntervalMs: 30000,
          maxConsecutiveFailures: 8,
          pauseWhenHidden: true,
        }
      );
    }

    start() {
      this.manager.start();
    }

    stop() {
      this.manager.stop();
    }
  }

  function stopAllPollers() {
    registry.forEach((p) => p.stop());
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
  }

  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      registry.forEach((p) => p.pauseForVisibility());
    } else {
      registry.forEach((p) => p.resumeFromVisibility());
      if (Connectivity.state !== "online") {
        Connectivity._scheduleReconnectProbe();
      }
    }
  });

  window.addEventListener("pagehide", stopAllPollers);
  window.addEventListener("beforeunload", stopAllPollers);

  window.PollingManager = PollingManager;
  window.JobPoller = JobPoller;
  window.Connectivity = Connectivity;
  window.PollerRegistry = { stopAll: stopAllPollers, size: () => registry.size };
})();
