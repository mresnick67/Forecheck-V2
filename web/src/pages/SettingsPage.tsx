import { useEffect, useState } from "react";

import { authRequest, refreshSession } from "../api";
import type { AuthSession, User } from "../types";

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
  current_season_id: string;
  last_game_log_sync_at?: string | null;
  game_log_checkpoint_date?: string | null;
  game_log_row_count: number;
  game_log_min_date?: string | null;
  game_log_max_date?: string | null;
  running_jobs: string[];
  recent_runs: AdminRun[];
};

type SettingsPageProps = {
  session: AuthSession;
  onSession: (session: AuthSession | null) => void;
};

export default function SettingsPage({ session, onSession }: SettingsPageProps) {
  const [user, setUser] = useState<User | null>(null);
  const [adminStatus, setAdminStatus] = useState<AdminStatus | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadAdminStatus() {
    try {
      const payload = await authRequest<AdminStatus>("/admin/status", session, onSession);
      setAdminStatus(payload);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin status");
    }
  }

  useEffect(() => {
    async function loadProfile() {
      try {
        const me = await authRequest<User>("/auth/me", session, onSession);
        setUser(me);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load profile");
      }
    }

    void loadProfile();
    void loadAdminStatus();
  }, [session, onSession]);

  async function runPipeline() {
    setError(null);
    setStatus(null);

    try {
      const payload = await authRequest<{ game_logs_updated: number; rolling_stats_updated: number }>(
        "/admin/sync/pipeline",
        session,
        onSession,
        { method: "POST" },
      );
      setStatus(
        `Pipeline complete. Game logs: ${payload.game_logs_updated}, rolling stats: ${payload.rolling_stats_updated}`,
      );
      await loadAdminStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pipeline failed");
    }
  }

  async function runFullBackfill() {
    setError(null);
    setStatus(null);
    try {
      const payload = await authRequest<{ updated: number }>(
        "/admin/sync/game-logs/full?reset_existing=false",
        session,
        onSession,
        { method: "POST" },
      );
      setStatus(`Full-season game-log backfill complete. Rows touched: ${payload.updated}`);
      await loadAdminStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Full backfill failed");
    }
  }

  async function forceRefreshToken() {
    setError(null);
    setStatus(null);

    try {
      const refreshed = await refreshSession(session);
      onSession(refreshed);
      setStatus("Session token refreshed.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Refresh failed");
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
      </section>

      <section className="card">
        <h2>Admin Pipeline</h2>
        <p className="muted">Run analytics sync on demand. All authenticated users are treated as admin in v2.</p>

        <button className="primary" onClick={() => void runPipeline()}>
          Run Sync Pipeline
        </button>
        <button onClick={() => void runFullBackfill()}>Run Full-Season Game Log Backfill</button>
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
            </ul>
          </>
        ) : (
          <p className="muted">Loading sync status...</p>
        )}

        {status ? <p className="success">{status}</p> : null}
      </section>

      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
