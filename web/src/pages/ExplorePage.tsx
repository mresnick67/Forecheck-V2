import { FormEvent, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { publicRequest } from "../api";
import type { Player } from "../types";

export default function ExplorePage() {
  const [query, setQuery] = useState("");
  const [players, setPlayers] = useState<Player[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load(search: string) {
    setLoading(true);
    setError(null);
    try {
      const encoded = encodeURIComponent(search.trim());
      const path = search.trim()
        ? `/players?search=${encoded}&limit=50`
        : "/players?limit=50&sort_by=streamer_score";
      const response = await publicRequest<Player[]>(path);
      setPlayers(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load players");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load("");
  }, []);

  function onSearch(event: FormEvent) {
    event.preventDefault();
    void load(query);
  }

  return (
    <section className="card">
      <h2>Explore Players</h2>
      <form onSubmit={onSearch}>
        <label>
          Search by player or team
          <input value={query} onChange={(event) => setQuery(event.target.value)} />
        </label>
        <button className="primary" type="submit" disabled={loading}>
          {loading ? "Searching..." : "Search"}
        </button>
      </form>

      {error ? <p className="error">{error}</p> : null}

      <table>
        <thead>
          <tr>
            <th>Player</th>
            <th>Team</th>
            <th>Pos</th>
            <th>Streamer</th>
            <th>Owned</th>
          </tr>
        </thead>
        <tbody>
          {players.map((player) => (
            <tr key={player.id}>
              <td>
                <Link to={`/players/${player.id}`}>{player.name}</Link>
              </td>
              <td>{player.team}</td>
              <td>{player.position}</td>
              <td>{player.current_streamer_score.toFixed(1)}</td>
              <td>{player.ownership_percentage.toFixed(1)}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
