import { FormEvent, useEffect, useState } from "react";

import { authRequest } from "../api";
import type { AuthSession, League } from "../types";

type LeaguesPageProps = {
  session: AuthSession;
  onSession: (session: AuthSession | null) => void;
};

function defaultWeights(leagueType: string): Record<string, number> {
  if (leagueType === "categories") {
    return {
      goals: 1,
      assists: 1,
      shots: 1,
      hits: 1,
      blocks: 1,
    };
  }

  return {
    goals: 3,
    assists: 2,
    shots: 0.4,
    hits: 0.25,
    blocks: 0.25,
    power_play_points: 0.75,
  };
}

export default function LeaguesPage({ session, onSession }: LeaguesPageProps) {
  const [leagues, setLeagues] = useState<League[]>([]);
  const [name, setName] = useState("");
  const [leagueType, setLeagueType] = useState("categories");
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadLeagues() {
    setLoading(true);
    try {
      const response = await authRequest<League[]>("/leagues", session, onSession);
      setLeagues(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load leagues");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadLeagues();
  }, []);

  async function createLeague(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setStatus(null);

    try {
      await authRequest(
        "/leagues",
        session,
        onSession,
        {
          method: "POST",
          json: {
            name,
            league_type: leagueType,
            scoring_weights: defaultWeights(leagueType),
          },
        },
      );

      setName("");
      await loadLeagues();
      setStatus("League profile created.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create league");
    }
  }

  async function deleteLeague(leagueId: string) {
    setError(null);
    setStatus(null);
    try {
      await authRequest(`/leagues/${leagueId}`, session, onSession, {
        method: "DELETE",
      });
      await loadLeagues();
      setStatus("League profile deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete league");
    }
  }

  function formatWeightName(stat: string): string {
    return stat
      .split("_")
      .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
      .join(" ");
  }

  const sortedLeagues = [...leagues].sort((a, b) => a.name.localeCompare(b.name));

  return (
    <div className="page-stack leagues-stack">
      <section className="card ios-card">
        <div className="list-head">
          <h2>League Profiles</h2>
          <small className="muted">{leagues.length} saved</small>
        </div>
        <p className="muted">
          Keep local scoring profiles for your leagues so scans and evaluations stay aligned with your categories.
        </p>
      </section>

      <section className="card ios-card">
        <h3>Create League Profile</h3>
        <form className="scan-builder" onSubmit={createLeague}>
          <label>
            League name
            <input value={name} onChange={(event) => setName(event.target.value)} required />
          </label>

          <div>
            <small className="muted">Scoring mode</small>
            <div className="chip-row">
              <button
                type="button"
                className={`chip ${leagueType === "categories" ? "active" : ""}`}
                onClick={() => setLeagueType("categories")}
              >
                Categories
              </button>
              <button
                type="button"
                className={`chip ${leagueType === "points" ? "active" : ""}`}
                onClick={() => setLeagueType("points")}
              >
                Points
              </button>
            </div>
          </div>

          <div className="league-weights">
            {Object.entries(defaultWeights(leagueType)).map(([stat, value]) => (
              <span key={stat} className="badge">
                {formatWeightName(stat)}: {value}
              </span>
            ))}
          </div>

          <div className="button-row">
            <button className="primary" type="submit">
              Save League
            </button>
          </div>
        </form>
      </section>

      <section className="card ios-card">
        <div className="list-head">
          <h3>Saved Leagues</h3>
          <small className="muted">{loading ? "Loading..." : `${sortedLeagues.length} profiles`}</small>
        </div>
        {sortedLeagues.length === 0 && !loading ? <p className="muted">No leagues yet. Create your first profile above.</p> : null}

        <div className="scan-list">
          {sortedLeagues.map((league) => (
            <article key={league.id} className="scan-card league-card">
              <div className="list-head">
                <strong>{league.name}</strong>
                <span className="badge">{league.is_active ? "Active" : "Inactive"}</span>
              </div>

              <div className="badge-row">
                <span className="badge">{league.league_type === "categories" ? "Categories" : "Points"}</span>
                <span className="badge">{Object.keys(league.scoring_weights ?? {}).length} weights</span>
              </div>

              <div className="league-weights">
                {Object.entries(league.scoring_weights ?? {}).map(([stat, value]) => (
                  <span key={stat} className="badge">
                    {formatWeightName(stat)}: {value}
                  </span>
                ))}
              </div>

              <div className="button-row">
                <button className="danger" onClick={() => void deleteLeague(league.id)}>
                  Delete
                </button>
              </div>
            </article>
          ))}
        </div>
      </section>

      {status ? <p className="success">{status}</p> : null}
      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
