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
  const [error, setError] = useState<string | null>(null);

  async function loadLeagues() {
    try {
      const response = await authRequest<League[]>("/leagues", session, onSession);
      setLeagues(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load leagues");
    }
  }

  useEffect(() => {
    void loadLeagues();
  }, []);

  async function createLeague(event: FormEvent) {
    event.preventDefault();
    setError(null);

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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create league");
    }
  }

  async function deleteLeague(leagueId: string) {
    setError(null);
    try {
      await authRequest(`/leagues/${leagueId}`, session, onSession, {
        method: "DELETE",
      });
      await loadLeagues();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete league");
    }
  }

  return (
    <div className="grid cols-2">
      <section className="card">
        <h2>Create League</h2>
        <form onSubmit={createLeague}>
          <label>
            League name
            <input value={name} onChange={(event) => setName(event.target.value)} required />
          </label>

          <label>
            Type
            <select value={leagueType} onChange={(event) => setLeagueType(event.target.value)}>
              <option value="categories">categories</option>
              <option value="points">points</option>
            </select>
          </label>

          <button className="primary" type="submit">
            Save League
          </button>
        </form>
      </section>

      <section className="card">
        <h2>My Leagues</h2>
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Type</th>
              <th>Status</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {leagues.map((league) => (
              <tr key={league.id}>
                <td>{league.name}</td>
                <td>{league.league_type}</td>
                <td>{league.is_active ? "Active" : "Inactive"}</td>
                <td>
                  <button className="danger" onClick={() => void deleteLeague(league.id)}>
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {error ? <p className="error">{error}</p> : null}
    </div>
  );
}
