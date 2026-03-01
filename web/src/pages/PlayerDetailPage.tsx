import { CSSProperties, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { publicRequest } from "../api";
import type { Player } from "../types";

type RollingStats = {
  window: string;
  games_played: number;
  goalie_games_started?: number;
  points_per_game: number;
  assists_per_game: number;
  goals_per_game: number;
  shots_per_game: number;
  hits_per_game: number;
  blocks_per_game: number;
  power_play_points_per_game: number;
  shorthanded_points_per_game: number;
  time_on_ice_per_game: number;
  save_percentage?: number;
  goals_against_average?: number;
  goalie_wins?: number;
  goalie_shutouts?: number;
  streamer_score: number;
};

type GameLog = {
  id: string;
  date: string;
  opponent_abbrev?: string;
  is_home?: boolean;
  goals: number;
  assists: number;
  points: number;
  shots: number;
  hits: number;
  blocks: number;
  saves?: number;
  goals_against?: number;
  save_percentage?: number;
  wins?: number;
  losses?: number;
};

type PlayerDetail = Player & {
  rolling_stats?: Record<string, RollingStats>;
  recent_games?: GameLog[];
};

type Game = {
  id: string;
  date: string;
  home_team: string;
  away_team: string;
  status: string;
};

type PlayerSignals = {
  trend_direction?: string | null;
  temperature_tag?: string | null;
  preset_matches: Array<{ id: string; name: string }>;
};

const WINDOWS = ["L5", "L10", "L20", "Season"] as const;

function scoreColor(score: number): string {
  if (score >= 75) return "#2be37d";
  if (score >= 60) return "#2bb8f1";
  if (score >= 45) return "#f6c344";
  return "#ff6f86";
}

function n(value?: number | null, digits = 2): string {
  return (value ?? 0).toFixed(digits);
}

function formatDate(value: string): string {
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export default function PlayerDetailPage() {
  const { playerId } = useParams();
  const [player, setPlayer] = useState<PlayerDetail | null>(null);
  const [schedule, setSchedule] = useState<Game[]>([]);
  const [signals, setSignals] = useState<PlayerSignals>({ preset_matches: [] });
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!playerId) return;

    async function load() {
      try {
        const [playerResult, scheduleResult, signalResult] = await Promise.allSettled([
          publicRequest<PlayerDetail>(`/players/${playerId}`),
          publicRequest<Game[]>(`/players/${playerId}/schedule`),
          publicRequest<PlayerSignals>(`/players/${playerId}/signals`),
        ]);

        if (playerResult.status !== "fulfilled" || scheduleResult.status !== "fulfilled") {
          throw new Error("Failed to load player detail");
        }

        setPlayer(playerResult.value);
        setSchedule(scheduleResult.value);
        if (signalResult.status === "fulfilled") {
          setSignals(signalResult.value);
        } else {
          setSignals({ preset_matches: [] });
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load player details");
      }
    }

    void load();
  }, [playerId]);

  const primaryStats = useMemo(() => {
    if (!player?.rolling_stats) return null;
    return player.rolling_stats.L10 ?? player.rolling_stats.L5 ?? null;
  }, [player]);

  const trendChips = useMemo(() => {
    const chips: string[] = [];
    if (signals.trend_direction === "hot") chips.push("Trending Up");
    if (signals.trend_direction === "cold") chips.push("Trending Down");
    chips.push(...signals.preset_matches.slice(0, 3).map((scan) => scan.name));
    return chips;
  }, [signals]);

  if (!playerId) {
    return <p className="error">Missing player id.</p>;
  }

  const isGoalie = player?.position === "G";
  const score = Math.max(0, Math.min(100, Math.round(primaryStats?.streamer_score ?? player?.current_streamer_score ?? 0)));
  const ringStyle: CSSProperties = {
    background: `conic-gradient(${scoreColor(score)} ${score}%, rgba(255,255,255,0.14) 0)`,
  };

  return (
    <div className="page-stack">
      <section className="card ios-card player-hero">
        <div className="player-hero-main">
          <h2>{player ? player.name : "Loading player..."}</h2>
          {player ? (
            <>
              <p className="muted">
                {player.team} {player.position} {player.number ? `#${player.number}` : ""}
              </p>
              <div className="badge-row">
                <span className="badge">{(player.ownership_percentage ?? 0).toFixed(1)}% owned</span>
                <span className="badge">{primaryStats?.games_played ?? 0} GP</span>
                <span className="badge">L10</span>
              </div>
              {trendChips.length > 0 ? (
                <div className="signal-row">
                  {trendChips.map((chip) => (
                    <span key={chip} className="signal-chip">
                      {chip}
                    </span>
                  ))}
                </div>
              ) : null}
            </>
          ) : null}
        </div>
        <div className="score-ring large" style={ringStyle}>
          <span>{score}</span>
        </div>
      </section>

      <section className="card ios-card">
        <h3>Stat Comparison</h3>
        <table className="stat-compare">
          <thead>
            <tr>
              <th>Stat</th>
              {WINDOWS.map((window) => (
                <th key={window}>{window}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>GP</td>
              {WINDOWS.map((window) => (
                <td key={window}>{player?.rolling_stats?.[window]?.games_played ?? 0}</td>
              ))}
            </tr>
            {isGoalie ? (
              <>
                <tr>
                  <td>GS</td>
                  {WINDOWS.map((window) => (
                    <td key={window}>{player?.rolling_stats?.[window]?.goalie_games_started ?? 0}</td>
                  ))}
                </tr>
                <tr>
                  <td>SV%</td>
                  {WINDOWS.map((window) => (
                    <td key={window}>{n(player?.rolling_stats?.[window]?.save_percentage, 3)}</td>
                  ))}
                </tr>
                <tr>
                  <td>GAA</td>
                  {WINDOWS.map((window) => (
                    <td key={window}>{n(player?.rolling_stats?.[window]?.goals_against_average, 2)}</td>
                  ))}
                </tr>
                <tr>
                  <td>W</td>
                  {WINDOWS.map((window) => (
                    <td key={window}>{player?.rolling_stats?.[window]?.goalie_wins ?? 0}</td>
                  ))}
                </tr>
                <tr>
                  <td>SO</td>
                  {WINDOWS.map((window) => (
                    <td key={window}>{player?.rolling_stats?.[window]?.goalie_shutouts ?? 0}</td>
                  ))}
                </tr>
              </>
            ) : (
              <>
                <tr>
                  <td>P/GP</td>
                  {WINDOWS.map((window) => (
                    <td key={window}>{n(player?.rolling_stats?.[window]?.points_per_game)}</td>
                  ))}
                </tr>
                <tr>
                  <td>A/GP</td>
                  {WINDOWS.map((window) => (
                    <td key={window}>{n(player?.rolling_stats?.[window]?.assists_per_game)}</td>
                  ))}
                </tr>
                <tr>
                  <td>G/GP</td>
                  {WINDOWS.map((window) => (
                    <td key={window}>{n(player?.rolling_stats?.[window]?.goals_per_game)}</td>
                  ))}
                </tr>
                <tr>
                  <td>S/GP</td>
                  {WINDOWS.map((window) => (
                    <td key={window}>{n(player?.rolling_stats?.[window]?.shots_per_game)}</td>
                  ))}
                </tr>
                <tr>
                  <td>H/GP</td>
                  {WINDOWS.map((window) => (
                    <td key={window}>{n(player?.rolling_stats?.[window]?.hits_per_game)}</td>
                  ))}
                </tr>
                <tr>
                  <td>B/GP</td>
                  {WINDOWS.map((window) => (
                    <td key={window}>{n(player?.rolling_stats?.[window]?.blocks_per_game)}</td>
                  ))}
                </tr>
                <tr>
                  <td>PPP/GP</td>
                  {WINDOWS.map((window) => (
                    <td key={window}>{n(player?.rolling_stats?.[window]?.power_play_points_per_game)}</td>
                  ))}
                </tr>
                <tr>
                  <td>SHP/GP</td>
                  {WINDOWS.map((window) => (
                    <td key={window}>{n(player?.rolling_stats?.[window]?.shorthanded_points_per_game)}</td>
                  ))}
                </tr>
                <tr>
                  <td>TOI</td>
                  {WINDOWS.map((window) => (
                    <td key={window}>{n(player?.rolling_stats?.[window]?.time_on_ice_per_game, 1)}</td>
                  ))}
                </tr>
              </>
            )}
          </tbody>
        </table>
      </section>

      <section className="card ios-card">
        <div className="list-head">
          <h3>Recent Games</h3>
          <small className="muted">{(player?.recent_games ?? []).length} games</small>
        </div>
        <div className="recent-games">
          {(player?.recent_games ?? []).map((game) => (
            <article key={game.id} className="recent-game-row">
              <div className="recent-game-head">
                <strong>{formatDate(game.date)}</strong>
                <small className="muted">
                  {game.opponent_abbrev ? (game.is_home ? `vs ${game.opponent_abbrev}` : `@ ${game.opponent_abbrev}`) : ""}
                </small>
              </div>
              {isGoalie ? (
                <p className="metric-line">
                  {game.saves ?? 0} S • {game.goals_against ?? 0} GA • SV% {n(game.save_percentage, 3)} •
                  {game.wins ? " W" : game.losses ? " L" : ""}
                </p>
              ) : (
                <p className="metric-line">
                  {game.goals} G • {game.assists} A • {game.points} P • {game.shots} S • {game.hits} H • {game.blocks} B
                </p>
              )}
            </article>
          ))}
          {(player?.recent_games ?? []).length === 0 ? <p className="muted">No recent games.</p> : null}
        </div>
      </section>

      <section className="card ios-card">
        <h3>Upcoming Schedule</h3>
        <ul className="simple-list">
          {schedule.map((game) => (
            <li key={game.id}>
              {formatDate(game.date)} • {game.away_team} @ {game.home_team} ({game.status})
            </li>
          ))}
        </ul>
      </section>

      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
