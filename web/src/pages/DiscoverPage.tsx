import { useEffect, useState } from "react";
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
          publicRequest<Player[]>("/players/top-streamers?limit=12"),
          publicRequest<TrendResponse>("/players/trending?window=L5&limit=8"),
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
    <div className="grid cols-2">
      <section className="card">
        <h2>Top Streamers</h2>
        {topStreamers.length === 0 ? <p className="muted">No data yet.</p> : null}
        <ul>
          {topStreamers.map((player) => (
            <li key={player.id}>
              <Link to={`/players/${player.id}`}>{player.name}</Link> ({player.team} {player.position}) - score{" "}
              {player.current_streamer_score.toFixed(1)}
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>Weekly Schedule</h2>
        {!schedule ? <p className="muted">Loading schedule...</p> : null}
        {schedule ? (
          <>
            <p className="muted">
              {schedule.week_start} to {schedule.week_end}
            </p>
            <table>
              <thead>
                <tr>
                  <th>Day</th>
                  <th>Teams</th>
                  <th>Light Night</th>
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

      <section className="card">
        <h2>Trending Up (L5)</h2>
        <ul>
          {hot.map((player) => (
            <li key={player.id}>
              <Link to={`/players/${player.id}`}>{player.name}</Link> ({player.team})
            </li>
          ))}
        </ul>
      </section>

      <section className="card">
        <h2>Trending Down (L5)</h2>
        <ul>
          {cold.map((player) => (
            <li key={player.id}>
              <Link to={`/players/${player.id}`}>{player.name}</Link> ({player.team})
            </li>
          ))}
        </ul>
      </section>

      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
