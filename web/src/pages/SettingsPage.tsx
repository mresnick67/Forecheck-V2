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
  current_season_id: string;
  last_game_log_sync_at?: string | null;
  last_rolling_stats_at?: string | null;
  last_scan_counts_at?: string | null;
  game_log_checkpoint_date?: string | null;
  game_log_row_count: number;
  game_log_min_date?: string | null;
  game_log_max_date?: string | null;
  running_jobs: string[];
  recent_runs: AdminRun[];
};

type StreamerScoreConfig = {
  league_influence: {
    enabled: boolean;
    weight: number;
    minimum_games: number;
  };
  skater: {
    weights: Record<string, number>;
    caps: {
      forward: Record<string, number>;
      defense: Record<string, number>;
    };
    toggles: Record<string, boolean>;
    toi_gate: Record<string, number>;
  };
  goalie: {
    weights: Record<string, number>;
    scales: Record<string, number>;
    toggles: Record<string, boolean>;
  };
};

type StreamerRecalcProgress = {
  running: boolean;
  status: string;
  run_id?: string | null;
  processed_players: number;
  total_players: number;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
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

function labelize(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

const STREAMER_SCORE_HELP: Record<string, string> = {
  "league_influence.enabled":
    "When enabled, streamer score blends your base model with league-fit scoring from the active league profile.",
  "league_influence.weight":
    "Blend ratio for league-fit impact. 0 keeps pure base model; 1 uses only league-fit scoring.",
  "league_influence.minimum_games":
    "Required sample size before full league blending. Smaller samples get reduced league influence.",

  "skater.weights.points_per_game": "Impact of point production (P/GP) in skater streamer score.",
  "skater.weights.shots_per_game": "Impact of shot volume (SOG/GP).",
  "skater.weights.power_play_points_per_game": "Impact of power-play scoring rate (PPP/GP).",
  "skater.weights.time_on_ice_per_game": "Impact of average time on ice per game.",
  "skater.weights.plus_minus_per_game": "Impact of +/- per game when plus/minus toggle is enabled.",
  "skater.weights.hits_blocks_per_game": "Impact of combined hits + blocks rate when that toggle is enabled.",
  "skater.weights.trend_hot_bonus": "Bonus added for players marked as hot trend.",
  "skater.weights.trend_stable_bonus": "Bonus added for players marked as stable trend.",
  "skater.weights.availability_bonus":
    "Bonus for low-rostered players when availability scoring is enabled.",

  "skater.toggles.use_plus_minus": "Include plus/minus component in skater score.",
  "skater.toggles.use_hits_blocks": "Include hits + blocks component in skater score.",
  "skater.toggles.use_trend_bonus": "Apply trend bonuses (hot/stable) to score.",
  "skater.toggles.use_availability_bonus": "Reward lower ownership (waiver availability).",
  "skater.toggles.use_toi_gate_for_availability":
    "Scale availability bonus by TOI floor so low-usage players are de-emphasized.",

  "skater.caps.forward.points_per_game": "Forward normalization cap for P/GP.",
  "skater.caps.forward.shots_per_game": "Forward normalization cap for SOG/GP.",
  "skater.caps.forward.power_play_points_per_game": "Forward normalization cap for PPP/GP.",
  "skater.caps.forward.time_on_ice_per_game": "Forward normalization cap for TOI/GP.",
  "skater.caps.forward.hits_blocks_per_game": "Forward normalization cap for combined hits + blocks per game.",

  "skater.caps.defense.points_per_game": "Defense normalization cap for P/GP.",
  "skater.caps.defense.shots_per_game": "Defense normalization cap for SOG/GP.",
  "skater.caps.defense.power_play_points_per_game": "Defense normalization cap for PPP/GP.",
  "skater.caps.defense.time_on_ice_per_game": "Defense normalization cap for TOI/GP.",
  "skater.caps.defense.hits_blocks_per_game": "Defense normalization cap for combined hits + blocks per game.",

  "skater.toi_gate.forward_floor":
    "Minimum forward TOI baseline used by availability gating.",
  "skater.toi_gate.defense_floor":
    "Minimum defense TOI baseline used by availability gating.",

  "goalie.weights.save_percentage": "Impact of save percentage quality.",
  "goalie.weights.goals_against_average": "Impact of goals-against-average quality (lower is better).",
  "goalie.weights.wins": "Impact of win rate over the window.",
  "goalie.weights.starts": "Impact of start volume/share over the window.",
  "goalie.weights.trend_hot_bonus": "Bonus for hot-trending goalies.",
  "goalie.weights.trend_stable_bonus": "Bonus for stable-trending goalies.",
  "goalie.weights.availability_bonus": "Bonus for low-rostered goalies when enabled.",

  "goalie.scales.save_percentage_floor":
    "Lower bound for save% normalization. Values at/under this contribute minimally.",
  "goalie.scales.save_percentage_range":
    "Normalization range above floor for save%. Larger range makes scale less sensitive.",
  "goalie.scales.goals_against_average_ceiling":
    "Upper GAA threshold used for normalization (lower GAA scores better).",
  "goalie.scales.goals_against_average_range":
    "Normalization range beneath GAA ceiling. Larger range makes scale less sensitive.",

  "goalie.toggles.use_trend_bonus": "Apply trend bonuses to goalie score.",
  "goalie.toggles.use_availability_bonus": "Reward lower ownership for goalies.",
  "goalie.toggles.use_sample_penalty":
    "Apply a penalty for very small goalie samples (e.g., 1 game).",
};

function helpText(path: string): string | undefined {
  return STREAMER_SCORE_HELP[path];
}

type HelpLabelProps = {
  text: string;
  tip?: string;
};

function HelpLabel({ text, tip }: HelpLabelProps) {
  return (
    <span className="help-label">
      <span>{text}</span>
      {tip ? (
        <span
          className="help-dot"
          tabIndex={0}
          role="note"
          aria-label={tip}
          data-tip={tip}
        >
          i
        </span>
      ) : null}
    </span>
  );
}

export default function SettingsPage({ session, onSession }: SettingsPageProps) {
  const [user, setUser] = useState<User | null>(null);
  const [adminStatus, setAdminStatus] = useState<AdminStatus | null>(null);
  const [scoreDraft, setScoreDraft] = useState<StreamerScoreConfig | null>(null);
  const [scoreSaving, setScoreSaving] = useState(false);
  const [recalcProgress, setRecalcProgress] = useState<StreamerRecalcProgress | null>(null);
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

  async function loadStreamerScoreConfig() {
    try {
      const payload = await authRequest<{ config: StreamerScoreConfig }>(
        "/admin/streamer-score/config",
        session,
        onSession,
      );
      setScoreDraft(payload.config);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load streamer score config"));
    }
  }

  async function loadStreamerRecalcProgress() {
    try {
      const payload = await authRequest<StreamerRecalcProgress>(
        "/admin/streamer-score/recalculate",
        session,
        onSession,
      );
      setRecalcProgress(payload);
    } catch (err) {
      setError(getErrorMessage(err, "Failed to load recalculation progress"));
    }
  }

  function updateScoreNumber(
    group: "league_influence" | "skater" | "goalie",
    section: "weights" | "caps" | "toggles" | "toi_gate" | "scales" | "league_influence",
    key: string,
    value: number,
    nested?: "forward" | "defense",
  ) {
    setScoreDraft((prev) => {
      if (!prev) return prev;
      const next = JSON.parse(JSON.stringify(prev)) as StreamerScoreConfig;
      if (group === "league_influence" && section === "league_influence") {
        if (key === "weight" || key === "minimum_games") {
          next.league_influence[key] = value;
        }
      } else if (group === "skater" && section === "caps" && nested) {
        next.skater.caps[nested][key] = value;
      } else if (group === "skater" && section === "toi_gate") {
        next.skater.toi_gate[key] = value;
      } else if (group === "skater" && section === "weights") {
        next.skater.weights[key] = value;
      } else if (group === "goalie" && section === "weights") {
        next.goalie.weights[key] = value;
      } else if (group === "goalie" && section === "scales") {
        next.goalie.scales[key] = value;
      }
      return next;
    });
  }

  function updateScoreToggle(group: "league_influence" | "skater" | "goalie", key: string, value: boolean) {
    setScoreDraft((prev) => {
      if (!prev) return prev;
      const next = JSON.parse(JSON.stringify(prev)) as StreamerScoreConfig;
      if (group === "league_influence") {
        if (key === "enabled") {
          next.league_influence.enabled = value;
        }
      } else if (group === "skater") {
        next.skater.toggles[key] = value;
      } else {
        next.goalie.toggles[key] = value;
      }
      return next;
    });
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
      await loadAdminStatus();
      if (canceled) return;
      await loadStreamerScoreConfig();
      if (canceled) return;
      await loadStreamerRecalcProgress();
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

    window.addEventListener("beforeinstallprompt", onBeforeInstallPrompt as EventListener);
    window.addEventListener("appinstalled", onInstalled);
    window.addEventListener("focus", updateStandalone);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstallPrompt as EventListener);
      window.removeEventListener("appinstalled", onInstalled);
      window.removeEventListener("focus", updateStandalone);
    };
  }, []);

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

  useEffect(() => {
    if (!recalcProgress?.running) return;
    const intervalId = window.setInterval(() => {
      void loadStreamerRecalcProgress();
      void loadAdminStatus();
    }, 2000);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [recalcProgress?.running, session, onSession]);

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

  async function saveScoreConfigAndRecalculate() {
    if (!scoreDraft) return;
    setError(null);
    setStatus(null);
    setScoreSaving(true);
    try {
      const saved = await authRequest<{ config: StreamerScoreConfig }>(
        "/admin/streamer-score/config",
        session,
        onSession,
        {
          method: "PUT",
          json: { config: scoreDraft },
        },
      );
      setScoreDraft(saved.config);

      const progress = await authRequest<StreamerRecalcProgress>(
        "/admin/streamer-score/recalculate",
        session,
        onSession,
        { method: "POST" },
      );
      setRecalcProgress(progress);
      setStatus("Streamer score config saved. Recalculation started.");
    } catch (err) {
      setError(getErrorMessage(err, "Failed to save streamer score config"));
    } finally {
      setScoreSaving(false);
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

  const recalcPercent =
    recalcProgress && recalcProgress.total_players > 0
      ? Math.min(100, Math.round((recalcProgress.processed_players / recalcProgress.total_players) * 100))
      : 0;

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
          <h2>Streamer Score Model</h2>
          <small className="muted">Editable weights + toggles</small>
        </div>
        <p className="muted">Adjust scoring components, save, and run a full rolling-stat recalculation.</p>
        {!scoreDraft ? (
          <p className="muted">Loading model settings...</p>
        ) : (
          <div className="score-config-grid">
            <article className="score-config-card">
              <h3>League Influence</h3>
              <p className="muted compact">
                Blend league scoring fit into streamer score using your active league profile.
              </p>
              <div className="score-toggle-grid">
                <label className="score-toggle-row">
                  <input
                    type="checkbox"
                    checked={Boolean(scoreDraft.league_influence.enabled)}
                    onChange={(event) =>
                      updateScoreToggle("league_influence", "enabled", event.target.checked)
                    }
                  />
                  <HelpLabel
                    text="Enable league-fit blending"
                    tip={helpText("league_influence.enabled")}
                  />
                </label>
              </div>
              <div className="score-config-fields">
                <label>
                  <HelpLabel
                    text="League Weight (0-1)"
                    tip={helpText("league_influence.weight")}
                  />
                  <input
                    type="number"
                    min={0}
                    max={1}
                    step="0.05"
                    value={scoreDraft.league_influence.weight}
                    onChange={(event) =>
                      updateScoreNumber(
                        "league_influence",
                        "league_influence",
                        "weight",
                        Number(event.target.value) || 0,
                      )
                    }
                  />
                </label>
                <label>
                  <HelpLabel
                    text="Min Games Before Full Blend"
                    tip={helpText("league_influence.minimum_games")}
                  />
                  <input
                    type="number"
                    min={0}
                    max={82}
                    step="1"
                    value={scoreDraft.league_influence.minimum_games}
                    onChange={(event) =>
                      updateScoreNumber(
                        "league_influence",
                        "league_influence",
                        "minimum_games",
                        Number(event.target.value) || 0,
                      )
                    }
                  />
                </label>
              </div>
            </article>

            <article className="score-config-card">
              <h3>Skater Weights</h3>
              <div className="score-config-fields">
                {Object.entries(scoreDraft.skater.weights).map(([key, value]) => (
                  <label key={`skater-weight-${key}`}>
                    <HelpLabel
                      text={labelize(key)}
                      tip={helpText(`skater.weights.${key}`)}
                    />
                    <input
                      type="number"
                      step="0.1"
                      value={value}
                      onChange={(event) =>
                        updateScoreNumber("skater", "weights", key, Number(event.target.value) || 0)
                      }
                    />
                  </label>
                ))}
              </div>
              <h3>Skater Toggles</h3>
              <div className="score-toggle-grid">
                {Object.entries(scoreDraft.skater.toggles).map(([key, value]) => (
                  <label key={`skater-toggle-${key}`} className="score-toggle-row">
                    <input
                      type="checkbox"
                      checked={Boolean(value)}
                      onChange={(event) => updateScoreToggle("skater", key, event.target.checked)}
                    />
                    <HelpLabel
                      text={labelize(key)}
                      tip={helpText(`skater.toggles.${key}`)}
                    />
                  </label>
                ))}
              </div>
            </article>

            <article className="score-config-card">
              <h3>Skater Caps (Forwards)</h3>
              <div className="score-config-fields">
                {Object.entries(scoreDraft.skater.caps.forward).map(([key, value]) => (
                  <label key={`skater-forward-cap-${key}`}>
                    <HelpLabel
                      text={labelize(key)}
                      tip={helpText(`skater.caps.forward.${key}`)}
                    />
                    <input
                      type="number"
                      step="0.1"
                      value={value}
                      onChange={(event) =>
                        updateScoreNumber("skater", "caps", key, Number(event.target.value) || 0, "forward")
                      }
                    />
                  </label>
                ))}
              </div>

              <h3>Skater Caps (Defense)</h3>
              <div className="score-config-fields">
                {Object.entries(scoreDraft.skater.caps.defense).map(([key, value]) => (
                  <label key={`skater-defense-cap-${key}`}>
                    <HelpLabel
                      text={labelize(key)}
                      tip={helpText(`skater.caps.defense.${key}`)}
                    />
                    <input
                      type="number"
                      step="0.1"
                      value={value}
                      onChange={(event) =>
                        updateScoreNumber("skater", "caps", key, Number(event.target.value) || 0, "defense")
                      }
                    />
                  </label>
                ))}
              </div>

              <h3>TOI Gate</h3>
              <div className="score-config-fields">
                {Object.entries(scoreDraft.skater.toi_gate).map(([key, value]) => (
                  <label key={`skater-toi-gate-${key}`}>
                    <HelpLabel
                      text={labelize(key)}
                      tip={helpText(`skater.toi_gate.${key}`)}
                    />
                    <input
                      type="number"
                      step="0.1"
                      value={value}
                      onChange={(event) =>
                        updateScoreNumber("skater", "toi_gate", key, Number(event.target.value) || 0)
                      }
                    />
                  </label>
                ))}
              </div>
            </article>

            <article className="score-config-card">
              <h3>Goalie Weights</h3>
              <div className="score-config-fields">
                {Object.entries(scoreDraft.goalie.weights).map(([key, value]) => (
                  <label key={`goalie-weight-${key}`}>
                    <HelpLabel
                      text={labelize(key)}
                      tip={helpText(`goalie.weights.${key}`)}
                    />
                    <input
                      type="number"
                      step="0.1"
                      value={value}
                      onChange={(event) =>
                        updateScoreNumber("goalie", "weights", key, Number(event.target.value) || 0)
                      }
                    />
                  </label>
                ))}
              </div>
              <h3>Goalie Scales</h3>
              <div className="score-config-fields">
                {Object.entries(scoreDraft.goalie.scales).map(([key, value]) => (
                  <label key={`goalie-scale-${key}`}>
                    <HelpLabel
                      text={labelize(key)}
                      tip={helpText(`goalie.scales.${key}`)}
                    />
                    <input
                      type="number"
                      step="0.01"
                      value={value}
                      onChange={(event) =>
                        updateScoreNumber("goalie", "scales", key, Number(event.target.value) || 0)
                      }
                    />
                  </label>
                ))}
              </div>
              <h3>Goalie Toggles</h3>
              <div className="score-toggle-grid">
                {Object.entries(scoreDraft.goalie.toggles).map(([key, value]) => (
                  <label key={`goalie-toggle-${key}`} className="score-toggle-row">
                    <input
                      type="checkbox"
                      checked={Boolean(value)}
                      onChange={(event) => updateScoreToggle("goalie", key, event.target.checked)}
                    />
                    <HelpLabel
                      text={labelize(key)}
                      tip={helpText(`goalie.toggles.${key}`)}
                    />
                  </label>
                ))}
              </div>
            </article>
          </div>
        )}

        <div className="button-row">
          <button
            className="primary"
            onClick={() => void saveScoreConfigAndRecalculate()}
            disabled={!scoreDraft || scoreSaving || recalcProgress?.running}
          >
            {scoreSaving ? "Saving..." : recalcProgress?.running ? "Recalculating..." : "Save + Recalculate"}
          </button>
          <button onClick={() => void loadStreamerScoreConfig()} disabled={scoreSaving}>
            Reset Draft
          </button>
          <button onClick={() => void loadStreamerRecalcProgress()}>Refresh Progress</button>
        </div>

        {recalcProgress ? (
          <div className="recalc-status">
            <p className="muted compact">
              Status: {recalcProgress.status} • Processed: {recalcProgress.processed_players}
              {recalcProgress.total_players > 0 ? ` / ${recalcProgress.total_players}` : ""}
            </p>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${recalcPercent}%` }} />
            </div>
            {recalcProgress.started_at ? (
              <small className="muted">Started: {formatDateTime(recalcProgress.started_at)}</small>
            ) : null}
            {recalcProgress.finished_at ? (
              <small className="muted">Finished: {formatDateTime(recalcProgress.finished_at)}</small>
            ) : null}
            {recalcProgress.error ? <p className="run-error">{compactError(recalcProgress.error)}</p> : null}
          </div>
        ) : null}
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

      <section className="card ios-card">
        <h2>External Integrations</h2>
        <p className="muted">
          Yahoo sync is disabled in local-first mode. Forecheck v2 now runs scans and analytics without ownership
          percentages, and the planned Yahoo path is a browser extension overlay on yahoo.com/fantasy pages.
        </p>
      </section>

      {status ? <p className="success">{status}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
