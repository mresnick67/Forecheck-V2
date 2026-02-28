import { CSSProperties, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { publicRequest } from "../api";
import type { Player } from "../types";

type RollingStats = {
  window: string;
  games_played: number;
  points_per_game: number;
  assists_per_game: number;
  goals_per_game: number;
  shots_per_game: number;
  hits_per_game: number;
  blocks_per_game: number;
  power_play_points_per_game: number;
  shorthanded_points_per_game: number;
  time_on_ice_per_game: number;
  streamer_score: number;
};

type GameLog = {
  id: string;
  date: string;
  goals: number;
  assists: number;
  points: number;
  shots: number;
  hits: number;
  blocks: number;
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

export default function PlayerDetailPage() {
  const { playerId } = useParams();
  const [player, setPlayer] = useState<PlayerDetail | null>(null);
  const [schedule, setSchedule] = useState<Game[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!playerId) return;

    async function load() {
      try {
        const [playerResponse, scheduleResponse] = await Promise.all([
          publicRequest<PlayerDetail>(`/players/${playerId}`),
          publicRequest<Game[]>(`/players/${playerId}/schedule`),
        ]);
        setPlayer(playerResponse);
        setSchedule(scheduleResponse);
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

  if (!playerId) {
    return <p className="error">Missing player id.</p>;
  }

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
            </>
          ) : null}
        </div>
        <div className="score-ring large" style={ringStyle}>
          <span>{score}</span>
        </div>
      </section>

      <section className="card ios-card">
        <h3>Stat Comparison</h3>
        <table>
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
          </tbody>
        </table>
      </section>

      <section className="card ios-card">
        <h3>Recent Games</h3>
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>P</th>
              <th>S</th>
              <th>H</th>
              <th>B</th>
            </tr>
          </thead>
          <tbody>
            {(player?.recent_games ?? []).map((game) => (
              <tr key={game.id}>
                <td>{new Date(game.date).toLocaleDateString()}</td>
                <td>{game.points}</td>
                <td>{game.shots}</td>
                <td>{game.hits}</td>
                <td>{game.blocks}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card ios-card">
        <h3>Upcoming Schedule</h3>
        <ul className="simple-list">
          {schedule.map((game) => (
            <li key={game.id}>
              {new Date(game.date).toLocaleDateString()} • {game.away_team} @ {game.home_team} ({game.status})
            </li>
          ))}
        </ul>
      </section>

      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
