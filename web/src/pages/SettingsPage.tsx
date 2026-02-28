import { useEffect, useState } from "react";

import { authRequest, refreshSession } from "../api";
import type { AuthSession, User } from "../types";

type SettingsPageProps = {
  session: AuthSession;
  onSession: (session: AuthSession | null) => void;
};

export default function SettingsPage({ session, onSession }: SettingsPageProps) {
  const [user, setUser] = useState<User | null>(null);
  const [adminKey, setAdminKey] = useState("");
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
  }, [session]);

  async function runPipeline() {
    setError(null);
    setStatus(null);

    try {
      const response = await fetch("/api/admin/sync/pipeline", {
        method: "POST",
        headers: {
          "X-Admin-Key": adminKey,
        },
      });

      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "Pipeline failed");
      }

      const payload = (await response.json()) as { game_logs_updated: number; rolling_stats_updated: number };
      setStatus(
        `Pipeline complete. Game logs: ${payload.game_logs_updated}, rolling stats: ${payload.rolling_stats_updated}`,
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Pipeline failed");
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
        <p className="muted">Run full analytics sync on demand.</p>

        <label>
          Admin API key
          <input value={adminKey} onChange={(event) => setAdminKey(event.target.value)} />
        </label>

        <button className="primary" onClick={() => void runPipeline()}>
          Run Sync Pipeline
        </button>

        {status ? <p className="success">{status}</p> : null}
      </section>

      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
