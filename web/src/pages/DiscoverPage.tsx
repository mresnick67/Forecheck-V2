import { CSSProperties, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { publicRequest } from "../api";
import type { Player } from "../types";

type TrendResponse = {
  hot: Player[];
  cold: Player[];
};

type WeeklySchedule = {
  week_start: string;
  week_end: string;
  days: Array<{ date: string; teams_playing: number; is_light: boolean }>;
};

function scoreColor(score: number): string {
  if (score >= 75) return "#2be37d";
  if (score >= 60) return "#2bb8f1";
  if (score >= 45) return "#f6c344";
  return "#ff6f86";
}

function initials(name: string): string {
  return name
    .split(" ")
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export default function DiscoverPage() {
  const [topStreamers, setTopStreamers] = useState<Player[]>([]);
  const [hot, setHot] = useState<Player[]>([]);
  const [cold, setCold] = useState<Player[]>([]);
  const [schedule, setSchedule] = useState<WeeklySchedule | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const [streamers, trend, week] = await Promise.all([
          publicRequest<Player[]>("/players/top-streamers?limit=20"),
          publicRequest<TrendResponse>("/players/trending?window=L5&limit=10"),
          publicRequest<WeeklySchedule>("/schedule/week"),
        ]);
        setTopStreamers(streamers);
        setHot(trend.hot);
        setCold(trend.cold);
        setSchedule(week);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load discover data");
      }
    }

    void load();
  }, []);

  return (
    <div className="page-stack">
      <section className="card ios-card">
        <div className="list-head">
          <h2>Top Streamers</h2>
          <small className="muted">{topStreamers.length} players</small>
        </div>
        <div className="scroll-row">
          {topStreamers.map((player) => {
            const score = Math.max(0, Math.min(100, Math.round(player.current_streamer_score)));
            const ringStyle: CSSProperties = {
              background: `conic-gradient(${scoreColor(score)} ${score}%, rgba(255,255,255,0.14) 0)`,
            };
            return (
              <Link className="streamer-card" key={player.id} to={`/players/${player.id}`}>
                <div className="avatar small">{initials(player.name)}</div>
                <strong>{player.name}</strong>
                <p className="muted compact">
                  {player.team} <span className="badge-pos">{player.position}</span>
                </p>
                <div className="score-ring compact" style={ringStyle}>
                  <span>{score}</span>
                </div>
              </Link>
            );
          })}
        </div>
      </section>

      <section className="card ios-card">
        <div className="list-head">
          <h3>Trending Up (L5)</h3>
        </div>
        <div className="mini-list">
          {hot.map((player) => (
            <Link key={player.id} to={`/players/${player.id}`} className="mini-row">
              <span>{player.name}</span>
              <small className="muted">
                {player.team} {player.position}
              </small>
            </Link>
          ))}
        </div>
      </section>

      <section className="card ios-card">
        <div className="list-head">
          <h3>Trending Down (L5)</h3>
        </div>
        <div className="mini-list">
          {cold.map((player) => (
            <Link key={player.id} to={`/players/${player.id}`} className="mini-row">
              <span>{player.name}</span>
              <small className="muted">
                {player.team} {player.position}
              </small>
            </Link>
          ))}
        </div>
      </section>

      <section className="card ios-card">
        <h3>Weekly Schedule</h3>
        {!schedule ? <p className="muted">Loading schedule...</p> : null}
        {schedule ? (
          <>
            <p className="muted compact">
              {schedule.week_start} to {schedule.week_end}
            </p>
            <table>
              <thead>
                <tr>
                  <th>Day</th>
                  <th>Teams</th>
                  <th>Light</th>
                </tr>
              </thead>
              <tbody>
                {schedule.days.map((day) => (
                  <tr key={day.date}>
                    <td>{day.date}</td>
                    <td>{day.teams_playing}</td>
                    <td>{day.is_light ? "Yes" : "No"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </>
        ) : null}
      </section>

      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
