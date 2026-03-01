import { CSSProperties, FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { publicRequest } from "../api";
import { PlayerAvatar, TeamLogo } from "../components/NhlAssets";
import type { ExplorePlayer } from "../types";

const WINDOWS = ["L5", "L10", "L20", "Season"] as const;
const POSITIONS = ["ALL", "C", "LW", "RW", "D", "G"] as const;

function scoreColor(score: number): string {
  if (score >= 75) return "#2be37d";
  if (score >= 60) return "#2bb8f1";
  if (score >= 45) return "#f6c344";
  return "#ff6f86";
}

function clampScore(score: number): number {
  if (!Number.isFinite(score)) return 0;
  return Math.max(0, Math.min(100, Math.round(score)));
}

export default function ExplorePage() {
  const [players, setPlayers] = useState<ExplorePlayer[]>([]);
  const [search, setSearch] = useState("");
  const [window, setWindow] = useState<(typeof WINDOWS)[number]>("L10");
  const [position, setPosition] = useState<(typeof POSITIONS)[number]>("ALL");
  const [sortBy, setSortBy] = useState("window_streamer_score");
  const [sortOrder, setSortOrder] = useState("desc");
  const [minScore, setMinScore] = useState("35");
  const [maxOwned, setMaxOwned] = useState("85");
  const [minGames, setMinGames] = useState("3");
  const [minWeeklyGames, setMinWeeklyGames] = useState("0");
  const [minLightGames, setMinLightGames] = useState("0");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      params.set("window", window);
      params.set("limit", "200");
      params.set("sort_by", sortBy);
      params.set("sort_order", sortOrder);

      if (search.trim()) params.set("search", search.trim());
      if (position !== "ALL") params.set("position", position);

      if (minScore.trim()) params.set("min_streamer_score", minScore.trim());
      if (maxOwned.trim()) params.set("max_ownership", maxOwned.trim());
      if (minGames.trim()) params.set("min_games_played", minGames.trim());
      if (minWeeklyGames.trim()) params.set("min_weekly_games", minWeeklyGames.trim());
      if (minLightGames.trim()) params.set("min_weekly_light_games", minLightGames.trim());

      const response = await publicRequest<ExplorePlayer[]>(`/players/explore?${params.toString()}`);
      setPlayers(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load explore data");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  function onApply(event: FormEvent) {
    event.preventDefault();
    void load();
  }

  function resetFilters() {
    setSearch("");
    setWindow("L10");
    setPosition("ALL");
    setSortBy("window_streamer_score");
    setSortOrder("desc");
    setMinScore("35");
    setMaxOwned("85");
    setMinGames("3");
    setMinWeeklyGames("0");
    setMinLightGames("0");
    setTimeout(() => {
      void load();
    }, 0);
  }

  return (
    <div className="page-stack">
      <section className="card ios-card">
        <h2>Explore</h2>
        <p className="muted">Window-aware filters and ranking, tuned for quick streamer discovery.</p>
        <form className="filter-grid" onSubmit={onApply}>
          <label>
            Search
            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Player or team"
            />
          </label>

          <div>
            <small className="muted">Window</small>
            <div className="chip-row">
              {WINDOWS.map((item) => (
                <button
                  key={item}
                  type="button"
                  className={`chip ${window === item ? "active" : ""}`}
                  onClick={() => setWindow(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          <div>
            <small className="muted">Position</small>
            <div className="chip-row">
              {POSITIONS.map((item) => (
                <button
                  key={item}
                  type="button"
                  className={`chip ${position === item ? "active" : ""}`}
                  onClick={() => setPosition(item)}
                >
                  {item}
                </button>
              ))}
            </div>
          </div>

          <label>
            Sort by
            <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
              <option value="window_streamer_score">Window Score</option>
              <option value="points">Points / GP</option>
              <option value="shots">Shots / GP</option>
              <option value="hits">Hits / GP</option>
              <option value="blocks">Blocks / GP</option>
              <option value="toi">TOI / GP</option>
              <option value="save_pct">Save %</option>
              <option value="gaa">GAA</option>
              <option value="wins">Goalie Wins</option>
              <option value="ownership">Ownership %</option>
              <option value="weekly_games">Weekly Games</option>
              <option value="weekly_light_games">Light-Night Games</option>
              <option value="name">Name</option>
            </select>
          </label>

          <label>
            Direction
            <select value={sortOrder} onChange={(event) => setSortOrder(event.target.value)}>
              <option value="desc">Descending</option>
              <option value="asc">Ascending</option>
            </select>
          </label>

          <label>
            Min score
            <input value={minScore} onChange={(event) => setMinScore(event.target.value)} />
          </label>

          <label>
            Max owned %
            <input value={maxOwned} onChange={(event) => setMaxOwned(event.target.value)} />
          </label>

          <label>
            Min GP
            <input value={minGames} onChange={(event) => setMinGames(event.target.value)} />
          </label>

          <label>
            Min weekly games
            <input value={minWeeklyGames} onChange={(event) => setMinWeeklyGames(event.target.value)} />
          </label>

          <label>
            Min light-night games
            <input value={minLightGames} onChange={(event) => setMinLightGames(event.target.value)} />
          </label>

          <div className="button-row">
            <button className="primary" type="submit" disabled={loading}>
              {loading ? "Applying..." : "Apply Filters"}
            </button>
            <button type="button" onClick={resetFilters}>
              Reset
            </button>
          </div>
        </form>
      </section>

      <section className="card ios-card">
        <div className="list-head">
          <h3>Results</h3>
          <small className="muted">
            {players.length} players • {window}
          </small>
        </div>
        {error ? <p className="error">{error}</p> : null}
        {!error && players.length === 0 ? <p className="muted">No players match current filters.</p> : null}

        <div className="player-list">
          {players.map((player) => {
            const score = clampScore(player.window_streamer_score);
            const ringStyle: CSSProperties = {
              background: `conic-gradient(${scoreColor(score)} ${score}%, rgba(255,255,255,0.14) 0)`,
            };

            return (
              <Link key={player.id} to={`/players/${player.id}`} className="player-row">
                <PlayerAvatar playerId={player.id} name={player.name} />
                <div className="player-main">
                  <div className="player-row-top">
                    <strong>{player.name}</strong>
                  </div>
                  <p className="muted compact">
                    <span className="team-inline">
                      <TeamLogo team={player.team} />
                      {player.team}
                    </span>{" "}
                    <span className="badge-pos">{player.position}</span> •{" "}
                    {player.ownership_percentage.toFixed(1)}% owned • {player.games_played} GP
                  </p>
                  {player.position === "G" ? (
                    <p className="metric-line">
                      SV% {(player.save_percentage ?? 0).toFixed(3)} • GAA {(player.goals_against_average ?? 0).toFixed(2)} •
                      W {player.goalie_wins ?? 0}
                    </p>
                  ) : (
                    <p className="metric-line">
                      P/GP {(player.points_per_game ?? 0).toFixed(2)} • S/GP {(player.shots_per_game ?? 0).toFixed(2)} • H/GP{" "}
                      {(player.hits_per_game ?? 0).toFixed(2)} • B/GP {(player.blocks_per_game ?? 0).toFixed(2)}
                    </p>
                  )}
                  <div className="badge-row">
                    <span className="badge">Wk {player.weekly_games ?? 0}</span>
                    <span className="badge">Light {player.weekly_light_games ?? 0}</span>
                    <span className="badge">{window}</span>
                  </div>
                </div>
                <div className="score-ring" style={ringStyle}>
                  <span>{score}</span>
                </div>
              </Link>
            );
          })}
        </div>
      </section>
    </div>
  );
}
