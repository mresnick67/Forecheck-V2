import { useEffect, useState } from "react";

import { authRequest, refreshSession } from "../api";
import type { AuthSession, Scan, User } from "../types";

type AdminRun = {
  job: string;
  status: string;
  started_at: string;
  finished_at?: string | null;
  row_count: number;
  error?: string | null;
};

type AdminStatus = {
  app_mode: string;
  run_sync_loop: boolean;
  nhl_sync_enabled: boolean;
  yahoo_enabled: boolean;
  yahoo_connected: boolean;
  current_season_id: string;
  last_game_log_sync_at?: string | null;
  last_rolling_stats_at?: string | null;
  last_scan_counts_at?: string | null;
  last_ownership_sync_at?: string | null;
  game_log_checkpoint_date?: string | null;
  game_log_row_count: number;
  game_log_min_date?: string | null;
  game_log_max_date?: string | null;
  running_jobs: string[];
  recent_runs: AdminRun[];
};

type YahooConnectionStatus = {
  connected: boolean;
  yahoo_user_guid?: string | null;
  expires_at?: string | null;
};

type BeforeInstallPromptEvent = Event & {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed"; platform: string }>;
};

type SettingsPageProps = {
  session: AuthSession;
  onSession: (session: AuthSession | null) => void;
};

