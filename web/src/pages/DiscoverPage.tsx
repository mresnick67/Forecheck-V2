import { CSSProperties, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { publicRequest } from "../api";
import type { Player, Scan } from "../types";

type TrendResponse = {
  hot: Player[];
  cold: Player[];
};

type WeeklySchedule = {
  week_start: string;
  week_end: string;
  days: Array<{ date: string; teams_playing: number; is_light: boolean }>;
};

const FEATURED_SCAN_ORDER = [
  "Buy Low Shooters",
  "Deployment Bump",
  "Hot Goalies",
  "Volume Starters",
  "Power Play QB",
  "Banger Stud",
  "Sell High Shooters",
  "High Volume Saves",
  "B2B Spot Start",
];
const FEATURED_SCAN_INDEX = new Map(FEATURED_SCAN_ORDER.map((name, index) => [name, index]));
const MAX_DISCOVER_SCANS = 6;
const PLAYERS_PER_SCAN = 12;

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

function presetRank(scan: Scan): number {
  return FEATURED_SCAN_INDEX.get(scan.name) ?? 999;
}

function selectFeaturedScans(scans: Scan[]): Scan[] {
  const visible = scans.filter((scan) => !scan.is_hidden);
  visible.sort((a, b) => {
    const rankDelta = presetRank(a) - presetRank(b);
    if (rankDelta !== 0) return rankDelta;
    return (b.match_count ?? 0) - (a.match_count ?? 0);
  });
  const withMatches = visible.filter((scan) => (scan.match_count ?? 0) > 0);
  const source = withMatches.length > 0 ? withMatches : visible;
  return source.slice(0, MAX_DISCOVER_SCANS);
}

export default function DiscoverPage() {
  const [topStreamers, setTopStreamers] = useState<Player[]>([]);
  const [presetScans, setPresetScans] = useState<Scan[]>([]);
  const [scanMatches, setScanMatches] = useState<Record<string, Player[]>>({});
  const [loadingScans, setLoadingScans] = useState(false);
  const [hot, setHot] = useState<Player[]>([]);
  const [cold, setCold] = useState<Player[]>([]);
  const [schedule, setSchedule] = useState<WeeklySchedule | null>(null);
  const [error, setError] = useState<string | null>(null);

  const featuredScans = useMemo(() => selectFeaturedScans(presetScans), [presetScans]);

  useEffect(() => {
    async function load() {
      setLoadingScans(true);
      setError(null);
      try {
        const [streamers, trend, week, presets] = await Promise.all([
          publicRequest<Player[]>("/players/top-streamers?limit=20"),
          publicRequest<TrendResponse>("/players/trending?window=L5&limit=10"),
          publicRequest<WeeklySchedule>("/schedule/week"),
          publicRequest<Scan[]>("/scans/presets?refresh_counts=true&stale_minutes=30"),
        ]);
        setTopStreamers(streamers);
        setHot(trend.hot);
        setCold(trend.cold);
        setSchedule(week);

        const nextScans = selectFeaturedScans(presets);
        setPresetScans(presets);

        const settled = await Promise.allSettled(
          nextScans.map(async (scan) => {
            const players = await publicRequest<Player[]>(`/scans/${scan.id}/evaluate?limit=${PLAYERS_PER_SCAN}`, {
              method: "POST",
            });
            return [scan.id, players] as const;
          }),
        );

        const resultsByScan: Record<string, Player[]> = {};
        for (const result of settled) {
          if (result.status !== "fulfilled") continue;
          const [scanId, players] = result.value;
          resultsByScan[scanId] = players;
        }
        setScanMatches(resultsByScan);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load discover data");
      } finally {
        setLoadingScans(false);
      }
    }

    void load();
  }, []);

  return (
    <div className="page-stack discover-stack">
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

      {featuredScans.map((scan) => (
        <section key={scan.id} className="card ios-card discover-scan-section">
          <div className="list-head">
            <h3>{scan.name}</h3>
            <small className="muted">{scan.match_count} matches</small>
          </div>
          <p className="muted compact">{scan.description}</p>
          <div className="discover-carousel">
            {(scanMatches[scan.id] ?? []).map((player) => {
              const score = Math.max(0, Math.min(100, Math.round(player.current_streamer_score)));
              const ringStyle: CSSProperties = {
                background: `conic-gradient(${scoreColor(score)} ${score}%, rgba(255,255,255,0.14) 0)`,
              };
              return (
                <Link className="discover-player-card" key={player.id} to={`/players/${player.id}`}>
                  <div className="discover-player-top">
                    <div className="avatar small">{initials(player.name)}</div>
                    <div className="score-ring compact" style={ringStyle}>
                      <span>{score}</span>
                    </div>
                  </div>
                  <strong>{player.name}</strong>
                  <p className="muted compact">
                    {player.team} <span className="badge-pos">{player.position}</span>
                  </p>
                  <small className="muted">{Math.round(player.ownership_percentage)}% owned</small>
                </Link>
              );
            })}
            {!loadingScans && (scanMatches[scan.id] ?? []).length === 0 ? (
              <p className="muted">No matches currently.</p>
            ) : null}
          </div>
        </section>
      ))}

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

      {loadingScans && featuredScans.length === 0 ? <p className="muted">Loading scan sections...</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
