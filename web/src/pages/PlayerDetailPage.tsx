import { CSSProperties, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";

import { publicRequest } from "../api";
import { PlayerAvatar, TeamLogo, hexToRgba, teamTheme } from "../components/NhlAssets";
import type { Player, StreamerScoreBreakdown, StreamerScoreComponent } from "../types";

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

function formatSigned(value: number, digits = 1): string {
  return `${value >= 0 ? "+" : "-"}${Math.abs(value).toFixed(digits)}`;
}

function componentFormula(component: StreamerScoreComponent): string {
  const parts: string[] = [];
  if (component.metric_value !== undefined && component.metric_value !== null) {
    parts.push(`metric ${component.metric_value.toFixed(2)}`);
  }
  if (component.cap !== undefined && component.cap !== null) {
    parts.push(`cap ${component.cap.toFixed(2)}`);
  }
  if (component.weight !== undefined && component.weight !== null) {
    parts.push(`weight ${component.weight.toFixed(2)}`);
  }
  if (component.normalized_value !== undefined && component.normalized_value !== null) {
    parts.push(`norm ${component.normalized_value.toFixed(2)}`);
  }
  return parts.join(" • ");
}

function scheduleOpponent(game: Game, playerTeam?: string): { opponent: string; venue: "@" | "vs" } {
  const team = (playerTeam ?? "").toUpperCase();
  const home = game.home_team.toUpperCase();
  const away = game.away_team.toUpperCase();
  if (team && home === team) return { opponent: away, venue: "vs" };
  if (team && away === team) return { opponent: home, venue: "@" };
  return { opponent: home, venue: "vs" };
}

export default function PlayerDetailPage() {
  const { playerId } = useParams();
  const [player, setPlayer] = useState<PlayerDetail | null>(null);
  const [schedule, setSchedule] = useState<Game[]>([]);
  const [signals, setSignals] = useState<PlayerSignals>({ preset_matches: [] });
  const [scoreBreakdown, setScoreBreakdown] = useState<StreamerScoreBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);
  const isGoalie = player?.position === "G";

  useEffect(() => {
    if (!playerId) return;

    async function load() {
      try {
        const [playerResult, scheduleResult, signalResult, breakdownResult] = await Promise.allSettled([
          publicRequest<PlayerDetail>(`/players/${playerId}`),
          publicRequest<Game[]>(`/players/${playerId}/schedule`),
          publicRequest<PlayerSignals>(`/players/${playerId}/signals`),
          publicRequest<StreamerScoreBreakdown>(`/players/${playerId}/score-breakdown?window=L10`),
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

        if (breakdownResult.status === "fulfilled") {
          setScoreBreakdown(breakdownResult.value);
        } else {
          setScoreBreakdown(null);
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

  const recentGames = useMemo(() => (player?.recent_games ?? []).slice(0, 5), [player?.recent_games]);
  const upcomingGames = useMemo(() => schedule.slice(0, 5), [schedule]);
  const topContributors = useMemo(() => {
    if (!scoreBreakdown) return [];
    return [...scoreBreakdown.components]
      .filter((component) => Math.abs(component.final_contribution) > 0.01)
      .sort((a, b) => Math.abs(b.final_contribution) - Math.abs(a.final_contribution))
      .slice(0, 4);
  }, [scoreBreakdown]);

  if (!playerId) {
    return <p className="error">Missing player id.</p>;
  }

  const palette = teamTheme(player?.team ?? "");
  const score = Math.max(
    0,
    Math.min(100, Math.round(scoreBreakdown?.final_score ?? primaryStats?.streamer_score ?? player?.current_streamer_score ?? 0)),
  );
  const ringStyle: CSSProperties = {
    background: `conic-gradient(${scoreColor(score)} ${score}%, rgba(255,255,255,0.14) 0)`,
  };
  const heroStyle: CSSProperties = {
    background: `linear-gradient(165deg, ${hexToRgba(palette.primary, 0.16)}, ${hexToRgba(
      palette.secondary,
      0.1,
    )} 42%, rgba(16, 20, 26, 0.97) 100%)`,
  };

  return (
    <div className="page-stack player-detail-stack">
      <section className="card ios-card player-hero" style={heroStyle}>
        <div className="player-hero-main">
          {player ? (
            <div className="player-heading">
              <PlayerAvatar
                playerId={player.id}
                externalId={player.external_id}
                headshotUrl={player.headshot_url}
                name={player.name}
                size="large"
              />
              <h2>{player.name}</h2>
            </div>
          ) : (
            <h2>Loading player...</h2>
          )}
          {player ? (
            <>
              <p className="muted">
                <span className="team-inline">
                  <TeamLogo team={player.team} />
                  {player.team}
                </span>{" "}
                {player.position} {player.number ? `#${player.number}` : ""}
              </p>
              <div className="badge-row">
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
        <div className="player-hero-side">
          {player ? <TeamLogo team={player.team} className="team-logo-hero" /> : null}
          <div className="score-ring large" style={ringStyle}>
            <span>{score}</span>
          </div>
        </div>
      </section>

      <section className="card ios-card player-panel score-explainer-panel">
        <div className="list-head panel-head">
          <h3>Streamer Score Explainer</h3>
          <small className="muted">{scoreBreakdown?.window ?? "L10"} true model</small>
        </div>
        <p className="muted score-explainer-copy">
          This is the exact backend calculation. Contributions below are the true weighted components used to produce
          this player&apos;s streamer score.
        </p>
        <div className="score-explainer-meta">
          <article className="score-meta-pill">
            <small>Current Score</small>
            <strong>{score}</strong>
          </article>
          <article className="score-meta-pill">
            <small>Trend Signal</small>
            <strong>
              {(scoreBreakdown?.trend_direction ?? signals.trend_direction) === "hot"
                ? "Trending Up"
                : (scoreBreakdown?.trend_direction ?? signals.trend_direction) === "cold"
                  ? "Trending Down"
                  : "Stable"}
            </strong>
          </article>
          <article className="score-meta-pill">
            <small>Window</small>
            <strong>{scoreBreakdown?.window ?? primaryStats?.window ?? "L10"}</strong>
          </article>
        </div>
        {topContributors.length > 0 ? (
          <div className="score-driver-list">
            {topContributors.map((component) => (
              <article key={component.key} className="score-driver-row">
                <div className="score-driver-main">
                  <strong>{component.label}</strong>
                  <small className="muted">{componentFormula(component)}</small>
                </div>
                <span
                  className={`score-driver-impact ${component.final_contribution >= 0 ? "positive" : "negative"}`}
                >
                  {formatSigned(component.final_contribution)}
                </span>
              </article>
            ))}
          </div>
        ) : null}

        {scoreBreakdown ? (
          <details className="score-breakdown-details">
            <summary>Show Full Contribution Breakdown</summary>
            <div className="score-breakdown-meta">
              <span className="badge">Base: {scoreBreakdown.base_score.toFixed(1)}</span>
              <span className="badge">League Blend: {(scoreBreakdown.league_blend_weight * 100).toFixed(0)}%</span>
              {scoreBreakdown.sample_factor !== null && scoreBreakdown.sample_factor !== undefined ? (
                <span className="badge">Sample Factor: {scoreBreakdown.sample_factor.toFixed(2)}x</span>
              ) : null}
            </div>
            <div className="score-breakdown-table">
              {scoreBreakdown.components.map((component) => (
                <article key={component.key} className="score-breakdown-row">
                  <div className="score-breakdown-main">
                    <strong>{component.label}</strong>
                    <small className="muted">
                      {componentFormula(component) || "No direct metric input"}
                      {component.notes ? ` • ${component.notes}` : ""}
                    </small>
                  </div>
                  <span
                    className={`score-driver-impact ${component.final_contribution >= 0 ? "positive" : "negative"}`}
                  >
                    {formatSigned(component.final_contribution)}
                  </span>
                </article>
              ))}
            </div>
          </details>
        ) : (
          <p className="muted">Score breakdown unavailable for this player/window.</p>
        )}
      </section>

      <section className="card ios-card player-panel stat-panel">
        <div className="panel-head">
          <h3>Stat Comparison</h3>
        </div>
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

      <section className="card ios-card player-panel recent-panel">
        <div className="list-head panel-head">
          <h3>Recent Games</h3>
          <small className="muted">{recentGames.length} games</small>
        </div>
        <div className="recent-games">
          {recentGames.map((game) => (
            <article key={game.id} className="recent-game-row">
              <div className="recent-game-head">
                <div className="recent-game-meta">
                  <strong>{formatDate(game.date)}</strong>
                  <small className="muted">
                    {game.opponent_abbrev ? (game.is_home ? `vs ${game.opponent_abbrev}` : `@ ${game.opponent_abbrev}`) : ""}
                  </small>
                </div>
                {isGoalie ? (
                  <div className="recent-stat-grid goalie">
                    <span><strong>{game.saves ?? 0}</strong><small>S</small></span>
                    <span><strong>{game.goals_against ?? 0}</strong><small>GA</small></span>
                    <span><strong>{n(game.save_percentage, 3)}</strong><small>SV%</small></span>
                    <span><strong>{game.wins ? "W" : game.losses ? "L" : "-"}</strong><small>DEC</small></span>
                  </div>
                ) : (
                  <div className="recent-stat-grid">
                    <span><strong>{game.goals}</strong><small>G</small></span>
                    <span><strong>{game.assists}</strong><small>A</small></span>
                    <span><strong>{game.points}</strong><small>P</small></span>
                    <span><strong>{game.shots}</strong><small>S</small></span>
                    <span><strong>{game.hits}</strong><small>H</small></span>
                    <span><strong>{game.blocks}</strong><small>B</small></span>
                  </div>
                )}
              </div>
            </article>
          ))}
          {recentGames.length === 0 ? <p className="muted">No recent games.</p> : null}
        </div>
      </section>

      <section className="card ios-card player-panel schedule-panel">
        <div className="list-head panel-head">
          <h3>Upcoming Schedule</h3>
          <small className="muted">{upcomingGames.length} games</small>
        </div>
        <div className="upcoming-list">
          {upcomingGames.map((game) => {
            const next = scheduleOpponent(game, player?.team);
            const opponentPalette = teamTheme(next.opponent);
            const opponentChipStyle: CSSProperties = {
              borderColor: hexToRgba(opponentPalette.primary, 0.58),
              background: hexToRgba(opponentPalette.primary, 0.26),
              color: "#f2f6ff",
            };
            return (
              <article key={game.id} className="upcoming-row">
                <strong>{formatDate(game.date)}</strong>
                <div className="upcoming-opponent">
                  <span className="muted">{next.venue}</span>
                  <span className="opponent-pill" style={opponentChipStyle}>
                    {next.opponent}
                  </span>
                </div>
              </article>
            );
          })}
          {upcomingGames.length === 0 ? <p className="muted">No upcoming games.</p> : null}
        </div>
      </section>

      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