function formatDateTime(value?: string | null): string {
  if (!value) return "n/a";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatDuration(startedAt?: string | null, finishedAt?: string | null): string {
  if (!startedAt) return "n/a";
  if (!finishedAt) return "running";
  const start = new Date(startedAt);
  const end = new Date(finishedAt);
  const diffSeconds = Math.max(0, Math.round((end.getTime() - start.getTime()) / 1000));
  if (!Number.isFinite(diffSeconds)) return "n/a";
  if (diffSeconds < 60) return `${diffSeconds}s`;
  const minutes = Math.floor(diffSeconds / 60);
  const seconds = diffSeconds % 60;
  if (minutes < 60) return seconds ? `${minutes}m ${seconds}s` : `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes ? `${hours}h ${remainingMinutes}m` : `${hours}h`;
}

function runBadgeClass(status: string): string {
  const normalized = status.toLowerCase();
  if (normalized === "success") return "run-badge run-success";
  if (normalized === "failed") return "run-badge run-failed";
  if (normalized === "running") return "run-badge run-running";
  if (normalized === "skipped") return "run-badge run-skipped";
  return "run-badge";
}

function compactError(value?: string | null): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  return trimmed.length > 200 ? `${trimmed.slice(0, 200)}...` : trimmed;
}

export default function SettingsPage({ session, onSession }: SettingsPageProps) {
  const [user, setUser] = useState<User | null>(null);
  const [adminStatus, setAdminStatus] = useState<AdminStatus | null>(null);
  const [yahooStatus, setYahooStatus] = useState<YahooConnectionStatus | null>(null);
  const [deferredInstall, setDeferredInstall] = useState<BeforeInstallPromptEvent | null>(null);
  const [isStandalone, setIsStandalone] = useState<boolean>(() => {
    const nav = navigator as Navigator & { standalone?: boolean };
    return window.matchMedia("(display-mode: standalone)").matches || Boolean(nav.standalone);
  });
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function getErrorMessage(err: unknown, fallback: string): string {
    if (!(err instanceof Error)) return fallback;
    try {
      const payload = JSON.parse(err.message);
      if (payload && typeof payload.detail === "string") return payload.detail;
    } catch {
      // Keep original message when body is not JSON.
    }
    return err.message || fallback;
  }

  async function loadAdminStatus(): Promise<AdminStatus | null> {
    try {
      const payload = await authRequest<AdminStatus>("/admin/status", session, onSession);
      setAdminStatus(payload);
      return payload;
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load admin status"));
      return null;
    }
  }

  async function loadYahooStatus() {
    try {
      const payload = await authRequest<YahooConnectionStatus>("/auth/yahoo/status", session, onSession);
      setYahooStatus(payload);
    } catch (err) {
      setYahooStatus(null);
      setError(getErrorMessage(err, "Failed to load Yahoo connection status"));
    }
  }

  useEffect(() => {
    let canceled = false;

    async function loadProfile() {
      try {
        const me = await authRequest<User>("/auth/me", session, onSession);
        if (!canceled) {
          setUser(me);
        }
      } catch (err) {
        if (!canceled) {
          setError(getErrorMessage(err, "Failed to load profile"));
        }
      }
    }

    async function loadDashboard() {
      const payload = await loadAdminStatus();
      if (canceled) return;
      if (payload?.yahoo_enabled) {
        await loadYahooStatus();
      } else {
        setYahooStatus(null);
      }
    }

    void Promise.all([loadProfile(), loadDashboard()]);

    return () => {
      canceled = true;
    };
  }, [session, onSession]);

  useEffect(() => {
    function onBeforeInstallPrompt(event: Event) {
      event.preventDefault();
      setDeferredInstall(event as BeforeInstallPromptEvent);
    }

    function onInstalled() {
      setIsStandalone(true);
      setDeferredInstall(null);
      setStatus("App installed.");
    }

    function updateStandalone() {
      const nav = navigator as Navigator & { standalone?: boolean };
      setIsStandalone(window.matchMedia("(display-mode: standalone)").matches || Boolean(nav.standalone));
    }

    function onMessage(event: MessageEvent) {
      if (!event.data || event.data.type !== "forecheck-yahoo-connected") return;
      if (!adminStatus?.yahoo_enabled) return;
      setStatus("Yahoo authorization completed.");
      void loadYahooStatus();
      void loadAdminStatus();
    }

    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt as EventListener);
    window.addEventListener("appinstalled", onInstalled);
    window.addEventListener("focus", updateStandalone);
    window.addEventListener("message", onMessage);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt as EventListener);
      window.removeEventListener("appinstalled", onInstalled);
      window.removeEventListener("focus", updateStandalone);
      window.removeEventListener("message", onMessage);
    };
  }, [adminStatus?.yahoo_enabled]);

  const runningJobsKey = adminStatus?.running_jobs.join("|") ?? "";

  useEffect(() => {
    if (!adminStatus || adminStatus.running_jobs.length === 0) return;
    const intervalId = window.setInterval(() => {
      void loadAdminStatus();
    }, 10000);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [runningJobsKey, session, onSession]);

  async function runPipeline() {
    setError(null);
    setStatus(null);

    try {
      const payload = await authRequest<{ game_logs_updated: number; rolling_stats_updated: number; scan_counts_updated?: number | null }>(
        "/admin/sync/pipeline",
        session,
        onSession,
        { method: "POST" },
      );
      setStatus(
        `Pipeline complete. Game logs: ${payload.game_logs_updated}, rolling stats: ${payload.rolling_stats_updated}, scan counts: ${payload.scan_counts_updated ?? "n/a"}`,
      );
      await loadAdminStatus();
    } catch (err) {
      setError(getErrorMessage(err, "Pipeline failed"));
    }
  }

  async function runFullBackfill() {
    setError(null);
    setStatus(null);
    try {
      const payload = await authRequest<{ updated: number; rolling_stats_updated?: number | null; scan_counts_updated?: number | null }>(
        "/admin/sync/game-logs/full?reset_existing=false",
        session,
        onSession,
        { method: "POST" },
      );
      setStatus(
        `Full-season game-log backfill complete. Rows: ${payload.updated}, rolling stats: ${payload.rolling_stats_updated ?? "n/a"}, scan counts: ${payload.scan_counts_updated ?? "n/a"}`,
      );
      await loadAdminStatus();
    } catch (err) {
      setError(getErrorMessage(err, "Full backfill failed"));
    }
  }

  async function refreshScanCounts() {
    setError(null);
    setStatus(null);
    try {
      const payload = await authRequest<Scan[]>(
        "/scans/refresh-counts?include_hidden=true&force=true",
        session,
        onSession,
        { method: "POST" },
      );
      setStatus(`Scan counts refreshed for ${payload.length} scans.`);
      await loadAdminStatus();
    } catch (err) {
      setError(getErrorMessage(err, "Scan count refresh failed"));
    }
  }

  async function connectYahoo() {
    setError(null);
    setStatus(null);
    try {
      const payload = await authRequest<{ authorization_url: string }>(
        "/auth/yahoo/login?redirect=false",
        session,
        onSession,
      );
      const popup = window.open(payload.authorization_url, "forecheck-yahoo-auth", "width=680,height=800");
      if (!popup) {
        window.location.href = payload.authorization_url;
        return;
      }
      popup.focus();
      setStatus("Yahoo authorization opened in popup.");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to open Yahoo authorization"));
    }
  }

  async function disconnectYahoo() {
    setError(null);
    setStatus(null);
    try {
      await authRequest("/auth/yahoo/disconnect", session, onSession, { method: "POST" });
      setStatus("Yahoo disconnected.");
      await loadYahooStatus();
      await loadAdminStatus();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to disconnect Yahoo"));
    }
  }

  async function refreshYahooToken() {
    setError(null);
    setStatus(null);
    try {
      await authRequest("/auth/yahoo/refresh", session, onSession, { method: "POST" });
      setStatus("Yahoo token refreshed.");
      await loadYahooStatus();
    } catch (err) {
      setError(getErrorMessage(err, "Failed to refresh Yahoo token"));
    }
  }

  async function syncYahooOwnership() {
    setError(null);
    setStatus(null);
    try {
      const payload = await authRequest<{ updated: number }>("/admin/sync/ownership", session, onSession, {
        method: "POST",
      });
      setStatus(`Yahoo ownership synced for ${payload.updated} players.`);
      await loadAdminStatus();
    } catch (err) {
      setError(getErrorMessage(err, "Yahoo ownership sync failed"));
    }
  }

  async function installApp() {
    setError(null);
    setStatus(null);
    if (!deferredInstall) {
      setStatus("Use your browser menu to install this app to desktop/home screen.");
      return;
    }
    await deferredInstall.prompt();
    const choice = await deferredInstall.userChoice;
    if (choice.outcome === "accepted") {
      setStatus("Install accepted.");
    } else {
      setStatus("Install dismissed.");
    }
    setDeferredInstall(null);
  }

  async function forceRefreshToken() {
    setError(null);
    setStatus(null);

    try {
      const refreshed = await refreshSession(session);
      onSession(refreshed);
      setStatus("Session token refreshed.");
    } catch (err) {
      setError(getErrorMessage(err, "Refresh failed"));
    }
  }

  function logout() {
    onSession(null);
  }

  return (
    <div className="page-stack settings-stack">
      <section className="card ios-card">
        <h2>Account</h2>
        {user ? (
          <ul>
            <li>Username: {user.username}</li>
            <li>Email: {user.email}</li>
            <li>Display name: {user.display_name}</li>
            <li>Scans created: {user.scans_created}</li>
          </ul>
        ) : (
          <p className="muted">Loading account...</p>
        )}

        <p>
          <button onClick={() => void forceRefreshToken()}>Refresh Session</button>{" "}
          <button className="danger" onClick={logout}>
            Logout
          </button>
        </p>

        <h3>PWA Install</h3>
        <p className="muted">
          Install mode: {isStandalone ? "installed" : "browser"}
        </p>
        <div className="button-row">
          <button onClick={() => void installApp()} disabled={isStandalone}>
            {isStandalone ? "Installed" : "Install App"}
          </button>
        </div>
      </section>

      <section className="card ios-card">
        <h2>Admin Pipeline</h2>
        <p className="muted">Run analytics sync on demand. All authenticated users are treated as admin in v2.</p>

        <div className="button-row">
          <button className="primary" onClick={() => void runPipeline()}>
            Run Sync Pipeline
          </button>
          <button onClick={() => void runFullBackfill()}>Run Full-Season Game Log Backfill</button>
          <button onClick={() => void refreshScanCounts()}>Refresh Scan Counts</button>
          <button onClick={() => void loadAdminStatus()}>Refresh Sync Status</button>
        </div>

        {adminStatus ? (
          <>
            <p className="muted">
              Season {adminStatus.current_season_id} | Sync enabled: {adminStatus.nhl_sync_enabled ? "Yes" : "No"} |
              Worker loop: {adminStatus.run_sync_loop ? "On" : "Off"}
            </p>
            <div className="sync-summary-grid">
              <article className="sync-summary-card">
                <small className="muted">Running jobs</small>
                <strong>{adminStatus.running_jobs.length || 0}</strong>
                <small className="muted">
                  {adminStatus.running_jobs.length ? adminStatus.running_jobs.join(", ") : "Idle"}
                </small>
              </article>
              <article className="sync-summary-card">
                <small className="muted">Game log rows</small>
                <strong>{adminStatus.game_log_row_count.toLocaleString()}</strong>
                <small className="muted">
                  {adminStatus.game_log_min_date ?? "n/a"} to {adminStatus.game_log_max_date ?? "n/a"}
                </small>
              </article>
              <article className="sync-summary-card">
                <small className="muted">Last game-log sync</small>
                <strong>{formatDateTime(adminStatus.last_game_log_sync_at)}</strong>
                <small className="muted">Checkpoint: {adminStatus.game_log_checkpoint_date ?? "n/a"}</small>
              </article>
              <article className="sync-summary-card">
                <small className="muted">Stats + scans refresh</small>
                <strong>{formatDateTime(adminStatus.last_rolling_stats_at)}</strong>
                <small className="muted">Scan counts: {formatDateTime(adminStatus.last_scan_counts_at)}</small>
              </article>
            </div>
          </>
        ) : (
          <p className="muted">Loading sync status...</p>
        )}
      </section>

      <section className="card ios-card">
        <div className="list-head">
          <h2>Recent Sync Runs</h2>
          <small className="muted">{adminStatus?.recent_runs.length ?? 0} runs</small>
        </div>
        <p className="muted">Latest worker and admin-triggered jobs with status and error details.</p>
        {adminStatus?.recent_runs.length ? (
          <div className="run-list">
            {adminStatus.recent_runs.map((run) => (
              <article key={`${run.job}-${run.started_at}`} className="run-item">
                <div className="run-head">
                  <strong>{run.job}</strong>
                  <span className={runBadgeClass(run.status)}>{run.status}</span>
                </div>
                <p className="muted compact">
                  Rows: {run.row_count.toLocaleString()} • Started: {formatDateTime(run.started_at)} • Duration:{" "}
                  {formatDuration(run.started_at, run.finished_at)}
                </p>
                {run.finished_at ? <small className="muted">Finished: {formatDateTime(run.finished_at)}</small> : null}
                {compactError(run.error) ? <p className="run-error">{compactError(run.error)}</p> : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="muted">No runs recorded yet.</p>
        )}
      </section>

      {adminStatus?.yahoo_enabled ? (
        <section className="card ios-card">
          <h2>Yahoo Integration</h2>
          <p className="muted">Optional OAuth integration for ownership sync.</p>
          <ul>
            <li>Enabled: Yes</li>
            <li>Connected: {yahooStatus?.connected ? "Yes" : "No"}</li>
            <li>Yahoo GUID: {yahooStatus?.yahoo_user_guid ?? "n/a"}</li>
            <li>Token expires: {formatDateTime(yahooStatus?.expires_at)}</li>
            <li>Last ownership sync: {formatDateTime(adminStatus.last_ownership_sync_at)}</li>
          </ul>
          <div className="button-row">
            <button className="primary" onClick={() => void connectYahoo()}>
              Connect Yahoo
            </button>
            <button onClick={() => void refreshYahooToken()} disabled={!yahooStatus?.connected}>
              Refresh Yahoo Token
            </button>
            <button onClick={() => void syncYahooOwnership()} disabled={!yahooStatus?.connected}>
              Sync Yahoo Ownership
            </button>
            <button className="danger" onClick={() => void disconnectYahoo()} disabled={!yahooStatus?.connected}>
              Disconnect Yahoo
            </button>
            <button onClick={() => void loadYahooStatus()}>Refresh Yahoo Status</button>
          </div>
        </section>
      ) : (
        <section className="card ios-card">
          <h2>External Integrations</h2>
          <p className="muted">
            Yahoo OAuth is intentionally disabled in local-first mode. Core analytics and scans run fully without it.
            Planned Yahoo support path: browser extension overlay for yahoo.com/fantasy pages.
          </p>
        </section>
      )}

      {status ? <p className="success">{status}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
