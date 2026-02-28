import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";

import { publicRequest } from "../api";
import type { Player } from "../types";

type RollingStats = {
  window: string;
  games_played: number;
  points_per_game: number;
  shots_per_game: number;
  hits_per_game: number;
  blocks_per_game: number;
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

type Game = {
  id: string;
  date: string;
  home_team: string;
  away_team: string;
  status: string;
};

export default function PlayerDetailPage() {
  const { playerId } = useParams();
  const [player, setPlayer] = useState<Player | null>(null);
  const [stats, setStats] = useState<RollingStats | null>(null);
  const [games, setGames] = useState<GameLog[]>([]);
  const [schedule, setSchedule] = useState<Game[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!playerId) return;

    async function load() {
      try {
        const [playerResponse, statsResponse, gamesResponse, scheduleResponse] = await Promise.all([
          publicRequest<Player>(`/players/${playerId}`),
          publicRequest<RollingStats>(`/players/${playerId}/stats/L10`),
          publicRequest<GameLog[]>(`/players/${playerId}/games?limit=10`),
          publicRequest<Game[]>(`/players/${playerId}/schedule`),
        ]);
        setPlayer(playerResponse);
        setStats(statsResponse);
        setGames(gamesResponse);
        setSchedule(scheduleResponse);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load player details");
      }
    }

    void load();
  }, [playerId]);

  if (!playerId) {
    return <p className="error">Missing player id.</p>;
  }

  return (
    <div className="grid cols-2">
      <section className="card">
        <h2>{player ? player.name : "Loading player..."}</h2>
        {player ? (
          <>
            <p>
              {player.team} {player.position} {player.number ? `#${player.number}` : ""}
            </p>
            <p>
              Streamer: {player.current_streamer_score.toFixed(1)} | Owned: {player.ownership_percentage.toFixed(1)}%
            </p>
          </>
        ) : null}
      </section>

      <section className="card">
        <h2>Rolling Stats (L10)</h2>
        {stats ? (
          <ul>
            <li>Games: {stats.games_played}</li>
            <li>Points / game: {stats.points_per_game.toFixed(2)}</li>
            <li>Shots / game: {stats.shots_per_game.toFixed(2)}</li>
            <li>Hits / game: {stats.hits_per_game.toFixed(2)}</li>
            <li>Blocks / game: {stats.blocks_per_game.toFixed(2)}</li>
            <li>Window score: {stats.streamer_score.toFixed(1)}</li>
          </ul>
        ) : (
          <p className="muted">No rolling stats yet.</p>
        )}
      </section>

      <section className="card">
        <h2>Recent Games</h2>
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
            {games.map((game) => (
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

      <section className="card">
        <h2>Upcoming Schedule</h2>
        <ul>
          {schedule.map((game) => (
            <li key={game.id}>
              {new Date(game.date).toLocaleDateString()} - {game.away_team} @ {game.home_team} ({game.status})
            </li>
          ))}
        </ul>
      </section>

      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
