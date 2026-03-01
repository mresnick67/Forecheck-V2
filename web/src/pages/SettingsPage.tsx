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

  async function loadAdminStatus() {
    try {
      const payload = await authRequest<AdminStatus>("/admin/status", session, onSession);
      setAdminStatus(payload);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load admin status"));
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
    async function loadProfile() {
      try {
        const me = await authRequest<User>("/auth/me", session, onSession);
        setUser(me);
      } catch (err) {
        setError(getErrorMessage(err, "Failed to load profile"));
      }
    }

    void loadProfile();
    void loadAdminStatus();
    void loadYahooStatus();
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
  }, [session]);

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
    <div className="grid cols-2">
      <section className="card">
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

      <section className="card">
        <h2>Admin Pipeline</h2>
        <p className="muted">Run analytics sync on demand. All authenticated users are treated as admin in v2.</p>

        <button className="primary" onClick={() => void runPipeline()}>
          Run Sync Pipeline
        </button>
        <button onClick={() => void runFullBackfill()}>Run Full-Season Game Log Backfill</button>
        <button onClick={() => void refreshScanCounts()}>Refresh Scan Counts</button>
        <button onClick={() => void loadAdminStatus()}>Refresh Sync Status</button>

        {adminStatus ? (
          <>
            <p className="muted">
              Season {adminStatus.current_season_id} | Sync enabled: {adminStatus.nhl_sync_enabled ? "Yes" : "No"} |
              Worker loop: {adminStatus.run_sync_loop ? "On" : "Off"}
            </p>
            <ul>
              <li>Running jobs: {adminStatus.running_jobs.length ? adminStatus.running_jobs.join(", ") : "none"}</li>
              <li>Game log rows: {adminStatus.game_log_row_count}</li>
              <li>
                Game log coverage: {adminStatus.game_log_min_date ?? "n/a"} to {adminStatus.game_log_max_date ?? "n/a"}
              </li>
              <li>Checkpoint date: {adminStatus.game_log_checkpoint_date ?? "n/a"}</li>
              <li>Last game-log sync: {adminStatus.last_game_log_sync_at ?? "n/a"}</li>
              <li>Last rolling-stats sync: {adminStatus.last_rolling_stats_at ?? "n/a"}</li>
              <li>Last scan-count refresh: {adminStatus.last_scan_counts_at ?? "n/a"}</li>
              <li>Last Yahoo ownership sync: {adminStatus.last_ownership_sync_at ?? "n/a"}</li>
            </ul>
          </>
        ) : (
          <p className="muted">Loading sync status...</p>
        )}

        {status ? <p className="success">{status}</p> : null}
      </section>

      <section className="card">
        <h2>Yahoo Integration</h2>
        <p className="muted">Connect Yahoo from this device and sync ownership into streamer workflows.</p>

        {adminStatus?.yahoo_enabled ? (
          <>
            <ul>
              <li>Enabled: Yes</li>
              <li>Connected: {yahooStatus?.connected ? "Yes" : "No"}</li>
              <li>Yahoo GUID: {yahooStatus?.yahoo_user_guid ?? "n/a"}</li>
              <li>Token expires: {yahooStatus?.expires_at ?? "n/a"}</li>
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
          </>
        ) : (
          <p className="muted">
            Yahoo is disabled. Set `YAHOO_ENABLED=true` plus Yahoo client env vars in `docker-compose.yml`, then restart.
          </p>
        )}
      </section>

      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
